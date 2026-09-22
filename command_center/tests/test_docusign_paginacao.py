"""O DocuSign devolve 100 envelopes por vez — e a sincronia pedia só a primeira página.

Dono, 22/09: abriu o painel e viu a waiver da Nadine Kozora Garcia como "enviada, não
assinada". No DocuSign ela está **Completed** desde 17/09/2026 16:21 (envelope
1ceee462-2383-8726-825b-424ddf410785). Não era erro de leitura: o envelope simplesmente
não vinha mais na resposta, e o espelho ficou congelado no status da última vez que ele
coube nos 100 primeiros.
"""
import os
import sys
import tempfile
import urllib.parse

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "adminai", "mcp"))
os.environ.setdefault("URACE_ENV", "/nao/existe")
import docusign_mcp as D  # noqa: E402


@pytest.fixture()
def conta_falsa(monkeypatch):
    """Uma conta com `total` envelopes, servidos de 100 em 100."""
    def fabricar(total, com_email=None):
        pedidos = []

        def req(caminho, *a, **k):
            pedidos.append(caminho)
            q = dict(urllib.parse.parse_qsl(caminho.split("?", 1)[1]))
            ini = int(q.get("start_position", 0))
            n = min(D.PAGINA, max(0, total - ini))
            envs = []
            for i in range(n):
                pos = ini + i
                e = {"envelopeId": f"env-{pos}", "status": "completed", "emailSubject": "Waiver"}
                if com_email and pos == total - 1:      # o alvo é o ÚLTIMO: só pagina o alcança
                    e["recipients"] = {"signers": [{"name": "Nadine Kozora Garcia", "email": com_email,
                                                    "status": "completed"}]}
                envs.append(e)
            return {"totalSetSize": str(total), "envelopes": envs}
        monkeypatch.setattr(D, "_req", req)
        monkeypatch.setattr(D, "_eh_demo", lambda: False)
        return pedidos
    return fabricar


def test_pagina_ate_o_fim(conta_falsa):
    pedidos = conta_falsa(237)
    envs, total = D._listar_envelopes({"from_date": "x", "include": "recipients"})
    assert (len(envs), total) == (237, 237)
    assert len(pedidos) == 3, "três páginas de 100"


def test_uma_pagina_so_nao_pede_a_segunda(conta_falsa):
    pedidos = conta_falsa(42)
    envs, total = D._listar_envelopes({"from_date": "x"})
    assert (len(envs), total) == (42, 42) and len(pedidos) == 1


def test_envelopes_diz_se_veio_completo(conta_falsa):
    conta_falsa(150)
    r = D.docusign_envelopes("completed", desde_dias=365)
    assert r["total"] == 150 and r["total_na_conta"] == 150 and r["completo"] is True


def test_o_envelope_da_nadine_e_alcancado(conta_falsa):
    """Envelope na posição 236 de 237: com uma página só, ele nunca voltava."""
    conta_falsa(237, com_email="nkozora1@gmail.com")
    achados = D._envelopes_de("nkozora1@gmail.com", desde_dias=365)
    assert len(achados) == 1 and achados[0]["envelopeId"] == "env-236"
    assert achados[0]["recipients"]["signers"][0]["status"] == "completed"


def test_teto_impede_varredura_infinita(conta_falsa):
    conta_falsa(100000)
    envs, _total = D._listar_envelopes({"from_date": "x"}, maximo=250)
    assert len(envs) == 250
