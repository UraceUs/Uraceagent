"""#282 (dono, 15/10): o ⓘ do security deposit — *"ao clicar com o dedo no celular ou passar o mouse em
cima diga que o valor é reembolsável 5 dias após desde que não tenha nenhum dano ao kart; danos acima do
valor do depósito podem ser cobrados adicionalmente"*.

Aqui: o texto é um só (Python, `carrinho.js`, e-mail, Stripe) e o ⓘ está na reserva e no pedido. O toque
e o mouse de verdade estão em `e2e/test_navegador.py::test_o_i_do_deposito_abre_no_toque_e_no_mouse`."""
import re
from pathlib import Path

from command_center.providers import carrinho
from command_center.tests.test_vitrine import cli  # noqa: F401
from command_center.vitrine import dica, paginas_site

STATIC = Path(__file__).resolve().parents[1] / "vitrine" / "static"


def test_o_texto_diz_o_que_o_dono_pediu():
    t = dica.DEPOSITO_INFO
    assert "5 business days after your session" in t and "no damage to the kart" in t     # #295: dias úteis
    assert "Damage above the deposit amount may be charged additionally" in t
    assert "5 dias úteis após a sessão" in dica.DEPOSITO_INFO_PT and "cobrados adicionalmente" in dica.DEPOSITO_INFO_PT


def test_o_carrinho_js_usa_o_mesmo_texto_e_liga_o_toque():
    js = (STATIC / "carrinho.js").read_text()
    assert f"'{dica.DEPOSITO_INFO}'" in js and f"'{dica.DEPOSITO_INFO_PT}'" in js
    # o toque (celular) abre e fecha; o Esc fecha
    assert "closest('.dica-botao')" in js and "aria-expanded" in js and "'Escape'" in js
    assert js.count("dicaDeposito()") >= 2, "na linha da sessão e no resumo do carrinho"


def test_o_i_tem_rotulo_alvo_de_toque_e_abre_no_mouse():
    h = dica.deposito()
    assert 'class="dica-botao"' in h and 'aria-label="About the security deposit"' in h
    assert 'role="tooltip"' in h and dica.DEPOSITO_INFO in h
    assert dica.DEPOSITO_INFO_PT in dica.deposito("pt") and "Sobre o depósito" in dica.deposito("pt")
    css = (STATIC / "site.css").read_text()
    assert re.search(r"\.dica-botao \{[^}]*width: 40px; height: 40px", css), "alvo de toque ≥ 40 px"
    assert "@media (hover: hover)" in css and ".dica:hover .dica-texto" in css


def test_a_reserva_mostra_o_deposito_com_o_i(cli):  # noqa: F811
    h = cli.get("/services/arrive-and-drive/").text
    bloco = re.search(r'<p class="agenda-deposito[^"]*"[^>]*>.*?</p>', h, re.S)
    assert bloco and "refundable security deposit" in bloco.group(0)
    assert 'class="dica-botao"' in bloco.group(0) and dica.DEPOSITO_INFO in bloco.group(0)


def test_o_pedido_mostra_o_i_e_o_stripe_e_o_email_dizem_o_mesmo():
    linha = {"deposit": 400, "kind": "sessao", "booking_id": None, "name": "4-stroke · Tue, Oct 20 · Morning",
             "variation": None, "product_slug": None, "quantity": 1, "unit_price": 719, "amount": 1119}
    h = paginas_site._pedido_linhas([linha], False, "en")
    assert "refundable security deposit" in h and 'class="dica-botao"' in h and dica.DEPOSITO_INFO in h
    assert dica.DEPOSITO_INFO_PT in paginas_site._pedido_linhas([linha], False, "pt")
    assert paginas_site._pedido_linhas([{**linha, "deposit": 0}], False, "en").count("dica-botao") == 0
    assert dica.DEPOSITO_INFO in carrinho.DEPOSITO_TXT                      # a descrição da linha no Stripe
    for fonte in (Path(carrinho.__file__).read_text(), Path(paginas_site.__file__).read_text()):
        # #295 (dono, 16/10): "business days" — um prazo só, o do contrato, em todo lugar
        assert not re.search(r"5 days after|5 dias após", fonte), "o prazo do depósito é em dias úteis"
    from command_center.providers import cobranca_agenda
    assert "5 business days" in cobranca_agenda.DESCRICAO_DEPOSITO, "a invoice do painel diz o mesmo prazo"
    assert "5 business days" in carrinho.DEPOSITO_TXT and "5 dias úteis" in dica.DEPOSITO_INFO_PT
