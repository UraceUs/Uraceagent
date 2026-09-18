"""Atualizar o sistema pelo painel (17/09): o dono não precisa de terminal.

O botão deixa um pedido em ~/.urace/deploy.request; no servidor, o path unit
`urace-deploy.path` vê o arquivo e roda `urace-deploy.service` (git pull + o mesmo
servir_command_center.sh de sempre) numa unit própria — fora do cgroup do painel, então
o restart do serviço no meio do deploy não mata o deploy. O log fica em
~/.urace/deploy-painel.log e o painel mostra a última rodada ao vivo.

Só ADMIN. Nenhum parâmetro vai para o shell: o comando é fixo na unit."""
import os
import sqlite3
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from command_center.api import auth
from command_center.db import agora, auditar, get_db

r = APIRouter(prefix="/ops/api/system", tags=["system"])
REPO = Path(__file__).resolve().parents[2]
LOG = "deploy-painel.log"
PEDIDO = "deploy.request"
UNIT = "urace-deploy"


def _dir():
    return Path(os.environ.get("URACE_DIR") or (Path.home() / ".urace"))


def _git(*args, timeout=20):
    try:
        p = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, timeout=timeout)
        return (p.stdout or "").strip() if p.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def versao():
    return {"commit": _git("rev-parse", "--short", "HEAD"), "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "quando": _git("log", "-1", "--format=%cI"), "mensagem": _git("log", "-1", "--format=%s")}


def novidades(branch):
    """Busca o remoto (uma chamada de rede) e diz quantos commits o servidor está atrás."""
    if not branch or _git("fetch", "-q", "origin", branch, timeout=40) is None:
        return {"erro": "não deu para consultar o GitHub agora"}
    atras = _git("rev-list", "--count", f"HEAD..origin/{branch}")
    lista = _git("log", "--format=%s", "-10", f"HEAD..origin/{branch}") or ""
    return {"atras": int(atras or 0), "commits": [x for x in lista.split("\n") if x], "remoto": _git("rev-parse", "--short", f"origin/{branch}")}


def _systemctl(*args):
    try:
        p = subprocess.run(["systemctl", *args], capture_output=True, text=True, timeout=10)
        return (p.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def instalado():
    return _systemctl("is-enabled", f"{UNIT}.path") in ("enabled", "static", "linked")


def rodando():
    return _systemctl("is-active", f"{UNIT}.service") in ("active", "activating", "reloading") or (_dir() / PEDIDO).exists()


def ultima_rodada(linhas=250):
    """A última rodada do log: do último "=== deploy" até o fim, e o resultado se já terminou."""
    f = _dir() / LOG
    if not f.exists():
        return {"log": "", "resultado": None, "inicio": None}
    try:
        texto = f.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"log": "", "resultado": None, "inicio": None}
    i = texto.rfind("=== deploy ")
    trecho = texto[i:] if i >= 0 else texto[-20000:]
    ls = trecho.split("\n")
    fim = next((x for x in reversed(ls) if x.startswith("=== fim: ")), None)
    resultado = None
    if fim:
        try:
            resultado = int(fim.split(":", 1)[1].strip(" =")) == 0
        except ValueError:
            resultado = False
    inicio = ls[0][len("=== deploy "):].split(" (")[0] if ls and ls[0].startswith("=== deploy ") else None
    return {"log": "\n".join(ls[-linhas:]), "resultado": resultado, "inicio": inicio}


@r.get("/update")
def estado(verificar: bool = False, u=Depends(auth.exige("ADMIN"))):
    v = versao()
    saida = {"versao": v, "instalado": instalado(), "rodando": rodando(), "ultima": ultima_rodada(), "agora": agora()}
    if verificar:
        saida["novidades"] = novidades(v.get("branch"))
    return saida


@r.post("/update")
def pedir(request: Request, u=Depends(auth.exige("ADMIN")), con: sqlite3.Connection = Depends(get_db)):
    if not instalado():
        raise HTTPException(503, "O botão ainda não está instalado no servidor: rode o deploy uma vez pelo terminal; a partir daí ele fica disponível aqui.")
    if rodando():
        raise HTTPException(409, "Já tem uma atualização rodando. Acompanhe o log abaixo.")
    d = _dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / PEDIDO).write_text(f"{agora()} {u['email']}\n", encoding="utf-8")
    auditar(con, "system.update", f"user:{u['id']}", user_id=u["id"], entity_type="system", entity_id=None,
            detail={"versao": versao()}, ip=auth._ip(request))
    con.commit()
    return {"ok": True, "pedido_em": agora()}
