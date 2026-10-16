"""Medição de campanha nas páginas públicas do site (#260).

Dono, 15/10, para *"o site novo não tem GTM, Analytics nem pixel do Meta — campanha paga fica
cega; ponho os mesmos ids do site antigo?"*: **"sim pfvr"**.

Os ids **nunca** moram no código. Vêm do ambiente do serviço — o mesmo `EnvironmentFile`
(`~/.urace/adminai.env`, ou o caminho em `URACE_ENV`) de onde sai o resto:

    SITE_GTM_ID         Google Tag Manager, ex. GTM-XXXXXXX (o Analytics entra por ele)
    SITE_META_PIXEL_ID  pixel do Meta, só dígitos

**Sem a variável, nada carrega**: nenhum script, nenhum host de fora na política de segurança,
nenhuma requisição ao Google ou ao Meta, e o site responde igual ao de hoje. Id com formato
errado também não carrega — melhor não medir do que medir num container de outra pessoa.

Nenhum script inline: o `<head>` leva só um bloco `application/json` (que o navegador não
executa, como o JSON-LD do schema) e o nosso `medicao.js`, servido do próprio site. Com isso a
política continua sem `'unsafe-inline'` em `script-src`.

Onde a medição entra e onde não entra:

* **entra** nas páginas públicas de marketing — início, serviços, Academy, Pro Team, iniciantes,
  carreira, sobre, acessibilidade, blog, loja, página de produto, contato, 404 — e na página de
  obrigado do pagamento (é o único lugar que sabe que o pagamento deu certo);
* **não entra** no painel nem na área do cliente (`/ops`, `/ops/portal`): a política de lá segue
  a de hoje, sem script de fora;
* **não entra** em `/cart/` (mostra o nome e o e-mail de quem está conectado) nem em
  `/order/<token>/` (o token do endereço é a chave da página, e o Analytics manda o endereço
  inteiro para o Google).

Na página de obrigado, o `medicao.js` tira a query do endereço (`?session_id=…`) **antes** de
carregar qualquer script de fora: o Google e o Meta só veem `/cart/thanks/`.

O que vai ao `dataLayer`: tipo de página, `add_to_cart` e `purchase` com valor, moeda, número do
pedido e o item do catálogo. **Nunca** nome, e-mail, telefone, endereço, medida, piloto ou
qualquer dado da pessoa — nem no `dataLayer`, nem em parâmetro de endereço.
"""
import json
import os
import re
from html import escape as e

ENV_PADRAO = "~/.urace/adminai.env"
VARIAVEIS = ("SITE_GTM_ID", "SITE_META_PIXEL_ID", "SITE_KOMMO_ID", "SITE_KOMMO_HASH")

GTM = re.compile(r"GTM-[A-Z0-9]{4,12}")
PIXEL = re.compile(r"[0-9]{8,20}")
KOMMO_ID = re.compile(r"[0-9]{4,12}")
KOMMO_HASH = re.compile(r"[0-9a-f]{32,128}")

HOST_GTM = "https://www.googletagmanager.com"
HOSTS_GA = ("https://www.google-analytics.com", "https://*.google-analytics.com",
            "https://analytics.google.com", "https://*.analytics.google.com")
HOST_FB_JS = "https://connect.facebook.net"
HOST_FB = "https://www.facebook.com"
# #170: o chat do Kommo. Medido de verdade (15/10, Chromium carregando o widget do urace.us de hoje): o botão
# vem do gso.kommo.com, o formulário do forms.kommo.com, o mensageiro do piper.amocrm.com e a conversa por
# WebSocket no lc-en.kommo.com. Só isso abre, e só quando o chat está configurado.
# #284: o widget põe estilo inline nos próprios elementos (posição, cor do balão) — sem 'unsafe-inline' no
# style-src o navegador recusa e o balão aparece sem forma. Só o estilo: script inline continua fechado.
KOMMO = {"script-src": ["https://gso.kommo.com", "https://forms.kommo.com", "https://piper.amocrm.com"],
         "style-src": ["'unsafe-inline'", "https://gso.kommo.com", "https://forms.kommo.com"],
         "font-src": ["https://gso.kommo.com"],
         "img-src": ["https://gso.kommo.com", "https://forms.kommo.com"],
         "connect-src": ["https://gso.kommo.com", "https://piper.amocrm.com", "wss://lc-en.kommo.com"],
         "frame-src": ["https://gso.kommo.com", "https://forms.kommo.com", "https://piper.amocrm.com"]}

# a marca do bloco de dados: a rota olha por ela para abrir a política só quando a página
# realmente levou a medição (a política nunca abre mais do que o HTML usa)
MARCA = 'id="urace-medicao"'
SCRIPT = "medicao.js"

# prefixos onde a medição nunca entra, mesmo com a variável posta
FORA = ("/order/",)
FORA_EXATO = ("/cart/",)

_lido = False


def _carregar():
    """Lê as duas variáveis do env do serviço, uma vez por processo e sem sobrescrever o ambiente."""
    global _lido
    if _lido:
        return
    _lido = True
    caminho = os.path.expanduser(os.environ.get("URACE_ENV") or ENV_PADRAO)
    try:
        with open(caminho, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha.startswith("#") or "=" not in linha:
                    continue
                k, v = linha.split("=", 1)
                if k.strip() in VARIAVEIS:
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass


def _id(nome, formato):
    v = (os.environ.get(nome) or "").strip()
    if not v:
        _carregar()
        v = (os.environ.get(nome) or "").strip()
    return v if formato.fullmatch(v) else ""


def gtm_id():
    return _id("SITE_GTM_ID", GTM)


def pixel_id():
    return _id("SITE_META_PIXEL_ID", PIXEL)


def kommo():
    """#170: o chat do Kommo ({'id', 'hash'}), ou None. O id e o hash são os do widget que o site antigo
    publica; ficam no ambiente, como os da medição (o repositório é público)."""
    i, h = _id("SITE_KOMMO_ID", KOMMO_ID), _id("SITE_KOMMO_HASH", KOMMO_HASH)
    return {"id": i, "hash": h} if i and h else None


def medindo():
    """Analytics ou pixel configurado (os que pedem consentimento, #171)."""
    return bool(gtm_id() or pixel_id())


def ligada():
    """Alguma coisa de fora configurada (medição ou chat)? Sem nada, nada carrega e nada abre na política."""
    return bool(medindo() or kommo())


def permitida(caminho):
    """Esta página pode levar medição? (vale mesmo com a variável posta)"""
    c = caminho or "/"
    return not c.startswith(FORA) and c not in FORA_EXATO


def ativa(caminho):
    return permitida(caminho) and ligada()


def cabeca(caminho, eventos=()):
    """O bloco de dados no `<head>`: `application/json`, que o navegador não executa.

    `eventos`: o que a página já sabe e o `medicao.js` empurra para o `dataLayer` antes de
    carregar o GTM (hoje, só o `purchase` da página do pedido pago)."""
    if not ativa(caminho):
        return ""
    dados = {"gtm": gtm_id(), "pixel": pixel_id(), "kommo": kommo(), "eventos": [x for x in eventos if x],
             # a volta do Stripe traz `?session_id=…` no endereço: sai antes de o GTM carregar
             "limpar_endereco": bool(caminho and caminho.endswith("/thanks/"))}
    # `</` dentro do JSON fecharia a tag <script> (o mesmo cuidado do JSON-LD)
    return (f'<script type="application/json" {MARCA}>'
            + json.dumps(dados, ensure_ascii=False).replace("</", "<\\/") + "</script>")


def noscript(caminho):
    """#171: nada. O `noscript` do GTM e o do pixel carregavam o Google e o Meta para quem está sem
    JavaScript — e quem está sem JavaScript não tem como dizer sim ou não ao banner de consentimento.
    Sem consentimento não há medição, então o `noscript` saiu. (A função fica para o layout não mudar.)"""
    return ""


def _noscript_antigo(caminho):                       # o de #260, guardado só como referência
    if not ativa(caminho):
        return ""
    partes = []
    g, p = gtm_id(), pixel_id()
    if g:
        # sem `style=` (a política não deixa estilo inline): quem esconde é a classe no site.css
        partes.append(f'<iframe class="medicao-ns" src="{HOST_GTM}/ns.html?id={e(g)}" width="0" height="0"'
                      ' title="Google Tag Manager"></iframe>')
    if p:
        partes.append(f'<img class="medicao-ns" width="1" height="1" alt=""'
                      f' src="{HOST_FB}/tr?id={e(p)}&amp;ev=PageView&amp;noscript=1">')
    return f"<noscript>{''.join(partes)}</noscript>"


def csp_hosts():
    """O mínimo que a política precisa abrir, e só nas respostas que levaram a medição."""
    partes = {}
    if gtm_id():
        partes["script-src"] = [HOST_GTM]
        partes["img-src"] = [HOST_GTM, *HOSTS_GA]
        partes["connect-src"] = [HOST_GTM, *HOSTS_GA]
        partes["frame-src"] = [HOST_GTM]             # o `noscript` do GTM é um iframe
    if pixel_id() or gtm_id():
        # o pixel entra direto (SITE_META_PIXEL_ID) ou como tag dentro do container do GTM:
        # nos dois casos o navegador busca o fbevents.js no connect.facebook.net
        partes.setdefault("script-src", []).append(HOST_FB_JS)
        partes.setdefault("img-src", []).append(HOST_FB)
        partes.setdefault("connect-src", []).append(HOST_FB)
    if kommo():
        for diretiva, hosts in KOMMO.items():
            partes.setdefault(diretiva, []).extend(hosts)
    return partes


# ------------------------------------------------------------------ eventos (sem dado de pessoa)
MOEDA = "USD"


def item_do_pedido(x):
    """Uma linha do pedido como item do catálogo. Só catálogo: nunca o piloto, o nome ou o e-mail."""
    if x["kind"] == "sessao":
        return {"item_id": f"sessao-{x['service_id']}", "item_name": x["service_name"] or "session",
                "item_category": "sessao", "price": round(float(x["unit_price"] or 0), 2),
                "quantity": int(x["quantity"] or 1)}
    item = {"item_id": x["product_slug"] or "produto", "item_name": x["name"] or x["product_slug"] or "produto",
            "item_category": "produto", "price": round(float(x["unit_price"] or 0), 2),
            "quantity": int(x["quantity"] or 1)}
    if x.get("variation"):
        item["item_variant"] = x["variation"]
    return item


def compra(o, ls):
    """O `purchase` do pedido pago: número do pedido, valor, moeda e os itens do catálogo."""
    valor = o["amount_paid"] if o["amount_paid"] is not None else o["amount"]
    return {"event": "purchase", "ecommerce": {
        "transaction_id": str(o["id"]), "currency": MOEDA, "value": round(float(valor or 0), 2),
        "items": [item_do_pedido(x) for x in ls]}}
