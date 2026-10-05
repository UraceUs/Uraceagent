"""CHECKLISTS — o que o mecânico e o coach conferem em cada atendimento (#92).

Dono, 05/10: *"tem checklist para cada atendimento… isso o mecânico que completa… checklists
tem que ter a opção de abrir a câmera, tirar fotos ou subir a foto"*. E as decisões:

- os modelos vêm da planilha **Master Checklist** (importada como está, sem redigitar) e o
  **gerente para cima** vê e edita;
- **foto opcional em todo item**; o gerente pode tornar obrigatória num item ou no checklist
  inteiro (aí ele pede pelo menos uma foto);
- **mecânico e coach** preenchem os deles.

Quando cada checklist aparece (`quando`): `treino` = dia com serviço (Academy, Arrive and Drive,
Daily…), `corrida` = corrida do calendário, `trimestral`/`avulso` = começa quando alguém quiser.
`per_kart` = um por kart (por serviço do dia ou por piloto da corrida); senão, um por dia/corrida.

O preenchimento é uma **cópia** do modelo no momento em que começa: editar o modelo depois não
muda o que já foi feito.
"""
import json
import os
import re
import urllib.parse
import urllib.request

from command_center.db import agora, atualizar, inserir, todos, um
from command_center.providers import portal

PLANILHA = os.environ.get("CHECKLIST_PLANILHA", "1OvS_kX1rRztjhnEmEDfAaDk0mCyq9wtTDpCZxh_3MGM")
ABA = "Master Operations"
QUANDO = ("treino", "corrida", "trimestral", "avulso")
CARGOS = ("MECANICO", "COACH", "ADM")
RX_ITEM = re.compile(r"^\s*\d+\s*[.)]\s*(.+)$")

# Onde cada checklist da planilha entra (o gerente muda depois, na tela). Chave: nome em minúsculas
# + seção (o "Coach checklist" de corrida não é o "Coach Checklist" do dia de treino).
PADRAO = {
    "the day before checklist": ("treino", "MECANICO", 0),
    "mechanic checklist": ("treino", "MECANICO", 0),
    "coach checklist|practice": ("treino", "COACH", 0),
    "lounge/vip area checklist": ("treino", "COACH", 0),
    "kart checklist": ("treino,corrida", "MECANICO", 1),
    "checklist ( adm )": ("corrida", "ADM", 0),
    "preparation before travel": ("corrida", "MECANICO", 0),
    "wednesday:": ("corrida", "MECANICO", 0),
    "mechanic checklist (race)": ("corrida", "MECANICO", 0),
    "coach checklist|race": ("corrida", "COACH", 0),
    "quarterly team checklist": ("trimestral", "MECANICO", 0),
}


class ErroChecklist(ValueError):
    """Mensagem para a tela."""


def hoje():
    return portal.hoje().isoformat()


def _padrao(nome, secao):
    n = re.sub(r"\s+", " ", (nome or "").strip().lower())
    s = (secao or "").lower()
    chave = f"{n}|{'race' if 'race' in s else 'practice'}"
    return PADRAO.get(chave) or PADRAO.get(n) or ("avulso", "MECANICO", 0)


# ------------------------------------------------------------------ importar da planilha
def ler_grade(token=None, planilha=PLANILHA, aba=ABA):
    from adminai import google_auth
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{planilha}/values/{urllib.parse.quote(aba + '!A1:Z300')}"
    req = urllib.request.Request(url + "?majorDimension=ROWS&valueRenderOption=FORMATTED_VALUE")
    req.add_header("Authorization", f"Bearer {token or google_auth.access_token()}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read()).get("values", [])


def interpretar(grade):
    """A grade da aba "Master Operations" → [{section, name, itens: [{grupo, text}]}].

    A linha dos NOMES é a que tem "Mechanic Checklist"; a de cima traz as seções (célula
    mesclada vem só na primeira coluna, então a seção vale até a próxima). Abaixo, "1. texto"
    é item; texto sem número é o grupo dos itens seguintes ("Engine:", "At arrival… 7:00")."""
    linhas = [[(c or "").strip() for c in ln] for ln in grade]
    rnome = next((i for i, ln in enumerate(linhas) if any(c.lower() == "mechanic checklist" for c in ln)), None)
    if rnome is None:
        raise ErroChecklist('a planilha não tem a linha dos checklists (esperava "Mechanic Checklist")')
    secoes = linhas[rnome - 1] if rnome else []
    largura = max(len(ln) for ln in linhas)
    saida, secao = [], None
    for col in range(largura):
        s = secoes[col] if col < len(secoes) else ""
        if s:
            secao = s
        nome = linhas[rnome][col] if col < len(linhas[rnome]) else ""
        if not nome:
            continue
        itens, grupo = [], None
        for ln in linhas[rnome + 1:]:
            c = ln[col] if col < len(ln) else ""
            if not c:
                continue
            m = RX_ITEM.match(c)
            if m:
                itens.append({"grupo": grupo, "text": m.group(1).strip()})
            else:
                grupo = c
        if itens:
            saida.append({"section": secao, "name": nome, "itens": itens})
    return saida


def importar(con, grade=None, por=None):
    """Cria os modelos que ainda não existem. Os que existem ficam como o gerente deixou."""
    grade = grade if grade is not None else ler_grade()
    novos, iguais = [], []
    for ordem, ck in enumerate(interpretar(grade)):
        if um(con, "SELECT id FROM checklist_templates WHERE section IS ? AND name=?", (ck["section"], ck["name"])):
            iguais.append(ck["name"])
            continue
        quando, cargo, per_kart = _padrao(ck["name"], ck["section"])
        tid = inserir(con, "checklist_templates", section=ck["section"], name=ck["name"], quando=quando, cargo=cargo,
                      per_kart=per_kart, sort=ordem, source="planilha", updated_by=por)
        for i, it in enumerate(ck["itens"]):
            inserir(con, "checklist_template_items", template_id=tid, sort=i, grupo=it["grupo"], text=it["text"])
        novos.append(ck["name"])
    return {"novos": novos, "ja_existiam": iguais}


# ------------------------------------------------------------------ modelos
def modelos(con, ativos=True):
    ts = todos(con, f"SELECT * FROM checklist_templates {'WHERE active=1' if ativos else ''} ORDER BY sort, id")
    for t in ts:
        t["itens"] = todos(con, f"SELECT * FROM checklist_template_items WHERE template_id=? {'AND active=1' if ativos else ''} ORDER BY sort, id",
                           (t["id"],))
    return ts


def _valida_quando(v):
    partes = [p.strip() for p in (v or "").split(",") if p.strip()]
    if not partes or any(p not in QUANDO for p in partes):
        raise ErroChecklist(f"'quando' tem de ser {', '.join(QUANDO)}")
    return ",".join(partes)


def criar_modelo(con, name, section=None, quando="avulso", cargo="MECANICO", per_kart=0, por=None):
    if not (name or "").strip():
        raise ErroChecklist("o checklist precisa de nome")
    if cargo not in CARGOS:
        raise ErroChecklist("cargo inválido")
    return inserir(con, "checklist_templates", name=name.strip(), section=section, quando=_valida_quando(quando), cargo=cargo,
                   per_kart=1 if per_kart else 0, updated_by=por)


def editar_modelo(con, tid, por=None, **campos):
    if not um(con, "SELECT id FROM checklist_templates WHERE id=?", (tid,)):
        raise LookupError("checklist não existe")
    if "quando" in campos:
        campos["quando"] = _valida_quando(campos["quando"])
    if "cargo" in campos and campos["cargo"] not in CARGOS:
        raise ErroChecklist("cargo inválido")
    for b in ("per_kart", "photo_required", "active"):
        if b in campos:
            campos[b] = 1 if campos[b] else 0
    atualizar(con, "checklist_templates", tid, updated_by=por, updated_at=agora(), **campos)


def adicionar_item(con, tid, text, grupo=None, photo_required=False):
    if not (text or "").strip():
        raise ErroChecklist("o item precisa de texto")
    if not um(con, "SELECT id FROM checklist_templates WHERE id=?", (tid,)):
        raise LookupError("checklist não existe")
    ultimo = um(con, "SELECT COALESCE(MAX(sort), -1) AS s FROM checklist_template_items WHERE template_id=?", (tid,))["s"]
    return inserir(con, "checklist_template_items", template_id=tid, sort=ultimo + 1, grupo=grupo, text=text.strip(),
                   photo_required=1 if photo_required else 0)


def editar_item(con, iid, **campos):
    if not um(con, "SELECT id FROM checklist_template_items WHERE id=?", (iid,)):
        raise LookupError("item não existe")
    for b in ("photo_required", "active"):
        if b in campos:
            campos[b] = 1 if campos[b] else 0
    if "text" in campos and not (campos["text"] or "").strip():
        raise ErroChecklist("o item precisa de texto")
    atualizar(con, "checklist_template_items", iid, **campos)


# ------------------------------------------------------------------ preencher
def _ctx(t, ctx):
    """(chave, data, task_id, race_id, client_id, título) de onde este preenchimento vale."""
    tipo = ctx.get("tipo")
    data = ctx.get("data") or hoje()
    if tipo == "task":
        return f"task:{int(ctx['task_id'])}", data, int(ctx["task_id"]), None, ctx.get("client_id"), ctx.get("titulo")
    if tipo == "race":
        cid = ctx.get("client_id")
        chave = f"race:{int(ctx['race_id'])}" + (f":client:{int(cid)}" if cid else "")
        return chave, data, None, int(ctx["race_id"]), cid, ctx.get("titulo")
    if tipo == "dia":
        return f"dia:{data}", data, None, None, None, ctx.get("titulo")
    if tipo == "avulso":
        return f"avulso:{data}", data, None, None, None, ctx.get("titulo")
    raise ErroChecklist("contexto inválido")


def abrir(con, template_id, ctx, por=None):
    """O preenchimento deste checklist neste contexto: o que já existe, ou começa agora."""
    t = um(con, "SELECT * FROM checklist_templates WHERE id=? AND active=1", (template_id,))
    if not t:
        raise LookupError("checklist não existe")
    chave, data, task_id, race_id, client_id, titulo = _ctx(t, ctx)
    r = um(con, "SELECT * FROM checklist_runs WHERE template_id=? AND ctx=?", (t["id"], chave))
    if r:
        return r["id"]
    if task_id and not client_id:
        tk = um(con, "SELECT client_id, title FROM tasks WHERE id=?", (task_id,))
        if not tk:
            raise LookupError("serviço não existe")
        client_id, titulo = tk["client_id"], titulo or tk["title"]
    rid = inserir(con, "checklist_runs", template_id=t["id"], ctx=chave, run_date=data, task_id=task_id, race_id=race_id,
                  client_id=client_id, title=titulo or t["name"], photo_required=t["photo_required"], started_by=por)
    for it in todos(con, "SELECT * FROM checklist_template_items WHERE template_id=? AND active=1 ORDER BY sort, id", (t["id"],)):
        inserir(con, "checklist_run_items", run_id=rid, item_id=it["id"], sort=it["sort"], grupo=it["grupo"], text=it["text"],
                photo_required=it["photo_required"])
    return rid


def preenchimento(con, rid):
    r = um(con, """SELECT r.*, t.name AS modelo, t.section, t.cargo, COALESCE(c.pilot_name, c.name) AS cliente
                     FROM checklist_runs r JOIN checklist_templates t ON t.id=r.template_id
                     LEFT JOIN clients c ON c.id=r.client_id WHERE r.id=?""", (rid,))
    if not r:
        raise LookupError("checklist não existe")
    itens = todos(con, """SELECT i.*, u.name AS por FROM checklist_run_items i LEFT JOIN users u ON u.id=i.done_by
                            WHERE i.run_id=? ORDER BY i.sort, i.id""", (rid,))
    for i in itens:
        i["fotos"] = [f["id"] for f in todos(con, "SELECT id FROM checklist_photos WHERE run_item_id=? ORDER BY id", (i["id"],))]
    feitos = sum(1 for i in itens if i["done"])
    return {**r, "itens": itens, "feitos": feitos, "total": len(itens), "faltando": faltando(con, rid, itens)}


def faltando(con, rid, itens=None):
    """O que impede concluir: item sem marcar, item com foto obrigatória sem foto, checklist que
    pede foto sem nenhuma."""
    r = um(con, "SELECT photo_required FROM checklist_runs WHERE id=?", (rid,))
    itens = itens if itens is not None else preenchimento(con, rid)["itens"]
    falta = [f"marcar: {i['text']}" for i in itens if not i["done"]]
    falta += [f"foto: {i['text']}" for i in itens if i["photo_required"] and not i["fotos"]]
    if r and r["photo_required"] and not any(i["fotos"] for i in itens):
        falta.append("foto: pelo menos uma neste checklist")
    return falta


def _aberto(con, rid):
    r = um(con, "SELECT status FROM checklist_runs WHERE id=?", (rid,))
    if not r:
        raise LookupError("checklist não existe")
    if r["status"] != "aberto":
        raise ErroChecklist("este checklist já foi concluído")


def marcar(con, rid, item_id, done, note=None, por=None):
    _aberto(con, rid)
    i = um(con, "SELECT id FROM checklist_run_items WHERE id=? AND run_id=?", (item_id, rid))
    if not i:
        raise LookupError("item não existe")
    campos = dict(done=1 if done else 0, done_by=por if done else None, done_at=agora() if done else None)
    if note is not None:
        campos["note"] = (note or "").strip()[:500] or None
    atualizar(con, "checklist_run_items", item_id, **campos)


def pasta_fotos(rid):
    p = os.path.join(os.environ.get("URACE_DIR", os.path.expanduser("~/.urace")), "checklists", str(int(rid)))
    os.makedirs(p, mode=0o700, exist_ok=True)
    return p


def guardar_foto(con, rid, item_id, dados, por=None):
    """Foto do celular → WebP ≤ 1600 px, sem EXIF (sem a posição GPS), em ~/.urace/checklists."""
    from command_center.providers import imagem
    _aberto(con, rid)
    if not um(con, "SELECT id FROM checklist_run_items WHERE id=? AND run_id=?", (item_id, rid)):
        raise LookupError("item não existe")
    try:
        webp, ext = imagem.comprimir(dados)
    except imagem.ImagemInvalida as e:
        raise ErroChecklist(str(e))
    fid = inserir(con, "checklist_photos", run_item_id=item_id, file_path="", by_user_id=por)
    caminho = os.path.join(pasta_fotos(rid), f"{item_id}-{fid}{ext}")
    with open(caminho, "wb") as f:
        f.write(webp)
    os.chmod(caminho, 0o600)
    atualizar(con, "checklist_photos", fid, file_path=caminho)
    return fid


def concluir(con, rid, por=None):
    _aberto(con, rid)
    falta = faltando(con, rid)
    if falta:
        raise ErroChecklist("Falta: " + "; ".join(falta[:6]) + (f" e mais {len(falta) - 6}" if len(falta) > 6 else ""))
    atualizar(con, "checklist_runs", rid, status="completo", completed_by=por, completed_at=agora())


# ------------------------------------------------------------------ meu dia
def _cargo_ve(cargo_usuario, cargo_modelo):
    if not cargo_usuario:                     # gerente, operador sem cargo: vê tudo
        return True
    return cargo_modelo == cargo_usuario


def _estado(con, tid, chave):
    r = um(con, "SELECT id, status FROM checklist_runs WHERE template_id=? AND ctx=?", (tid, chave))
    if not r:
        return {"run_id": None, "status": "nao_iniciado", "feitos": 0, "total": None}
    n = um(con, "SELECT COUNT(*) AS t, SUM(done) AS f FROM checklist_run_items WHERE run_id=?", (r["id"],))
    return {"run_id": r["id"], "status": r["status"], "feitos": n["f"] or 0, "total": n["t"]}


def meu_dia(con, data=None, cargo=None):
    """O dia de quem está no box: serviços, corridas, sessões do site e os checklists de cada um.
    Sem valor, sem contato do cliente — é o calendário do mecânico e do coach."""
    data = data or hoje()
    ts = [t for t in modelos(con) if _cargo_ve(cargo, t["cargo"])]
    servicos = todos(con, """SELECT t.id, t.title, t.status, t.section, t.client_id, COALESCE(c.pilot_name, c.name) AS cliente
                               FROM tasks t LEFT JOIN clients c ON c.id=t.client_id
                              WHERE substr(t.due_on,1,10)=? AND LOWER(COALESCE(t.section,''))!='races'
                              ORDER BY t.title""", (data,))
    corridas = todos(con, """SELECT id, name, series, track, city, date_start, date_end FROM races
                              WHERE active=1 AND date_start<=? AND COALESCE(date_end, date_start)>=? ORDER BY date_start""",
                     (data, data))
    sessoes = todos(con, """SELECT b.id, b.period, b.status, p.name AS piloto, b.service_name AS servico FROM bookings b
                              LEFT JOIN portal_pilots p ON p.id=b.pilot_id
                             WHERE b.date=? AND b.status IN ('confirmada','pendente') ORDER BY b.period, b.id""", (data,))

    def ck(t, ctx, chave):
        return {"template_id": t["id"], "nome": t["name"], "cargo": t["cargo"], "ctx": ctx, **_estado(con, t["id"], chave)}
    do_dia = []
    if servicos:
        do_dia += [ck(t, {"tipo": "dia", "data": data}, f"dia:{data}") for t in ts if "treino" in t["quando"] and not t["per_kart"]]
    for s in servicos:
        s["checklists"] = [ck(t, {"tipo": "task", "task_id": s["id"], "data": data}, f"task:{s['id']}")
                           for t in ts if "treino" in t["quando"] and t["per_kart"]]
    for r in corridas:
        pilotos = todos(con, """SELECT i.client_id, COALESCE(c.pilot_name, c.name) AS piloto FROM race_invites i
                                  JOIN clients c ON c.id=i.client_id WHERE i.race_id=? AND i.status IN ('invited','confirmed')""",
                        (r["id"],))
        r["pilotos"] = pilotos
        r["checklists"] = [ck(t, {"tipo": "race", "race_id": r["id"], "data": data}, f"race:{r['id']}")
                           for t in ts if "corrida" in t["quando"] and not t["per_kart"]]
        for p in pilotos:
            p["checklists"] = [ck(t, {"tipo": "race", "race_id": r["id"], "client_id": p["client_id"], "data": data},
                                  f"race:{r['id']}:client:{p['client_id']}") for t in ts if "corrida" in t["quando"] and t["per_kart"]]
    avulsos = [{"template_id": t["id"], "nome": t["name"], "quando": t["quando"]} for t in ts
               if "trimestral" in t["quando"] or "avulso" in t["quando"]]
    return {"data": data, "servicos": servicos, "corridas": corridas, "sessoes": sessoes, "do_dia": do_dia, "avulsos": avulsos}


def incompletos(con, antes_de=None):
    """Checklists começados e não concluídos de dias que já passaram: vão para Precisa de atenção."""
    return todos(con, """SELECT r.id, r.title, r.run_date, t.name AS modelo, (SELECT COUNT(*) FROM checklist_run_items i
                           WHERE i.run_id=r.id AND i.done=0) AS faltam FROM checklist_runs r
                           JOIN checklist_templates t ON t.id=r.template_id
                          WHERE r.status='aberto' AND r.run_date<? ORDER BY r.run_date, r.id""", (antes_de or hoje(),))
