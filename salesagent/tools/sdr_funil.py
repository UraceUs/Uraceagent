#!/usr/bin/env python3
"""Confere no Kommo os funis e etapas que o SDR usa: Urace (página 1) e
Comercial (página 2), que são da equipe.

Só leitura, sempre. O SDR não cria funil nem etapa (D-09-17): se uma etapa
usada pelas regras não existir (alguém renomeou, por exemplo), ela aparece
como pendência para uma pessoa corrigir o nome no Kommo ou em
salesagent/sdr/regras.py.

Uso (no VPS, com ~/.urace/kommo.env):
    python3 salesagent/tools/sdr_funil.py
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "bridge"))

# Mesmo padrão dos outros scripts (incidente 11 do Chase): se o python do
# sistema não tem httpx, reexecuta no venv da ponte.
try:
    import httpx  # noqa: F401
except ModuleNotFoundError:
    venv = HERE.parent / "bridge" / ".venv" / "bin" / "python3"
    if venv.exists() and Path(sys.executable).resolve() != venv.resolve():
        os.execv(str(venv), [str(venv), *sys.argv])
    raise

import kommo_client as kommo  # noqa: E402
from sdr import funil, regras  # noqa: E402


def main() -> int:
    pipelines = kommo.list_pipelines()
    print(f"Funis na conta ({len(pipelines)}): " + ", ".join(p.get("name", "?") for p in pipelines))
    plano = funil.planejar(pipelines)
    print(json.dumps(plano, ensure_ascii=False, indent=2))

    if plano["funis_faltando"]:
        print("\nPENDÊNCIA: não achei " + ", ".join(plano["funis_faltando"])
              + ". Confira o nome em regras.FUNIS; o SDR não cria funil.")
        return 1
    if plano["etapas_faltando"]:
        print("\nPENDÊNCIA: etapa usada pelas regras não existe no Kommo. Corrija o nome na tela "
              "do Kommo ou em salesagent/sdr/regras.py e rode de novo; o SDR não cria etapa.")
        return 1
    if plano["etapas_duplicadas"]:
        print("\nAVISO: etapas com nome repetido — a ponte usa a primeira.")
    print(f"\nOK: {regras.FUNIS[regras.ENTRADA]} e {regras.FUNIS[regras.COMERCIAL]} têm todas as etapas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
