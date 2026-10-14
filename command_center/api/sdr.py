"""Robô SDR: o interruptor do Chase e, desde 12/10, a página onde o comercial gere o robô.

Dono, 06/10: "deixe um switch no command center onde dê para ligar e desligar o chase".
Dono, 12/10: "uma sessão robô SDR onde ele consiga ligar e desligar, passar o que precisa ser
feito pelo robô, reportar alguma coisa, gerir o robô".

O Chase é a ponte de vendas (salesagent/bridge, serviço `sales-bridge`). O nível dela vem de
`SDR_MODO` em ~/.urace/bridge.env e só vale depois que a ponte reinicia:
  - "observar"  decide e registra, não escreve no Kommo e não responde;
  - "organizar" etiqueta, nota, tarefa e etapa no Kommo; não responde ao lead;
  - "atender"   organiza E responde (o Chase ligado).

O painel grava o nível no bridge.env e deixa ~/.urace/sdr.request; no servidor, o path unit
`urace-sdr.path` vê o pedido e `urace-sdr.service` reinicia a ponte (mesmo desenho do botão
"Atualizar sistema"). Só ADMIN. Nada que o usuário manda vai para o shell: o nível é validado
contra a lista fixa e o comando da unit é fixo.

A página (/sdr):
- **Instruções** (MANAGER+ escreve, todos leem): o que o comercial quer do robô. Valem acima da
  persona, com duas exceções fixas: o preço vem da tabela (ratecard) e as travas de segurança.
  Cada escrita regrava ~/.urace/sdr_instrucoes.md (atômico), que a ponte lê a cada turno. Uma
  instrução "aplicada" é a que alguém já colou na tela do agente do Kommo: continua valendo
  para a ponte; só "arquivada" sai do arquivo.
- **Relatos** (qualquer pessoa logada): o robô errou; MANAGER+ resolve. Aberto acende o menu.
- **Auditoria**: as decisões do SDR (kind='sdr') lidas de ~/.urace/salesbridge.db só em leitura.
"""
import fcntl
import json
import os
import re
import sqlite3
import subprocess
import textwrap
import time
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from command_center.api import auth
from command_center.db import agora, atualizar, auditar, get_db, inserir, todos, um

r = APIRouter(prefix="/ops/api/sdr", tags=["sdr"])
NIVEIS = ("observar", "organizar", "atender")
PEDIDO = "sdr.request"
UNIT = "urace-sdr"
PONTE = os.environ.get("CC_PONTE_URL", "http://127.0.0.1:8800")
FUSO = ZoneInfo("America/New_York")

ARQUIVO_INSTRUCOES = "sdr_instrucoes.md"
ARQUIVO_PAUSAS = "sdr_pausas.json"    # conversas com a IA pausada (13/10); a ponte lê a cada mensagem
CATEGORIAS = {"tom": "tom", "idioma": "idioma", "preco": "preço e condições", "horario": "horário",
              "pessoa": "passar para pessoa", "followup": "follow-up", "canal": "canal",
              "nunca": "nunca dizer", "outro": "outro"}
TIPOS_RELATO = {"respondeu_errado": "o robô respondeu errado", "preco_errado": "preço errado",
                "ignorou_lead": "ignorou o lead", "outro": "outro"}
STATUS_INSTRUCAO = ("ativa", "aplicada", "arquivada")
EM_VIGOR = ("ativa", "aplicada")
MAX_TEXTO = 1000
LINHA_KOMMO = 300                   # cada diretriz na tela do agente do Kommo cabe em 300 caracteres
AVISO_PRECO = "Preço vem da tabela do sistema (ratecard). Uma instrução não muda preço; se o preço mudou, avise o dono."
RX_PRECO = re.compile(r"\$|pre[çc]o|price", re.I)
# Decisão de 06/10 (D-2026-10-06): atendimento humano segunda a sexta, 8h às 18h (Orlando).
HORARIO_HUMANO = {"dias": "seg–sex", "de": "08:00", "ate": "18:00", "fuso": "America/New_York",
                  "texto": "seg–sex 8h–18h (Orlando)"}


def _dir():
    return Path(os.environ.get("URACE_DIR") or (Path.home() / ".urace"))


# ------------------------------------------------------------------ o nível (interruptor)
def nivel_gravado():
    """O SDR_MODO do bridge.env (o que vale depois do próximo restart da ponte)."""
    f = _dir() / "bridge.env"
    if f.exists():
        for linha in f.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*SDR_MODO\s*=\s*['\"]?([a-z]+)", linha)
            if m:
                return m.group(1) if m.group(1) in NIVEIS else "observar"
    return "observar"


def gravar_nivel(nivel):
    """Troca só a linha SDR_MODO do bridge.env; o resto (tokens, números) fica como está."""
    f = _dir() / "bridge.env"
    linhas = f.read_text(encoding="utf-8").splitlines() if f.exists() else []
    novas, achou = [], False
    for linha in linhas:
        if re.match(r"\s*SDR_MODO\s*=", linha):
            if not achou:
                novas.append(f"SDR_MODO={nivel}")
            achou = True
        else:
            novas.append(linha)
    if not achou:
        novas.append(f"SDR_MODO={nivel}")
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".env.tmp")
    tmp.write_text("\n".join(novas) + "\n", encoding="utf-8")
    if f.exists():
        os.chmod(tmp, f.stat().st_mode & 0o777)
    else:
        os.chmod(tmp, 0o600)
    os.replace(tmp, f)


def ponte_no_ar():
    try:
        with urllib.request.urlopen(PONTE + "/health", timeout=2) as resp:
            return bool(json.loads(resp.read() or b"{}").get("ok"))
    except Exception:                                        # noqa: BLE001 — fora do ar é resposta
        return False


def instalado():
    try:
        p = subprocess.run(["systemctl", "is-enabled", f"{UNIT}.path"], capture_output=True, text=True, timeout=10)
        return (p.stdout or "").strip() in ("enabled", "static", "linked")
    except (OSError, subprocess.SubprocessError):
        return False


def estado():
    nivel = nivel_gravado()
    return {"nivel": nivel, "chase_ligado": nivel == "atender", "ponte_no_ar": ponte_no_ar(),
            "reiniciando": (_dir() / PEDIDO).exists(), "instalado": instalado()}


class NivelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nivel: str


@r.get("")
def ver(u=Depends(auth.exige("ADMIN"))):
    return estado()


@r.put("")
def trocar(dados: NivelIn, request: Request, u=Depends(auth.exige("ADMIN")), con: sqlite3.Connection = Depends(get_db)):
    nivel = (dados.nivel or "").strip().lower()
    if nivel not in NIVEIS:
        raise HTTPException(400, "Nível inválido: use observar, organizar ou atender.")
    antes = nivel_gravado()
    gravar_nivel(nivel)
    (_dir() / PEDIDO).write_text(f"{nivel} {u['email']}\n", encoding="utf-8")
    auditar(con, "sdr.nivel", f"user:{u['id']}", user_id=u["id"], entity_type="sdr", entity_id="sales-bridge",
            detail={"antes": antes, "depois": nivel}, ip=auth._ip(request))
    con.commit()
    return estado()


# ------------------------------------------------------------------ a auditoria da ponte (só leitura)
def _abrir_ponte():
    """O salesbridge.db da ponte, só em leitura (mode=ro). None se o arquivo não existe ou não abre."""
    f = _dir() / "salesbridge.db"
    if not f.exists():
        return None
    con = sqlite3.connect(f"file:{f}?mode=ro", uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    return con


def _ler_auditoria(limite=50, lead=None, desde=None):
    """As decisões do SDR em ~/.urace/salesbridge.db, mais novas primeiro, filtradas no SQL
    (lead e corte de tempo): o filtro nunca fica preso às N linhas mais recentes. Sem o arquivo: None."""
    con = _abrir_ponte()
    if con is None:
        return None
    where, par = ["kind='sdr'"], []
    if lead not in (None, ""):
        where.append("lead_id=?")
        par.append(str(lead).strip())
    if desde is not None:
        where.append("ts>=?")
        par.append(int(desde))
    try:
        rows = con.execute(f"SELECT id, ts, lead_id, kind, detail FROM audit WHERE {' AND '.join(where)} "
                           "ORDER BY ts DESC, id DESC LIMIT ?", (*par, limite)).fetchall()
    except sqlite3.Error:
        return None
    finally:
        con.close()
    return [_decisao(x) for x in rows]


def _contar_auditoria(desde):
    """Quantas decisões do SDR desde `desde` (epoch), contadas no SQL. None sem a ponte."""
    con = _abrir_ponte()
    if con is None:
        return None
    try:
        return con.execute("SELECT COUNT(*) FROM audit WHERE kind='sdr' AND ts>=?", (int(desde),)).fetchone()[0]
    except sqlite3.Error:
        return None
    finally:
        con.close()


def _decisao(x):
    try:
        d = json.loads(x["detail"] or "")
        if not isinstance(d, dict):
            d = {"texto": str(d)}
    except ValueError:
        d = {"texto": x["detail"] or ""}
    fez = []
    if d.get("moveu"):
        fez.append(f"etapa → {d['moveu']}")
    if d.get("tags"):
        fez.append("tags: " + ", ".join(str(t) for t in d["tags"]))
    if d.get("nota"):
        fez.append("nota")
    if d.get("tarefa"):
        fez.append("tarefa")
    if d.get("segurado"):
        fez.append("segurou a resposta")
    if d.get("sem_regra_2"):
        fez.append("sem regra 2")
    if d.get("nao_marcou"):
        fez.append("não marcou")
    if d.get("ignorado"):
        fez.append(f"ignorado: {d['ignorado']}")
    if d.get("texto"):
        fez.append(str(d["texto"])[:200])
    ts = int(x["ts"] or 0)
    return {"id": x["id"], "ts": ts, "quando": datetime.fromtimestamp(ts, timezone.utc).astimezone(FUSO).isoformat(timespec="seconds"),
            "lead_id": x["lead_id"] if x["lead_id"] is not None else d.get("lead_id"),
            "acao": d.get("acao") or ("ignorado" if d.get("ignorado") else None), "motivo": d.get("motivo"),
            "nivel": d.get("modo"), "fez": " · ".join(fez), "moveu": d.get("moveu"), "tags": d.get("tags") or []}


def auditoria_ponte(lead=None, acao=None, n=50):
    # a ação só existe dentro do JSON: filtra em Python, mas sobre um lote maior quando há filtro
    itens = _ler_auditoria(limite=n if not acao else 2000, lead=lead)
    if itens is None:
        return {"itens": [], "motivo": "ponte sem auditoria"}
    acoes = sorted({i["acao"] for i in (_ler_auditoria(limite=500) or []) if i["acao"]})
    if acao:
        itens = [i for i in itens if (i["acao"] or "") == acao]
    return {"itens": itens[:n], "acoes": acoes}


# ------------------------------------------------------------------ as instruções
def _rotulo(categoria):
    return CATEGORIAS.get(categoria, categoria)


def instrucoes_em_vigor(con):
    return todos(con, f"""SELECT i.*, u.name AS quem FROM sdr_instrucoes i LEFT JOIN users u ON u.id=i.created_by
                          WHERE i.status IN ({','.join('?' * len(EM_VIGOR))}) ORDER BY i.id DESC""", EM_VIGOR)


def escrever_arquivo(con):
    """~/.urace/sdr_instrucoes.md: uma instrução em vigor por linha, "- [categoria] texto". É por este
    arquivo que a ponte lê o que o comercial quer (nunca pelo bridge.env). Escrita atômica."""
    f = _dir() / ARQUIVO_INSTRUCOES
    linhas = [f"- [{_rotulo(i['categoria'])}] {' '.join(i['texto'].split())}" for i in instrucoes_em_vigor(con)]
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".md.tmp")
    tmp.write_text(("\n".join(linhas) + "\n") if linhas else "", encoding="utf-8")
    os.chmod(tmp, 0o644)
    os.replace(tmp, f)
    return len(linhas)


def texto_kommo(con):
    """O bloco pronto para colar na tela do agente de IA do Kommo: uma diretriz por linha, cada
    uma com até 300 caracteres (o limite de lá)."""
    linhas = []
    for i in instrucoes_em_vigor(con):
        texto = f"[{_rotulo(i['categoria'])}] " + " ".join(i["texto"].split())
        linhas += textwrap.wrap(texto, LINHA_KOMMO, break_long_words=True, break_on_hyphens=False) or [texto]
    return "\n".join(linhas)


def _instrucao(con, iid):
    i = um(con, "SELECT i.*, u.name AS quem, a.name AS aplicada_por FROM sdr_instrucoes i LEFT JOIN users u ON u.id=i.created_by "
                "LEFT JOIN users a ON a.id=i.applied_by WHERE i.id=?", (iid,))
    if not i:
        raise HTTPException(404, "Instrução não encontrada.")
    return {**i, "aviso_preco": bool(RX_PRECO.search(i["texto"]))}


class InstrucaoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    categoria: str
    texto: str


class StatusInstrucaoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str


@r.get("/instrucoes/texto-kommo")
def instrucoes_texto_kommo(u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    t = texto_kommo(con)
    return {"texto": t, "linhas": len(t.splitlines()) if t else 0, "limite_por_linha": LINHA_KOMMO}


@r.get("/instrucoes")
def instrucoes_lista(status: str | None = None, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """Por padrão as em vigor (ativa e aplicada); `status=arquivada` mostra o histórico."""
    if status and status not in STATUS_INSTRUCAO:
        raise HTTPException(400, "status: ativa, aplicada ou arquivada")
    where, par = (("i.status=?", (status,)) if status else (f"i.status IN ({','.join('?' * len(EM_VIGOR))})", EM_VIGOR))
    itens = [{**i, "aviso_preco": bool(RX_PRECO.search(i["texto"]))} for i in todos(con, f"""
        SELECT i.*, u.name AS quem, a.name AS aplicada_por FROM sdr_instrucoes i
          LEFT JOIN users u ON u.id=i.created_by LEFT JOIN users a ON a.id=i.applied_by
         WHERE {where} ORDER BY i.id DESC LIMIT 200""", par)]
    return {"itens": itens, "categorias": CATEGORIAS, "aviso_preco": AVISO_PRECO, "limite": MAX_TEXTO}


@r.post("/instrucoes", status_code=201)
def instrucoes_criar(dados: InstrucaoIn, request: Request, u=Depends(auth.exige("MANAGER")),
                     con: sqlite3.Connection = Depends(get_db)):
    cat = (dados.categoria or "").strip().lower()
    texto = (dados.texto or "").strip()
    if cat not in CATEGORIAS:
        raise HTTPException(400, "Categoria inválida.")
    if not texto or len(texto) > MAX_TEXTO:
        raise HTTPException(400, f"A instrução precisa de texto, até {MAX_TEXTO} caracteres.")
    iid = inserir(con, "sdr_instrucoes", categoria=cat, texto=texto, created_by=u["id"])
    auditar(con, "sdr.instrucao", f"user:{u['id']}", user_id=u["id"], entity_type="sdr_instrucao", entity_id=iid,
            detail={"acao": "criada", "categoria": cat, "texto": texto[:200]}, ip=auth._ip(request))
    n = escrever_arquivo(con)
    con.commit()
    return {**_instrucao(con, iid), "em_vigor": n}


@r.patch("/instrucoes/{iid}")
def instrucoes_status(iid: int, dados: StatusInstrucaoIn, request: Request, u=Depends(auth.exige("MANAGER")),
                      con: sqlite3.Connection = Depends(get_db)):
    novo = (dados.status or "").strip().lower()
    if novo not in STATUS_INSTRUCAO:
        raise HTTPException(400, "status: ativa, aplicada ou arquivada")
    i = _instrucao(con, iid)
    campos = {"status": novo}
    if novo == "aplicada":
        campos.update(applied_at=agora(), applied_by=u["id"])
    elif novo == "arquivada":
        campos.update(archived_at=agora(), archived_by=u["id"])
    else:
        campos.update(archived_at=None, archived_by=None)
    atualizar(con, "sdr_instrucoes", iid, **campos)
    auditar(con, "sdr.instrucao", f"user:{u['id']}", user_id=u["id"], entity_type="sdr_instrucao", entity_id=iid,
            detail={"acao": novo, "antes": i["status"], "categoria": i["categoria"]}, ip=auth._ip(request))
    n = escrever_arquivo(con)
    con.commit()
    return {**_instrucao(con, iid), "em_vigor": n}


# ------------------------------------------------------------------ os relatos
class RelatoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tipo: str
    texto: str
    lead_ref: str | None = None


class StatusRelatoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str


def _relato(con, rid):
    x = um(con, "SELECT r.*, u.name AS quem, v.name AS resolvido_por FROM sdr_relatos r LEFT JOIN users u ON u.id=r.created_by "
                "LEFT JOIN users v ON v.id=r.resolved_by WHERE r.id=?", (rid,))
    if not x:
        raise HTTPException(404, "Relato não encontrado.")
    return x


@r.get("/relatos")
def relatos_lista(status: str | None = None, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    if status and status not in ("aberto", "resolvido"):
        raise HTTPException(400, "status: aberto ou resolvido")
    where, par = ("r.status=?", (status,)) if status else ("1=1", ())
    itens = todos(con, f"""SELECT r.*, u.name AS quem, v.name AS resolvido_por FROM sdr_relatos r
                            LEFT JOIN users u ON u.id=r.created_by LEFT JOIN users v ON v.id=r.resolved_by
                           WHERE {where} ORDER BY (r.status='aberto') DESC, r.id DESC LIMIT 200""", par)
    return {"itens": itens, "tipos": TIPOS_RELATO,
            "abertos": (um(con, "SELECT COUNT(*) AS n FROM sdr_relatos WHERE status='aberto'") or {}).get("n", 0)}


@r.post("/relatos", status_code=201)
def relatos_criar(dados: RelatoIn, request: Request, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    tipo = (dados.tipo or "").strip().lower()
    texto = (dados.texto or "").strip()
    if tipo not in TIPOS_RELATO:
        raise HTTPException(400, "Tipo de relato inválido.")
    if not texto or len(texto) > MAX_TEXTO:
        raise HTTPException(400, f"O relato precisa de texto, até {MAX_TEXTO} caracteres.")
    ref = " ".join((dados.lead_ref or "").split())[:120] or None
    rid = inserir(con, "sdr_relatos", tipo=tipo, texto=texto, lead_ref=ref, created_by=u["id"])
    auditar(con, "sdr.relato", f"user:{u['id']}", user_id=u["id"], entity_type="sdr_relato", entity_id=rid,
            detail={"acao": "criado", "tipo": tipo, "lead": ref, "texto": texto[:200]}, ip=auth._ip(request))
    con.commit()
    return _relato(con, rid)


@r.patch("/relatos/{rid}")
def relatos_status(rid: int, dados: StatusRelatoIn, request: Request, u=Depends(auth.exige("MANAGER")),
                   con: sqlite3.Connection = Depends(get_db)):
    novo = (dados.status or "").strip().lower()
    if novo not in ("aberto", "resolvido"):
        raise HTTPException(400, "status: aberto ou resolvido")
    _relato(con, rid)
    if novo == "resolvido":
        atualizar(con, "sdr_relatos", rid, status=novo, resolved_at=agora(), resolved_by=u["id"])
    else:
        atualizar(con, "sdr_relatos", rid, status=novo, resolved_at=None, resolved_by=None)
    auditar(con, "sdr.relato", f"user:{u['id']}", user_id=u["id"], entity_type="sdr_relato", entity_id=rid,
            detail={"acao": novo}, ip=auth._ip(request))
    con.commit()
    return _relato(con, rid)


# ------------------------------------------------------------------ IA pausada por conversa
# Dono, 13/10: "ter a possibilidade de desativar pelo command center ... respostas da ia em uma
# conversa específica". Quem pausa é quem atende (OPERATOR+): a pessoa assume a conversa e o robô
# para de responder ali, inclusive follow-up e resgate. O card continua sendo organizado.
# O arquivo ~/.urace/sdr_pausas.json é a fonte da verdade para a ponte; o histórico fica no audit.
def ler_pausas():
    f = _dir() / ARQUIVO_PAUSAS
    try:
        d = json.loads(f.read_text(encoding="utf-8") or "{}")
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def gravar_pausas(d):
    f = _dir() / ARQUIVO_PAUSAS
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    os.chmod(tmp, 0o644)
    os.replace(tmp, f)


@contextmanager
def _trava_pausas():
    """14/10: o arquivo passou a ter dois escritores (a pausa manual e o atendimento humano).
    Ler, mudar e gravar sem trava deixava um apagar a mudança do outro. `flock` num arquivo
    ao lado vale entre threads e entre processos (mais de um worker do uvicorn)."""
    f = _dir() / (ARQUIVO_PAUSAS + ".lock")
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "a+") as trava:
        fcntl.flock(trava, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(trava, fcntl.LOCK_UN)


def alterar_pausas(fn):
    """Lê, aplica `fn(dict)` e grava, tudo sob a trava. Devolve o que `fn` devolver."""
    with _trava_pausas():
        d = ler_pausas()
        resultado = fn(d)
        gravar_pausas(d)
        return resultado


class PausaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pausada: bool
    motivo: str | None = None


@r.get("/pausas")
def pausas_lista(u=Depends(auth.usuario_atual)):
    itens = [{"lead_id": int(k), **(v if isinstance(v, dict) else {})} for k, v in ler_pausas().items() if str(k).isdigit()]
    itens.sort(key=lambda i: str(i.get("em") or ""), reverse=True)
    return {"itens": itens}


@r.put("/pausas/{lead_id}")
def pausa_trocar(lead_id: int, dados: PausaIn, request: Request, u=Depends(auth.exige("OPERATOR")),
                 con: sqlite3.Connection = Depends(get_db)):
    """lead_id é o id do lead no Kommo (o mesmo da URL /leads/detail/<id>)."""
    if lead_id <= 0:
        raise HTTPException(400, "Informe o id do lead no Kommo.")
    chave = str(lead_id)
    motivo = " ".join((dados.motivo or "").split())[:200] or None

    def _mudar(d):
        atual = d.get(chave) if isinstance(d.get(chave), dict) else None
        if dados.pausada:
            d[chave] = {**(atual or {}), "por": u.get("name") or u.get("email") or f"user:{u['id']}",
                        "por_id": u["id"], "em": datetime.now(FUSO).isoformat(timespec="seconds"),
                        "motivo": motivo, "manual": True}
            return None
        if atual and atual.get("handoff"):
            # 14/10: atendimento humano aberto. Tirar a pausa aqui deixaria a IA responder no meio
            # do atendimento; quem devolve a conversa à IA é o botão do caso, que avisa a ponte.
            return atual["handoff"]
        d.pop(chave, None)
        return None

    caso = alterar_pausas(_mudar)
    if caso:
        raise HTTPException(409, f"Esta conversa está com um atendimento humano aberto (caso #{caso}). "
                                 "Para a IA voltar, use 'Devolver à IA' no Atendimento.")
    d = ler_pausas()
    auditar(con, "sdr.pausa", f"user:{u['id']}", user_id=u["id"], entity_type="kommo_lead", entity_id=lead_id,
            detail={"pausada": dados.pausada, "motivo": motivo}, ip=auth._ip(request))
    con.commit()
    return {"lead_id": lead_id, "pausada": dados.pausada, "total": len(d)}


# ------------------------------------------------------------------ o painel
@r.get("/painel")
def painel(u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """O estado do robô para todo papel (mudar o nível continua só ADMIN, em PUT /sdr)."""
    e = estado()
    ultima = _ler_auditoria(limite=1)
    return {**e, "pode_trocar": auth.pode(u["role"], "ADMIN"), "pode_instruir": auth.pode(u["role"], "MANAGER"),
            "decisoes_24h": _contar_auditoria(int(time.time()) - 86400),
            "ultima_decisao": ultima[0]["quando"] if ultima else None,
            "ponte_sem_auditoria": ultima is None,
            "conversas_pausadas": len(ler_pausas()),
            "instrucoes_em_vigor": (um(con, f"SELECT COUNT(*) AS n FROM sdr_instrucoes WHERE status IN ({','.join('?' * len(EM_VIGOR))})", EM_VIGOR) or {}).get("n", 0),
            "relatos_abertos": (um(con, "SELECT COUNT(*) AS n FROM sdr_relatos WHERE status='aberto'") or {}).get("n", 0),
            "horario_humano": HORARIO_HUMANO, "niveis": NIVEIS}


@r.get("/auditoria")
def auditoria(lead: str | None = None, acao: str | None = None, n: int = 50, u=Depends(auth.usuario_atual)):
    return auditoria_ponte(lead, acao, max(1, min(n, 200)))
