#!/usr/bin/env python3
"""chase_validate — a validação completa do Chase, num comando só.

Camada fina sobre as peças que já existem (não duplica lógica):

  1. chase_doctor em modo diagnóstico  (ambiente saudável?)
  2. suíte offline completa            (lógica intacta?)
  3. validate_existing_lead --lead X   (o teste REAL, com humano no circuito)

Uso (no VPS):
    python3 salesagent/tools/chase_validate.py                    # 1+2
    python3 salesagent/tools/chase_validate.py --lead 31764961    # 1+2+3
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent

# Mesmo bootstrap do chase_doctor: os testes importam a ponte, e a ponte
# vive no venv dela. Sem isto (bug pego pela extensão em 27/08), a suíte
# rodava no python do sistema e os 3 testes que importam `app` caíam com
# ModuleNotFoundError: httpx — um FAIL de ambiente disfarçado de FAIL de
# lógica, contradizendo o doctor que rodava a MESMA suíte no venv, 5/5.
_VENV = TOOLS.parent / "bridge" / ".venv" / "bin" / "python"
if _VENV.exists() and not os.environ.get("CHASE_VALIDATE_REEXEC"):
    os.environ["CHASE_VALIDATE_REEXEC"] = "1"
    os.execv(str(_VENV), [str(_VENV), str(Path(__file__).resolve()), *sys.argv[1:]])


def run(script: str, *args: str) -> int:
    return subprocess.call([sys.executable, str(TOOLS / script), *args])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lead", type=int,
                    help="roda também o teste real de continuidade neste lead")
    args = ap.parse_args()

    print("\n########## 1/3 — AMBIENTE (chase_doctor, sem fix) ##########")
    rc_doc = run("chase_doctor.py", "--no-fix",
                 *(["--lead", str(args.lead)] if args.lead else []))

    print("\n########## 2/3 — SUÍTE OFFLINE ##########")
    testes = sorted((TOOLS.parent / "tests").glob("test_*.py"))
    falhas = 0
    for t in testes:
        rc = subprocess.call([sys.executable, str(t)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"  {'PASS' if rc == 0 else 'FAIL'}  {t.name}")
        falhas += rc != 0

    if not args.lead:
        print("\n(sem --lead: o teste real com humano no circuito não rodou)")
        return 1 if (rc_doc or falhas) else 0

    print("\n########## 3/3 — TESTE REAL (lead existente, humano no circuito) ##########")
    if rc_doc or falhas:
        print("!! ambiente/suíte com falhas acima — o teste real fica mais "
              "difícil de interpretar; siga por sua conta ou corrija antes "
              "com: python3 salesagent/tools/chase_doctor.py")
    rc_real = run("validate_existing_lead.py", "--lead", str(args.lead))
    return 1 if (rc_doc or falhas or rc_real) else 0


if __name__ == "__main__":
    sys.exit(main())
