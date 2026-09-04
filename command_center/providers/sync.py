"""Sincroniza os espelhos do banco a partir das fontes reais.

Fontes de cliente, nesta ordem de confiança:
  1. tarefas do U-RACE no Asana — a descrição segue o modelo do cérebro
     (Driver's name / Date of Birth / Responsible Name / Email / Phone)
  2. notas de brain/20_ENTIDADES/clientes/*.md (responsável = título,
     `piloto:` e `vip:` no frontmatter)
  3. DocuSign — signatários de waiver, ligados por e-mail ao cliente

Identidade é chave externa (entity_links). O e-mail só serve para JUNTAR
o mesmo cliente vindo de duas fontes; nunca é a identidade.
"""
import glob
import json
import os
import re
from datetime import date, datetime

from command_center.db import agora, atualizar, inserir, todos, um
from command_center.providers import NaoConectado, REPO, chamar

# fonte: skills/urace-asana/SKILL.md — colunas do U-RACE
PROJETO_URACE = "1205450093098920"
SECOES_DIAS = {
    "1209248561126025": "TUESDAY", "1205141832260875": "WEDNESDAY",
    "1205141832260876": "THURSDAY", "1205141832260877": "FRIDAY",
    "1205141832260878": "SATURDAY", "1205141832260879": "SUNDAY",
}
SECAO_FINISHED = "1208640396741022"
ASANA_LINK = "https://app.asana.com/0/{proj}/{gid}/f"
DOCUSIGN_LINK = "https://apps.docusign.com/send/documents/details/{env}"


# ------------------------------------------------ parsing da descrição
def _campo(txt, rotulo):
    """Aceita 'Rótulo: valor' e a linha 'a / b / c' abaixo dos rótulos."""
    m = re.search(rf"^{re.escape(rotulo)}\s*:\s*(.+)$", txt, re.M | re.I)
    return m.group(1).strip() if m else None


def parse_descricao(notes):
    """Lê o bloco padrão do modelo de serviço. Tolera as duas formas que
    aparecem na prática: uma linha por campo, ou os valores separados por
    ' / ' na linha seguinte aos rótulos."""
    n = notes or ""
    d = {
        "piloto": _campo(n, "Driver's name") or _campo(n, "Driver"),
        "nascimento": _campo(n, "Date of Birth"),
        "idade": _campo(n, "Age"),
        "responsavel": _campo(n, "Responsible Name") or _campo(n, "Responsible"),
        "email": _campo(n, "Email"),
        "telefone": _campo(n, "Phone"),
        "datas": _campo(n, "Service Dates for this Month"),
    }
    # forma "Driver's name / Date of Birth / Age / ...\n<v1> / <v2> / <v3>"
    if not d["piloto"]:
        m = re.search(r"Driver's name\s*/\s*Date of Birth.*?\n([^\n]+)", n, re.I)
        if m and " / " in m.group(1):
            partes = [p.strip() for p in re.split(r"\s/\s", m.group(1))]
            d["piloto"], d["nascimento"], d["idade"] = (partes + [None] * 3)[:3]
    if not d["responsavel"]:
        m = re.search(r"Responsible Name\s*/\s*Email\s*/\s*Phone.*?\n([^\n]+)", n, re.I)
        if m and " / " in m.group(1):
            partes = [p.strip() for p in re.split(r"\s/\s", m.group(1))]
            d["responsavel"], d["email"], d["telefone"] = (partes + [None] * 3)[:3]
    if d["email"] and "@" not in d["email"]:
        d["email"] = None
    if d["email"]:
        d["email"] = d["email"].lower()
    if d["nascimento"]:
        d["nascimento"] = _data_iso(d["nascimento"])
    return d


def _data_iso(s):
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def nome_da_tarefa(nome):
    """'Renato Frota Pionti_Professional Coaching_2T [1/1]' → partes."""
    nome = (nome or "").strip()
    m = re.match(r"^(.+?)_(.+?)_(.+?)\s*\[(\d+)/(\d+)\]\s*$", nome)
    if m:
        return dict(piloto=m.group(1).strip(), servico=m.group(2).strip(),
                    categoria=m.group(3).strip(), n=int(m.group(4)), total=int(m.group(5)))
    m = re.match(r"^(.+?)\s*\[(.+?)\]\s*$", nome)         # 'Enzo Kurian [4 strokes 09/05/26]'
    if m:
        return dict(piloto=m.group(1).strip(), servico=m.group(2).strip(), categoria=None, n=None, total=None)
    return dict(piloto=nome, servico=None, categoria=None, n=None, total=None)


# ------------------------------------------------------ clientes
def _acha_cliente(con, email=None, nome=None, piloto=None):
    if email:
        c = um(con, "SELECT * FROM clients WHERE email = ?", (email,))
        if c:
            return c
    if nome and piloto:
        return um(con, "SELECT * FROM clients WHERE name = ? AND pilot_name = ?", (nome, piloto))
    if piloto:
        return um(con, "SELECT * FROM clients WHERE pilot_name = ?", (piloto,))
    return None


def _upsert_cliente(con, nome, email=None, telefone=None, piloto=None, nascimento=None,
                    vip=None, source="asana"):
    c = _acha_cliente(con, email, nome, piloto)
    campos = dict(name=nome, updated_at=agora())
    if email: campos["email"] = email
    if telefone: campos["phone"] = telefone
    if piloto: campos["pilot_name"] = piloto
    if nascimento: campos["pilot_dob"] = nascimento
    if vip is not None: campos["vip"] = 1 if vip else 0
    if c:
        atualizar(con, "clients", c["id"], **campos)
        return c["id"], False
    campos.setdefault("email", None)
    cid = inserir(con, "clients", source=source, status="ACTIVE", **campos)
    return cid, True


def _liga(con, tipo, id_, sistema, ext, link=None):
    con.execute("""INSERT OR IGNORE INTO entity_links (entity_type, entity_id, system, external_id, deep_link)
                   VALUES (?,?,?,?,?)""", (tipo, id_, sistema, ext, link))


# ------------------------------------------------------ Asana
SECAO_SEM_ESPELHO = "matt tasks"     # dado sensível, fora de qualquer automação (dono, 28/08)


def _grava_tarefa(con, gid, campos):
    tid = um(con, "SELECT entity_id FROM entity_links WHERE system='asana' AND external_id=? AND entity_type='task'", (gid,))
    if tid:
        atualizar(con, "tasks", tid["entity_id"], **campos)
    else:
        nid = inserir(con, "tasks", **campos)
        _liga(con, "task", nid, "asana", gid, ASANA_LINK.format(proj=PROJETO_URACE, gid=gid))


def sync_asana(con):
    """Espelha o quadro U-RACE inteiro (menos "Matt tasks").

    Colunas dos dias: leitura completa de cada tarefa (notas → cliente,
    subtarefas). Demais colunas (RACES, Finished Services…): só o resumo da
    lista, sem cliente — servem para a visão de calendário/quadro.
    """
    inicio = agora()
    novos = tarefas = 0
    try:
        secoes = chamar("asana", "asana_secoes", projeto_gid=PROJETO_URACE)
        for sec in secoes:
            sec_gid, sec_nome = sec["gid"], sec["nome"]
            if (sec_nome or "").strip().lower() == SECAO_SEM_ESPELHO:
                continue
            eh_dia = sec_gid in SECOES_DIAS
            eh_finished = sec_gid == SECAO_FINISHED
            # colunas de cliente: dias (agenda) e Finished Services (histórico desde a criação do projeto)
            eh_cliente = eh_dia or eh_finished
            for t in chamar("asana", "asana_tarefas_da_secao", secao_gid=sec_gid, incluir_concluidas=eh_finished):
                comum = dict(project="U-RACE", section=sec_nome, section_gid=sec_gid,
                             status="completed" if t.get("concluida") else "open",
                             due_on=t.get("vence_em"), assignee=t.get("responsavel"),
                             fields=json.dumps(t.get("campos"), ensure_ascii=False) if t.get("campos") else None,
                             synced_at=agora())
                ja = um(con, """SELECT t.id, t.client_id, t.status FROM entity_links l JOIN tasks t ON t.id=l.entity_id
                                WHERE l.system='asana' AND l.external_id=? AND l.entity_type='task'""", (t["gid"],))
                # histórico já lido e concluído não muda: só o resumo (evita reler centenas de tarefas)
                rapido = (not eh_cliente) or (eh_finished and ja and ja["client_id"] and ja["status"] == "completed" and t.get("concluida"))
                if rapido:
                    campos = dict(title=t.get("nome"), subtasks_total=t.get("subtarefas"), **comum)
                    if ja and ja["client_id"]:
                        campos.pop("subtasks_total")          # o resumo não sabe quantas estão feitas; mantém o lido
                    _grava_tarefa(con, t["gid"], campos)
                    tarefas += 1
                    continue
                full = chamar("asana", "asana_tarefa", gid=t["gid"])
                d = parse_descricao(full.get("notas"))
                partes = nome_da_tarefa(full.get("nome"))
                resp = d["responsavel"] or partes["piloto"]
                cid, novo = _upsert_cliente(con, resp, d["email"], d["telefone"],
                                            d["piloto"] or partes["piloto"], d["nascimento"])
                novos += novo
                _liga(con, "client", cid, "asana", t["gid"], ASANA_LINK.format(proj=PROJETO_URACE, gid=t["gid"]))
                subs = full.get("subtarefas_lista") or []
                _grava_tarefa(con, t["gid"], dict(client_id=cid, title=full.get("nome"),
                                                 subtasks_total=len(subs),
                                                 subtasks_done=sum(1 for s in subs if s.get("concluida")), **comum))
                tarefas += 1
        _marca(con, "asana", True, tarefas, f"{tarefas} tarefas em {len(secoes)} colunas, {novos} clientes novos", inicio)
        return {"ok": True, "tarefas": tarefas, "clientes_novos": novos, "colunas": len(secoes)}
    except NaoConectado as e:
        _marca(con, "asana", False, 0, f"não conectado: {e}", inicio, desconectado=True)
        return {"ok": False, "motivo": "not connected"}
    except Exception as e:
        _marca(con, "asana", False, 0, f"{type(e).__name__}: {str(e)[:300]}", inicio)
        return {"ok": False, "motivo": str(e)[:300]}


# ------------------------------------------------------ cérebro
def sync_cerebro(con):
    """Notas de cliente do segundo cérebro: enriquecem (VIP, piloto), não criam identidade externa."""
    n = 0
    for arq in glob.glob(os.path.join(REPO, "brain", "20_ENTIDADES", "clientes", "*.md")):
        txt = open(arq, encoding="utf-8", errors="replace").read()
        fm = re.match(r"^---\n(.*?)\n---", txt, re.S)
        if not fm:
            continue
        meta = dict(re.findall(r"^([a-z_]+):\s*(.+)$", fm.group(1), re.M))
        nome = os.path.basename(arq)[:-3]
        piloto = meta.get("piloto", "").strip() or None
        vip = meta.get("vip", "").strip().lower() == "true"
        email = (meta.get("email") or "").strip().strip('"') or None
        cid, _ = _upsert_cliente(con, nome, email, None, piloto, None, vip if vip else None, source="brain")
        _liga(con, "client", cid, "brain", os.path.basename(arq))
        n += 1
    return {"ok": True, "notas": n}


# ------------------------------------------------------ DocuSign
def sync_docusign(con, desde_dias=180):
    inicio = agora()
    try:
        r = chamar("docusign", "docusign_envelopes", status="sent,delivered,completed,declined,voided", desde_dias=desde_dias)
        n = 0
        for e in r.get("envelopes", []):
            assunto = (e.get("assunto") or "").lower()
            template = "parental" if "parental" in assunto else "adult" if "adult" in assunto or "waiver" in assunto else "other"
            for s in e.get("signatarios") or []:
                email = (s.get("email") or "").lower() or None
                cli = _acha_cliente(con, email=email) if email else None
                wid = um(con, "SELECT entity_id FROM entity_links WHERE system='docusign' AND external_id=? AND entity_type='waiver'", (e["envelopeId"],))
                campos = dict(client_id=cli["id"] if cli else None, signer_name=s.get("nome"), signer_email=email,
                              template=template, status=s.get("status") if s.get("status") == "autoresponded" else e.get("status"),
                              sent_at=e.get("enviado_em"), completed_at=e.get("concluido_em"),
                              expires_at=e.get("expira_em"), synced_at=agora())
                if wid:
                    atualizar(con, "waivers", wid["entity_id"], **campos)
                else:
                    nid = inserir(con, "waivers", **campos)
                    _liga(con, "waiver", nid, "docusign", e["envelopeId"], DOCUSIGN_LINK.format(env=e["envelopeId"]))
                n += 1
        _marca(con, "docusign", True, n, f"{n} envelopes · {r.get('ambiente')}", inicio,
               detalhe={"ambiente": r.get("ambiente")})
        return {"ok": True, "envelopes": n, "ambiente": r.get("ambiente")}
    except NaoConectado as e:
        _marca(con, "docusign", False, 0, f"não conectado: {e}", inicio, desconectado=True)
        return {"ok": False, "motivo": "not connected"}
    except Exception as e:
        _marca(con, "docusign", False, 0, f"{type(e).__name__}: {str(e)[:300]}", inicio)
        return {"ok": False, "motivo": str(e)[:300]}


# ------------------------------------------------------ Gmail
def sync_gmail(con, dias=3):
    inicio = agora()
    try:
        n = 0
        for conta in ("urace", "support"):
            try:
                r = chamar("gmail", "gmail_buscar", conta=conta, consulta=f"newer_than:{dias}d", so_inbox=True, maximo=50)
            except Exception as e:
                if type(e).__name__ == "ErroFerramenta" and "não configurada" in str(e):
                    continue
                raise
            for t in r.get("threads", []):
                eid = um(con, "SELECT entity_id FROM entity_links WHERE system='gmail' AND external_id=? AND entity_type='email'", (t["thread_id"],))
                remetente = (t.get("de") or "")
                m = re.search(r"<([^>]+)>", remetente)
                email = (m.group(1) if m else remetente).strip().lower()
                cli = _acha_cliente(con, email=email) if "@" in email else None
                campos = dict(client_id=cli["id"] if cli else None, mailbox=conta, subject=t.get("assunto"),
                              sender=remetente[:200], last_at=t.get("data"),
                              labels=json.dumps(t.get("marcadores") or [], ensure_ascii=False), synced_at=agora())
                if eid:
                    atualizar(con, "emails", eid["entity_id"], **campos)
                else:
                    nid = inserir(con, "emails", **campos)
                    _liga(con, "email", nid, "gmail", t["thread_id"],
                          f"https://mail.google.com/mail/u/{0 if conta == 'urace' else 1}/#inbox/{t['thread_id']}")
                n += 1
        _marca(con, "gmail", True, n, f"{n} threads em {dias} dias", inicio)
        return {"ok": True, "threads": n}
    except NaoConectado as e:
        _marca(con, "gmail", False, 0, f"não conectado: {e}", inicio, desconectado=True)
        return {"ok": False, "motivo": "not connected"}
    except Exception as e:
        _marca(con, "gmail", False, 0, f"{type(e).__name__}: {str(e)[:300]}", inicio)
        return {"ok": False, "motivo": str(e)[:300]}


# ------------------------------------------------------ registro
def _marca(con, sistema, ok, itens, msg, inicio, desconectado=False, detalhe=None):
    inserir(con, "sync_logs", system=sistema, started_at=inicio, finished_at=agora(),
            ok=1 if ok else 0, items=itens, message=msg)
    if ok:
        con.execute("""UPDATE integrations SET status='CONNECTED', last_success_at=?, last_attempt_at=?,
                       error_count=0, last_error=NULL, detail=? WHERE system=?""",
                    (agora(), agora(), json.dumps(detalhe or {}, ensure_ascii=False), sistema))
    else:
        con.execute("""UPDATE integrations SET status=?, last_attempt_at=?, error_count=error_count+1,
                       last_error=? WHERE system=?""",
                    ("DISCONNECTED" if desconectado else "ERROR", agora(), msg[:500], sistema))


def sync_tudo(con):
    return {"cerebro": sync_cerebro(con), "asana": sync_asana(con),
            "docusign": sync_docusign(con), "gmail": sync_gmail(con)}
