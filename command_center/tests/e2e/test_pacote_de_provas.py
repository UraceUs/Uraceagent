"""Pacote de provas do site e do processo de vendas (#253).

Dono, 15/10: *"me de um bloco para a extensão testar todo o site e processo de vendas criando uma
conta fictícia para testar de ponta a ponta"* e *"de o comando para a extensão capturar tela a cada
passo para poder te passar e testar todas as funcionalidades"*.

Isto não é um teste de regressão: é o **roteiro fotografado** que o dono (ou a extensão) roda na VPS
por `adminai/deploy/command_center/testar_tudo.sh`. Ele percorre a venda inteira com uma conta
fictícia (conta no site → kart, dia e turno → carrinho → checkout no Stripe falso → pago → o pedido,
a sessão e a venda no painel) e depois todas as telas do painel, tirando uma foto por passo em 390 px
e em 1280 px, e escrevendo um `RESUMO.md` em português ao lado das fotos.

- Só roda com `CC_E2E=1` **e** `CC_FOTOS=<pasta>`: na suíte normal fica de fora.
- Erro no meio não para a entrega: o passo vira FALHOU, a foto do estado do erro é tirada e o
  roteiro segue, para o pacote chegar completo nas mãos do dono.
- Banco descartável, servidor isolado e Stripe falso: as mesmas travas do resto do end-to-end
  (nada de Asana, Gmail, QuickBooks, Google ou Stripe de verdade), e todo dado é fictício.
"""
import contextlib
import json
import os
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from command_center.tests.e2e import test_navegador as tn
from command_center.tests.e2e.test_navegador import navegador, servidor  # noqa: F401  (as mesmas fixtures)

pytestmark = pytest.mark.skipif(
    os.environ.get("CC_E2E") != "1" or not os.environ.get("CC_FOTOS"),
    reason="pacote de provas: rode por adminai/deploy/command_center/testar_tudo.sh (CC_E2E=1 e CC_FOTOS)")

SENHA_SITE = "pista-molhada-7"
LARGURAS = [("390", 390, 844), ("1280", 1280, 900)]
# rolagem lateral e alvo de toque: o mesmo olhar do resto do end-to-end (`_VAZA` e `_PEQUENOS`),
# que é o de celular.mjs, para o resumo nunca contradizer a suíte.


class Caderno:
    """As fotos numeradas de uma largura e o que aconteceu em cada passo."""

    def __init__(self, raiz, nome):
        self.nome = nome
        self.pasta = os.path.join(raiz, nome)
        os.makedirs(self.pasta, exist_ok=True)
        self.n = 0
        self.passos = []
        self.celular = []

    def _foto(self, pg, apelido, inteira):
        self.n += 1
        arq = f"{self.n:02d}-{apelido}.png".lower()
        try:
            pg.screenshot(path=os.path.join(self.pasta, arq), full_page=inteira)
        except Exception as e:                                  # noqa: BLE001  (a foto nunca derruba o roteiro)
            return f"(sem foto: {type(e).__name__})"
        return arq

    def anotar(self, pg, apelido, titulo, feito, resposta, ok, inteira=True):
        self.passos.append({"n": self.n + 1, "titulo": titulo, "feito": feito, "resposta": resposta,
                            "foto": self._foto(pg, apelido, inteira), "ok": ok})

    @property
    def falhas(self):
        return [p for p in self.passos if not p["ok"]]


@contextlib.contextmanager
def passo(cad, pg, apelido, titulo, feito, inteira=True):
    """Um passo do roteiro. Deu erro: marca FALHOU, fotografa o estado e o roteiro continua."""
    estado = {"resposta": ""}
    try:
        yield estado
    except Exception as e:                                      # noqa: BLE001  (#253: entregar o pacote completo)
        primeira = (str(e).strip().splitlines() or [""])[0]
        cad.anotar(pg, apelido, titulo, feito, f"FALHOU — {type(e).__name__}: {primeira[:300]}", False, inteira)
    else:
        cad.anotar(pg, apelido, titulo, feito, estado["resposta"] or "como esperado", True, inteira)


def _preparar(adm, base):
    """O painel do teste: um serviço de sessão para o kart "4-stroke" e a semana toda aberta."""
    csrf = {"X-CSRF": next(c["value"] for c in adm.context.cookies() if c["name"] == "cc_csrf")}
    r = adm.request.post(base + "/api/site/servicos", headers=csrf,
                         data={"name": "Arrive and Drive 4-stroke", "price": 719, "deposit": 400})
    assert r.ok, r.text()
    semana = [{"weekday": d, "period": p, "open": True, "capacity": 5}
              for d in range(7) for p in ("manha", "tarde")]
    assert adm.request.put(base + "/api/site/agenda/semana", data=semana, headers=csrf).ok


def _venda(cad, br, base, site, largura, altura, produto, quem, dia):
    """O caminho de venda inteiro, com conta fictícia, fotografando passo a passo."""
    v = br.new_page(viewport={"width": largura, "height": altura},
                           extra_http_headers={"X-Forwarded-For": quem["ip"]})
    erros = []
    v.on("pageerror", lambda e: erros.append(str(e)))
    with passo(cad, v, "home-do-site", "A home do site abre", "abri a página inicial do site") as st:
        v.goto(site + "/")
        v.get_by_role("heading", level=1).first.wait_for()
        st["resposta"] = f"a home abriu com o título {v.title()!r}"
    with passo(cad, v, "arrive-and-drive", "A página do Arrive and Drive abre", "abri /services/arrive-and-drive/") as st:
        v.goto(site + "/services/arrive-and-drive/")
        v.locator(".agenda-dia.aberto").first.wait_for()
        st["resposta"] = "a página abriu com a agenda pública carregada"
    with passo(cad, v, "kart-escolhido", "Escolher o kart", 'cliquei no kart "4-stroke"') as st:
        v.locator("label.kart", has_text="4-stroke").first.click()
        st["resposta"] = f"o resumo mostra {v.locator('.agenda-resumo').inner_text()!r} e o preço do painel {v.locator('.agenda-preco').inner_text()}"
    with passo(cad, v, "dia-escolhido", "Escolher o dia", f"cliquei em {dia.strftime('%d/%m')} no calendário") as st:
        tn._clicar_dia(v, dia)
        botao = v.locator(".agenda-ir").inner_text().strip()
        assert botao == "Pick a time to continue", f"o botão diz {botao!r} (#253: tem de pedir o turno)"
        st["resposta"] = f"o botão pede o que falta: {botao!r}"
    with passo(cad, v, "turno-escolhido", "Escolher o turno", "cliquei em Morning") as st:
        v.get_by_role("button", name=re.compile("^Morning")).click()
        st["resposta"] = (f"o botão virou {v.locator('.agenda-ir').inner_text().strip()!r} e apareceu "
                          f"{v.locator('.agenda-carrinho').inner_text().strip()!r}")
    with passo(cad, v, "sessao-no-carrinho", "Pôr a sessão no carrinho", 'cliquei em "Add to cart"') as st:
        v.get_by_role("button", name=re.compile("^Add to cart")).click()
        v.get_by_text("Added to your cart.").wait_for()
        st["resposta"] = "a sessão entrou no carrinho (com o preço e o depósito do painel)"
    with passo(cad, v, "produto-da-loja", "Pôr um produto da loja no carrinho", f"abri {produto['name']!r} e pus no carrinho") as st:
        v.goto(site + f"/store/p/{produto['slug']}/")
        v.get_by_role("button", name="Add to cart").click()
        v.get_by_text("Added to your cart.").wait_for()
        st["resposta"] = f"o contador do topo mostra {v.locator('[data-carrinho-n]').inner_text()} itens"
    with passo(cad, v, "carrinho-pede-a-conta", "O carrinho pede a conta", "abri /cart/") as st:
        v.goto(site + "/cart/")
        v.get_by_role("heading", name="Your cart", level=1).wait_for()
        v.get_by_role("link", name="Create account").wait_for()
        st["resposta"] = "o carrinho mostra os itens e pede a conta URACE para comprar"
    with passo(cad, v, "criar-a-conta-ficticia", "Criar a conta fictícia no site", f"preenchi o cadastro de {quem['nome']}") as st:
        v.get_by_role("link", name="Create account").click()
        v.get_by_role("heading", name="Create your account", level=1).wait_for()
        v.get_by_label("Full name").fill(quem["nome"])
        v.get_by_label("Date of birth").fill("1990-05-05")
        v.get_by_label("Email").fill(quem["email"])
        v.get_by_label("Password").fill(SENHA_SITE)
        v.get_by_label("Phone").fill(quem["telefone"])
        v.get_by_label("Street address").fill("10724 Cosmonaut Blvd")
        v.get_by_label("City").fill("Orlando")
        v.get_by_role("textbox", name="State").fill("FL")
        v.get_by_label("ZIP").fill("32824")
        v.get_by_label("I accept the").check()
        st["resposta"] = "o cadastro foi preenchido com dado fictício (nada de cliente de verdade)"
    with passo(cad, v, "conta-criada", "A conta criada volta para o carrinho", 'cliquei em "Create account"') as st:
        v.get_by_role("button", name="Create account").click()
        v.wait_for_url("**/cart/", timeout=20000)
        v.get_by_text("Signed in as").wait_for()
        st["resposta"] = f"a conta de {quem['email']} foi criada e o carrinho já diz quem está conectado"
    with passo(cad, v, "piloto-na-conta", "Pôr o piloto na conta", f"cadastrei o piloto {quem['piloto']}") as st:
        v.get_by_role("link", name="Add a driver").click()
        v.get_by_label("Driver's full name").fill(quem["piloto"])
        v.get_by_label("Date of birth").fill("2013-07-01")
        for rot, val in (("Height (in)", "56"), ("Weight (lb)", "85"), ("Chest (in)", "28"), ("Waist (in)", "25")):
            v.get_by_label(rot).fill(val)
        v.get_by_label("Karting experience").fill("First time")
        v.get_by_role("button", name="Save driver").click()
        v.get_by_text(quem["piloto"]).first.wait_for()
        st["resposta"] = "o piloto entrou na conta com as medidas"
    with passo(cad, v, "carrinho-pronto", "O carrinho pronto para pagar", "voltei para /cart/") as st:
        v.goto(site + "/cart/")
        pagar = v.get_by_role("button", name=re.compile(r"^Checkout · \$"))
        pagar.wait_for()
        st["resposta"] = f"o carrinho fecha em {pagar.inner_text().strip()!r}, com o piloto da conta escolhido"
    total = None
    with passo(cad, v, "checkout-no-stripe", "O checkout no Stripe (o falso do teste)", 'cliquei em "Checkout"') as st:
        v.get_by_role("button", name=re.compile(r"^Checkout · \$")).click()
        v.wait_for_url(tn.STRIPE.origem + "/pay/**")
        total = re.search(r"US\$ ([\d.]+)", v.content())
        st["resposta"] = (f"abriu um checkout só, de US$ {total.group(1) if total else '?'}, com as linhas da sessão, "
                          "do depósito e do produto")
    with passo(cad, v, "pagamento-confirmado", "Pagar e voltar para o site", 'cliquei em "Pay" no checkout') as st:
        v.get_by_role("link", name="Pay").click()
        v.get_by_role("heading", name="Payment confirmed", level=1).wait_for()
        assert v.evaluate("JSON.parse(localStorage.getItem('urace.carrinho') || '{}').itens.length") == 0
        st["resposta"] = "a página do pedido pago abriu, com a sessão reservada, e o carrinho esvaziou"
    with passo(cad, v, "pedido-do-cliente", "O pedido na área do cliente", "abri a página do pedido") as st:
        r = v.evaluate(tn._VAZA)
        assert not r["rola"] and not r["culpados"], r
        st["resposta"] = "a página do pedido não rola para o lado nesta largura"
    v.close()
    return erros


def _painel_da_venda(cad, br, base, largura, altura, quem, produto):
    """O outro lado: a venda GANHO, a sessão paga em Agendamentos do site e o card do piloto."""
    adm = tn.entrar(br, base, email="italo@urace.us", largura=largura, altura=altura)
    with passo(cad, adm, "painel-vendas-ganho", "A venda no painel", "abri Vendas e abri o pedido do site") as st:
        tn.abrir(adm, base, "/sales")
        adm.get_by_text(quem["nome"]).first.click()
        adm.get_by_role("heading", name=re.compile(r"^Pedido do site #\d+")).wait_for()
        assert adm.get_by_text(quem["piloto"]).count() >= 1 and adm.get_by_text(produto["name"]).count() >= 1
        st["resposta"] = "o pedido do site está na venda, com o piloto e o item da loja"
    with passo(cad, adm, "painel-agendamentos-do-site", "A sessão em Agendamentos do site", "abri Agendamentos do site") as st:
        tn.abrir(adm, base, "/site")
        adm.get_by_text(re.compile(r"pago no site · pedido #\d+")).first.wait_for()
        st["resposta"] = "a sessão aparece paga pelo site, com o número do pedido"
    with passo(cad, adm, "painel-card-do-piloto", "O registro no card", "procurei o piloto em Clientes e abri o card") as st:
        tn.abrir(adm, base, "/clients")
        adm.get_by_label("Filtrar").fill(quem["piloto"])
        adm.get_by_text(quem["piloto"]).first.click()
        card = adm.get_by_role("dialog")
        card.wait_for()
        st["resposta"] = "o card do piloto abriu com o registro da venda do site"
    erros = list(adm.erros_js) + list(adm.erros_api)
    adm.close()
    return erros


def _telas_do_painel(cad, br, base, largura, altura):
    """Uma foto de cada tela do painel, com o erro de JavaScript/API e o celular de cada uma."""
    pg = tn.entrar(br, base, email="italo@urace.us", largura=largura, altura=altura)
    for rota in tn.ROTAS:
        antes_js, antes_api = len(pg.erros_js), len(pg.erros_api)
        apelido = "tela" + (rota.rstrip("/").replace("/", "-") or "-inicio")
        with passo(cad, pg, apelido, f"A tela {rota} abre", f"abri {rota}", inteira=False) as st:
            tn.abrir(pg, base, rota)
            novos = pg.erros_js[antes_js:] + pg.erros_api[antes_api:]
            assert not novos, "; ".join(novos)[:300]
            r = pg.evaluate(tn._VAZA)
            toque = pg.evaluate(tn._PEQUENOS) if largura <= 390 else []
            if r["rola"] or r["culpados"] or toque:
                cad.celular.append({"rota": rota, "rola": r["rola"], "culpados": r["culpados"], "toque": toque})
            st["resposta"] = ("abriu sem erro de JavaScript nem de API"
                              + (", mas rola para o lado" if r["rola"] else "")
                              + (f", e tem {len(toque)} alvo(s) de toque menor(es) que 40 px" if toque else ""))
    pg.close()


def _resumo(raiz, cadernos, erros_js):
    agora = datetime.now(ZoneInfo("America/New_York")).strftime("%d/%m/%Y %H:%M")
    L = [f"# Prova do site e do processo de vendas — {agora} (hora da Flórida)", "",
         "Pacote gerado por `adminai/deploy/command_center/testar_tudo.sh` (#253). Tudo aqui rodou num",
         "**banco descartável** e num servidor isolado, com **Stripe falso** e **dado fictício**: nenhuma",
         "cobrança, nenhum e-mail e nenhum sistema de verdade foram tocados.", "",
         "**O que este pacote prova:** o site abre, o kart/dia/turno viram sessão com o preço do painel,",
         "a conta fictícia é criada no próprio site, o carrinho soma sessão + depósito + produto, o",
         "checkout fecha num pagamento só, a volta do pagamento mostra o pedido pago, e o painel registra",
         "a venda GANHO, a sessão em Agendamentos do site e o card do piloto. Mais: todas as telas do",
         "painel abrem sem erro de JavaScript nem de API, em celular e em computador.", "",
         "**O que ele NÃO prova:** cobrança de verdade no Stripe (chave real), e-mail de verdade saindo,",
         "e nada de Asana, QuickBooks, DocuSign ou Google de verdade — tudo isso é falso aqui, de propósito.", ""]
    for cad in cadernos:
        L += [f"## Caminho de venda e telas — {cad.nome} px", "",
              "| # | Passo | O que foi feito | O que o sistema respondeu | Foto | Resultado |",
              "|---|---|---|---|---|---|"]
        for p in cad.passos:
            L.append(f"| {p['n']} | {p['titulo']} | {p['feito']} | {p['resposta'].replace('|', '/')} | "
                     f"`{cad.nome}/{p['foto']}` | {'PASSOU' if p['ok'] else 'FALHOU'} |")
        L.append("")
    L += ["## Resumo", ""]
    for cad in cadernos:
        L.append(f"- **{cad.nome} px**: {len(cad.passos) - len(cad.falhas)} passos PASSOU, {len(cad.falhas)} FALHOU"
                 + (": " + "; ".join(p["titulo"] for p in cad.falhas) if cad.falhas else ""))
    L += ["", "## Telas com rolagem lateral ou alvo de toque pequeno", ""]
    ruins = [(cad.nome, x) for cad in cadernos for x in cad.celular]
    if not ruins:
        L.append("Nenhuma: nada rola para o lado e nenhum alvo de toque ficou abaixo de 40 px.")
    for nome, x in ruins:
        L.append(f"- `{nome} px` {x['rota']}: " + ("rola para o lado" if x["rola"] else "cabe na largura")
                 + (f" · fora da largura: {', '.join(x['culpados'])}" if x["culpados"] else "")
                 + (" · alvo de toque < 40 px: " + "; ".join(x["toque"]) if x["toque"] else ""))
    if erros_js:
        L += ["", "## Erros de JavaScript vistos no caminho de venda", ""] + [f"- {x[:300]}" for x in erros_js]
    L += ["", f"Fotos: {sum(len(c.passos) for c in cadernos)} em {len(cadernos)} larguras.", ""]
    with open(os.path.join(raiz, "RESUMO.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def test_pacote_de_provas_do_site_e_da_venda(servidor, navegador):  # noqa: F811
    """O roteiro inteiro, fotografado, com o RESUMO.md ao lado das fotos."""
    from command_center.vitrine import paginas_site
    raiz = os.environ["CC_FOTOS"]
    os.makedirs(raiz, exist_ok=True)
    base, br = servidor, navegador
    site = base.removesuffix("/ops")
    produto = next(p for p in paginas_site.dados("produtos.json")["produtos"]
                   if not p["variations"] and p["price"] and p["in_stock"] and p["images"])
    dia = datetime.now(ZoneInfo("America/New_York")).date() + timedelta(days=5)
    adm = tn.entrar(br, base, email="italo@urace.us")
    _preparar(adm, base)
    adm.close()
    cadernos, erros = [], []
    for i, (nome, largura, altura) in enumerate(LARGURAS):
        cad = Caderno(raiz, nome)
        cadernos.append(cad)
        quem = {"nome": f"Teste Extensao {nome}", "piloto": f"Piloto Teste {nome}",
                "email": f"teste.extensao.{nome}@example.com", "telefone": f"(407) 555-01{20 + i:02d}",
                "ip": f"10.9.{80 + i}.1"}
        erros += _venda(cad, br, base, site, largura, altura, produto, quem, dia)
        erros += _painel_da_venda(cad, br, base, largura, altura, quem, produto)
        _telas_do_painel(cad, br, base, largura, altura)
    _resumo(raiz, cadernos, erros)
    with open(os.path.join(raiz, "resumo.json"), "w", encoding="utf-8") as f:
        json.dump({"gerado_em": time.time(), "larguras": [c.nome for c in cadernos],
                   "passos": {c.nome: c.passos for c in cadernos},
                   "celular": {c.nome: c.celular for c in cadernos}, "erros_js": erros}, f, ensure_ascii=False, indent=1)
    falhas = [f"{c.nome} px · {p['titulo']}: {p['resposta']}" for c in cadernos for p in c.falhas]
    assert not falhas and not erros, "\n".join(falhas + erros)
