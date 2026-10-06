#!/usr/bin/env python3
"""Horário de atendimento humano (dono, 06/10/2026): segunda a sexta, das 8h às 18h, em Orlando.

Uso:
    python3 salesagent/tests/test_horario_comercial.py
"""
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
os.environ["URACE_DIR"] = tempfile.mkdtemp(prefix="urace-horario-")
sys.path.insert(0, str(HERE.parent / "bridge"))
sys.path.insert(0, str(HERE.parent.parent))

import scheduler  # noqa: E402
from salesagent.sdr import regras  # noqa: E402

NY = ZoneInfo("America/New_York")


def _ts(*a):
    return int(datetime(*a, tzinfo=NY).timestamp())


def test_segunda_a_sexta_das_8_as_18():
    assert scheduler.in_business_hours(_ts(2026, 10, 5, 8, 0))       # segunda, 8h
    assert scheduler.in_business_hours(_ts(2026, 10, 9, 17, 59))     # sexta, 17h59
    assert not scheduler.in_business_hours(_ts(2026, 10, 5, 7, 59))  # antes das 8h
    assert not scheduler.in_business_hours(_ts(2026, 10, 9, 18, 0))  # 18h já é fora
    assert not scheduler.in_business_hours(_ts(2026, 10, 10, 10, 0))  # sábado
    assert not scheduler.in_business_hours(_ts(2026, 10, 11, 10, 0))  # domingo


def test_a_regra_do_sdr_tem_o_mesmo_horario_e_ja_esta_confirmada():
    h = regras.HORARIO
    assert h["dias"] == [0, 1, 2, 3, 4] and (h["inicio"], h["fim"]) == (8, 18)
    assert h["confirmacao_pendente"] is False


if __name__ == "__main__":
    test_segunda_a_sexta_das_8_as_18()
    test_a_regra_do_sdr_tem_o_mesmo_horario_e_ja_esta_confirmada()
    print("ok")
