"""O gerador de filtros nativos do Gmail (adminai/gerar_filtros_gmail.py).

Dono, 14/09: *"identifique as keywords de cada e-mail e coloque nativamente neles
os marcadores"*. A parte que decide — quais remetentes viram regra — é pura e
testável sem tocar no Gmail. É ela que impede o erro que importa: dar a um
marcador um remetente que na verdade pertence a outro.
"""
import importlib.util
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "adminai", "mcp"))
_spec = importlib.util.spec_from_file_location("gerar_filtros_gmail",
                                               os.path.join(RAIZ, "adminai", "gerar_filtros_gmail.py"))
g = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(g)


@pytest.mark.parametrize("bruto,esperado", [
    ("Amazon.com <shipment-tracking@amazon.com>", "shipment-tracking@amazon.com"),
    ("MCINFO@UPS.COM", "mcinfo@ups.com"),
    ("sem endereço nenhum", ""),
    ("", ""),
])
def test_endereco(bruto, esperado):
    assert g._endereco(bruto) == esperado


def test_remetente_dominante_vira_regra_e_o_ambiguo_nao():
    por_remetente = {
        "mcinfo@ups.com": {"Shipping Status": 9},                       # 100% -> regra
        "service@paypal.com": {"Finances/Receipt": 7, "Banks/PayPal": 1},  # 87% -> regra
        "contato@aleatorio.com": {"Suppliers": 1},                      # 1 msg -> sem evidência
        "meio@a@meio.com": {"Finances": 5, "Suppliers": 5},             # 50/50 -> nenhum
    }
    r = g.regras({k: __import__("collections").Counter(v) for k, v in por_remetente.items()},
                 share=0.6, minimo=3)
    assert [e for e, _n, _t in r["Shipping Status"]] == ["mcinfo@ups.com"]
    assert [e for e, _n, _t in r["Finances/Receipt"]] == ["service@paypal.com"]
    assert "Banks/PayPal" not in r          # 1 de 8 nao sustenta
    assert "Suppliers" not in r             # nem 1 mensagem, nem maioria


def test_xml_agrupa_por_marcador_e_so_arquiva_wnews():
    r = {"wNews": [("promo@loja.com", 9, 9)],
         "Shipping Status": [("mcinfo@ups.com", 9, 9), ("tracking@shipstation.com", 4, 4)]}
    x = g.xml(r, "urace")
    assert x.startswith("<?xml version='1.0' encoding='UTF-8'?>")
    assert x.count("<entry>") == 2                                   # um filtro por marcador
    assert 'value="mcinfo@ups.com OR tracking@shipstation.com"' in x  # remetentes no mesmo filtro
    assert x.count("shouldArchive") == 1                             # so a propaganda sai da inbox
    assert "shouldArchive" in x.split("wNews")[1].split("</entry>")[0] or \
           "shouldArchive" in x.split("<entry>")[1]


def test_relatorio_marca_o_que_ficou_sem_regra_e_o_que_nao_e_do_manual():
    r = {"wNews": [("promo@loja.com", 9, 9)]}
    md = g.relatorio(r, ["wNews", "Suppliers"], ["wNews", "Suppliers", "Intruso/Novo"],
                     "urace", 0.6, 3)
    assert "marcadores com filtro: **1**" in md
    assert "Sem remetente estável" in md and "`Suppliers`" in md
    assert "NÃO estão no manual" in md and "`Intruso/Novo`" in md


def test_nao_usa_dominio_pessoal_como_regra():
    """gmail.com/hotmail e afins pegariam a caixa inteira — ficam de fora na amostra."""
    assert "gmail.com" in g.DOMINIOS_PROIBIDOS and "outlook.com" in g.DOMINIOS_PROIBIDOS


def test_abre_a_caixa_carregando_env_E_tokens(monkeypatch):
    """O bug de 14/09: o script carregava o env e esquecia os tokens. O Gmail
    respondia "conta não configurada. Disponíveis: []", que parece falta de
    credencial e não é — o token estava lá, ninguém tinha lido."""
    chamadas = []
    falso = type("M", (), {
        "_carregar_env": staticmethod(lambda: chamadas.append("env")),
        "_carregar_contas": staticmethod(lambda: chamadas.append("contas")),
        "_contas": {"urace": {}},
        "_sem_token": {"support": "/home/ubuntu/.urace/google-token-support.json"},
        "_mapa_labels": staticmethod(lambda c: {"wNews": "Label_1"}),
    })
    monkeypatch.setattr(g, "gmail_mcp", falso)
    assert g.marcadores_da_caixa("urace") == {"wNews": "Label_1"}
    assert chamadas == ["env", "contas"]
    # caixa sem token: erro que diz o que fazer, não stack trace
    with pytest.raises(SystemExit) as ex:
        g.marcadores_da_caixa("support")
    assert "google_auth.py --conta support" in str(ex.value)
