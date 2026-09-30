"""Ponte do chat da equipe com o WhatsApp (dono, 30/09).

Cada pessoa da equipe no WhatsApp (mecânico, coach, administrativo) é um **contato** com
uma conversa no chat da equipe. O que alguém escreve ali sai no WhatsApp dela, assinado com
o primeiro nome de quem escreveu ("*Italo:* …") — é assim que a mensagem chega "como se
fosse uma pessoa", mesmo saindo de um número só. O que ela responde volta para a mesma
conversa, e quem participa recebe o aviso no celular.

**Sem aprovação** para a equipe interna (dono, 30/09), e só para quem está cadastrado aqui:
número desconhecido que escreve não vira conversa — fica registrado na auditoria.

A janela de 24 h manda: dentro dela, texto livre; fora, o template aprovado
(`WA_TEMPLATE`) — ou a mensagem fica marcada "fora da janela" e ninguém é enganado
achando que ela chegou.
"""
import json
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from command_center.api import auth
from command_center.db import agora, auditar, get_db, inserir, todos, um
from command_center.providers import whatsapp as wa

r = APIRouter(prefix="/ops/api/whatsapp", tags=["whatsapp"])


def _dentro_da_janela(ultima):
    if not ultima:
        return False
    try:
        t = datetime.fromisoformat(ultima.replace("Z", "+00:00"))
    except ValueError:
        return False
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - t < timedelta(hours=wa.JANELA_H)


def _contato_publico(c):
    d = dict(c)
    d["janela_aberta"] = _dentro_da_janela(c["last_inbound_at"])
    return d


# --------------------------------------------------------------------- saída
def encaminhar(message_id):
    """Leva uma mensagem do painel para o WhatsApp. Roda em segundo plano, com conexão
    própria; o resultado fica na mensagem (`wa_status`), e a tela mostra."""
    from command_center.db import conectar
    con = conectar()
    try:
        m = um(con, """SELECT m.*, c.bridge, c.bridge_id FROM team_messages m JOIN team_channels c ON c.id=m.channel_id
                       WHERE m.id=?""", (message_id,))
        if not m or m["bridge"] != "whatsapp" or m["origem"] != "painel":
            return
        ct = um(con, "SELECT * FROM team_contacts WHERE phone=? AND active=1", (m["bridge_id"],))
        if not ct:
            con.execute("UPDATE team_messages SET wa_status='falhou', wa_error=? WHERE id=?",
                        ("contato inativo ou removido", message_id))
            return
        autor = (m["author"] or "URACE").split(" ")[0]
        if not wa.aplicar():
            # sem número liberado nada sai — nem se discute janela
            con.execute("UPDATE team_messages SET wa_status='simulado', wa_error=? WHERE id=?",
                        ("WhatsApp em simulação: nada saiu (falta configurar o número ou WA_APLICAR=1)", message_id))
            return
        try:
            if _dentro_da_janela(ct["last_inbound_at"]):
                res = wa.enviar_texto(ct["phone"], f"*{autor}:* {m['text']}")
            elif wa.cfg("WA_TEMPLATE"):
                res = wa.enviar_template(ct["phone"], wa.cfg("WA_TEMPLATE"), wa.cfg("WA_TEMPLATE_IDIOMA", "pt_BR"),
                                         [autor, m["text"][:900]])
            else:
                con.execute("UPDATE team_messages SET wa_status='fora_da_janela', wa_error=? WHERE id=?",
                            (f"{ct['name']} não escreve há mais de 24 h e não há template aprovado (WA_TEMPLATE): "
                             "a Meta não deixa mandar texto livre. Peça para a pessoa mandar um 'oi', ou configure o template.",
                             message_id))
                return
        except (wa.ErroWhatsApp, ValueError) as e:
            con.execute("UPDATE team_messages SET wa_status='falhou', wa_error=? WHERE id=?", (str(e)[:300], message_id))
            return
        if res.get("simulado"):
            con.execute("UPDATE team_messages SET wa_status='simulado', wa_error=? WHERE id=?",
                        ("WhatsApp em simulação: nada saiu (falta configurar o número ou WA_APLICAR=1)", message_id))
        else:
            con.execute("UPDATE team_messages SET wa_status='enviado', wa_error=NULL, external_id=? WHERE id=?",
                        (res["id"], message_id))
    finally:
        con.commit()
        con.close()


# --------------------------------------------------------------------- webhook
@r.get("/webhook")
def verificar(request: Request):
    """A Meta confirma o endereço com hub.challenge, uma vez, quando você salva o webhook."""
    q = request.query_params
    esperado = wa.cfg("WA_VERIFY_TOKEN")
    if q.get("hub.mode") == "subscribe" and esperado and q.get("hub.verify_token") == esperado:
        return Response(q.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(403, "Forbidden.")


def _texto_de(msg):
    tipo = msg.get("type")
    if tipo == "text":
        return (msg.get("text") or {}).get("body")
    if tipo == "button":
        return (msg.get("button") or {}).get("text")
    if tipo == "interactive":
        i = msg.get("interactive") or {}
        return ((i.get("button_reply") or i.get("list_reply") or {}).get("title"))
    rotulo = {"image": "uma imagem", "audio": "um áudio", "video": "um vídeo", "document": "um documento",
              "sticker": "uma figurinha", "location": "uma localização", "contacts": "um contato"}.get(tipo, tipo)
    legenda = ((msg.get(tipo) or {}) if isinstance(msg.get(tipo), dict) else {}).get("caption")
    return f"[mandou {rotulo} pelo WhatsApp{': ' + legenda if legenda else ''} — veja no aparelho do número]"


def _avisar(con, cid, autor, canal_nome):
    """Quem participa da conversa recebe o aviso; se ninguém abriu ainda, os gerentes."""
    from command_center.api import push
    alvos = [x["user_id"] for x in todos(con, "SELECT user_id FROM team_members WHERE channel_id=? AND muted=0", (cid,))]
    if not alvos:
        alvos = [x["id"] for x in todos(con, "SELECT id FROM users WHERE active=1 AND role IN ('ADMIN','MANAGER')")]
    try:
        push.avisar(con, alvos, f"{autor.split(' ')[0]} no WhatsApp", "Nova mensagem no chat da equipe.",
                    f"/ops/equipe?c={cid}")
    except Exception:                                  # noqa: BLE001
        pass


@r.post("/webhook")
async def receber(request: Request, con: sqlite3.Connection = Depends(get_db)):
    """Mensagem e status que a Meta manda. Assinatura conferida antes de ler qualquer coisa."""
    bruto = await request.body()
    if not wa.assinatura_ok(bruto, request.headers.get("x-hub-signature-256")):
        raise HTTPException(403, "Forbidden.")
    try:
        dados = json.loads(bruto.decode() or "{}")
    except ValueError:
        raise HTTPException(400, "JSON inválido.")
    novas = estados = 0
    for entrada in dados.get("entry", []):
        for mud in entrada.get("changes", []):
            v = mud.get("value") or {}
            for msg in v.get("messages", []):
                try:
                    fone = wa.normaliza_fone(msg.get("from"))
                except ValueError:
                    continue
                ct = um(con, "SELECT * FROM team_contacts WHERE phone=? AND active=1", (fone,))
                if not ct or not ct["channel_id"]:
                    auditar(con, "whatsapp.desconhecido", "system", entity_type="whatsapp", entity_id=fone[-4:],
                            detail={"final": fone[-4:], "tipo": msg.get("type")})
                    continue
                texto = _texto_de(msg) or "[mensagem sem texto]"
                try:
                    quando = datetime.fromtimestamp(int(msg.get("timestamp")), timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                except (TypeError, ValueError):
                    quando = agora()
                from command_center.api.equipe import guardar_mensagem
                mid = guardar_mensagem(con, ct["channel_id"], texto, ct["name"], origem="whatsapp",
                                       external_id=msg.get("id"), quando=quando)
                con.execute("UPDATE team_contacts SET last_inbound_at=? WHERE id=? AND (last_inbound_at IS NULL OR last_inbound_at<?)",
                            (quando, ct["id"], quando))
                if mid:
                    novas += 1
                    canal = um(con, "SELECT name FROM team_channels WHERE id=?", (ct["channel_id"],))
                    _avisar(con, ct["channel_id"], ct["name"], canal["name"] if canal else ct["name"])
            for st in v.get("statuses", []):
                novo = {"sent": "enviado", "delivered": "entregue", "read": "lido", "failed": "falhou"}.get(st.get("status"))
                if not novo:
                    continue
                erro = "; ".join((e.get("title") or e.get("message") or "") for e in st.get("errors", [])) or None
                # status só anda para a frente: "entregue" atrasado não desfaz "lido"
                ordem = "CASE wa_status WHEN 'lido' THEN 3 WHEN 'entregue' THEN 2 WHEN 'enviado' THEN 1 ELSE 0 END"
                peso = {"enviado": 1, "entregue": 2, "lido": 3, "falhou": 9}[novo]
                cur = con.execute(f"UPDATE team_messages SET wa_status=?, wa_error=COALESCE(?, wa_error) "
                                  f"WHERE origem='painel' AND external_id=? AND ({ordem} < ? OR ?=9)",
                                  (novo, erro, st.get("id"), peso, peso))
                estados += cur.rowcount or 0
    con.commit()
    return {"ok": True, "mensagens": novas, "status": estados}


# --------------------------------------------------------------------- contatos
@r.get("/status")
def status(u=Depends(auth.exige("OPERATOR"))):
    return wa.estado()


@r.get("/contatos")
def contatos(con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    return {"contatos": [_contato_publico(c) for c in todos(con, "SELECT * FROM team_contacts ORDER BY active DESC, name")],
            **wa.estado()}


class ContatoIn(BaseModel):
    model_config = {"extra": "forbid"}
    name: str | None = None
    funcao: str | None = None
    phone: str | None = None
    active: bool | None = None
    notes: str | None = None


@r.post("/contatos", status_code=201)
def criar(dados: ContatoIn, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    """Quem da equipe recebe pelo WhatsApp. É de gerente: é o cadastro que decide para quem
    o painel pode mandar mensagem sem aprovação."""
    nome = (dados.name or "").strip()
    if not nome:
        raise HTTPException(400, "O contato precisa de nome.")
    try:
        fone = wa.normaliza_fone(dados.phone)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if um(con, "SELECT 1 AS x FROM team_contacts WHERE phone=?", (fone,)):
        raise HTTPException(409, "Esse telefone já está cadastrado.")
    cid = inserir(con, "team_channels", name=f"{nome} · WhatsApp"[:120], kind="EQUIPE", topic=(dados.funcao or None),
                  bridge="whatsapp", bridge_id=fone, created_by=u["id"])
    con.execute("INSERT OR IGNORE INTO team_members (channel_id, user_id) VALUES (?,?)", (cid, u["id"]))
    ctid = inserir(con, "team_contacts", name=nome[:80], funcao=(dados.funcao or "").strip() or None, phone=fone,
                   channel_id=cid, notes=dados.notes, created_by=u["id"])
    auditar(con, "whatsapp.contact.create", f"user:{u['id']}", user_id=u["id"], entity_type="team_contact", entity_id=ctid,
            detail={"nome": nome, "funcao": dados.funcao, "final": fone[-4:]}, ip=auth._ip(request))
    con.commit()
    return {"id": ctid, "channel_id": cid}


@r.patch("/contatos/{ctid}")
def editar(ctid: int, dados: ContatoIn, request: Request, con: sqlite3.Connection = Depends(get_db),
           u=Depends(auth.exige("MANAGER"))):
    ct = um(con, "SELECT * FROM team_contacts WHERE id=?", (ctid,))
    if not ct:
        raise HTTPException(404, "Contato não encontrado.")
    campos = dados.model_dump(exclude_unset=True)
    if "phone" in campos:
        try:
            campos["phone"] = wa.normaliza_fone(campos["phone"])
        except ValueError as e:
            raise HTTPException(400, str(e))
        if um(con, "SELECT 1 AS x FROM team_contacts WHERE phone=? AND id<>?", (campos["phone"], ctid)):
            raise HTTPException(409, "Esse telefone já está cadastrado.")
    if "name" in campos and not (campos["name"] or "").strip():
        raise HTTPException(400, "O contato precisa de nome.")
    if "active" in campos:
        campos["active"] = 1 if campos["active"] else 0
    if not campos:
        return {"ok": True}
    con.execute(f"UPDATE team_contacts SET {', '.join(f'{k}=?' for k in campos)} WHERE id=?", (*campos.values(), ctid))
    if ct["channel_id"]:
        novo = um(con, "SELECT * FROM team_contacts WHERE id=?", (ctid,))
        con.execute("UPDATE team_channels SET name=?, topic=?, bridge_id=?, archived_at=? WHERE id=?",
                    (f"{novo['name']} · WhatsApp"[:120], novo["funcao"], novo["phone"],
                     None if novo["active"] else agora(), ct["channel_id"]))
    auditar(con, "whatsapp.contact.edit", f"user:{u['id']}", user_id=u["id"], entity_type="team_contact", entity_id=ctid,
            detail={k: (v if k != "phone" else str(v)[-4:]) for k, v in campos.items()}, ip=auth._ip(request))
    con.commit()
    return {"ok": True}
