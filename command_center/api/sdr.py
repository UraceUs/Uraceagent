"""Interruptor do Chase no painel (dono, 06/10: "deixe um switch no command center onde dê para
ligar e desligar o chase").

O Chase é a ponte de vendas (salesagent/bridge, serviço `sales-bridge`). O nível dela vem de
`SDR_MODO` em ~/.urace/bridge.env e só vale depois que a ponte reinicia:
  - "observar"  decide e registra, não escreve no Kommo e não responde;
  - "organizar" etiqueta, nota, tarefa e etapa no Kommo; não responde ao lead;
  - "atender"   organiza E responde (o Chase ligado).

O painel grava o nível no bridge.env e deixa ~/.urace/sdr.request; no servidor, o path unit
`urace-sdr.path` vê o pedido e `urace-sdr.service` reinicia a ponte (mesmo desenho do botão
"Atualizar sistema"). Só ADMIN. Nada que o usuário manda vai para o shell: o nível é validado
contra a lista fixa e o comando da unit é fixo."""
import json
import os
import re
import sqlite3
import subprocess
import urllib.request
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from command_center.api import auth
from command_center.db import auditar, get_db

r = APIRouter(prefix="/ops/api/sdr", tags=["sdr"])
NIVEIS = ("observar", "organizar", "atender")
PEDIDO = "sdr.request"
UNIT = "urace-sdr"
PONTE = os.environ.get("CC_PONTE_URL", "http://127.0.0.1:8800")


def _dir():
    return Path(os.environ.get("URACE_DIR") or (Path.home() / ".urace"))


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
