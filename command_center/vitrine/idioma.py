"""Português e inglês nas páginas da compra do site (#248).

Dono, 14/10: *"mesmo jeito do command center, switch para mudar de português para inglês"*.

O site novo é em inglês. A página do pedido, o carrinho e as páginas de obrigado e de cancelado ganham
a chave EN/PT (as bandeiras, como no painel). A escolha fica num cookie (`urace_lang`, um ano) e o
pedido guarda o idioma em que a pessoa comprou: os e-mails do pagamento saem nele.

As páginas que mudam de idioma são de cada pessoa (`no-store`), então o cookie não mistura cache.
"""
import re
from html import escape as e

COOKIE = "urace_lang"
IDIOMAS = ("en", "pt")
UM_ANO = 365 * 24 * 3600
# só volta para as páginas que têm a chave (nada de endereço de fora)
VOLTA_OK = re.compile(r"^/(cart/(thanks/)?|store/(thanks|cancelled)/|order/[0-9]+-[A-Za-z0-9_-]{27}/(cart/)?)(\?[A-Za-z0-9_=&%.-]{0,300})?$")


def norma(v):
    return v if v in IDIOMAS else "en"


def de_request(request):
    return norma((request.cookies.get(COOKIE) or "").strip().lower())


def t(lang, en, pt):
    """O texto no idioma: `t(lang, "Your cart", "Seu carrinho")`."""
    return pt if lang == "pt" else en


def html_lang(lang):
    return "pt-BR" if lang == "pt" else "en"


def volta_ok(caminho):
    return bool(caminho) and bool(VOLTA_OK.match(caminho))


def chave(lang, volta):
    """O botão EN/PT: um formulário (funciona sem JavaScript) que grava a escolha e volta para a página."""
    if not volta_ok(volta):
        return ""
    def b(cod, bandeira, nome):
        atual = lang == cod
        return (f'<button class="idioma-btn{" on" if atual else ""}" type="submit" name="lang" value="{cod}" '
                f'aria-pressed="{"true" if atual else "false"}" lang="{html_lang(cod)}">'
                f'<span aria-hidden="true">{bandeira}</span> {nome}</button>')
    rotulo = t(lang, "Language", "Idioma")
    return (f'<form class="idioma" method="post" action="/language/" aria-label="{rotulo}">'
            f'<input type="hidden" name="volta" value="{e(volta)}">'
            + b("en", "🇺🇸", "English") + b("pt", "🇧🇷", "Português") + "</form>")


# ------------------------------------------------------------------ as mensagens do servidor (carrinho e checkout)
MENSAGENS_PT = {
    # #305: o cadastro no carrinho (as mensagens do `portal.criar_conta` e da senha)
    "Fill in your details to continue.": "Preencha os seus dados para continuar.",
    "Use a password with at least 8 characters.": "Use uma senha com pelo menos 8 caracteres.",
    "The passwords don't match.": "As senhas não são iguais.",
    "Too many sign-ups from this connection. Try again later.": "Muitos cadastros desta conexão. Tente mais tarde.",
    "You need to accept the terms to create an account.": "Para continuar, aceite os termos e a política de privacidade.",
    "Enter a valid email address.": "Digite um e-mail válido.",
    "Enter your full name (first and last).": "Digite o seu nome completo (nome e sobrenome).",
    "Enter the driver's full name (first and last).": "Digite o nome completo do piloto (nome e sobrenome).",
    "The account holder must be 18 or older. A parent or guardian can create the account and add the young driver to it.":
        "O titular da conta precisa ter 18 anos ou mais. O pai, a mãe ou o responsável cria a conta e põe o piloto jovem nela.",
    "An account with this email already exists. Sign in instead.": "Já existe uma conta com este e-mail. Entre com ela.",
    "Enter a valid phone number, with area code.": "Digite um telefone válido, com DDD.",
    "Enter a valid phone number for your country.": "Digite um telefone válido para o seu país.",
    "Country code: use + and up to 4 digits, like +1 or +55.": "Código do país: use + e até 4 dígitos, como +1 ou +55.",
    "Choose your country.": "Escolha o seu país.",
    "State: use the 2-letter code, like FL.": "Estado: use a sigla de 2 letras, como FL.",
    "ZIP code: use 5 digits (or 5+4).": "ZIP: use 5 dígitos (ou 5+4).",
    "Postal code: use letters, numbers, spaces or hyphens.": "Código postal: use letras, números, espaço ou hífen.",
    "Date of birth: use a valid date.": "Data de nascimento: use uma data válida.",
    "Date of birth can't be in the future.": "A data de nascimento não pode estar no futuro.",
    "Product not found": "Produto não encontrado",
    "Product not found.": "Produto não encontrado.",
    "Session": "Sessão",
    "This product is no longer in the store. Remove it from the cart.": "Este produto não está mais na loja. Tire-o do carrinho.",
    "Please choose an option on the product page.": "Escolha uma opção na página do produto.",
    "Please choose an option.": "Escolha uma opção.",
    "This item can't be bought online right now. Send us an order request instead.":
        "Este item não pode ser comprado online agora. Mande um pedido para a equipe.",
    "This session is no longer offered. Remove it and pick another one.": "Esta sessão não é mais oferecida. Tire-a e escolha outra.",
    "Choose a valid date.": "Escolha uma data válida.",
    "Choose morning or afternoon.": "Escolha manhã ou tarde.",
    "This time is no longer available. Please pick another one.": "Este horário não está mais disponível. Escolha outro.",
    "Choose the driver for this session.": "Escolha o piloto desta sessão.",
    "Please complete the account holder details (Account) before booking.":
        "Complete os dados do responsável (Account) antes de reservar.",
    "Your cart is empty.": "O seu carrinho está vazio.",
    "Please sign in or create your URACE account to buy.": "Entre ou crie a sua conta URACE para comprar.",
    "Online payment isn't available right now. Please call or WhatsApp us.":
        "O pagamento online não está disponível agora. Ligue ou mande WhatsApp.",
    "Security check failed. Reload the page and try again.": "A verificação de segurança falhou. Recarregue a página e tente de novo.",
    "Too many requests in a row. Please try again in a few minutes.": "Muitos pedidos seguidos. Tente de novo em alguns minutos.",
    "We couldn’t open the secure checkout just now. Please try again in a minute.":
        "Não conseguimos abrir o checkout seguro agora. Tente de novo em um minuto.",
}
PADROES_PT = (
    (re.compile(r"^Please fill in: (.+)\.$"), "Preencha: {0}."),                      # #305: o cadastro no carrinho
    (re.compile(r"^(.+) already has a session at this time\.$"), "{0} já tem uma sessão neste horário."),
    (re.compile(r"^(.+) is already in this cart at this time\.$"), "{0} já está neste carrinho neste horário."),
    (re.compile(r"^Up to (\d+) items per order\.$"), "Até {0} itens por pedido."),
    (re.compile(r"^Please complete (.+)'s profile \(measurements and karting experience\) before booking\.$"),
     "Complete o perfil de {0} (medidas e experiência no kart) antes de reservar."),
    (re.compile(r"^(.+)'s measurements are more than (\d+) days old\. Please review and save them in Drivers before booking\.$"),
     "As medidas de {0} têm mais de {1} dias. Revise e salve em Drivers antes de reservar."),
)


def traduzir(msg, lang):
    """A mensagem do servidor no idioma da pessoa (o código fala inglês; o português vem daqui)."""
    if lang != "pt" or not msg:
        return msg
    if msg in MENSAGENS_PT:
        return MENSAGENS_PT[msg]
    for rx, modelo in PADROES_PT:
        m = rx.match(msg)
        if m:
            return modelo.format(*m.groups())
    return msg
