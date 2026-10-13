#!/usr/bin/env python3
"""O log de acesso do uvicorn não guarda a chave do webhook nem telefone.

Contexto (13/10): o journal da sales-bridge tinha a KOMMO_HOOK_KEY em texto
puro, porque o uvicorn registra a URL completa de POST /kommo/eventos?key=...
state.instalar_mascara_nos_logs() põe um filtro nos loggers do uvicorn.

Uso:
    python3 salesagent/tests/test_log_mascara.py
"""
import io
import logging
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ["URACE_DIR"] = tempfile.mkdtemp(prefix="urace-logmascara-")
sys.path.insert(0, str(HERE.parent / "bridge"))

import state  # noqa: E402

falhas = []


def check(rotulo, cond, detalhe=""):
    print(("  PASS  " if cond else "  FAIL  ") + rotulo + ("" if cond else f"  -> {detalhe}"))
    if not cond:
        falhas.append(rotulo)


def _logger_capturado(nome):
    lg = logging.getLogger(nome)
    lg.handlers.clear(); lg.propagate = False; lg.setLevel(logging.INFO)
    buf = io.StringIO()
    h = logging.StreamHandler(buf); h.setFormatter(logging.Formatter("%(message)s"))
    lg.addHandler(h)
    return lg, buf


def rodar() -> list[str]:
    falhas.clear()
    state.instalar_mascara_nos_logs()
    state.instalar_mascara_nos_logs()
    check("filtro instalado uma vez só", sum(isinstance(f, state._MascaraDeLog) for f in logging.getLogger("uvicorn.access").filters) == 1)

    lg, buf = _logger_capturado("uvicorn.access")
    # a linha exata que o uvicorn grava: '%s - "%s %s HTTP/%s" %d'
    lg.info('%s - "%s %s HTTP/%s" %d', "127.0.0.1:5000", "POST", "/kommo/eventos?key=chave-secreta-123&x=1", "1.1", 200)
    saida = buf.getvalue()
    check("a chave do webhook não aparece", "chave-secreta-123" not in saida, saida)
    check("a rota continua legível", "/kommo/eventos?key=[oculto]&x=1" in saida, saida)
    check("método e status continuam", 'POST' in saida and saida.strip().endswith("200"), saida)

    lg2, buf2 = _logger_capturado("uvicorn.error")
    lg2.error("falha em https://urace.kommo.com/api/v4/leads/1?token=eyJhbGciOiJIUzI1NiJ9.eyJsZWFkIjoxfQ.YXNzaW5hdHVyYQ phone=+14075551234")
    s2 = buf2.getvalue()
    check("JWT e telefone saem do log de erro", "eyJhbGci" not in s2 and "+14075551234" not in s2, s2)

    lg3, buf3 = _logger_capturado("outro.logger")
    lg3.info("key=aberta-por-design")
    check("outros loggers não são tocados", "aberta-por-design" in buf3.getvalue())
    return list(falhas)


def test_log_mascara():
    assert rodar() == []


def main(argv=None) -> int:
    f = rodar()
    print("\nRESULTADO:", "PASSOU" if not f else f"FALHOU ({len(f)})")
    return 1 if f else 0


if __name__ == "__main__":
    sys.exit(main())
