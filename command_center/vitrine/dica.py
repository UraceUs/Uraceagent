"""#282 (dono, 15/10): o ⓘ do security deposit — *"ao clicar com o dedo no celular ou passar o mouse em
cima diga que o valor é reembolsável 5 dias após desde que não tenha nenhum dano ao kart; danos acima
do valor do depósito podem ser cobrados adicionalmente"*.

Um texto só para o site inteiro: a reserva, o carrinho (que o desenha em `carrinho.js`, com o mesmo
texto — `test_dica_do_deposito.py` confere), a página do pedido, o e-mail e o Stripe. O botão abre
no toque (o `carrinho.js`, que roda em toda página pública, liga o toque) e no mouse/teclado pelo CSS."""
from html import escape as e

DEPOSITO_INFO = ("Refundable within 5 days after your session, as long as there is no damage to the kart. "
                 "Damage above the deposit amount may be charged additionally.")
DEPOSITO_INFO_PT = ("Reembolsável em até 5 dias após a sessão, desde que não haja nenhum dano ao kart. "
                    "Danos acima do valor do depósito podem ser cobrados adicionalmente.")
ROTULO = "About the security deposit"
ROTULO_PT = "Sobre o depósito de segurança"

ICONE = ('<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">'
         '<circle cx="12" cy="12" r="9.5" fill="none" stroke="currentColor" stroke-width="2"/>'
         '<path d="M12 11v6M12 7.6v.2" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>')


def deposito(lang="en"):
    """O ⓘ com o texto do depósito, pronto para pôr ao lado do valor."""
    pt = lang == "pt"
    texto, rotulo = (DEPOSITO_INFO_PT, ROTULO_PT) if pt else (DEPOSITO_INFO, ROTULO)
    return (f'<span class="dica"><button type="button" class="dica-botao" aria-expanded="false" aria-label="{e(rotulo)}">'
            f'{ICONE}</button><span class="dica-texto" role="tooltip">{e(texto)}</span></span>')
