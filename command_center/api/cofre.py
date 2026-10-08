"""Cofre de logins e senhas (#162) — as rotas. A criptografia mora em `providers/cofre.py`.

**Quem entra:** só a conta de **acesso livre**, pelo navegador (cookie de sessão). ADMIN comum,
chave de API, conector MCP e a IA levam 403: requisição com `Authorization` não entra, nem que
seja do próprio dono.

**Desbloquear:** ver, criar ou mudar um item pede a senha de login de novo; o desbloqueio vale
`DESBLOQUEIO_MIN` minutos naquela sessão (tabela `vault_unlocks`). Errar a senha conta no mesmo
limite de tentativas do login.

**Rastro:** toda ação vai para a auditoria com o id e o nome do item, nunca com o valor. As
respostas com senha saem `Cache-Control: no-store`. Nada se apaga: arquiva.
"""
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from command_center.api import auth
from command_center.db import agora, atualizar, auditar, get_db, inserir, todos, um
from command_center.providers import cofre

r = APIRouter(prefix="/ops/api/cofre", tags=["cofre"])
DESBLOQUEIO_MIN = 10
SO_LIVRE = "O cofre é só da conta de acesso livre, pelo navegador."
CAMPOS = "id, name, url, username, key_fp, archived, created_at, updated_at, revealed_at"


def so_livre(request: Request, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """Acesso livre, com sessão de navegador, e sem credencial de máquina na requisição."""
    if request.headers.get("authorization") or request.headers.get("x-api-key"):
        raise HTTPException(403, SO_LIVRE)
    s = auth.sessao_valida(con, request.cookies.get(auth.COOKIE_SESSAO))
    if not (s and s["user_id"] == u["id"] and u.get("free") and auth.livre(s["email"])):
        raise HTTPException(403, SO_LIVRE)
    return {**u, "sessao": s["id"]}


def _aud(con, request, u, evento, eid=None, detalhe=None):
    auditar(con, evento, f"user:{u['id']}", user_id=u["id"], entity_type="vault_item", entity_id=eid,
            detail=detalhe, ip=auth._ip(request))


def _ate(con, u):
    d = um(con, "SELECT until FROM vault_unlocks WHERE session_id=? AND user_id=?", (u["sessao"], u["id"]))
    return d["until"] if d and d["until"] > agora() else None


def _exige_desbloqueio(con, u):
    if not _ate(con, u):
        raise HTTPException(423, "Confirme a sua senha para abrir o cofre.")


def _exige_ligado():
    ok, motivo = cofre.ligado()
    if not ok:
        raise HTTPException(503, motivo)


def _item(con, iid):
    it = um(con, f"SELECT {CAMPOS}, secret_enc IS NOT NULL AS tem_senha, notes_enc IS NOT NULL AS tem_nota "
                 "FROM vault_items WHERE id=?", (iid,))
    if not it:
        raise HTTPException(404, "Item não encontrado.")
    return dict(it)


@r.get("")
def listar(response: Response, arquivados: bool = False, u=Depends(so_livre), con: sqlite3.Connection = Depends(get_db)):
    ok, motivo = cofre.ligado()
    itens = todos(con, f"SELECT {CAMPOS}, secret_enc IS NOT NULL AS tem_senha, notes_enc IS NOT NULL AS tem_nota "
                       "FROM vault_items WHERE archived=? ORDER BY name COLLATE NOCASE", (1 if arquivados else 0,))
    fp = cofre.impressao() if ok else None
    response.headers["Cache-Control"] = "no-store"
    return {"ligado": ok, "motivo": motivo, "impressao": fp, "desbloqueado_ate": _ate(con, u),
            "itens": [dict(i, outra_chave=bool(fp and i["key_fp"] != fp)) for i in itens]}


class Senha(BaseModel):
    senha: str


@r.post("/desbloquear")
def desbloquear(dados: Senha, request: Request, u=Depends(so_livre), con: sqlite3.Connection = Depends(get_db)):
    _exige_ligado()
    chave = f"cofre:{u['id']}"
    if auth._falhas_recentes(con, chave) >= auth.MAX_FALHAS:
        raise HTTPException(429, "Muitas tentativas. Espere alguns minutos.")
    p = um(con, "SELECT pw_salt, pw_hash FROM users WHERE id=?", (u["id"],))
    ok = bool(p and auth.confere_senha(dados.senha or "", p["pw_salt"], p["pw_hash"]))
    auth._registra_tentativa(con, chave, ok)
    if not ok:
        _aud(con, request, u, "vault.unlock_failed")
        raise HTTPException(401, "Senha incorreta.")
    ate = (datetime.now(timezone.utc) + timedelta(minutes=DESBLOQUEIO_MIN)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    con.execute("INSERT OR REPLACE INTO vault_unlocks (session_id, user_id, until) VALUES (?,?,?)",
                (u["sessao"], u["id"], ate))
    _aud(con, request, u, "vault.unlocked")
    return {"desbloqueado_ate": ate}


@r.post("/travar")
def travar(request: Request, u=Depends(so_livre), con: sqlite3.Connection = Depends(get_db)):
    con.execute("DELETE FROM vault_unlocks WHERE session_id=?", (u["sessao"],))
    _aud(con, request, u, "vault.locked")
    return {"ok": True}


class ItemIn(BaseModel):
    name: str | None = None
    url: str | None = None
    username: str | None = None
    senha: str | None = None
    nota: str | None = None


def _limpo(v):
    return v.strip() if isinstance(v, str) else v


@r.post("", status_code=201)
def criar(dados: ItemIn, request: Request, u=Depends(so_livre), con: sqlite3.Connection = Depends(get_db)):
    _exige_ligado()
    _exige_desbloqueio(con, u)
    if not _limpo(dados.name):
        raise HTTPException(400, "Diga de que serviço é.")
    iid = inserir(con, "vault_items", name=_limpo(dados.name)[:200], url=_limpo(dados.url) or None,
                  username=_limpo(dados.username) or None, secret_enc=cofre.cifrar(dados.senha, "senha"),
                  notes_enc=cofre.cifrar(_limpo(dados.nota), "nota"), key_fp=cofre.impressao(),
                  created_by=u["id"], updated_by=u["id"])
    _aud(con, request, u, "vault.created", iid, {"nome": _limpo(dados.name)[:200]})
    return _item(con, iid)


@r.patch("/{iid}")
def mudar(iid: int, dados: ItemIn, request: Request, u=Depends(so_livre), con: sqlite3.Connection = Depends(get_db)):
    _exige_ligado()
    _exige_desbloqueio(con, u)
    it = _item(con, iid)
    enviados = dados.model_dump(exclude_unset=True)
    campos = {}
    for k in ("name", "url", "username"):
        if k in enviados:
            campos[k] = _limpo(enviados[k]) or None
    if "name" in campos and not campos["name"]:
        raise HTTPException(400, "Diga de que serviço é.")
    if "senha" in enviados:
        campos["secret_enc"] = cofre.cifrar(enviados["senha"], "senha")
    if "nota" in enviados:
        campos["notes_enc"] = cofre.cifrar(_limpo(enviados["nota"]), "nota")
    if ("senha" in enviados) != ("nota" in enviados) and it["key_fp"] != cofre.impressao():
        # trocar só um dos dois deixaria o item com duas chaves diferentes
        raise HTTPException(409, "Este item foi guardado com outra chave: regrave a senha e a observação juntas.")
    if "senha" in enviados or "nota" in enviados:
        campos["key_fp"] = cofre.impressao()
    if campos:
        atualizar(con, "vault_items", iid, updated_by=u["id"], updated_at=agora(), **campos)
    _aud(con, request, u, "vault.updated", iid, {"nome": it["name"], "campos": sorted(enviados)})
    return _item(con, iid)


@r.post("/{iid}/revelar")
def revelar(iid: int, request: Request, response: Response, u=Depends(so_livre), con: sqlite3.Connection = Depends(get_db)):
    _exige_ligado()
    _exige_desbloqueio(con, u)
    it = _item(con, iid)
    bruto = um(con, "SELECT secret_enc, notes_enc FROM vault_items WHERE id=?", (iid,))
    try:
        senha, nota = cofre.decifrar(bruto["secret_enc"], "senha"), cofre.decifrar(bruto["notes_enc"], "nota")
    except cofre.ChaveErrada as e:
        raise HTTPException(409, str(e)) from e
    con.execute("UPDATE vault_items SET revealed_at=? WHERE id=?", (agora(), iid))
    _aud(con, request, u, "vault.revealed", iid, {"nome": it["name"]})
    response.headers["Cache-Control"] = "no-store"
    return {"id": iid, "senha": senha, "nota": nota}


@r.post("/{iid}/arquivar")
def arquivar(iid: int, request: Request, u=Depends(so_livre), con: sqlite3.Connection = Depends(get_db)):
    it = _item(con, iid)
    atualizar(con, "vault_items", iid, archived=1, updated_by=u["id"], updated_at=agora())
    _aud(con, request, u, "vault.archived", iid, {"nome": it["name"]})
    return _item(con, iid)


@r.post("/{iid}/restaurar")
def restaurar(iid: int, request: Request, u=Depends(so_livre), con: sqlite3.Connection = Depends(get_db)):
    it = _item(con, iid)
    atualizar(con, "vault_items", iid, archived=0, updated_by=u["id"], updated_at=agora())
    _aud(con, request, u, "vault.restored", iid, {"nome": it["name"]})
    return _item(con, iid)
