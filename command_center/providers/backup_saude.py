"""O backup do banco na tela Sistemas (#299).

Dono, 16/10: decisão **SQLite + backup diário**. O painel avisa quando o backup do dia falhou ou faltou:
- `adminai/backup_banco.py` (03:15) e `adminai/backup_drive.py` (04:00) gravam o resultado em
  `~/.urace/backups/estado-local.json` e `estado-drive.json`;
- aqui só se lê: **ERROR** quando a cópia local de hoje falhou ou faltou (mais de 26 h sem cópia boa);
  **DEGRADED** quando só a cópia de fora da VPS (Drive, cifrada) falhou ou faltou; **CONNECTED** com as duas em dia.
Nada de cliente sai daqui: o detalhe tem hora, arquivo, tamanho, o número de clientes e a impressão da chave.
"""
import json
import os
import time
from datetime import datetime, timezone

MAX_H = 26                 # uma rodada por dia, com folga para a máquina que ficou fora do ar


def _pasta():
    from command_center.db import db_path
    return os.path.join(os.path.dirname(db_path()), "backups")


def _ler(pasta, tipo):
    try:
        with open(os.path.join(pasta, f"estado-{tipo}.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _horas(iso, agora):
    try:
        return (agora - datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()) / 3600
    except ValueError:
        return None


def _ultima_copia(pasta):
    """Antes do #299 não havia estado: a cópia mais nova da pasta diz quando foi o último backup bom."""
    try:
        copias = [os.path.join(pasta, n) for n in os.listdir(pasta) if n.startswith("command-center-")]
    except OSError:
        return None
    if not copias:
        return None
    nova = max(copias, key=os.path.getmtime)
    return {"ok": True, "em": datetime.fromtimestamp(os.path.getmtime(nova), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "arquivo": os.path.basename(nova), "tamanho": os.path.getsize(nova)}


def estado(agora=None):
    """(status, detalhe) no formato da sondagem dos sistemas."""
    agora = agora or time.time()
    pasta = _pasta()
    local = _ler(pasta, "local") or _ultima_copia(pasta)
    drive = _ler(pasta, "drive")
    problemas, grave = [], False
    if not local:
        problemas.append("nenhum backup do banco ainda: rode python3 adminai/backup_banco.py --aplicar")
        grave = True
    elif not local.get("ok"):
        problemas.append(f"o backup local falhou: {local.get('erro') or 'sem detalhe'}")
        grave = True
    elif (_horas(local.get("em"), agora) or 0) > MAX_H:
        problemas.append(f"o backup local de hoje não rodou (o último é de {local.get('em')}): veja systemctl status urace-backup.timer")
        grave = True
    if not drive:
        problemas.append("a cópia fora da VPS (Drive, cifrada) ainda não rodou: veja systemctl status urace-backup-drive.timer")
    elif not drive.get("ok"):
        problemas.append(f"a cópia fora da VPS (Drive) falhou: {drive.get('erro') or 'sem detalhe'}")
    elif (_horas(drive.get("em"), agora) or 0) > MAX_H:
        problemas.append(f"a cópia fora da VPS (Drive) de hoje não rodou (a última é de {drive.get('em')})")
    detalhe = {"local": local, "drive": drive, "problemas": problemas}
    if grave:
        return "ERROR", {**detalhe, "motivo": problemas[0]}
    if problemas:
        return "DEGRADED", {**detalhe, "motivo": problemas[0]}
    return "CONNECTED", detalhe
