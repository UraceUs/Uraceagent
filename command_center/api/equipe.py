"""Chat interno da equipe.

Dono, 21/09: unificar o que hoje se fala no WhatsApp (mecânicos, coach, designers,
fornecedor de suit) e no Google Chat (staff adm, financeiro, comercial) — *"queria uma
ponte, onde unisse ambos"*. A decisão de desenho está em `D-2026-09-21`: o painel é o
hub, e os dois viram canais.

Este arquivo é a **base**, e ela vem primeiro de propósito: o Google Chat depende de um
app aprovado pelo admin do Workspace, e o WhatsApp depende de conta verificada na Meta,
número dedicado e do limite de 8 pessoas por grupo de API. Nada disso trava o chat de
dentro — e é justamente o chat de dentro que resolve a objeção certa do dono ("chat que
não toca no celular perde para o WhatsApp"), porque ele notifica sem custo por mensagem e
sem janela de 24 h.

**Três coisas que este módulo faz e que um chat ingênuo não faz:**

1. **Conversa tem dono.** Canal se liga a corrida, serviço ou cliente. Conversa solta
   vira conversa perdida — e a pergunta "o que ficou combinado do kart do Pedro?" tem de
   ter resposta em um lugar só.
2. **Não lido é por mensagem, não por relógio.** `last_read_id` em vez de data: relógio de
   celular mente, ordem de mensagem não.
3. **A mensagem já nasce sabendo de onde veio** (`origem`, `external_id`). Quando as
   pontes entrarem, elas escrevem na mesma tabela — sem migrar conversa, que é o mesmo que
   perder conversa.
"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from command_center.api import auth
from command_center.db import agora, auditar, get_db, inserir, todos, um

r = APIRouter(prefix="/ops/api/equipe", tags=["equipe"])

TIPOS = ("EQUIPE", "CORRIDA", "SERVICO", "CLIENTE", "DIRETO")
LIMITE_TEXTO = 8000


def _canal(con, cid):
    c = um(con, "SELECT * FROM team_channels WHERE id=?", (cid,))
    if not c:
        raise HTTPException(404, "Conversa não encontrada.")
    return c


def _pode_ver(con, cid, u):
    """Membro vê. ADMIN e MANAGER veem tudo — quem responde pela operação não pode ficar
    de fora de uma conversa de serviço por não terem lembrado de adicioná-lo."""
    if u.get("free") or u["role"] in ("ADMIN", "MANAGER"):
        return True
    return bool(um(con, "SELECT 1 AS x FROM team_members WHERE channel_id=? AND user_id=?", (cid, u["id"])))


def entrar(con, cid, user_id):
    con.execute("INSERT OR IGNORE INTO team_members (channel_id, user_id) VALUES (?,?)", (cid, user_id))


def garantir_canal(con, kind, entity_type=None, entity_id=None, name=None, por=None):
    """O canal da corrida/serviço/cliente, criado na primeira vez que alguém fala nele.

    Existe para a ponte e para o resto do painel: quando o serviço abre, a conversa dele
    já tem casa, sem ninguém precisar criar nada à mão."""
    if entity_type and entity_id:
        c = um(con, "SELECT * FROM team_channels WHERE entity_type=? AND entity_id=? AND kind=?",
               (entity_type, entity_id, kind))
        if c:
            return c["id"]
    return inserir(con, "team_channels", name=(name or "Conversa")[:120], kind=kind,
                   entity_type=entity_type, entity_id=entity_id, created_by=por)


def guardar_mensagem(con, cid, texto, autor, user_id=None, origem="painel", external_id=None, quando=None):
    """Escreve uma mensagem. É por aqui que as pontes vão entrar — mesma tabela, `origem`
    diferente. Mensagem repetida da mesma origem não duplica (o UNIQUE cuida)."""
    texto = (texto or "").strip()
    if not texto:
        raise ValueError("mensagem vazia")
    if external_id and um(con, """SELECT id FROM team_messages WHERE channel_id=? AND origem=? AND external_id=?""",
                          (cid, origem, external_id)):
        return None                                    # já espelhada
    return inserir(con, "team_messages", channel_id=cid, user_id=user_id, author=autor[:80],
                   text=texto[:LIMITE_TEXTO], at=quando or agora(), origem=origem, external_id=external_id)


def nao_lidas(con, user_id):
    """Quantas mensagens novas por canal, para quem pergunta. Mensagem própria não conta:
    ninguém tem notificação do que acabou de escrever."""
    return {x["channel_id"]: x["n"] for x in todos(con, """
        SELECT m.channel_id, COUNT(*) AS n FROM team_messages m
        JOIN team_members s ON s.channel_id = m.channel_id AND s.user_id = ?
        WHERE m.id > s.last_read_id AND m.deleted_at IS NULL AND COALESCE(m.user_id, -1) <> ?
        GROUP BY m.channel_id""", (user_id, user_id))}


# --------------------------------------------------------------------- rotas
@r.get("/canais")
def canais(u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """As conversas que a pessoa vê, com a última mensagem e quantas não leu."""
    visiveis = "" if (u.get("free") or u["role"] in ("ADMIN", "MANAGER")) else \
        "AND c.id IN (SELECT channel_id FROM team_members WHERE user_id = :uid)"
    linhas = todos(con, f"""
        SELECT c.*, (SELECT COUNT(*) FROM team_members m WHERE m.channel_id=c.id) AS membros,
               (SELECT text FROM team_messages x WHERE x.channel_id=c.id AND x.deleted_at IS NULL
                 ORDER BY x.id DESC LIMIT 1) AS ultima,
               (SELECT author FROM team_messages x WHERE x.channel_id=c.id AND x.deleted_at IS NULL
                 ORDER BY x.id DESC LIMIT 1) AS ultimo_autor,
               (SELECT at FROM team_messages x WHERE x.channel_id=c.id AND x.deleted_at IS NULL
                 ORDER BY x.id DESC LIMIT 1) AS ultima_em
        FROM team_channels c WHERE c.archived_at IS NULL {visiveis}
        ORDER BY COALESCE(ultima_em, c.created_at) DESC""", {"uid": u["id"]})
    novas = nao_lidas(con, u["id"])
    return {"canais": [{**dict(c), "nao_lidas": novas.get(c["id"], 0)} for c in linhas],
            "total_nao_lidas": sum(novas.values())}


class CanalIn(BaseModel):
    name: str
    kind: str = "EQUIPE"
    entity_type: str | None = None
    entity_id: int | None = None
    topic: str | None = None
    membros: list[int] = []


@r.post("/canais", status_code=201)
def criar_canal(dados: CanalIn, request: Request, u=Depends(auth.exige("OPERATOR")),
                con: sqlite3.Connection = Depends(get_db)):
    if dados.kind not in TIPOS:
        raise HTTPException(400, f"Tipo inválido. Use um de: {', '.join(TIPOS)}.")
    if not (dados.name or "").strip():
        raise HTTPException(400, "A conversa precisa de um nome.")
    cid = inserir(con, "team_channels", name=dados.name.strip()[:120], kind=dados.kind,
                  entity_type=dados.entity_type, entity_id=dados.entity_id,
                  topic=(dados.topic or None), created_by=u["id"])
    entrar(con, cid, u["id"])                          # quem cria participa
    for m in dados.membros:
        if um(con, "SELECT id FROM users WHERE id=? AND active=1", (m,)):
            entrar(con, cid, m)
    auditar(con, "equipe.canal", f"user:{u['id']}", user_id=u["id"], entity_type="team_channel",
            entity_id=cid, detail={"nome": dados.name, "tipo": dados.kind}, ip=auth._ip(request))
    con.commit()
    return {"id": cid}


@r.get("/canais/{cid}")
def canal(cid: int, desde: int = 0, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """A conversa. `desde` traz só o que é mais novo que aquele id — é assim que a tela
    atualiza sem baixar tudo de novo a cada 5 segundos."""
    c = _canal(con, cid)
    if not _pode_ver(con, cid, u):
        raise HTTPException(403, "Você não participa desta conversa.")
    msgs = todos(con, """SELECT m.*, u.name AS usuario FROM team_messages m
                         LEFT JOIN users u ON u.id = m.user_id
                         WHERE m.channel_id=? AND m.id > ? AND m.deleted_at IS NULL
                         ORDER BY m.id LIMIT 300""", (cid, int(desde or 0)))
    membros = todos(con, """SELECT u.id, u.name, u.email, u.role, m.last_read_id, m.muted
                            FROM team_members m JOIN users u ON u.id=m.user_id
                            WHERE m.channel_id=? ORDER BY u.name""", (cid,))
    return {"canal": dict(c), "mensagens": msgs, "membros": membros,
            "participo": bool(um(con, "SELECT 1 AS x FROM team_members WHERE channel_id=? AND user_id=?",
                                 (cid, u["id"])))}


class MensagemIn(BaseModel):
    text: str
    reply_to: int | None = None


@r.post("/canais/{cid}/mensagens", status_code=201)
def escrever(cid: int, dados: MensagemIn, u=Depends(auth.exige("OPERATOR")),
             con: sqlite3.Connection = Depends(get_db)):
    _canal(con, cid)
    if not _pode_ver(con, cid, u):
        raise HTTPException(403, "Você não participa desta conversa.")
    texto = (dados.text or "").strip()
    if not texto:
        raise HTTPException(400, "Mensagem vazia.")
    entrar(con, cid, u["id"])                          # quem escreve passa a participar
    mid = inserir(con, "team_messages", channel_id=cid, user_id=u["id"], author=u["name"],
                  text=texto[:LIMITE_TEXTO], at=agora(), origem="painel", reply_to=dados.reply_to)
    # quem escreveu já leu o que escreveu
    con.execute("UPDATE team_members SET last_read_id=? WHERE channel_id=? AND user_id=? AND last_read_id<?",
                (mid, cid, u["id"], mid))
    con.commit()
    return {"id": mid}


class LidoIn(BaseModel):
    ate: int


@r.post("/canais/{cid}/lido")
def marcar_lido(cid: int, dados: LidoIn, u=Depends(auth.usuario_atual),
                con: sqlite3.Connection = Depends(get_db)):
    """Só anda para a frente: marcar como lido não desfaz o que já foi lido."""
    con.execute("UPDATE team_members SET last_read_id=? WHERE channel_id=? AND user_id=? AND last_read_id<?",
                (int(dados.ate), cid, u["id"], int(dados.ate)))
    con.commit()
    return {"ok": True}


class MembroIn(BaseModel):
    user_id: int


@r.post("/canais/{cid}/membros")
def adicionar(cid: int, dados: MembroIn, u=Depends(auth.exige("OPERATOR")),
              con: sqlite3.Connection = Depends(get_db)):
    _canal(con, cid)
    if not _pode_ver(con, cid, u):
        raise HTTPException(403, "Você não participa desta conversa.")
    if not um(con, "SELECT id FROM users WHERE id=? AND active=1", (dados.user_id,)):
        raise HTTPException(404, "Pessoa não encontrada (ou inativa).")
    entrar(con, cid, dados.user_id)
    con.commit()
    return {"ok": True}
