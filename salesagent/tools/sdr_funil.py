#!/usr/bin/env python3
"""Confere (e, com --aplicar, cria) o "Novo funil" do SDR no Kommo.

Sem --aplicar não escreve nada: lista os funis da conta e diz o que falta.
Com --aplicar cria o funil inteiro SE ele não existir. Etapa faltando num
funil que já existe NUNCA é criada por aqui — aparece como pendência para
uma pessoa corrigir (os funis são da equipe; D-09-17).

A extensão também pode criar o funil pela tela (docs/extensao/PROMPT-SDR-KOMMO.md);
o resultado é o mesmo: a ponte acha o funil e as etapas pelo NOME.

Uso (no VPS, com ~/.urace/kommo.env):
    python3 salesagent/tools/sdr_funil.py              # plano, só leitura
    python3 salesagent/tools/sdr_funil.py --aplicar    # cria se faltar
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
    aplicar = "--aplicar" in sys.argv
    pipelines = kommo.list_pipelines()
    print(f"Funis na conta ({len(pipelines)}): " + ", ".join(p.get("name", "?") for p in pipelines))
    plano = funil.planejar(pipelines)
    print(json.dumps(plano, ensure_ascii=False, indent=2))

    if plano["criar_funil"]:
        if not aplicar:
            print(f"\nFalta o '{regras.NOVO_FUNIL}'. Nada foi alterado; rode com --aplicar para criar.")
            return 0
        maior = max((int(p.get("sort") or 0) for p in pipelines), default=0)
        kommo.create_pipelines(funil.corpo_criacao(sort=maior + 10))
        novo = funil.planejar(kommo.list_pipelines())
        print("\nCriado. Conferência depois de criar:")
        print(json.dumps(novo, ensure_ascii=False, indent=2))
        return 0 if novo["ok"] else 1

    if plano["etapas_faltando"]:
        print("\nPENDÊNCIA: o Novo funil existe mas faltam etapas. Não crio etapa em funil "
              "existente — corrija na tela do Kommo com o nome exato e rode de novo.")
        return 1
    if plano["incoming_ligado"]:
        print("\nAVISO: o Novo funil está com 'Incoming leads' ligado. Conversa nova fica "
              "presa ali e a ponte não consegue mover. Desligue na configuração do funil.")
    if plano["etapas_duplicadas"]:
        print("\nAVISO: etapas com nome repetido — a ponte usa a primeira.")
    print("\nOK: o Novo funil tem todas as etapas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
