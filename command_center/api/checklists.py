"""Checklists e "Meu dia" (#92).

- **ver e preencher** (marcar, foto, concluir) é OPERATOR — inclui o mecânico e o coach, que
  são OPERATOR com cargo; cada um vê os checklists do seu cargo.
- **editar os modelos e importar da planilha** é MANAGER (dono, 05/10: *"gerente para cima
  consegue ver e editar o que tem em cada checklist"*).
"""
import os
import sqlite3

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel

from command_center.api import auth
from command_center.db import auditar, get_db, um
from command_center.providers import checklists as ck

r = APIRouter(prefix="/ops/api/checklists", tags=["checklists"])
dia = APIRouter(prefix="/ops/api/meu-dia", tags=["checklists"])
MAX_FOTO = 15 * 1024 * 1024


def _aud(con, request, u, evento, eid, detalhe=None):
    auditar(con, evento, f"user:{u['id']}", user_id=u["id"], entity_type="checklist", entity_id=eid, detail=detalhe,
            ip=auth._ip(request))


def _erro(e):
    if isinstance(e, LookupError):
        return HTTPException(404, str(e))
    return HTTPException(400, str(e))


@dia.get("")
def meu_dia(data: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"), con: sqlite3.Connection = Depends(get_db),
            u=Depends(auth.exige("OPERATOR"))):
    return {**ck.meu_dia(con, data, u.get("cargo")), "cargo": u.get("cargo"),
            "gerente": bool(u.get("free")) or auth.pode(u["role"], "MANAGER")}


# ------------------------------------------------------------------ modelos
@r.get("/modelos")
def modelos(todos: bool = False, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    return {"modelos": ck.modelos(con, ativos=not todos), "planilha": ck.PLANILHA}


@r.post("/importar")
def importar(request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    try:
        res = ck.importar(con, por=u["id"])
    except ck.ErroChecklist as e:
        raise HTTPException(400, str(e))
    except Exception as e:                           # noqa: BLE001 — Google fora, token sem permissão
        raise HTTPException(502, f"Não consegui ler a planilha: {str(e)[:300]}")
    _aud(con, request, u, "checklist.importar", None, res)
    con.commit()
    return res


class ModeloIn(BaseModel):
    name: str | None = None
    section: str | None = None
    quando: str | None = None
    cargo: str | None = None
    per_kart: bool | None = None
    photo_required: bool | None = None
    active: bool | None = None


@r.post("/modelos", status_code=201)
def criar_modelo(dados: ModeloIn, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    try:
        tid = ck.criar_modelo(con, dados.name or "", dados.section, dados.quando or "avulso", dados.cargo or "MECANICO",
                              dados.per_kart or False, u["id"])
    except ck.ErroChecklist as e:
        raise HTTPException(400, str(e))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Já existe um checklist com esse nome nessa seção.")
    _aud(con, request, u, "checklist.modelo.criar", tid, {"nome": dados.name})
    con.commit()
    return {"id": tid}


@r.patch("/modelos/{tid}")
def editar_modelo(tid: int, dados: ModeloIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                  u=Depends(auth.exige("MANAGER"))):
    campos = {k: v for k, v in dados.model_dump().items() if v is not None}
    try:
        ck.editar_modelo(con, tid, u["id"], **campos)
    except (LookupError, ck.ErroChecklist) as e:
        raise _erro(e)
    _aud(con, request, u, "checklist.modelo.editar", tid, campos)
    con.commit()
    return {"ok": True}


class ItemIn(BaseModel):
    text: str | None = None
    grupo: str | None = None
    sort: int | None = None
    photo_required: bool | None = None
    active: bool | None = None


@r.post("/modelos/{tid}/itens", status_code=201)
def adicionar_item(tid: int, dados: ItemIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                   u=Depends(auth.exige("MANAGER"))):
    try:
        iid = ck.adicionar_item(con, tid, dados.text or "", dados.grupo, bool(dados.photo_required))
    except (LookupError, ck.ErroChecklist) as e:
        raise _erro(e)
    _aud(con, request, u, "checklist.item.criar", tid, {"item": iid})
    con.commit()
    return {"id": iid}


@r.patch("/itens/{iid}")
def editar_item(iid: int, dados: ItemIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                u=Depends(auth.exige("MANAGER"))):
    campos = {k: v for k, v in dados.model_dump().items() if v is not None}
    try:
        ck.editar_item(con, iid, **campos)
    except (LookupError, ck.ErroChecklist) as e:
        raise _erro(e)
    _aud(con, request, u, "checklist.item.editar", iid, campos)
    con.commit()
    return {"ok": True}


# ------------------------------------------------------------------ preencher
class AbrirIn(BaseModel):
    template_id: int
    ctx: dict


@r.post("/runs", status_code=201)
def abrir(dados: AbrirIn, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    t = um(con, "SELECT cargo FROM checklist_templates WHERE id=?", (dados.template_id,))
    if t and u.get("cargo") and t["cargo"] != u["cargo"]:
        raise HTTPException(403, "Este checklist não é do seu cargo.")
    try:
        rid = ck.abrir(con, dados.template_id, dados.ctx, u["id"])
    except (LookupError, ck.ErroChecklist, KeyError, ValueError) as e:
        raise _erro(e if not isinstance(e, KeyError) else ck.ErroChecklist("contexto incompleto"))
    con.commit()
    return ck.preenchimento(con, rid)


@r.get("/runs/{rid}")
def ver(rid: int, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    try:
        return ck.preenchimento(con, rid)
    except LookupError as e:
        raise _erro(e)


class MarcarIn(BaseModel):
    done: bool
    note: str | None = None


@r.post("/runs/{rid}/itens/{iid}")
def marcar(rid: int, iid: int, dados: MarcarIn, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    try:
        ck.marcar(con, rid, iid, dados.done, dados.note, u["id"])
    except (LookupError, ck.ErroChecklist) as e:
        raise _erro(e)
    con.commit()
    return ck.preenchimento(con, rid)


@r.post("/runs/{rid}/itens/{iid}/foto", status_code=201)
async def foto(rid: int, iid: int, arquivo: UploadFile = File(...), con: sqlite3.Connection = Depends(get_db),
               u=Depends(auth.exige("OPERATOR"))):
    dados = await arquivo.read(MAX_FOTO + 1)
    if len(dados) > MAX_FOTO:
        raise HTTPException(413, "Foto grande demais (máximo 15 MB).")
    try:
        ck.guardar_foto(con, rid, iid, dados, u["id"])
    except (LookupError, ck.ErroChecklist) as e:
        raise _erro(e)
    con.commit()
    return ck.preenchimento(con, rid)


@r.get("/fotos/{fid}")
def ver_foto(fid: int, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    f = um(con, "SELECT file_path FROM checklist_photos WHERE id=?", (fid,))
    if not f or not f["file_path"] or not os.path.isfile(f["file_path"]):
        raise HTTPException(404, "Foto não encontrada.")
    with open(f["file_path"], "rb") as a:
        return Response(a.read(), media_type="image/webp", headers={"Cache-Control": "private, max-age=86400"})


@r.post("/runs/{rid}/concluir")
def concluir(rid: int, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    try:
        ck.concluir(con, rid, u["id"])
    except (LookupError, ck.ErroChecklist) as e:
        raise _erro(e)
    _aud(con, request, u, "checklist.concluir", rid)
    con.commit()
    return ck.preenchimento(con, rid)
