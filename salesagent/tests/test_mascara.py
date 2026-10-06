#!/usr/bin/env python3
"""A auditoria da ponte não guarda segredo nem telefone.

Contexto (28/09): as linhas hook_raw traziam o JWT do Salesbot, a URL de
continuação e o telefone do contato em texto aberto. state.log agora
mascara tudo antes de gravar, e tools/mascarar_auditoria.py limpa o antigo.

Uso:
    python3 salesagent/tests/test_mascara.py
"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ["URACE_DIR"] = tempfile.mkdtemp(prefix="urace-mascara-")
sys.path.insert(0, str(HERE.parent / "bridge"))

import state  # noqa: E402

falhas = []


def check(rotulo, cond, detalhe=""):
    print(("  PASS  " if cond else "  FAIL  ") + rotulo + ("" if cond else f"  -> {detalhe}"))
    if not cond:
        falhas.append(rotulo)


JWT = "eyJhbGciOiJIUzI1NiJ9.eyJsZWFkIjoxMjM0NX0.c2lnbmF0dXJlLXRlc3Rl"
FORM = ("ct=application/x-www-form-urlencoded :: token=" + JWT +
        "&data%5Bphone%5D=%2B14075551234&data%5Bmessage%5D=quanto+custa"
        "&return_url=https%3A%2F%2Furace.kommo.com%2Fapi%2Fv4%2Fbots%2F9%2Fcontinue%2Fabc"
        "&leads%5Badd%5D%5B0%5D%5Bid%5D=31764961")
JSON = ('{"token": "' + JWT + '", "contact": {"phone": "+14075551234", "email": "a@b.com"},'
        ' "text": "how much is a day?", "lead_id": 31764961}')


def rodar() -> list[str]:
    falhas.clear()
    m = state.mascarar(FORM)
    check("form: JWT do bot some", JWT not in m and "token=[oculto]" in m, m)
    check("form: telefone some", "14075551234" not in m, m)
    check("form: URL de continuação some", "continue" not in m and "return_url=[oculto]" in m, m)
    check("form: texto da mensagem e id do lead continuam", "quanto+custa" in m and "31764961" in m, m)

    m = state.mascarar(JSON)
    check("json: token, telefone e e-mail somem",
          JWT not in m and "14075551234" not in m and "a@b.com" not in m, m)
    check("json: texto e lead_id continuam", "how much is a day?" in m and "31764961" in m, m)

    check("JWT solto em texto livre some", JWT not in state.mascarar(f"bot token {JWT} inválido"))
    check("?key= numa URL some", "segredo123" not in state.mascarar("https://x/kommo/hook?key=segredo123"))
    check("texto comum não muda", state.mascarar("lead 31764961 pediu preço às 1730000000") ==
          "lead 31764961 pediu preço às 1730000000")

    state.log("hook_raw", None, FORM)
    with state.db() as conn:
        gravado = conn.execute("SELECT detail FROM audit ORDER BY id DESC LIMIT 1").fetchone()[0]
    check("state.log grava mascarado", JWT not in gravado and "14075551234" not in gravado, gravado)

    # Linha antiga, gravada antes da máscara: o script de limpeza resolve.
    with state.db() as conn:
        conn.execute("INSERT INTO audit (ts, lead_id, kind, detail) VALUES (1, NULL, 'hook_raw', ?)", (FORM,))
    sys.path.insert(0, str(HERE.parent / "tools"))
    import mascarar_auditoria
    mascarar_auditoria.main(["--aplicar"])
    with state.db() as conn:
        restos = [d for (d,) in conn.execute("SELECT detail FROM audit") if JWT in d or "14075551234" in d]
    check("mascarar_auditoria limpa as linhas antigas", restos == [], str(restos))
    return list(falhas)


def test_mascara():
    assert rodar() == []


if __name__ == "__main__":
    erros = rodar()
    print("\nPASSOU - a auditoria não guarda token, chave, URL de continuação nem telefone"
          if not erros else f"\nFALHOU - {len(erros)} verificação(ões)")
    sys.exit(1 if erros else 0)
