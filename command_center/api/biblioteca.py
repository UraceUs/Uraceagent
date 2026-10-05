"""Biblioteca (#88): todos os documentos de cada cliente, num lugar só. **Gerente para cima**
(dono, 05/10: *"a biblioteca, onde está tudo reunido, de gerente para cima"*). Operador e
mecânico continuam vendo a waiver e a invoice no card do cliente.

A rodada é do timer do VPS, toda madrugada, sem IA. O botão "Atualizar agora" roda a mesma
rodada em segundo plano, uma de cada vez.
"""
import os
import sqlite3
import threading

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from command_center.api import auth
from command_center.db import auditar, conectar, get_db, um
from command_center.providers import biblioteca as bib

r = APIRouter(prefix="/ops/api/biblioteca", tags=["biblioteca"])
_rodando = threading.Lock()


@r.get("")
def lista(tipo: str | None = Query(None), q: str | None = None, client_id: int | None = None,
          limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
          con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    if tipo and tipo not in bib.KINDS:
        raise HTTPException(400, "Tipo de documento inválido.")
    return bib.listar(con, tipo, q, client_id, limit, offset)


@r.get("/resumo")
def resumo(con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    return {**bib.resumo(con), "rodando": _rodando.locked()}


@r.get("/{doc_id}/pdf")
def pdf(doc_id: int, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    d = um(con, "SELECT * FROM library_docs WHERE id=?", (doc_id,))
    if not d or not d["file_path"] or not os.path.isfile(d["file_path"]):
        raise HTTPException(404, "PDF não encontrado.")
    auditar(con, "biblioteca.ver", f"user:{u['id']}", user_id=u["id"], entity_type="library_doc", entity_id=doc_id,
            detail={"tipo": d["kind"], "cliente": d["client_id"]}, ip=auth._ip(request))
    con.commit()
    with open(d["file_path"], "rb") as f:
        return Response(f.read(), media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{d["kind"]}-{d["ref"]}.pdf"', "Cache-Control": "private, no-store"})


def _rodar():
    try:
        con = conectar()
        try:
            bib.rodada(con, log=lambda *_: None)
        finally:
            con.close()
    finally:
        _rodando.release()


@r.post("/atualizar", status_code=202)
def atualizar_agora(request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    if not _rodando.acquire(blocking=False):
        raise HTTPException(409, "A Biblioteca já está atualizando.")
    auditar(con, "biblioteca.atualizar", f"user:{u['id']}", user_id=u["id"], ip=auth._ip(request))
    con.commit()
    threading.Thread(target=_rodar, daemon=True, name="cc-biblioteca").start()
    return {"ok": True}
