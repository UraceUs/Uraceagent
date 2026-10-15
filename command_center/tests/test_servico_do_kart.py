"""#263 e #262: o site vende o kart que ele mostra, por um caminho de compra só.

Dono, 15/10, olhando a página com os quatro karts e os preços na tela: *"mas esses serviços já estão
sendo mostrados no site… o mais lógico é ir com o produto que foi selecionado na mesma página que
selecionou a data e daí clicar no add to cart"*. E sobre o caminho: *"sim um caminho somente levando
para o carrinho; de lá do carrinho para seguir com a compra requer criar a conta e seguir, lembre-se
que o único método de pagamento do site será o Stripe"*.

O que estes testes trancam:
- os quatro serviços de sessão nascem da **migração**, com os preços da Rate Card (719/719/819/899),
  ligados ao kart pela coluna `site_kart`;
- a migração **não destrói nem sobrescreve**: serviço que a equipe já criou para o kart é *ligado*, e
  preço, nome e estado de linha que já existe ficam como estão, subida após subida;
- o site acha o serviço **pela chave**, nunca por "o nome contém o nome do kart";
- **o painel manda no preço** (#50): painel e `KARTS` discordando, a página mostra o do painel;
- kart sem serviço ativo **sai da página**, em vez de oferecer o que não dá para comprar;
- a página do serviço tem **um** botão, o do carrinho, e o texto embaixo conta o caminho que existe
  (carrinho → conta → Stripe → waiver), não a invoice do QuickBooks;
- o carrinho **exige a conta** para seguir (#248) e o pagamento é **só Stripe**;
- os endereços de afiliado do urace.us não caem no 404 nem prometem programa (dono: *"encerra"*).
"""
import json
import os
import re

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir, todos, um  # noqa: E402
from command_center.providers import carrinho as ca, servicos_site as sv  # noqa: E402
from command_center.vitrine import conteudo as C, paginas, paginas_site as ps  # noqa: E402

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOST = "novo.urace.us"
CHAVES = ("Baby Kart", "4-stroke", "2-stroke", "Adult Shifter", "Own kart")   # #279: o kart próprio é a 5ª


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


@pytest.fixture()
def cli(tmp_path, monkeypatch):
    """O site, com o banco deste teste: a página sai com os serviços do painel."""
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "site.sqlite"))
    monkeypatch.setenv("CC_SITE_HOSTS", HOST)
    c = conectar(); aplicar_schema(c); c.close()
    with TestClient(app, base_url=f"http://{HOST}") as t:
        yield t


def _de_sessao(con):
    return {s["site_kart"]: s for s in todos(con, "SELECT * FROM booking_services WHERE site_kart IS NOT NULL "
                                                  "AND COALESCE(kind,'session')='session'")}


# --------------------------------------------------------------- a migração (#263)
def test_a_migracao_cria_os_quatro_servicos_do_site(con):
    """Sem ninguém cadastrar nada à mão: os quatro karts da página têm serviço, com o preço da Rate
    Card ditada pelo dono em 09/09 — o mesmo que a página mostra."""
    por_kart = _de_sessao(con)
    assert set(por_kart) == set(CHAVES) == {k["nome"] for k in C.KARTS}
    for k in C.KARTS:
        s = por_kart[k["nome"]]
        assert s["name"] == f"Arrive and Drive {k['nome']}"
        assert s["price"] == float(k["preco"]), k["nome"]
        assert s["active"] == 1 and (s["kind"] or "session") == "session"
        # o depósito é o que o próprio site publica nos termos desta página; o kart próprio (#279) não tem:
        # o depósito reembolsável cobre o kart da URACE
        assert s["deposit"] == float(k.get("deposito", 400)), k["nome"]
        # o site cobra pelo Stripe: item do QuickBooks nasce vazio (#263)
        assert s["qbo_item_id"] is None and s["invoice_text"] is None


def test_subir_de_novo_nao_duplica_nem_sobrescreve_o_que_a_equipe_mudou(con):
    """A migração roda em toda subida. O gerente mudar preço, nome ou estado é decisão dele: a subida
    seguinte não desfaz, e não cria uma segunda linha para o mesmo kart."""
    sid = _de_sessao(con)["2-stroke"]["id"]
    con.execute("UPDATE booking_services SET price=1234, name='2-stroke da equipe', active=0, deposit=0 WHERE id=?", (sid,))
    aplicar_schema(con)
    aplicar_schema(con)
    s = um(con, "SELECT * FROM booking_services WHERE id=?", (sid,))
    assert (s["price"], s["name"], s["active"], s["deposit"]) == (1234.0, "2-stroke da equipe", 0, 0)
    assert len(todos(con, "SELECT id FROM booking_services WHERE site_kart='2-stroke'")) == 1
    assert len(todos(con, "SELECT id FROM booking_services")) == len(C.KARTS) + 1, "os karts e o Lead and Follow (#279)"


def test_a_migracao_liga_o_servico_que_a_equipe_criou_em_vez_de_criar_outro(con):
    """O caso do dono: a equipe já tinha criado o serviço do kart à mão. A migração **liga** pela
    chave — não duplica e não mexe em preço, nome nem estado."""
    con.execute("DELETE FROM booking_services WHERE site_kart='Adult Shifter'")
    sid = inserir(con, "booking_services", name="Adult Shifter session (equipe)", price=950.0,
                  deposit=0.0, kind="session", active=0, sort=0)
    aplicar_schema(con)
    s = um(con, "SELECT * FROM booking_services WHERE id=?", (sid,))
    assert s["site_kart"] == "Adult Shifter", "liga pela chave o que a equipe já criou"
    assert (s["price"], s["name"], s["active"]) == (950.0, "Adult Shifter session (equipe)", 0), "nada é sobrescrito"
    assert len(todos(con, "SELECT id FROM booking_services WHERE site_kart='Adult Shifter'")) == 1


def test_a_linha_com_o_nome_do_padrao_e_ligada_mesmo_com_outra_parecida_ao_lado(con):
    """Banco que já subiu antes da coluna: a linha "Arrive and Drive <kart>" existe, sem chave, e ao
    lado há outra com o nome do kart. É a do padrão que é ligada — e nada é criado nem sobrescrito."""
    con.execute("DELETE FROM booking_services WHERE site_kart='4-stroke'")
    padrao = inserir(con, "booking_services", name="Arrive and Drive 4-stroke", price=699.0,
                     deposit=0.0, kind="session", active=1, sort=0)
    outro = inserir(con, "booking_services", name="4-stroke de sábado", price=750.0, kind="session", active=1)
    aplicar_schema(con)
    assert um(con, "SELECT site_kart FROM booking_services WHERE id=?", (padrao,))["site_kart"] == "4-stroke"
    assert um(con, "SELECT site_kart FROM booking_services WHERE id=?", (outro,))["site_kart"] is None
    assert um(con, "SELECT price FROM booking_services WHERE id=?", (padrao,))["price"] == 699.0, "nada sobrescrito"
    assert len(todos(con, "SELECT id FROM booking_services WHERE site_kart='4-stroke'")) == 1


def test_dois_candidatos_do_mesmo_kart_a_migracao_nao_escolhe_por_ninguem(con):
    """Duas linhas com o nome do kart é ambíguo: a migração não adivinha qual é a do site — cria a
    dela, com o nome do padrão, e deixa as outras em paz."""
    con.execute("DELETE FROM booking_services WHERE site_kart='Baby Kart'")
    a = inserir(con, "booking_services", name="Baby Kart manhã", price=500.0, kind="session", active=1)
    b = inserir(con, "booking_services", name="Baby Kart tarde", price=600.0, kind="session", active=1)
    aplicar_schema(con)
    assert um(con, "SELECT site_kart FROM booking_services WHERE id=?", (a,))["site_kart"] is None
    assert um(con, "SELECT site_kart FROM booking_services WHERE id=?", (b,))["site_kart"] is None
    nova = um(con, "SELECT * FROM booking_services WHERE site_kart='Baby Kart'")
    assert nova["name"] == "Arrive and Drive Baby Kart" and nova["price"] == 719.0


# --------------------------------------------------------------- a chave, não o nome (#263)
def test_o_site_acha_o_servico_pela_chave_e_nunca_pelo_nome(con):
    """O defeito de #253 em uma linha: um serviço chamado "teste" não é o produto, e um serviço com o
    nome do kart no nome também não é — do kart é o que tem a chave do kart."""
    inserir(con, "booking_services", name="teste", description="teste de produto", price=500.0, kind="session", active=1)
    fingido = inserir(con, "booking_services", name="Arrive and Drive 2-stroke (cópia)", price=1.0, kind="session", active=1)
    assert sv.do_kart(con, "teste") is None
    assert sv.do_kart(con, "2-stroke")["id"] == _de_sessao(con)["2-stroke"]["id"], "o do kart é o da chave"
    # tirar a chave do verdadeiro e deixar só o que tem o nome: nenhum é do kart
    con.execute("UPDATE booking_services SET site_kart=NULL WHERE site_kart='2-stroke'")
    assert sv.do_kart(con, "2-stroke") is None, "nome parecido não vale: a chave é exata"
    con.execute("UPDATE booking_services SET site_kart='2-stroke' WHERE id=?", (fingido,))
    assert sv.do_kart(con, "2-stroke")["id"] == fingido, "quem tem a chave é o do kart"


def test_a_chave_vem_na_lista_publica_e_so_aceita_kart_de_verdade(con):
    assert {s["site_kart"] for s in sv.para_cliente(con)} == set(CHAVES)
    sid = _de_sessao(con)["4-stroke"]["id"]
    assert sv.mudar(con, None, sid, {"site_kart": " 2-STROKE "})["site_kart"][1] == "2-stroke", "aparado, sem maiúscula"
    with pytest.raises(sv.ErroServico):
        sv.mudar(con, None, sid, {"site_kart": "Kart que não existe"})
    assert sv.mudar(con, None, sid, {"site_kart": ""})["site_kart"][1] is None, "vazio = não é do site"


def test_a_chave_do_kart_e_a_mesma_no_painel_na_pagina_e_no_banco(con):
    """Três lugares escrevem a chave: `KARTS`, a migração e o seletor do painel. Se um mudar sozinho,
    o kart desaparece do site sem ninguém entender — então os três andam juntos."""
    tsx = open(os.path.join(RAIZ, "command_center", "web", "src", "pages", "SitePublico.tsx"), encoding="utf-8").read()
    m = re.search(r"const KARTS_DO_SITE = \[([^\]]*)\]", tsx)
    assert m, "o painel precisa do seletor 'Kart do site' com as chaves"
    do_painel = tuple(x.strip().strip("'\"") for x in m.group(1).split(","))
    assert do_painel == tuple(k["nome"] for k in C.KARTS) == tuple(_de_sessao(con))


def test_o_agenda_js_casa_pela_chave_e_nao_volta_a_casar_pelo_nome():
    js = open(os.path.join(RAIZ, "command_center", "vitrine", "static", "agenda.js"), encoding="utf-8").read()
    assert "site_kart" in js, "a agenda do site acha o serviço pela chave"
    for ruim in ("s.name.toLowerCase().indexOf", "indexOf(k.nome"):
        assert ruim not in js, f"casar pelo nome é o defeito de #263 ({ruim})"


# --------------------------------------------------------------- o painel manda no preço (#50)
def test_o_painel_manda_no_preco_mesmo_discordando_de_karts(cli):
    """Regra do dono (#50): o preço vive no painel. Painel e `KARTS` discordando, a página, o resumo e
    o schema do Google mostram o do painel — nunca o do código."""
    con = conectar()
    sid = um(con, "SELECT id FROM booking_services WHERE site_kart='2-stroke'")["id"]
    con.execute("UPDATE booking_services SET price=1234 WHERE id=?", (sid,))
    con.close()
    html = cli.get(C.ARRIVE["caminho"]).text
    assert 'value="2-stroke" data-kart="2-stroke" data-preco="1234"' in html
    assert "$1,234" in html
    de_karts = next(k["preco"] for k in C.KARTS if k["nome"] == "2-stroke")
    assert f'data-preco="{de_karts:g}"' not in html.split('value="2-stroke"')[1].split("</label>")[0]
    servico = next(x for x in _ld(html) if x.get("@type") == "Service")
    assert "1234.00" in [o["price"] for o in servico["offers"]]


def _ld(html):
    return [json.loads(m) for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


# --------------------------------------------------------------- o kart sem serviço sai da página (#263)
def test_kart_sem_servico_ativo_sai_da_pagina(cli):
    con = conectar()
    con.execute("UPDATE booking_services SET active=0 WHERE site_kart='Baby Kart'")
    con.close()
    html = cli.get(C.ARRIVE["caminho"]).text
    assert 'value="Baby Kart"' not in html, "o kart que não dá para comprar não fica na página"
    assert 'value="2-stroke"' in html, "os outros continuam"
    servico = next(x for x in _ld(html) if x.get("@type") == "Service")
    assert len(servico["offers"]) == len(C.KARTS) - 1, "o Google também não recebe a oferta que saiu"


def test_sem_servico_nenhum_a_pagina_pede_contato_em_vez_de_oferecer(cli):
    con = conectar()
    con.execute("UPDATE booking_services SET active=0")
    con.close()
    html = cli.get(C.ARRIVE["caminho"]).text
    assert 'name="kart"' not in html, "nenhum kart à venda: nenhum botão de escolha"
    assert "Online booking is closed right now" in html
    assert C.SITE["emails"][0] in html and "wa.me" in html, "o aviso vem com o contato"
    servico = next(x for x in _ld(html) if x.get("@type") == "Service")
    assert "offers" not in servico and "potentialAction" not in servico, "nada à venda, nada prometido"
    assert len(re.findall(r"<h1[ >]", html)) == 1, "um h1 por página"


def test_o_painel_fora_do_ar_nao_apaga_a_pagina():
    """Banco fora não é "nada à venda": a página sai com os quatro karts de `KARTS` e o `agenda.js`
    corrige quando a lista do painel chegar."""
    html = paginas.arrive_and_drive(HOST, servicos=None)
    for k in C.KARTS:
        assert f'value="{k["nome"]}"' in html
    assert "Online booking is closed right now" not in html.split('class="karts"')[1].split("</fieldset>")[0]


# --------------------------------------------------------------- um caminho de compra só (#262)
def test_a_pagina_do_servico_tem_um_botao_e_ele_leva_ao_carrinho(cli):
    html = cli.get(C.ARRIVE["caminho"]).text
    assert "Continue to booking" not in html, "o segundo caminho saiu (dono, 15/10)"
    assert "/ops/portal/reserve" not in html, "o site público não oferece mais a reserva do portal"
    assert 'class="agenda-ir"' not in html
    assert html.count('class="btn btn-cheio agenda-carrinho"') == 1, "um botão só"
    assert 'data-carrinho="/cart/"' in html
    assert "Pick a day to continue" in html, "o botão diz o que falta antes de a agenda carregar"


def test_o_texto_embaixo_do_botao_conta_o_caminho_que_existe(cli):
    """O texto antigo prometia a invoice do QuickBooks, que o site público não oferece mais."""
    nota = paginas.NOTA_RESERVA
    assert "invoice" not in nota.lower() and "QuickBooks" not in nota
    for pedaco in ("cart", "account", "Stripe", "waiver", "deposit", "Track fees"):
        assert pedaco in nota, pedaco
    html = cli.get(C.ARRIVE["caminho"]).text
    assert paginas.e(nota) in html
    assert "Then you get the invoice" not in html


def test_do_carrinho_para_frente_a_conta_e_obrigatoria_e_o_pagamento_e_stripe(con):
    """#248 confirmado: sem a conta do site, o checkout do carrinho recusa — e o único checkout é o
    do Stripe (`providers/carrinho.py` não tem outro)."""
    sid = _de_sessao(con)["4-stroke"]["id"]
    itens = [{"tipo": "sessao", "servico": sid, "data": "2026-12-05", "turno": "manha"}]
    assert ca.cotar(con, itens, None)["precisa_conta"] is True
    with pytest.raises(ca.PrecisaConta):
        ca.criar_checkout(con, itens, "retirada", None, f"https://{HOST}", HOST)
    # o único checkout do carrinho é o do Stripe: não existe outro jeito de pagar pelo site
    fonte = open(os.path.join(RAIZ, "command_center", "providers", "carrinho.py"), encoding="utf-8").read()
    assert "stripe_loja.criar_sessao" in fonte or "stripe_loja" in fonte
    for outro in ("criar_invoice", "qbo_invoice", "invoice_link", "payment_link"):
        assert outro not in fonte, f"o site não oferece {outro}: o pagamento é só Stripe (#262)"


# --------------------------------------------------------------- afiliados encerrados (#262)
def test_os_enderecos_de_afiliado_vao_para_uma_pagina_publica_e_nao_prometem_nada(cli):
    for antigo in ("/affiliate-account/", "/affiliate-registration/", "/affiliate-reset-password/",
                   "/affiliate-login/", "/affiliate-area/", "/affiliates/"):
        assert ps.destino(antigo) == "/contact/", antigo
        r = cli.get(antigo, follow_redirects=False)
        assert r.status_code == 301 and r.headers["location"] == "/contact/", antigo
    assert cli.get("/contact/").status_code == 200


def test_nenhuma_pagina_do_site_novo_oferece_afiliacao(cli):
    """Não prometer um programa que não existe mais: a palavra só pode aparecer onde o site diz que a
    URACE **não** é afiliada a terceiros."""
    for caminho in ps.caminhos():
        texto = re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", "", cli.get(caminho).text, flags=re.S))
        for achado in re.findall(r"[^.]*\baffiliat\w*[^.]*", texto, re.I):
            assert "not affiliated" in achado.lower(), (caminho, achado.strip()[:200])
