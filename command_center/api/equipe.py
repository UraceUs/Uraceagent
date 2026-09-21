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

**A intenção, na palavra do dono (21/09):** falar com uma pessoa em um clique, montar
grupo com nome, participantes e foto, e poder **silenciar** tanto a conversa individual
quanto o grupo. É chat de gente, não só de operação — e as duas coisas convivem aqui: a
conversa do serviço continua existindo, ligada ao serviço.

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
import os
import sqlite3

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
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


def _chave_direta(a, b):
    """Par de pessoas vira uma chave estável: o menor id primeiro.

    É isso que impede duas conversas paralelas entre as mesmas duas pessoas — cada uma
    com metade do histórico, que é o defeito clássico de chat direto feito na pressa. O
    índice único no banco é quem garante, não a boa vontade do código."""
    x, y = sorted((int(a), int(b)))
    return f"{x}-{y}"


def canal_direto(con, eu, outro):
    """A conversa entre duas pessoas, criada na primeira vez que alguém abre. Chamar de
    novo devolve a mesma."""
    if int(eu) == int(outro):
        raise ValueError("não dá para abrir conversa consigo mesmo")
    chave = _chave_direta(eu, outro)
    c = um(con, "SELECT * FROM team_channels WHERE dm_key=?", (chave,))
    if c:
        entrar(con, c["id"], eu); entrar(con, c["id"], outro)   # alguém pode ter saído
        return c["id"]
    cid = inserir(con, "team_channels", name="", kind="DIRETO", dm_key=chave, created_by=eu)
    entrar(con, cid, eu)
    entrar(con, cid, outro)
    return cid


def _nome_para(con, canal, user_id):
    """Conversa direta não tem nome próprio: ela se chama como a OUTRA pessoa, e isso
    depende de quem está olhando."""
    if canal["kind"] != "DIRETO":
        return canal["name"]
    o = um(con, """SELECT u.name FROM team_members m JOIN users u ON u.id=m.user_id
                   WHERE m.channel_id=? AND m.user_id<>? LIMIT 1""", (canal["id"], user_id))
    return o["name"] if o else "Conversa"


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


def total_nao_lidas(con, user_id):
    """O número do menu. Exclui o que a pessoa silenciou — é isso que silenciar significa
    para quem olha o menu. A contagem POR CONVERSA continua incluindo os silenciados: some
    da vista, não da memória."""
    mudos = {x["channel_id"] for x in todos(con, "SELECT channel_id FROM team_members WHERE user_id=? AND muted=1",
                                            (user_id,))}
    return sum(n for cid, n in nao_lidas(con, user_id).items() if cid not in mudos)


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
    mudos = {x["channel_id"] for x in todos(con, "SELECT channel_id FROM team_members WHERE user_id=? AND muted=1",
                                            (u["id"],))}
    saida = [{**dict(c), "name": _nome_para(con, c, u["id"]), "nao_lidas": novas.get(c["id"], 0),
              "mudo": c["id"] in mudos} for c in linhas]
    return {"canais": saida, "total_nao_lidas": sum(n for cid, n in novas.items() if cid not in mudos)}


class CanalIn(BaseModel):
    name: str
    kind: str = "EQUIPE"
    entity_type: str | None = None
    entity_id: int | None = None
    topic: str | None = None
    membros: list[int] = []
    icone: str | None = None            # emoji; a foto sobe depois, por rota própria


@r.post("/canais", status_code=201)
def criar_canal(dados: CanalIn, request: Request, u=Depends(auth.exige("OPERATOR")),
                con: sqlite3.Connection = Depends(get_db)):
    if dados.kind not in TIPOS:
        raise HTTPException(400, f"Tipo inválido. Use um de: {', '.join(TIPOS)}.")
    if not (dados.name or "").strip():
        raise HTTPException(400, "A conversa precisa de um nome.")
    cid = inserir(con, "team_channels", name=dados.name.strip()[:120], kind=dados.kind,
                  entity_type=dados.entity_type, entity_id=dados.entity_id,
                  topic=(dados.topic or None), created_by=u["id"],
                  icon=(dados.icone or None) and dados.icone.strip()[:8])
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
    meu = um(con, "SELECT muted FROM team_members WHERE channel_id=? AND user_id=?", (cid, u["id"]))
    return {"canal": {**dict(c), "name": _nome_para(con, c, u["id"])},
            "mensagens": msgs, "membros": membros,
            "participo": bool(meu), "mudo": bool(meu and meu["muted"])}


class MensagemIn(BaseModel):
    text: str
    reply_to: int | None = None


def _avisar_quem_nao_esta_vendo(cid, autor_id, autor_nome, canal_nome, texto):
    """O aviso no celular sai em segundo plano, com conexão própria.

    Em segundo plano porque notificação não pode segurar a resposta de quem escreveu — a
    mensagem já está salva, o aviso é consequência. E o texto da mensagem NÃO vai junto:
    o aviso passa por servidor da Apple/Google, e conversa da equipe não tem por que
    passar por lá. Vai quem escreveu, onde, e o link."""
    from command_center.api import push
    from command_center.db import conectar
    con = conectar()
    try:
        alvos = [x["user_id"] for x in todos(con, """SELECT user_id FROM team_members
                                                     WHERE channel_id=? AND muted=0 AND user_id<>?""",
                                             (cid, autor_id))]
        if alvos:
            push.avisar(con, alvos, f"{autor_nome.split(' ')[0]} em {canal_nome}",
                        "Nova mensagem no chat da equipe.", f"/ops/equipe?c={cid}")
    except Exception:                                  # noqa: BLE001
        pass                                           # aviso que falha não estraga a conversa
    finally:
        con.close()


@r.post("/canais/{cid}/mensagens", status_code=201)
def escrever(cid: int, dados: MensagemIn, fundo: BackgroundTasks, u=Depends(auth.exige("OPERATOR")),
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
    c = _canal(con, cid)
    fundo.add_task(_avisar_quem_nao_esta_vendo, cid, u["id"], u["name"], c["name"], texto)
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


@r.get("/pessoas")
def pessoas(u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """Quem existe para conversar, com a conversa direta que já existe (se existir).

    É esta lista que faz "falar com alguém em um clique": a tela mostra as pessoas e, ao
    tocar, abre a conversa — criando na hora se for a primeira vez."""
    novas = nao_lidas(con, u["id"])
    saida = []
    for p in todos(con, """SELECT id, name, email, role FROM users
                           WHERE active=1 AND id<>? ORDER BY name""", (u["id"],)):
        c = um(con, "SELECT id FROM team_channels WHERE dm_key=?", (_chave_direta(u["id"], p["id"]),))
        saida.append({**dict(p), "canal_id": c["id"] if c else None,
                      "nao_lidas": novas.get(c["id"], 0) if c else 0})
    return saida


@r.post("/direto/{user_id}", status_code=201)
def abrir_direto(user_id: int, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    """Abre (ou reabre) a conversa com uma pessoa. Chamar duas vezes devolve a mesma."""
    if not um(con, "SELECT id FROM users WHERE id=? AND active=1", (user_id,)):
        raise HTTPException(404, "Pessoa não encontrada (ou inativa).")
    try:
        cid = canal_direto(con, u["id"], user_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    con.commit()
    return {"id": cid}


class MudoIn(BaseModel):
    mudo: bool


@r.post("/canais/{cid}/silenciar")
def silenciar(cid: int, dados: MudoIn, u=Depends(auth.usuario_atual),
              con: sqlite3.Connection = Depends(get_db)):
    """Silenciar é por PESSOA: eu calo o grupo para mim, e não para os outros.

    Silenciado não manda aviso no celular e não entra no número do menu. As mensagens
    continuam chegando e contando na lista — some da vista, não da memória."""
    _canal(con, cid)
    if not um(con, "SELECT 1 AS x FROM team_members WHERE channel_id=? AND user_id=?", (cid, u["id"])):
        raise HTTPException(403, "Você não participa desta conversa.")
    con.execute("UPDATE team_members SET muted=? WHERE channel_id=? AND user_id=?",
                (1 if dados.mudo else 0, cid, u["id"]))
    con.commit()
    return {"ok": True, "mudo": dados.mudo}


def _pasta_imagens():
    caminho = os.path.join(os.environ.get("URACE_DIR", os.path.expanduser("~/.urace")), "equipe")
    os.makedirs(caminho, exist_ok=True)
    return caminho


TIPOS_IMAGEM = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
IMAGEM_MAX = 4 * 1024 * 1024


@r.post("/canais/{cid}/imagem")
async def subir_imagem(cid: int, arquivo: UploadFile = File(...), u=Depends(auth.exige("OPERATOR")),
                       con: sqlite3.Connection = Depends(get_db)):
    """Foto do grupo. Fica em ~/.urace/equipe, fora do repositório e fora do banco.

    Só conversa de grupo tem foto: conversa direta já se identifica pela pessoa."""
    c = _canal(con, cid)
    if c["kind"] == "DIRETO":
        raise HTTPException(400, "Conversa direta não tem foto: ela é a pessoa.")
    if not _pode_ver(con, cid, u):
        raise HTTPException(403, "Você não participa desta conversa.")
    ext = TIPOS_IMAGEM.get((arquivo.content_type or "").lower())
    if not ext:
        raise HTTPException(400, "Use PNG, JPG ou WEBP.")
    dados = await arquivo.read(IMAGEM_MAX + 1)
    if len(dados) > IMAGEM_MAX:
        raise HTTPException(400, "Imagem grande demais (máximo 4 MB).")
    nome = f"canal-{cid}{ext}"
    with open(os.path.join(_pasta_imagens(), nome), "wb") as f:
        f.write(dados)
    con.execute("UPDATE team_channels SET image_path=?, icon=NULL WHERE id=?", (nome, cid))
    con.commit()
    return {"ok": True}


@r.get("/canais/{cid}/imagem")
def ver_imagem(cid: int, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """A foto sai pelo servidor, com sessão — nunca por link público adivinhável."""
    c = _canal(con, cid)
    if not c["image_path"] or not _pode_ver(con, cid, u):
        raise HTTPException(404)
    caminho = os.path.join(_pasta_imagens(), os.path.basename(c["image_path"]))
    if not os.path.isfile(caminho):
        raise HTTPException(404)
    from fastapi.responses import FileResponse
    return FileResponse(caminho, headers={"Cache-Control": "private, max-age=300"})


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
