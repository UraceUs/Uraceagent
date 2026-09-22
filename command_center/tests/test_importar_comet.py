"""A educação do importador, provada sem fazer uma requisição.

O que estes testes garantem é o que mantém a ferramenta podendo rodar amanhã: obedecer
o robots.txt, não rebuscar o que já se tem, e não marcar catálogo como sumido depois de
uma varredura parcial.
"""
import importlib
import json
import types
import os
import sys
import tempfile

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

importar_comet = importlib.import_module("adminai.importar_comet")


class BuscaFalsa(importar_comet.Educado):
    """Mesma classe, sem rede: `_baixar` devolve o que o teste mandar."""

    def __init__(self, paginas, robots="User-agent: *\nAllow: /\n", **kw):
        kw.setdefault("cache", tempfile.mkdtemp(prefix="cache-comet-"))
        kw.setdefault("pausa", 0)
        super().__init__(site="https://exemplo.test", **kw)
        self.paginas, self.robots_txt = paginas, robots
        self.pedidos = []

    def _baixar(self, url, respeitar=True):
        if url.endswith("/robots.txt"):
            return self.robots_txt.encode()
        if respeitar and not self.permitido(url):
            raise PermissionError(url)
        self.pedidos.append(url)
        if url not in self.paginas:
            import urllib.error
            raise urllib.error.HTTPError(url, 404, "nao", {}, None)
        return self.paginas[url]


def _json(obj):
    return json.dumps(obj).encode()


PROD = {"products": [{"id": 1, "title": "Pneu", "handle": "pneu", "variants": [
    {"id": 11, "sku": "A-1", "title": "Default Title", "price": "10.00", "available": True}]}]}


def test_robots_que_proibe_e_obedecido():
    """Caminho proibido não é buscado. Ponto — não há negociação aqui."""
    bus = BuscaFalsa({}, robots="User-agent: *\nDisallow: /\n")
    assert bus.permitido("https://exemplo.test/products.json") is False
    assert importar_comet.pelo_json_da_loja(bus) == ([], False)
    assert bus.pedidos == [], "não bateu no site nenhuma vez"


def test_sem_robots_legivel_a_varredura_para():
    """Sem saber o que é permitido, o respeito manda parar, não seguir em frente."""
    class SemRobots(BuscaFalsa):
        def _baixar(self, url, respeitar=True):
            if url.endswith("/robots.txt"):
                raise OSError("timeout")
            return b"{}"
    with pytest.raises(SystemExit) as e:
        SemRobots({}).permitido("https://exemplo.test/x")
    assert "robots.txt" in str(e.value)


def test_o_que_ja_foi_baixado_nao_e_buscado_de_novo():
    """Repetir a importação não pode voltar a bater no site deles."""
    paginas = {"https://exemplo.test/products.json?limit=250&page=1": _json(PROD),
               "https://exemplo.test/products.json?limit=250&page=2": _json({"products": []})}
    bus = BuscaFalsa(paginas)
    importar_comet.pelo_json_da_loja(bus)
    assert bus.buscadas == 2 and bus.do_cache == 0
    bus2 = BuscaFalsa(paginas, cache=bus.cache)
    importar_comet.pelo_json_da_loja(bus2)
    assert bus2.buscadas == 0 and bus2.do_cache == 2, "tudo veio do disco"


def test_a_paginacao_para_quando_a_loja_diz_que_acabou():
    paginas = {"https://exemplo.test/products.json?limit=250&page=1": _json(PROD),
               "https://exemplo.test/products.json?limit=250&page=2": _json({"products": []})}
    bus = BuscaFalsa(paginas)
    produtos, completa = importar_comet.pelo_json_da_loja(bus)
    assert [p["sku"] for p in produtos] == ["A-1"]
    assert completa is True, "a loja disse que acabou: isso é varredura completa"


def test_site_que_nao_e_shopify_apenas_devolve_vazio():
    """Cair para a estratégia seguinte é normal, não é erro."""
    bus = BuscaFalsa({})
    assert importar_comet.pelo_json_da_loja(bus) == ([], False), \
        "depois de um erro nunca se alega completude"


def test_completo_com_limite_e_recusado(monkeypatch, capsys):
    """--completo depois de --limite marcaria como sumido tudo que o limite cortou."""
    monkeypatch.setattr(sys, "argv", ["x", "--aplicar", "--completo", "--limite", "10"])
    assert importar_comet.main() == 2
    assert "sumido" in capsys.readouterr().out


def test_o_agente_se_identifica():
    """O site tem direito de saber quem está batendo na porta."""
    assert "URACE" in importar_comet.AGENTE


# ---------------------------------------------------- o caminho sem rede: export
def test_importa_de_csv_do_fornecedor(tmp_path):
    """É assim que isto roda numa máquina sem acesso ao site — e é o que o dono pode
    pedir ao fornecedor hoje mesmo."""
    f = tmp_path / "comet.csv"
    f.write_text("SKU,Name,Price,Brand\nA-1,Pneu MG,$129.95,MG\nB-2,Pistão,89,IAME\n")
    p = importar_comet.de_arquivo(str(f))
    assert [x["sku"] for x in p] == ["A-1", "B-2"]
    assert p[0]["price"] == 129.95 and p[0]["brand"] == "MG"


def test_importa_de_json_do_shopify(tmp_path):
    f = tmp_path / "comet.json"
    f.write_text(json.dumps(PROD))
    assert [x["sku"] for x in importar_comet.de_arquivo(str(f))] == ["A-1"]


def test_csv_com_cabecalho_em_outra_lingua_ainda_e_lido(tmp_path):
    """Export de fornecedor raramente vem com o cabeçalho que a gente esperava."""
    f = tmp_path / "c.csv"
    f.write_text("Item,Description,MSRP\nX-9,Corrente 219,45.50\n")
    p = importar_comet.de_arquivo(str(f))
    assert p[0]["sku"] == "X-9" and p[0]["name"] == "Corrente 219" and p[0]["price"] == 45.50


# ------------------------------------- o defeito que a pergunta da extensão descobriu
def _pagina(ids):
    return _json({"products": [
        {"id": i, "title": f"P{i}", "handle": f"p{i}",
         "variants": [{"id": i * 10, "sku": f"SKU{i}", "title": "Default Title",
                       "price": "10.00", "available": True}]} for i in ids]})


def test_loja_que_ignora_page_nao_vira_400_batidas_no_site():
    """`?page=` é obsoleto no /products.json público e várias lojas devolvem a página 1
    de novo. Sem detectar, o laço buscaria a MESMA página 400 vezes — e ninguém veria,
    porque o SKU repetido é descartado no fim. O site deles veria."""
    class Teimosa(BuscaFalsa):
        def _baixar(self, url, respeitar=True):
            if url.endswith("/robots.txt"):
                return self.robots_txt.encode()
            self.pedidos.append(url)
            return _pagina([1, 2, 3])          # sempre a mesma, aconteça o que acontecer
    bus = Teimosa({})
    produtos, completa = importar_comet.pelo_json_da_loja(bus)
    assert len(bus.pedidos) == 2, "detecta na segunda página e para"
    assert [p["sku"] for p in produtos] == ["SKU1", "SKU2", "SKU3"]
    assert completa is False, "catálogo assim é parcial, e tem de se saber disso"


def test_paginacao_de_verdade_segue_ate_a_loja_dizer_que_acabou():
    paginas = {
        "https://exemplo.test/products.json?limit=250&page=1": _pagina([1, 2]),
        "https://exemplo.test/products.json?limit=250&page=2": _pagina([3, 4]),
        "https://exemplo.test/products.json?limit=250&page=3": _json({"products": []}),
    }
    produtos, completa = importar_comet.pelo_json_da_loja(BuscaFalsa(paginas))
    assert [p["sku"] for p in produtos] == ["SKU1", "SKU2", "SKU3", "SKU4"]
    assert completa is True


def test_limite_deixa_claro_que_a_varredura_e_parcial():
    """A prova curta é parcial DE PROPÓSITO — e o programa tem de saber disso, senão
    `--completo` depois marcaria o resto do catálogo como sumido."""
    paginas = {"https://exemplo.test/products.json?limit=250&page=1": _pagina([1, 2, 3]),
               "https://exemplo.test/products.json?limit=250&page=2": _pagina([4, 5])}
    produtos, completa = importar_comet.pelo_json_da_loja(BuscaFalsa(paginas), limite=2)
    assert len(produtos) == 3 and completa is False


def test_completo_e_recusado_depois_de_varredura_parcial(monkeypatch, capsys):
    """A trava de verdade: numa base já carregada, marcar sumido depois de uma varredura
    truncada esconderia milhares de peças de uma vez."""
    def varredura_truncada(bus, limite=None):
        return [{"sku": "A-1", "name": "Pneu"}], False
    monkeypatch.setattr(importar_comet, "pelo_json_da_loja", varredura_truncada)
    monkeypatch.setattr(importar_comet, "Educado",
                        lambda **kw: types.SimpleNamespace(buscadas=0, do_cache=0))
    monkeypatch.setattr(sys, "argv", ["x", "--aplicar", "--completo"])
    assert importar_comet.main() == 2
    saida = capsys.readouterr().out
    assert "RECUSADO" in saida and "PARCIAL" in saida


def test_completo_passa_quando_a_varredura_terminou(monkeypatch, capsys, tmp_path):
    """O contraste que prova que a trava não é só um 'não' permanente."""
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setattr(importar_comet, "pelo_json_da_loja",
                        lambda bus, limite=None: ([{"sku": "A-1", "name": "Pneu"}], True))
    monkeypatch.setattr(importar_comet, "Educado",
                        lambda **kw: types.SimpleNamespace(buscadas=0, do_cache=0))
    monkeypatch.setattr(sys, "argv", ["x", "--aplicar", "--completo"])
    assert importar_comet.main() == 0
    assert "GRAVADO" in capsys.readouterr().out


def test_export_de_arquivo_conta_como_completo(monkeypatch, capsys, tmp_path):
    """Export é o catálogo inteiro por definição — não faz sentido chamá-lo de parcial."""
    f = tmp_path / "c.csv"
    f.write_text("SKU,Name\nA-1,Pneu\n")
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setattr(sys, "argv", ["x", "--arquivo", str(f), "--aplicar", "--completo"])
    assert importar_comet.main() == 0
    assert "COMPLETA" in capsys.readouterr().out
