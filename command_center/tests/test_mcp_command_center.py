"""O servidor MCP do próprio Command Center (para um Claude de fora consultar o painel).

Dono, 21/09: a chave é para um agente — *"vai ser um Claude provavelmente"*. O que se
prova aqui é o que protege: **não existe ferramenta de escrita**, a chave vai no header e
nunca no log, e erro de credencial vira explicação, não traceback.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "adminai", "mcp"))

os.environ.setdefault("CC_API_KEY", "urk_teste0000_segredo-de-teste")
os.environ.setdefault("CC_URL", "https://painel.test")

import command_center_mcp as cc  # noqa: E402
from mcp_stdio import ErroFerramenta  # noqa: E402


class Resposta:
    def __init__(self, corpo):
        self._c = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()

    def read(self):
        return self._c

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Pedidos(list):
    """Os pedidos que saíram, mais o que o painel vai responder."""
    corpo = {"ok": True}

    def responder(self, c):
        self.corpo = c


@pytest.fixture()
def pedidos(monkeypatch):
    feitos = Pedidos()

    def falso(req, timeout=None):
        feitos.append(req)
        if isinstance(feitos.corpo, Exception):
            raise feitos.corpo
        return Resposta(feitos.corpo)
    monkeypatch.setattr(cc.urllib.request, "urlopen", falso)
    return feitos


# --------------------------------------------------------------- o que protege
def test_nenhuma_ferramenta_escreve():
    """A trava principal não é confiança no modelo: a ferramenta que não deve existir não
    é registrada, e aí não há como desobedecer."""
    nomes = set(cc.srv._ferramentas)
    assert nomes and all(n.startswith("cc_") for n in nomes)
    proibidas = ("responder", "reply", "criar", "create", "aplicar", "enviar", "send",
                 "apagar", "delete", "mudar", "atualizar", "update", "preco", "revogar")
    assert not [n for n in nomes for p in proibidas if p in n]
    # e o arquivo inteiro não sabe fazer outro verbo além de GET
    fonte = open(cc.__file__, encoding="utf-8").read()
    assert 'method="GET"' in fonte
    for verbo in ('method="POST"', 'method="PUT"', 'method="PATCH"', 'method="DELETE"'):
        assert verbo not in fonte


def test_a_chave_vai_no_header_e_a_url_e_a_do_painel(pedidos):
    pedidos.responder({"vendas": 3})
    assert cc.cc_dashboard() == {"vendas": 3}
    req = pedidos[0]
    assert req.full_url == "https://painel.test/ops/api/dashboard"
    assert req.get_header("Authorization") == "Bearer " + os.environ["CC_API_KEY"]
    assert req.get_method() == "GET"


def test_consulta_livre_nao_sai_do_painel(pedidos):
    """O escape é para caminho de dentro da API — não para o modelo apontar a chave para
    outro servidor."""
    with pytest.raises(ErroFerramenta):
        cc.cc_consultar("https://outro-lugar.example/roubar")
    with pytest.raises(ErroFerramenta):
        cc.cc_consultar("//outro-lugar.example/roubar")
    pedidos.responder([{"id": 1}])
    cc.cc_consultar("crm/board")                       # sem barra na frente também vale
    assert pedidos[-1].full_url == "https://painel.test/ops/api/crm/board"


# --------------------------------------------------------------- erros que explicam
def test_chave_recusada_vira_explicacao(pedidos):
    pedidos.responder(cc.urllib.error.HTTPError("u", 401, "Unauthorized", {}, None))
    with pytest.raises(ErroFerramenta) as e:
        cc.cc_dashboard()
    assert "revogada" in str(e.value) and "urk_" not in str(e.value)    # e sem vazar a chave


def test_sem_permissao_diz_o_que_falta(pedidos):
    import io
    pedidos.responder(cc.urllib.error.HTTPError("u", 403, "Forbidden", {},
                                                io.BytesIO(b'{"detail":"so de leitura"}')))
    with pytest.raises(ErroFerramenta) as e:
        cc.cc_dashboard()
    assert "não tem acesso" in str(e.value)


def test_painel_fora_do_ar_nao_vira_traceback(pedidos):
    pedidos.responder(cc.urllib.error.URLError("conexão recusada"))
    with pytest.raises(ErroFerramenta) as e:
        cc.cc_dashboard()
    assert "não consegui falar com o Command Center" in str(e.value)


# --------------------------------------------------------------- caminhos
def test_cada_ferramenta_bate_na_rota_certa(pedidos):
    pedidos.responder({"ok": True})
    casos = [
        (lambda: cc.cc_atencao(), "/ops/api/needs-attention"),
        (lambda: cc.cc_invoices("OPEN"), "/ops/api/invoices?status=OPEN"),
        (lambda: cc.cc_financeiro(), "/ops/api/qbo/summary"),
        (lambda: cc.cc_oportunidades(), "/ops/api/sales/board"),
        (lambda: cc.cc_clientes("maria"), "/ops/api/clients?q=maria"),
        (lambda: cc.cc_cliente(12), "/ops/api/clients/12"),
        (lambda: cc.cc_conversas(), "/ops/api/crm/inbox"),
        (lambda: cc.cc_conversa(7), "/ops/api/crm/leads/7"),
        (lambda: cc.cc_corridas(), "/ops/api/races"),
        (lambda: cc.cc_buscar("charles"), "/ops/api/search?q=charles"),
    ]
    for chamar, esperado in casos:
        chamar()
        assert pedidos[-1].full_url == "https://painel.test" + esperado


def test_auditoria_respeita_o_teto_do_painel(pedidos):
    pedidos.responder([])
    cc.cc_auditoria(9999)
    assert pedidos[-1].full_url.endswith("limit=500")
    cc.cc_auditoria(3)
    assert pedidos[-1].full_url.endswith("limit=3")
    cc.cc_auditoria(None)                              # não dizer nada é o padrão do painel
    assert pedidos[-1].full_url.endswith("limit=100")


def test_parametro_vazio_nao_vira_lixo_na_url(pedidos):
    pedidos.responder([])
    cc.cc_clientes(None)
    assert pedidos[-1].full_url == "https://painel.test/ops/api/clients"
