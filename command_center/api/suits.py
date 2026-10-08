"""Suits (Alpha Line) — as rotas (#153). As regras moram em `providers/suits.py`.

**Quem pode o quê:** ver, registrar, anotar e avançar etapa é OPERATOR (é quem atende o
cliente); importar do Asana, editar o modelo do e-mail e os fornecedores é MANAGER.
Foto de cada nota fica em ~/.urace/suits (WebP, ≤ 1600 px, sem EXIF) e só sai com sessão.
"""
import json
import os
import re
import sqlite3
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel

from command_center.api import auth
from command_center.api.cache_api import paginar
from command_center.db import agora, atualizar, auditar, get_db, inserir, todos, um
from command_center.providers import suits

r = APIRouter(prefix="/ops/api/suits", tags=["suits"])
IMAGEM_MAX = 8 * 1024 * 1024
TIPOS_IMAGEM = {"image/png", "image/jpeg", "image/webp"}


def pasta_imagens():
    caminho = os.path.join(os.environ.get("URACE_DIR", os.path.expanduser("~/.urace")), "suits")
    os.makedirs(caminho, exist_ok=True)
    return caminho


def _aud(con, request, u, evento, eid, detalhe=None, tipo="suit_order"):
    auditar(con, evento, f"user:{u['id']}", user_id=u["id"], entity_type=tipo, entity_id=eid, detail=detalhe,
            ip=auth._ip(request) if request else None)


def _pedido(con, pid):
    p = suits.detalhe(con, pid)
    if not p:
        raise HTTPException(404, "Pedido não encontrado.")
    return p


def _invalido(e):
    return HTTPException(400, str(e))


# ------------------------------------------------------------------ o básico
@r.get("/etapas")
def etapas(u=Depends(auth.exige("OPERATOR"))):
    """O que a tela precisa para montar o formulário: etapas, medidas e campos de design."""
    return {"etapas": [{"codigo": c, "nome": n, "descricao": d} for c, n, d in suits.ETAPAS],
            "medidas": [{"chave": k, "numero": num, "nome": nome, "tipo": t} for k, num, nome, t in suits.MEDIDAS],
            "design": [{"chave": k, "nome": n} for k, n in suits.DESIGN]}


@r.get("/resumo")
def resumo(con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    por = {x["status"]: x["n"] for x in todos(con, "SELECT status, COUNT(*) AS n FROM suit_orders WHERE closed=0 GROUP BY status")}
    return {"por_etapa": por, "abertos": sum(por.values()),
            "fechados": um(con, "SELECT COUNT(*) AS n FROM suit_orders WHERE closed=1")["n"],
            "leads": um(con, "SELECT COUNT(*) AS n FROM suit_leads WHERE status='aberto'")["n"],
            "fornecedores": um(con, "SELECT COUNT(*) AS n FROM suit_suppliers")["n"]}


@r.get("")
def listar(response: Response, estado: str = "abertos", status: str | None = None, q: str | None = None,
           limit: int | None = 50, offset: int = 0, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    where, p = [], []
    if estado in ("abertos", "fechados"):
        where.append("o.closed=?"); p.append(1 if estado == "fechados" else 0)
    if status:
        where.append("o.status=?"); p.append(suits.etapa_valida(status) if status in suits.CODIGOS else "_")
    if q and q.strip():
        t = f"%{q.strip().lower()}%"
        where.append("(lower(o.title) LIKE ? OR lower(coalesce(o.customer_name,'')) LIKE ? OR lower(coalesce(o.driver_name,'')) LIKE ? "
                     "OR lower(coalesce(o.customer_email,'')) LIKE ?)")
        p += [t, t, t, t]
    sql = f"""SELECT o.id, o.title, o.product, o.quantity, o.customer_name, o.driver_name, o.status, o.closed, o.order_date, o.due_on,
                     o.source, o.created_at, o.updated_at, s.name AS fornecedor,
                     (SELECT COUNT(*) FROM suit_notes n WHERE n.order_id=o.id AND n.kind!='etapa') AS notas,
                     (SELECT MAX(created_at) FROM suit_notes n WHERE n.order_id=o.id) AS ultima_nota
              FROM suit_orders o LEFT JOIN suit_suppliers s ON s.id=o.supplier_id
              {'WHERE ' + ' AND '.join(where) if where else ''}
              ORDER BY o.closed, coalesce(o.updated_at, o.created_at) DESC, o.id DESC"""
    return paginar(con, sql, p, response, limit, offset)


class MedidasIn(BaseModel):
    valores: dict[str, str | float | int | None] = {}
    unidade: str = "cm"
    unidade_peso: str = "kg"


class PedidoIn(BaseModel):
    title: str | None = None
    product: str | None = None
    quantity: int | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    ship_address: str | None = None
    driver_name: str | None = None
    language: str | None = None
    client_id: int | None = None
    supplier_id: int | None = None
    order_date: str | None = None
    due_on: str | None = None
    paid_at: str | None = None
    tracking: str | None = None
    site_order: str | None = None
    gmail_thread_cliente: str | None = None
    gmail_thread_designer: str | None = None
    gmail_thread_fornecedor: str | None = None
    design: dict[str, str | None] | None = None
    medidas: MedidasIn | None = None
    status: str | None = None
    nota: str | None = None


CAMPOS = ("title", "product", "quantity", "customer_name", "customer_email", "customer_phone", "ship_address",
          "driver_name", "language", "client_id", "supplier_id", "order_date", "due_on", "paid_at", "tracking",
          "site_order", "gmail_thread_cliente", "gmail_thread_designer", "gmail_thread_fornecedor")


def _limpo(v):
    return v.strip() if isinstance(v, str) else v


def thread_do_link(v):
    """Aceita o id da thread (hex, como a API devolve) ou o link do Gmail colado: o 'thread-f:<número>'
    do link é o mesmo id, em decimal."""
    v = (v or "").strip()
    m = re.search(r"thread-f:(\d+)", v)
    if m:
        return format(int(m.group(1)), "x")
    m = re.search(r"\b([0-9a-f]{16})\b", v)
    return m.group(1) if m else (v or None)


def gravar(con, dados: dict, u_id, pid=None, fonte="manual"):
    """Cria (pid None) ou atualiza um pedido. `dados` no formato de PedidoIn. Devolve o id."""
    campos = {k: _limpo(dados[k]) for k in CAMPOS if k in dados and dados[k] is not None}
    for k in ("gmail_thread_cliente", "gmail_thread_designer", "gmail_thread_fornecedor"):
        if k in campos:
            campos[k] = thread_do_link(campos[k])
    if "quantity" in campos and not (1 <= int(campos["quantity"]) <= 50):
        raise suits.Invalido("quantidade entre 1 e 50")
    if campos.get("supplier_id") and not um(con, "SELECT id FROM suit_suppliers WHERE id=?", (campos["supplier_id"],)):
        raise suits.Invalido("fornecedor não existe")
    if campos.get("client_id") and not um(con, "SELECT id FROM clients WHERE id=?", (campos["client_id"],)):
        raise suits.Invalido("cliente não existe")
    if dados.get("client_id") == 0:          # 0 = desvincular (a tela manda 0 quando tira o cliente)
        campos["client_id"] = None
    atual = um(con, "SELECT * FROM suit_orders WHERE id=?", (pid,)) if pid else None
    if pid and not atual:
        raise LookupError("Pedido não encontrado.")
    if dados.get("design") is not None:
        d = json.loads(atual["design"] or "{}") if atual else {}
        d.update({k: (v or "").strip() for k, v in dados["design"].items() if k in dict(suits.DESIGN)})
        campos["design"] = json.dumps({k: v for k, v in d.items() if v}, ensure_ascii=False)
    if dados.get("medidas"):
        m = dados["medidas"]
        novas = suits.normalizar_medidas(m.get("valores"), m.get("unidade", "cm"), m.get("unidade_peso", "kg"))
        antes = json.loads(atual["measurements"] or "{}") if atual else {}
        apagar = [k for k, v in (m.get("valores") or {}).items() if v is None or str(v).strip() == ""]
        antes.update(novas)
        for k in apagar:
            antes.pop(k, None)
        campos["measurements"] = json.dumps(antes, ensure_ascii=False)
    if not pid:
        titulo = campos.get("title") or campos.get("customer_name") or campos.get("driver_name")
        if not titulo:
            raise suits.Invalido("Diga pelo menos o nome do cliente.")
        campos.setdefault("title", titulo)
        if dados.get("status"):
            campos["status"] = suits.etapa_valida(dados["status"])
            campos["closed"] = 1 if campos["status"] in suits.FECHADAS else 0
        campos.setdefault("order_date", datetime.now(ZoneInfo("America/New_York")).date().isoformat())
        pid = inserir(con, "suit_orders", source=fonte, created_by=u_id, updated_at=agora(), **campos)
        suits.anotar(con, pid, "Pedido registrado" + (" pela IA" if fonte == "ia" else ""), "etapa",
                     campos.get("status", "standby"), user_id=u_id)
    else:
        if campos:
            atualizar(con, "suit_orders", pid, updated_at=agora(), **campos)
        if dados.get("status"):
            suits.mudar_etapa(con, pid, dados["status"], u_id)
    if dados.get("nota"):
        p = um(con, "SELECT status FROM suit_orders WHERE id=?", (pid,))
        suits.anotar(con, pid, dados["nota"], "nota", p["status"], user_id=u_id)
    suits.vincular_por_email(con, pid)
    return pid


@r.post("", status_code=201)
def criar(dados: PedidoIn, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    try:
        pid = gravar(con, dados.model_dump(exclude_unset=True), u["id"])
    except suits.Invalido as e:
        raise _invalido(e)
    _aud(con, request, u, "suit.created", pid, {"title": dados.title or dados.customer_name})
    return _pedido(con, pid)


# --------------------------------------------------------------------- modelo
class ModeloIn(BaseModel):
    subject: str
    body: str


@r.get("/modelo")
def ver_modelo(con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    return dict(suits.modelo(con), campos=list(suits.CAMPOS_MODELO), padrao=suits.MODELO_PADRAO)


@r.put("/modelo")
def salvar_modelo(dados: ModeloIn, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    if not dados.subject.strip() or "{medidas}" not in dados.body:
        raise HTTPException(400, "O modelo precisa de assunto e do campo {medidas}.")
    con.execute("""INSERT INTO suit_templates (key, subject, body, updated_at, updated_by) VALUES ('fornecedor',?,?,?,?)
                   ON CONFLICT(key) DO UPDATE SET subject=excluded.subject, body=excluded.body,
                   updated_at=excluded.updated_at, updated_by=excluded.updated_by""",
                (dados.subject.strip()[:200], dados.body[:8000], agora(), u["id"]))
    _aud(con, request, u, "suit.template", "fornecedor", tipo="suit_template")
    return suits.modelo(con)


# ------------------------------------------------------------------- leads
@r.get("/leads")
def leads(response: Response, estado: str = "aberto", q: str | None = None, limit: int | None = 100, offset: int = 0,
          con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    where, p = [], []
    if estado in ("aberto", "convertido", "perdido"):
        where.append("status=?"); p.append(estado)
    if q and q.strip():
        t = f"%{q.strip().lower()}%"
        where.append("(lower(name) LIKE ? OR lower(coalesce(email,'')) LIKE ? OR lower(coalesce(notes,'')) LIKE ?)"); p += [t, t, t]
    sql = f"SELECT * FROM suit_leads {'WHERE ' + ' AND '.join(where) if where else ''} ORDER BY id DESC"
    return paginar(con, sql, p, response, limit, offset)


class LeadIn(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    notes: str | None = None
    status: str | None = None
    client_id: int | None = None


@r.post("/leads", status_code=201)
def criar_lead(dados: LeadIn, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    if not (dados.name or "").strip():
        raise HTTPException(400, "Diga o nome.")
    if dados.client_id and not um(con, "SELECT id FROM clients WHERE id=?", (dados.client_id,)):
        raise HTTPException(400, "Cliente não existe.")
    lid = inserir(con, "suit_leads", name=dados.name.strip(), email=_limpo(dados.email) or None,
                  phone=_limpo(dados.phone) or None, notes=_limpo(dados.notes) or None, client_id=dados.client_id,
                  updated_at=agora())
    _aud(con, request, u, "suit.lead.created", lid, tipo="suit_lead")
    return um(con, "SELECT * FROM suit_leads WHERE id=?", (lid,))


@r.patch("/leads/{lid}")
def mudar_lead(lid: int, dados: LeadIn, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    if not um(con, "SELECT id FROM suit_leads WHERE id=?", (lid,)):
        raise HTTPException(404, "Lead não encontrado.")
    campos = {k: _limpo(v) for k, v in dados.model_dump(exclude_unset=True).items()}
    if "status" in campos and campos["status"] not in ("aberto", "convertido", "perdido"):
        raise HTTPException(400, "Situação inválida.")
    if campos.get("client_id") and not um(con, "SELECT id FROM clients WHERE id=?", (campos["client_id"],)):
        raise HTTPException(400, "Cliente não existe.")
    if campos:
        atualizar(con, "suit_leads", lid, updated_at=agora(), **campos)
    _aud(con, request, u, "suit.lead.updated", lid, {"campos": list(campos)}, tipo="suit_lead")
    return um(con, "SELECT * FROM suit_leads WHERE id=?", (lid,))


@r.post("/leads/{lid}/pedido", status_code=201)
def lead_vira_pedido(lid: int, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    lead = um(con, "SELECT * FROM suit_leads WHERE id=?", (lid,))
    if not lead:
        raise HTTPException(404, "Lead não encontrado.")
    if lead["order_id"]:
        return _pedido(con, lead["order_id"])
    pid = gravar(con, {"customer_name": lead["name"], "customer_email": lead["email"], "customer_phone": lead["phone"],
                       "client_id": lead["client_id"],
                       "nota": f"Veio do lead: {lead['notes']}" if lead["notes"] else None}, u["id"])
    atualizar(con, "suit_leads", lid, status="convertido", order_id=pid, updated_at=agora())
    _aud(con, request, u, "suit.lead.converted", lid, {"pedido": pid}, tipo="suit_lead")
    return _pedido(con, pid)


# -------------------------------------------------------------- fornecedores
@r.get("/fornecedores")
def fornecedores(con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    return todos(con, """SELECT s.*, (SELECT COUNT(*) FROM suit_orders o WHERE o.supplier_id=s.id) AS pedidos
                         FROM suit_suppliers s ORDER BY s.is_current DESC, pedidos DESC, s.name""")


class FornecedorIn(BaseModel):
    name: str | None = None
    contact: str | None = None
    email: str | None = None
    phone: str | None = None
    has_fia: int | None = None
    status: str | None = None
    price: str | None = None
    shipping: str | None = None
    payment: str | None = None
    lead_time: str | None = None
    comments: str | None = None
    is_current: bool | None = None


def _forn_campos(dados):
    c = {k: _limpo(v) for k, v in dados.model_dump(exclude_unset=True).items()}
    if "is_current" in c:
        c["is_current"] = 1 if c["is_current"] else 0
    return c


@r.post("/fornecedores", status_code=201)
def criar_fornecedor(dados: FornecedorIn, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    c = _forn_campos(dados)
    if not (c.get("name") or "").strip():
        raise HTTPException(400, "Diga o nome do fornecedor.")
    if c.get("is_current"):
        con.execute("UPDATE suit_suppliers SET is_current=0")
    fid = inserir(con, "suit_suppliers", updated_at=agora(), **c)
    _aud(con, request, u, "suit.supplier.created", fid, tipo="suit_supplier")
    return um(con, "SELECT * FROM suit_suppliers WHERE id=?", (fid,))


@r.patch("/fornecedores/{fid}")
def mudar_fornecedor(fid: int, dados: FornecedorIn, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    if not um(con, "SELECT id FROM suit_suppliers WHERE id=?", (fid,)):
        raise HTTPException(404, "Fornecedor não encontrado.")
    c = _forn_campos(dados)
    if c.get("is_current"):
        con.execute("UPDATE suit_suppliers SET is_current=0")       # o atual é um só
    if c:
        atualizar(con, "suit_suppliers", fid, updated_at=agora(), **c)
    _aud(con, request, u, "suit.supplier.updated", fid, {"campos": list(c)}, tipo="suit_supplier")
    return um(con, "SELECT * FROM suit_suppliers WHERE id=?", (fid,))


# ------------------------------------------------------------ importar do Asana
@r.post("/importar")
def importar(request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    """Lê o projeto SUITS do Asana (só leitura) e traz pedidos, leads e fornecedores. Pode repetir."""
    from command_center.providers import NaoConectado, modulo
    try:
        tarefas = modulo("asana").tarefas_do_suits()
    except NaoConectado as e:
        raise HTTPException(503, f"Asana não conectado: {e}")
    except Exception as e:
        raise HTTPException(502, f"Não deu para ler o Asana: {str(e)[:200]}")
    res = suits.importar(con, tarefas)
    _aud(con, request, u, "suit.import.asana", "1205661933760052", res, tipo="asana_project")
    return res


# ------------------------------------------------------------ ponte de e-mail
def _ponte():
    from command_center.providers import suits_ponte
    return suits_ponte


@r.get("/ponte")
def ver_ponte(con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    from command_center.api import ia
    sp = _ponte()
    ult = um(con, "SELECT at, detail FROM audit_logs WHERE event='suit.bridge.round' ORDER BY id DESC LIMIT 1")
    return {"config": sp.config(con), "manual": os.path.isfile(sp.manual_pdf()),
            "motor": ia.motor_da_ia(), "ultima_rodada": dict(ult) if ult else None}


class PonteIn(BaseModel):
    ponte_ligada: bool | None = None
    envio_automatico: bool | None = None
    designer_nome: str | None = None
    designer_email: str | None = None
    assinatura: str | None = None
    boas_vindas: str | None = None
    politica: str | None = None


@r.put("/ponte")
def salvar_ponte(dados: PonteIn, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    sp = _ponte()
    d = dados.model_dump(exclude_unset=True)
    for k in ("ponte_ligada", "envio_automatico"):
        if k in d and d[k] is not None:
            d[k] = "1" if d[k] else "0"
    try:
        cfg = sp.salvar_config(con, d, u["id"])
    except sp.Recusado as e:
        raise HTTPException(400, str(e))
    _aud(con, request, u, "suit.bridge.config", "ponte", {k: (v if k != "boas_vindas" else "…") for k, v in d.items()}, tipo="suit_bridge")
    return {"config": cfg, "manual": os.path.isfile(sp.manual_pdf())}


@r.post("/ponte/manual")
async def subir_manual(request: Request, arquivo: UploadFile = File(...), con: sqlite3.Connection = Depends(get_db),
                       u=Depends(auth.exige("MANAGER"))):
    """O PDF do manual de medidas que vai nas boas-vindas."""
    dados = await arquivo.read(IMAGEM_MAX + 1)
    if not dados.startswith(b"%PDF") or len(dados) > IMAGEM_MAX:
        raise HTTPException(400, "Mande o PDF do manual (até 8 MB).")
    with open(_ponte().manual_pdf(), "wb") as f:
        f.write(dados)
    _aud(con, request, u, "suit.bridge.manual", "ponte", {"bytes": len(dados)}, tipo="suit_bridge")
    return {"ok": True, "bytes": len(dados)}


@r.post("/ponte/manual/gmail")
def manual_do_gmail(request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    """Busca o 'GUIDE TO FILLING IN SIZING - URACE FORM.pdf' no último e-mail enviado com ele."""
    from command_center.providers import NaoConectado, modulo
    sp = _ponte()
    try:
        gm = modulo("gmail")
        r = gm.gmail_buscar(sp.CONTA, 'in:sent filename:"GUIDE TO FILLING IN SIZING"', so_inbox=False, maximo=1)
        for t in r.get("threads") or []:
            for m in reversed(gm.mensagens_da_thread(sp.CONTA, t["thread_id"])["mensagens"]):
                for a in m.get("anexos") or []:
                    if (a.get("nome") or "").lower().endswith(".pdf") and "sizing" in (a.get("nome") or "").lower():
                        dados = gm.anexo_bytes(sp.CONTA, m["message_id"], a["attachment_id"])
                        with open(sp.manual_pdf(), "wb") as f:
                            f.write(dados)
                        _aud(con, request, u, "suit.bridge.manual", "ponte", {"de": "gmail", "bytes": len(dados)}, tipo="suit_bridge")
                        return {"ok": True, "bytes": len(dados), "nome": a["nome"]}
    except NaoConectado as e:
        raise HTTPException(503, f"Gmail não conectado: {e}")
    raise HTTPException(404, "Não achei o PDF do manual nos e-mails enviados. Suba o arquivo à mão.")


@r.get("/ponte/manual")
def baixar_manual(u=Depends(auth.exige("OPERATOR"))):
    caminho = _ponte().manual_pdf()
    if not os.path.isfile(caminho):
        raise HTTPException(404)
    from fastapi.responses import FileResponse
    return FileResponse(caminho, media_type="application/pdf", filename="GUIDE TO FILLING IN SIZING - URACE FORM.pdf",
                        headers={"Cache-Control": "private, max-age=60"})


@r.post("/ponte/rodar")
def rodar_ponte(request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    """Roda um ciclo agora (em segundo plano), em vez de esperar os 15 minutos."""
    ok = _ponte().rodar_em_segundo_plano()
    _aud(con, request, u, "suit.bridge.run", "ponte", {"iniciada": ok}, tipo="suit_bridge")
    return {"iniciada": ok, "nota": None if ok else "Já tem um ciclo rodando."}


# ------------------------------------------------------------ vincular ao cliente
@r.get("/cliente/{cid}")
def dados_do_cliente(cid: int, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    """O que o cadastro já sabe do cliente, para o formulário puxar (#158)."""
    d = suits.dados_do_cliente(con, cid)
    if not d:
        raise HTTPException(404, "Cliente não encontrado.")
    return d


# ------------------------------------------------------------------- pedido
@r.get("/notas/{nid}/imagem")
def imagem_da_nota(nid: int, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    """A foto sai pelo servidor, com sessão — nunca por link público adivinhável."""
    n = um(con, "SELECT image_path FROM suit_notes WHERE id=?", (nid,))
    if not n or not n["image_path"]:
        raise HTTPException(404)
    caminho = os.path.join(pasta_imagens(), os.path.basename(n["image_path"]))
    if not os.path.isfile(caminho):
        raise HTTPException(404)
    from fastapi.responses import FileResponse
    return FileResponse(caminho, media_type="image/webp", headers={"Cache-Control": "private, max-age=300"})


@r.get("/{pid}")
def ver(pid: int, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    p = _pedido(con, pid)
    for n in p["notas"]:                          # o que a IA respondeu a cada nota
        if n.get("command_id"):
            c = um(con, "SELECT status, output, error FROM ai_commands WHERE id=?", (n["command_id"],))
            n["ia"] = dict(c) if c else None
    return p


@r.patch("/{pid}")
def mudar(pid: int, dados: PedidoIn, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    d = dados.model_dump(exclude_unset=True)
    try:
        gravar(con, d, u["id"], pid)
    except LookupError:
        raise HTTPException(404, "Pedido não encontrado.")
    except suits.Invalido as e:
        raise _invalido(e)
    _aud(con, request, u, "suit.updated", pid, {"campos": [k for k in d if k != "medidas"] + (["medidas"] if "medidas" in d else [])})
    return ver(pid, con, u)


def pedir_a_ia(con, pid, u, nota_id, texto, imagem):
    """Leva a nota (e a imagem) ao AI Command, na conversa de quem escreveu: a IA lê o pedido,
    entende e avança. A resposta aparece aqui na nota e no AI Command."""
    from command_center.api import acoes, ia, motor
    p = suits.detalhe(con, pid)
    etapa = dict((c, n) for c, n, _ in suits.ETAPAS)[p["status"]]
    pedido = (f"SUITS — pedido de macacão #{pid} ({p['title']}), etapa atual: {etapa}.\n"
              f"Nota de {u.get('name') or 'alguém da equipe'}: {texto or '(sem texto)'}\n"
              + (f"Screenshot anexado à nota: {os.path.join(pasta_imagens(), imagem)} (leia a imagem).\n" if imagem else "")
              + "Leia o pedido inteiro (suits_pedido), entenda a nota e avance o pedido: atualize os dados, as medidas e a "
                "etapa (suits_atualizar_pedido) e registre o que fez (suits_anotar). Mensagem ao cliente ou ao designer: no "
                "idioma do cliente, educada e comercial (ainda é venda), respeitando o que ele pediu.")
    prompt = pedido + motor.aprendizados(con) + acoes.estado_do_dia(con, u["id"])
    sk = f"agent:{ia.AGENTE}:web-{u['id']}-{datetime.now(ZoneInfo('America/New_York')).date().isoformat()}"
    cid = inserir(con, "ai_commands", user_id=u["id"], text=f"Suits #{pid}: {texto or 'imagem'}"[:4000], prompt=prompt, session_key=sk)
    con.execute("UPDATE suit_notes SET command_id=? WHERE id=?", (cid, nota_id))
    auditar(con, "ai.command", f"user:{u['id']}", user_id=u["id"], entity_type="ai_command", entity_id=cid,
            detail={"suit": pid, "nota": nota_id})
    threading.Thread(target=ia._executa, args=(cid, texto or "", sk, u["id"], prompt), daemon=True).start()
    return cid


@r.post("/{pid}/notas", status_code=201)
async def nova_nota(pid: int, request: Request, texto: str = Form(""), status: str = Form(""), pedir_ia: bool = Form(False),
                    imagem: UploadFile | None = File(None), con: sqlite3.Connection = Depends(get_db),
                    u=Depends(auth.exige("OPERATOR"))):
    """Nota em qualquer etapa, com screenshot opcional; pode mudar a etapa e pedir à IA para seguir."""
    p = um(con, "SELECT id, status FROM suit_orders WHERE id=?", (pid,))
    if not p:
        raise HTTPException(404, "Pedido não encontrado.")
    texto = (texto or "").strip()
    nome_img = None
    if imagem is not None and (imagem.filename or imagem.size):
        if (imagem.content_type or "").lower() not in TIPOS_IMAGEM:
            raise HTTPException(400, "Use PNG, JPG ou WEBP.")
        dados = await imagem.read(IMAGEM_MAX + 1)
        if len(dados) > IMAGEM_MAX:
            raise HTTPException(400, "Imagem grande demais (máximo 8 MB).")
        from command_center.providers import imagem as img
        try:
            dados, ext = img.comprimir(dados)
        except img.ImagemInvalida:
            raise HTTPException(400, "Essa imagem não abriu. Tente outra.")
        nome_img = f"pedido-{pid}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}{ext}"
        with open(os.path.join(pasta_imagens(), nome_img), "wb") as f:
            f.write(dados)
    if not texto and not nome_img and not status:
        raise HTTPException(400, "Escreva a nota, anexe uma imagem ou mude a etapa.")
    try:
        if status and status != p["status"]:
            suits.mudar_etapa(con, pid, status, u["id"])
    except suits.Invalido as e:
        raise _invalido(e)
    nid = None
    if texto or nome_img:
        nid = suits.anotar(con, pid, texto, "nota", status or p["status"], nome_img, u["id"])
        atualizar(con, "suit_orders", pid, updated_at=agora())
    cid = pedir_a_ia(con, pid, u, nid, texto, nome_img) if pedir_ia and nid else None
    _aud(con, request, u, "suit.note", pid, {"nota": nid, "imagem": bool(nome_img), "etapa": status or None, "ia": cid})
    return {"id": nid, "command_id": cid}


@r.get("/{pid}/anexos")
def anexos(pid: int, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    if not um(con, "SELECT id FROM suit_orders WHERE id=?", (pid,)):
        raise HTTPException(404, "Pedido não encontrado.")
    sp = _ponte()
    return [{"nome": n, "bytes": os.path.getsize(os.path.join(sp.pasta(pid), n))} for n in sp.anexos_do_pedido(pid)]


@r.get("/{pid}/anexos/{nome}")
def anexo(pid: int, nome: str, u=Depends(auth.exige("OPERATOR"))):
    sp = _ponte()
    caminho = os.path.join(sp.pasta(pid), os.path.basename(nome))
    if not os.path.isfile(caminho):
        raise HTTPException(404)
    from fastapi.responses import FileResponse
    return FileResponse(caminho, filename=os.path.basename(nome), headers={"Cache-Control": "private, max-age=300"})


@r.post("/{pid}/ponte/simular", status_code=202)
def simular(pid: int, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    """A IA faz o próximo passo da ponte neste pedido, sem mandar nada: os e-mails viram nota."""
    if not um(con, "SELECT id FROM suit_orders WHERE id=?", (pid,)):
        raise HTTPException(404, "Pedido não encontrado.")
    sp = _ponte()

    def _vai():
        from command_center.db import conectar
        c = conectar()
        try:
            sp.simular_pedido(c, pid)
        except Exception as e:
            suits.anotar(c, pid, f"A simulação não rodou: {type(e).__name__}: {str(e)[:200]}", "ia")
        finally:
            c.close()
    threading.Thread(target=_vai, daemon=True, name=f"cc-suits-sim-{pid}").start()
    _aud(con, request, u, "suit.bridge.simulate", pid)
    return {"iniciada": True}


@r.get("/{pid}/email-fornecedor")
def email_fornecedor(pid: int, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    p = um(con, "SELECT * FROM suit_orders WHERE id=?", (pid,))
    if not p:
        raise HTTPException(404, "Pedido não encontrado.")
    f = um(con, "SELECT * FROM suit_suppliers WHERE id=?", (p["supplier_id"],)) if p["supplier_id"] else \
        um(con, "SELECT * FROM suit_suppliers WHERE is_current=1")
    return dict(suits.email_fornecedor(con, dict(p), dict(f) if f else None, u), fornecedor=dict(f) if f else None)


@r.post("/{pid}/email-fornecedor/rascunho")
def rascunho_fornecedor(pid: int, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    """O pedido de produção vira um RASCUNHO no Gmail do urace@: anexar o mockup final e enviar é humano."""
    e = email_fornecedor(pid, con, u)
    if e["faltam"]:
        raise HTTPException(400, "Falta " + " e ".join(e["faltam"]) + " para montar o pedido ao fornecedor.")
    from command_center.providers import NaoConectado, chamar
    anterior = os.environ.get("APLICAR")
    os.environ["APLICAR"] = "1"                   # o clique da pessoa é a autorização, só nesta chamada
    try:
        res = chamar("gmail", "gmail_rascunho", conta="urace", para=e["para"], assunto=e["assunto"], corpo=e["corpo"])
    except NaoConectado as ex:
        raise HTTPException(503, f"Gmail não conectado: {ex}")
    finally:
        if anterior is None:
            os.environ.pop("APLICAR", None)
        else:
            os.environ["APLICAR"] = anterior
    st = um(con, "SELECT status FROM suit_orders WHERE id=?", (pid,))["status"]
    suits.anotar(con, pid, f"Rascunho do pedido ao fornecedor criado no Gmail (para {e['para']}): anexe o mockup final e envie.",
                 "email", st, user_id=u["id"])
    _aud(con, request, u, "suit.supplier.draft", pid, {"para": e["para"], "draft": res.get("draft_id")})
    return {"ok": True, "draft_id": res.get("draft_id"), "para": e["para"]}


# ------------------------------------------------------------- para a IA (#152)
def ferramentas_ia():
    """As ferramentas da aba Suits para o agente do AI Command: (nome, descrição, propriedades,
    obrigatórios, função(con, user_id, **args)). Ler e trabalho interno — nada sai da empresa."""
    def pedidos(con, uid, busca=None, estado="abertos", **_):
        where, p = ["1=1"], []
        if estado in ("abertos", "fechados"):
            where.append("closed=?"); p.append(1 if estado == "fechados" else 0)
        if busca:
            t = f"%{str(busca).lower()}%"
            where.append("(lower(title) LIKE ? OR lower(coalesce(customer_name,'')) LIKE ? OR lower(coalesce(customer_email,'')) LIKE ?)")
            p += [t, t, t]
        return todos(con, f"""SELECT id, title, product, customer_name, customer_email, driver_name, status, order_date, due_on
                               FROM suit_orders WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT 100""", p)

    def pedido(con, uid, id, **_):
        p = suits.detalhe(con, int(id))
        if not p:
            return {"erro": "pedido não encontrado"}
        f = um(con, "SELECT * FROM suit_suppliers WHERE id=?", (p["supplier_id"],)) if p.get("supplier_id") else \
            um(con, "SELECT * FROM suit_suppliers WHERE is_current=1")
        crua = um(con, "SELECT * FROM suit_orders WHERE id=?", (int(id),))
        p["email_fornecedor"] = suits.email_fornecedor(con, dict(crua), dict(f) if f else None, {"name": ""})
        return p

    def criar(con, uid, **args):
        return {"id": gravar(con, args, uid, fonte="ia")}

    def atualizar_pedido(con, uid, id, **args):
        gravar(con, args, uid, int(id))
        return {"ok": True, "id": int(id)}

    def anotar_(con, uid, id, texto, **_):
        st = um(con, "SELECT status FROM suit_orders WHERE id=?", (int(id),))
        if not st:
            return {"erro": "pedido não encontrado"}
        return {"id": suits.anotar(con, int(id), texto, "ia", st["status"], user_id=uid)}

    def email_(con, uid, id, para, assunto, corpo, anexos=None, responder=True, **_):
        from command_center.providers import suits_ponte
        try:
            return suits_ponte.enviar(con, int(id), para, assunto, corpo, anexos or [], bool(responder), uid)
        except suits_ponte.Recusado as e:
            return {"recusado": str(e)}

    def anexos_(con, uid, id, **_):
        from command_center.providers import suits_ponte
        return {"pasta": suits_ponte.pasta(int(id)), "arquivos": suits_ponte.anexos_do_pedido(int(id)),
                "manual_medidas": os.path.isfile(suits_ponte.manual_pdf())}

    def humano_(con, uid, id, motivo, **_):
        from command_center.providers import suits_ponte
        return suits_ponte.precisa_humano(con, int(id), motivo, uid)

    def leads_(con, uid, busca=None, **_):
        t = f"%{str(busca or '').lower()}%"
        return todos(con, "SELECT * FROM suit_leads WHERE lower(name) LIKE ? OR lower(coalesce(notes,'')) LIKE ? ORDER BY id DESC LIMIT 100", (t, t))

    def fornecedores_(con, uid, **_):
        return todos(con, "SELECT * FROM suit_suppliers ORDER BY is_current DESC, name")

    s, n, o = {"type": "string"}, {"type": "integer"}, {"type": "object"}
    campos_pedido = {"title": s, "product": s, "quantity": n, "customer_name": s, "customer_email": s, "customer_phone": s,
                     "ship_address": s, "driver_name": s, "language": dict(s, description="idioma do cliente: en, pt, es…"),
                     "supplier_id": n, "order_date": s, "due_on": s, "paid_at": s, "tracking": s,
                     "design": dict(o, description="ideia, cores, logos, posicao_logos, nome, bandeira, observacoes"),
                     "medidas": dict(o, description='{"valores": {"head": 59, "foot": "42 EUR"}, "unidade": "cm|in", "unidade_peso": "kg|lb"}'),
                     "client_id": dict(n, description="o card do cliente no painel (urace_clientes), quando já existe"),
                     "status": dict(s, enum=suits.CODIGOS), "nota": s, "site_order": s,
                     "gmail_thread_cliente": s, "gmail_thread_designer": s, "gmail_thread_fornecedor": s}
    return [
        ("suits_pedidos", "Pedidos de macacão (aba Suits), mais recentes primeiro. Filtra por nome ou e-mail.",
         {"busca": s, "estado": dict(s, enum=["abertos", "fechados", "todos"])}, [], pedidos),
        ("suits_pedido", "Um pedido de macacão inteiro: cliente, etapa, as 29 medidas, design, notas e o e-mail ao "
         "fornecedor já montado pelo modelo.", {"id": n}, ["id"], pedido),
        ("suits_criar_pedido", "Registra um pedido de macacão novo na aba Suits (etapa standby se não disser outra). "
         "Nunca invente medida ou dado do cliente.", campos_pedido, [], criar),
        ("suits_atualizar_pedido", "Atualiza um pedido de macacão: dados, design, medidas (só as que vierem) e etapa.",
         dict(campos_pedido, id=n), ["id"], atualizar_pedido),
        ("suits_anotar", "Escreve na linha do tempo do pedido o que a IA fez ou descobriu.", {"id": n, "texto": s},
         ["id", "texto"], anotar_),
        ("suits_email", "Manda e-mail sobre o pedido para o CLIENTE, o DESIGNER ou o FORNECEDOR daquele pedido (o endereço "
         "vem do pedido, não de você), respondendo na conversa que já existe. Anexos: nomes de suits_anexos, ou "
         "\"manual_medidas\" (o PDF do manual de medidas). Para o designer, só o design e \"Suits #id\": nunca nome "
         "completo, e-mail, telefone, endereço ou pagamento do cliente. Para o cliente, nunca o nome ou o contato do "
         "designer. Se a ponte estiver em simulação, o e-mail vira nota no pedido e não sai.",
         {"id": n, "para": dict(s, enum=["cliente", "designer", "fornecedor"]), "assunto": s, "corpo": s,
          "anexos": {"type": "array", "items": s}, "responder": {"type": "boolean"}},
         ["id", "para", "assunto", "corpo"], email_),
        ("suits_anexos", "Os arquivos do pedido (o que chegou por e-mail: medidas, inspiração, logos, arte) e onde lê-los.",
         {"id": n}, ["id"], anexos_),
        ("suits_precisa_humano", "Para e chama a equipe: aparece em Precisa de atenção e na linha do tempo do pedido.",
         {"id": n, "motivo": s}, ["id", "motivo"], humano_),
        ("suits_leads", "Leads de macacão (oportunidades guardadas para vender de novo).", {"busca": s}, [], leads_),
        ("suits_fornecedores", "Fornecedores de macacão com contato, FIA, preço e qual é o atual.", {}, [], fornecedores_),
    ]
