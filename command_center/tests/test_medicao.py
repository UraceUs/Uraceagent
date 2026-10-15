"""Medição de campanha nas páginas públicas do site (#260).

Dono, 15/10, para *"o site novo não tem GTM, Analytics nem pixel do Meta — campanha paga fica
cega; ponho os mesmos ids do site antigo?"*: **"sim pfvr"**.

O que estes testes trancam:

* **sem a variável de ambiente, nada carrega**: nenhum bloco, nenhum script, nenhum host de fora
  na política de segurança — e a política do site fica byte a byte a de antes;
* id com formato errado também não carrega (melhor não medir do que medir no container errado);
* com a variável, a política abre **o mínimo** (os hosts do Google Tag Manager e do Meta) e **só**
  nas respostas das páginas públicas que levaram a medição;
* o **painel** (`/ops`) mantém a política estrita de hoje, mesmo com a variável posta;
* `/cart/` (mostra o nome e o e-mail de quem está conectado) e `/order/<token>/` (o token do
  endereço é a chave da página) **nunca** levam medição;
* o `purchase` do pedido pago leva número do pedido, valor, moeda e item do catálogo — e **nenhum**
  dado da pessoa (nome, e-mail, telefone, endereço, piloto);
* o formulário de contato grava a campanha (utm_*, gclid, fbclid, fbp, fbc, campaign_id, adset_id),
  cortada e sem HTML, e Vendas lê isso na oportunidade.

Dados fictícios (@example.com, 555-01xx, nome inventado)."""
import json
import os
import re

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api.main import app  # noqa: E402
from command_center.api.vitrine import csp  # noqa: E402
from command_center.db import um  # noqa: E402
from command_center.tests.test_carrinho import _checkout, _entrar, _sessao, loja  # noqa: E402, F401
from command_center.tests.test_pedido_site import _pedido, _webhook, pedido_sessao  # noqa: E402, F401
from command_center.tests.test_stripe_loja import _assinado, _comprar, _emails, _evento, _simples, amb  # noqa: E402, F401
from command_center.vitrine import medicao  # noqa: E402

SITE = "https://novo.urace.us"
GTM = "GTM-59CCNDC"                 # formato de id do Tag Manager (o do urace.us)
PIXEL = "380948601336488"           # formato de id de pixel do Meta
ESTATIC = "/home/ignorado"

# a política do site como ela é hoje, sem medição: a medição não pode mexer num caractere dela
CSP_DE_HOJE = ("default-src 'self'; img-src 'self' data:; style-src 'self'; font-src 'self'; "
               "script-src 'self'; connect-src 'self'; base-uri 'none'; "
               "form-action 'self' https://checkout.stripe.com; frame-ancestors 'none'")

DE_FORA = ("googletagmanager.com", "google-analytics.com", "connect.facebook.net", "facebook.com/tr")


@pytest.fixture()
def cli(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    monkeypatch.delenv("CC_SITE_HOSTS", raising=False)
    monkeypatch.delenv("CC_SITE_PREVIEW", raising=False)
    monkeypatch.delenv("SITE_GTM_ID", raising=False)
    monkeypatch.delenv("SITE_META_PIXEL_ID", raising=False)
    with TestClient(app, base_url=SITE) as t:
        yield t


def _bloco(html):
    """O JSON que o servidor manda para o `medicao.js` (`application/json`, não executa)."""
    m = re.search(r'<script type="application/json" id="urace-medicao">(.*?)</script>', html, re.S)
    return json.loads(m.group(1).replace("<\\/", "</")) if m else None


# ------------------------------------------------------------------ sem a variável, nada carrega
PUBLICAS = ("/", "/store/", "/services/", "/contact/", "/academy/", "/blog/")


@pytest.mark.parametrize("caminho", PUBLICAS)
def test_sem_a_variavel_nada_carrega_e_a_politica_e_a_de_hoje(cli, caminho):
    r = cli.get(caminho)
    assert r.status_code == 200
    assert _bloco(r.text) is None and "urace-medicao" not in r.text
    assert "medicao.js" not in r.text
    for host in DE_FORA:
        assert host not in r.text, host
    assert r.headers["content-security-policy"] == CSP_DE_HOJE
    assert csp() == CSP_DE_HOJE


@pytest.mark.parametrize("valor", ["", "  ", "GTM", "UA-12345", "GTM-59CCNDC; evil", "<script>", "gtm-59ccndc"])
def test_id_com_formato_errado_nao_carrega(cli, monkeypatch, valor):
    monkeypatch.setenv("SITE_GTM_ID", valor)
    r = cli.get("/")
    assert _bloco(r.text) is None and r.headers["content-security-policy"] == CSP_DE_HOJE


def test_pixel_com_formato_errado_nao_carrega(cli, monkeypatch):
    monkeypatch.setenv("SITE_META_PIXEL_ID", "380948601336488'); alert(1)")
    r = cli.get("/")
    assert _bloco(r.text) is None and r.headers["content-security-policy"] == CSP_DE_HOJE


# ------------------------------------------------------------------ com a variável
@pytest.mark.parametrize("caminho", PUBLICAS)
def test_com_a_variavel_a_pagina_leva_a_medicao_e_a_politica_abre_o_minimo(cli, monkeypatch, caminho):
    monkeypatch.setenv("SITE_GTM_ID", GTM)
    monkeypatch.setenv("SITE_META_PIXEL_ID", PIXEL)
    r = cli.get(caminho)
    assert r.status_code == 200
    d = _bloco(r.text)
    assert d and d["gtm"] == GTM and d["pixel"] == PIXEL and d["eventos"] == []
    # o nosso script, servido do próprio site: nenhum script inline e nenhum `src` de fora no HTML
    assert re.search(r'<script src="/_s/medicao\.js\?v=[0-9a-f]+" defer></script>', r.text)
    assert not re.search(r'<script(?![^>]*\bsrc=)[^>]*>(?!\s*\{)', r.text.replace(
        '<script type="application/ld+json">', "").replace('<script type="application/json" id="urace-medicao">', ""))
    # o `noscript` do GTM e o do pixel, sem `style=` (a política do site não deixa estilo inline)
    assert f'<iframe class="medicao-ns" src="https://www.googletagmanager.com/ns.html?id={GTM}"' in r.text
    assert f'src="https://www.facebook.com/tr?id={PIXEL}&amp;ev=PageView&amp;noscript=1"' in r.text
    assert "style=" not in r.text
    pol = r.headers["content-security-policy"]
    assert "script-src 'self' https://www.googletagmanager.com https://connect.facebook.net;" in pol
    assert "frame-src https://www.googletagmanager.com" in pol
    assert "'unsafe-inline'" not in pol and "'unsafe-eval'" not in pol and "*" not in pol.replace("https://*.", "")
    # o que NÃO abriu: nada além dos hosts do Google e do Meta
    hosts = set(re.findall(r"https://[^\s;]+", pol))
    assert hosts <= {"https://checkout.stripe.com", medicao.HOST_GTM, medicao.HOST_FB, medicao.HOST_FB_JS,
                     *medicao.HOSTS_GA}, hosts


def test_so_o_pixel_nao_abre_o_google(cli, monkeypatch):
    monkeypatch.setenv("SITE_META_PIXEL_ID", PIXEL)
    r = cli.get("/")
    d = _bloco(r.text)
    assert d and d["pixel"] == PIXEL and d["gtm"] == ""
    pol = r.headers["content-security-policy"]
    assert "googletagmanager" not in pol and "google-analytics" not in pol
    assert "connect.facebook.net" in pol and "frame-src" not in pol
    assert "googletagmanager" not in r.text


# ------------------------------------------------------------------ o painel continua estrito
def test_o_painel_nao_recebe_script_de_fora_nem_com_a_variavel_posta(cli, monkeypatch):
    monkeypatch.setenv("SITE_GTM_ID", GTM)
    monkeypatch.setenv("SITE_META_PIXEL_ID", PIXEL)
    for endereco in ("https://ops.urace.us/ops/", "https://ops.urace.us/ops/api/saude",
                     "https://my.urace.us/ops/portal"):
        r = cli.get(endereco, follow_redirects=False)
        pol = r.headers.get("content-security-policy", "")
        assert pol, endereco
        for host in DE_FORA:
            assert host not in pol and host not in r.text, (endereco, host)
        assert "script-src" not in pol, "o painel segue no default-src 'self', sem script de fora"


# ------------------------------------------------------------------ onde a medição nunca entra
def test_carrinho_nunca_leva_medicao(cli, monkeypatch):
    """O carrinho mostra o nome e o e-mail de quem está conectado: nenhum script de fora ali."""
    monkeypatch.setenv("SITE_GTM_ID", GTM)
    r = cli.get("/cart/")
    assert r.status_code == 200 and _bloco(r.text) is None
    assert r.headers["content-security-policy"] == CSP_DE_HOJE
    assert not medicao.permitida("/cart/") and medicao.permitida("/store/")


def test_link_pessoal_do_pedido_nunca_leva_medicao(amb, monkeypatch):  # noqa: F811
    """`/order/<token>/`: o token do endereço é a chave da página. O Analytics manda o endereço
    inteiro para o Google, então essa página não mede nada."""
    from command_center.providers import pedido_site
    cli, con, st, qbo, tmp = amb
    monkeypatch.setenv("SITE_GTM_ID", GTM)
    _comprar(cli, _simples())
    o = _pedido(con)
    r = cli.get(f"/order/{pedido_site.token(o)}/")
    assert r.status_code == 200 and _bloco(r.text) is None
    for host in DE_FORA:
        assert host not in r.text
    assert r.headers["content-security-policy"] == CSP_DE_HOJE


# ------------------------------------------------------------------ purchase, sem dado da pessoa
def test_purchase_do_pedido_pago_com_valor_e_moeda_e_sem_nenhum_dado_da_pessoa(pedido_sessao, monkeypatch):  # noqa: F811
    cli, con, st, qbo, tmp, sid, conta, pid, dia, p, s = pedido_sessao
    monkeypatch.setenv("SITE_GTM_ID", GTM)
    monkeypatch.setenv("SITE_META_PIXEL_ID", PIXEL)
    s.update(payment_status="paid", payment_intent="pi_260",
             customer_details={"email": "maya.teste@example.com", "name": "Maya Teste"})
    assert _webhook(cli, s, "checkout.session.completed", "evt_m1") == "pago"
    o = _pedido(con)
    r = cli.get(f"/cart/thanks/?session_id={s['id']}")
    assert r.status_code == 200
    d = _bloco(r.text)
    assert d and d["limpar_endereco"] is True, "a query sai do endereço antes de o GTM carregar"
    ev = [x for x in d["eventos"] if x["event"] == "purchase"]
    assert len(ev) == 1
    c = ev[0]["ecommerce"]
    assert c["transaction_id"] == str(o["id"]) and c["currency"] == "USD"
    assert c["value"] == round(float(o["amount_paid"] if o["amount_paid"] is not None else o["amount"]), 2)
    assert {x["item_category"] for x in c["items"]} == {"sessao", "produto"}
    # NUNCA dado da pessoa no dataLayer: nem no evento, nem em chave nenhuma
    cru = json.dumps(d, ensure_ascii=False).lower()
    for proibido in ("maya", "teste", "noah", "@example.com", "example.com", "555", "cosmonaut", "@"):
        assert proibido not in cru, proibido
    assert "Maya Teste" in r.text, "a página continua mostrando os dados dela para ela (#248)"


def test_pedido_que_nao_foi_pago_nao_manda_purchase(pedido_sessao, monkeypatch):  # noqa: F811
    cli, con, st, qbo, tmp, sid, conta, pid, dia, p, s = pedido_sessao
    monkeypatch.setenv("SITE_GTM_ID", GTM)
    s.update(payment_status="unpaid", customer_details={"email": "maya.teste@example.com", "name": "Maya Teste"})
    assert _webhook(cli, s, "checkout.session.completed", "evt_m2") == "aguardando"
    r = cli.get(f"/cart/thanks/?session_id={s['id']}")
    assert _bloco(r.text)["eventos"] == [], "sem pagamento confirmado, nenhuma conversão é contada"


# ------------------------------------------------------------------ add_to_cart
def test_add_to_cart_sai_do_carrinho_e_da_agenda():
    """Os dois "Add to cart" do site empurram `add_to_cart` com valor, moeda e item do catálogo."""
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vitrine", "static")
    for nome in ("carrinho.js", "agenda.js"):
        js = open(os.path.join(base, nome), encoding="utf-8").read()
        assert "add_to_cart" in js and "uraceMedicao" in js, nome
        assert "currency: 'USD'" in js, nome
        for proibido in ("email", "e-mail", "telefone", "phone", "endereco", "address"):
            trecho = js[js.index("add_to_cart") - 400:js.index("add_to_cart") + 600]
            assert proibido not in trecho, (nome, proibido)
    med = open(os.path.join(base, "medicao.js"), encoding="utf-8").read()
    assert GTM not in med and PIXEL not in med, "nenhum id no código: tudo vem do ambiente"


def test_nenhum_id_no_codigo():
    """Os ids vivem no ambiente do VPS, nunca no repositório."""
    import subprocess
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    arquivos = subprocess.run(["git", "ls-files"], cwd=raiz, capture_output=True, text=True, check=True).stdout.split()
    for caminho in arquivos:
        if caminho.startswith(("command_center/vitrine/", "command_center/api/")) and caminho.endswith((".py", ".js")):
            texto = open(os.path.join(raiz, caminho), encoding="utf-8", errors="replace").read()
            assert GTM not in texto and PIXEL not in texto, caminho


# ------------------------------------------------------------------ campanha no formulário
CAMPOS = {"nome": "Maya Teste", "email": "maya.teste@example.com", "assunto": "store",
          "mensagem": "Do you have size 10 gloves?"}


def _contato(cli, **extra):
    r = cli.post("/ops/api/vitrine/contato", json={**CAMPOS, **extra},
                 headers={"Accept": "application/json"})
    assert r.status_code == 200, r.text
    return r


def test_contato_grava_a_campanha_de_onde_o_contato_veio(cli):
    _contato(cli, utm_source="google", utm_medium="cpc", utm_campaign="arrive-and-drive",
             utm_term="kart orlando", utm_content="anuncio-a", gclid="Cj0KCQ", fbclid="IwAR",
             fbp="fb.1.1700000000.123", fbc="fb.1.1700000000.IwAR", campaign_id="120200", adset_id="120300")
    from command_center.db import conectar
    con = conectar()
    o = um(con, "SELECT * FROM opportunities ORDER BY id DESC LIMIT 1")
    camp = json.loads(o["campaign"])
    assert camp == {"utm_source": "google", "utm_medium": "cpc", "utm_campaign": "arrive-and-drive",
                    "utm_term": "kart orlando", "utm_content": "anuncio-a", "gclid": "Cj0KCQ",
                    "fbclid": "IwAR", "fbp": "fb.1.1700000000.123", "fbc": "fb.1.1700000000.IwAR",
                    "campaign_id": "120200", "adset_id": "120300"}
    con.close()


def test_contato_sem_campanha_nao_inventa_nada(cli):
    _contato(cli)
    from command_center.db import conectar
    con = conectar()
    assert um(con, "SELECT * FROM opportunities ORDER BY id DESC LIMIT 1")["campaign"] is None
    con.close()


def test_campanha_cortada_sem_html_e_sem_chave_de_fora(cli):
    _contato(cli, utm_source="<script>alert(1)</script>google", utm_campaign="x" * 900,
             senha="nao", telefone_do_vizinho="nao", email_oculto="quem@example.com")
    from command_center.db import conectar
    con = conectar()
    camp = json.loads(um(con, "SELECT * FROM opportunities ORDER BY id DESC LIMIT 1")["campaign"])
    assert "<" not in camp["utm_source"] and ">" not in camp["utm_source"]
    assert len(camp["utm_campaign"]) == 200
    assert set(camp) == {"utm_source", "utm_campaign"}, "só chave de campanha entra"
    con.close()


def test_vendas_mostra_a_campanha_do_contato(cli):
    """Quem vende abre a oportunidade e vê de onde o contato veio."""
    from command_center.api import auth
    from command_center.db import conectar
    _contato(cli, utm_source="instagram", utm_medium="paid_social", fbclid="IwAR260")
    con = conectar()
    oid = um(con, "SELECT id FROM opportunities ORDER BY id DESC LIMIT 1")["id"]
    auth.criar_usuario(con, "closer@urace.us", "Carla Vendas", "OPERATOR", "senha-forte-123")
    con.commit()
    con.close()
    assert cli.post("/ops/api/auth/login", json={"email": "closer@urace.us", "password": "senha-forte-123"}).status_code == 200
    r = cli.get(f"/ops/api/sales/{oid}")
    assert r.status_code == 200, r.text
    assert r.json()["oportunidade"]["campaign"] == {"utm_source": "instagram", "utm_medium": "paid_social",
                                                    "fbclid": "IwAR260"}


def test_campanha_vai_para_o_dataLayer_so_como_campanha():
    """O `campanha.js` lê endereço e cookie do pixel — e nunca nada da pessoa."""
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vitrine", "static")
    js = open(os.path.join(base, "campanha.js"), encoding="utf-8").read()
    assert "'utm_source'" in js and "'gclid'" in js and "'fbclid'" in js and "_fbp" in js and "_fbc" in js
    assert "localStorage" in js and "googletagmanager" not in js and "facebook.net" not in js
