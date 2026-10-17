"""#306: a seção Site do painel e o painel com as métricas do site.

Dono, 16/10: *"uma sessão dedicada exclusiva somente para o site … uma seção com subseções de cada painel de lá … E aí
também do site um dashboard com as métricas dele"*.

O que estes testes trancam:
- as visitas: cada página do site aberta por um navegador conta +1 no dia (da Flórida), sem IP nem cookie; robô,
  pré-carregamento, pedaço de página, HEAD, 404, redirecionamento e a volta do Stripe não contam; a entrada guarda de
  onde a pessoa veio (campanha, site ou app que mandou, direto) e navegar dentro do site não é entrada nova (o site
  manda `no-referrer`: quem diz é o `Sec-Fetch-Site`); a conta fica na memória e vai ao banco de uma vez; ninguém
  enche a tabela de fontes;
- o painel soma só o que o sistema tem: recebido (pedidos pagos no Stripe, a mensalidade do plano e a sessão paga
  pela invoice), o período anterior, o caminho do carrinho e o Buy now à parte, os mais vendidos sem depósito e
  frete, os agendamentos, as contas, os contatos e as campanhas uma vez por venda; o dia é o da Flórida; o período
  anterior medido pela metade não compara; as pendências olham os últimos 30 dias;
- só a equipe vê (operador para cima), com ETag e sem cache compartilhado;
- o menu ganhou a seção Site com uma subseção por painel.
"""
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from command_center.api import auth
from command_center.api.main import app
from command_center.db import inserir, todos, um
from command_center.tests.test_carrinho import loja  # noqa: F401
from command_center.tests.test_pedido_site import EMAIL, _pedido, _webhook, pedido_sessao  # noqa: F401
from command_center.tests.test_stripe_loja import amb  # noqa: F401

SENHA = "pista-molhada-7"
NAV = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1",
       "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate"}
FL = ZoneInfo("America/New_York")
REPO = Path(__file__).resolve().parents[2]


def _ps():
    from command_center.providers import painel_site
    return painel_site


def _iso(t):
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


@pytest.fixture()
def site(amb):  # noqa: F811 — o site (novo.urace.us) e o banco do teste
    _ps().zerar()                                       # a conta da memória é do processo: começa limpa
    return amb


@pytest.fixture()
def equipe(site):
    """O painel (outro endereço, o mesmo banco): um operador e alguém só de leitura."""
    cli, con, *_ = site
    auth.criar_usuario(con, "op.painel@example.com", "Operador Painel", "OPERATOR", SENHA)
    auth.criar_usuario(con, "ver.painel@example.com", "Leitura Painel", "VIEWER", SENHA)
    con.commit()
    with TestClient(app, base_url="https://cc.test") as t:
        yield t


def _entra(t, email):
    t.cookies.clear()
    assert t.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200


def _visitas(con):
    _ps().descarregar()
    return {r["path"]: r["n"] for r in todos(con, "SELECT path, SUM(n) AS n FROM site_views GROUP BY path")}


def _fontes(con):
    _ps().descarregar()
    return {r["source"]: r["n"] for r in todos(con, "SELECT source, SUM(n) AS n FROM site_sources GROUP BY source")}


# ------------------------------------------------------------------ 1. as visitas
def test_visita_conta_so_pagina_aberta_por_navegador(site):
    cli, con, *_ = site
    assert cli.get("/", headers=NAV).status_code == 200                                   # entrou direto
    cli.get("/services/arrive-and-drive/?utm_source=Instagram", headers={**NAV, "Sec-Fetch-Site": "cross-site"})
    cli.get("/academy/", headers={**NAV, "Sec-Fetch-Site": "cross-site", "Referer": "https://www.google.com/"})
    cli.get("/academy/", headers={**NAV, "Sec-Fetch-Site": "same-origin"})               # navegando no site
    cli.get("/cart/", headers={**NAV, "Sec-Fetch-Site": "same-origin"})
    # o que não conta
    cli.get("/academy/", headers={**NAV, "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"})
    cli.get("/academy/", headers={**NAV, "User-Agent": "Mozilla/5.0 (compatible; GoogleOther) Chrome/120"})
    cli.get("/academy/", headers={**NAV, "User-Agent": "python-httpx/0.27"})
    cli.get("/academy/", headers={**NAV, "Sec-Purpose": "prefetch"})
    cli.get("/academy/", headers={**NAV, "Sec-Fetch-Dest": "iframe"})
    cli.get("/academy/", headers={**NAV, "User-Agent": ""})
    cli.head("/academy/", headers=NAV)
    cli.get("/cart/?cancelled=1", headers={**NAV, "Sec-Fetch-Site": "cross-site", "Referer": "https://checkout.stripe.com/"})
    assert cli.get("/esta-pagina-nao-existe/", headers=NAV).status_code == 404
    assert cli.get("/academy", headers=NAV, follow_redirects=False).status_code == 301
    # gente de verdade com "bot" no nome do celular conta
    cli.get("/about/", headers={**NAV, "User-Agent": "Mozilla/5.0 (Linux; Android 11; CUBOT X50) Chrome/120 Mobile"})
    assert _visitas(con) == {"/": 1, "/services/arrive-and-drive/": 1, "/academy/": 2, "/cart/": 1, "/about/": 1}
    assert _fontes(con) == {"direto": 2, "instagram": 1, "google": 1}, "navegar dentro do site não é entrada nova"
    hoje = datetime.now(FL).date().isoformat()
    assert {r["day"] for r in todos(con, "SELECT day FROM site_views")} == {hoje}, "o dia é o da Flórida"
    # nada de quem é: só o dia, o endereço e a conta
    assert [c["name"] for c in con.execute("PRAGMA table_info(site_views)")] == ["day", "path", "n"]
    assert [c["name"] for c in con.execute("PRAGMA table_info(site_sources)")] == ["day", "source", "n"]


def test_de_onde_a_pessoa_entrou():
    hosts = {"novo.urace.us"}
    f = _ps().fonte_da_entrada
    assert f(None, None, hosts) == "direto" and f(None, None, hosts, "none") == "direto"
    assert f(None, None, hosts, "same-origin") is None, "o site manda no-referrer: dentro dele, o Sec-Fetch-Site diz"
    assert f(None, "instagram", hosts, "same-origin") is None, "o utm que o site leva de uma página a outra não é entrada"
    assert f(None, None, hosts, "cross-site") == "outro site"
    assert f("https://novo.urace.us/store/", None, hosts) is None
    assert f("https://novo.urace.us/store/", "Insta Gram!", hosts) == "instagram"
    assert f("https://www.google.com.br/", None, hosts, "cross-site") == "google"
    assert f("https://l.instagram.com/?u=x", None, hosts) == "instagram"
    assert f("https://m.facebook.com/", None, hosts) == "facebook"
    assert f("android-app://com.google.android.gm/", None, hosts) == "gmail", "o app do Gmail não é a busca do Google"
    assert f("https://checkout.stripe.com/c/pay/x", None, hosts, "cross-site") is None, "a volta do pagamento"
    assert f("https://www.kartingnews.example.com/post", None, hosts) == "kartingnews.example.com"
    assert f("http://[::1", None, hosts) is None


def test_ninguem_enche_a_tabela_de_fontes_e_uma_conexao_tem_limite(site, monkeypatch):
    cli, con, *_ = site
    ps = _ps()
    for i in range(ps.MAX_FONTES_DIA + 5):
        ps.anotar("/", f"lixo{i}")
    ps.descarregar()
    fontes = _fontes(con)
    assert len(fontes) == ps.MAX_FONTES_DIA + 1 and fontes["outros"] == 5
    # com o teto cheio de lixo, as fontes que o painel conhece continuam na linha delas
    for f in ("google", "direto", "instagram"):
        ps.anotar("/", f)
    fontes = _fontes(con)
    assert fontes["google"] == fontes["direto"] == fontes["instagram"] == 1 and fontes["outros"] == 5
    monkeypatch.setattr(ps, "MAX_POR_IP_HORA", 3)
    for _ in range(6):
        ps.anotar("/about/", None, ip="203.0.113.9")
    assert _visitas(con)["/about/"] == 3


def test_a_conta_fica_na_memoria_e_vai_ao_banco_de_uma_vez(site, monkeypatch):
    cli, con, *_ = site
    ps = _ps()
    cli.get("/", headers=NAV)
    cli.get("/about/", headers=NAV)
    assert not todos(con, "SELECT * FROM site_views"), "nada de gravar a cada visita"
    assert ps.descarregar() == 2 and _visitas(con) == {"/": 1, "/about/": 1}
    # banco ocupado: a conta volta para a memória e entra na próxima vez
    ps.anotar("/academy/", None)
    import sqlite3

    from command_center import db

    def ocupado(*a, **k):
        raise sqlite3.OperationalError("database is locked")
    with monkeypatch.context() as m:
        m.setattr(db, "conectar", ocupado)
        assert ps.descarregar() == 0
    assert _visitas(con)["/academy/"] == 1


def test_de_onde_veio_a_venda():
    f = _ps()._fonte_utm
    assert f(json.dumps({"utm_source": "Instagram"})) == "instagram"
    assert f(json.dumps({"gclid": "x"})) == "google ads"
    assert f(json.dumps({"fbclid": "x"})) == "facebook/instagram", "um clique no Facebook não é por si um anúncio"
    assert f(json.dumps({"fbclid": "x", "campaign_id": "123"})) == "meta ads"
    assert f(None) is None and f("lixo") is None


def test_try_again_guarda_a_campanha(pedido_sessao):  # noqa: F811
    """O pagamento não passou e a pessoa toca em "Try again": o pedido novo continua com a campanha do primeiro."""
    cli, con, st, qbo, tmp, sid, conta, pid, dia, p, s = pedido_sessao
    con.execute("UPDATE store_orders SET utm=?", (json.dumps({"utm_source": "instagram", "utm_campaign": "outubro"}),))
    con.commit()
    s.update(customer_details={"email": EMAIL, "name": "Maya Teste"})
    _webhook(cli, s, "checkout.session.async_payment_failed", "evt_u1")
    velho = _pedido(con)
    from command_center.providers import pedido_site
    r = cli.post(f"/order/{pedido_site.token(velho)}/retry", data={"csrf": cli.cookies.get("cp_csrf")}, follow_redirects=False)
    assert r.status_code == 303
    novo = _pedido(con)
    assert novo["id"] != velho["id"] and json.loads(novo["utm"]) == {"utm_source": "instagram", "utm_campaign": "outubro"}


def test_contar_visita_nunca_derruba_a_pagina(site):
    cli, con, *_ = site
    con.execute("DROP TABLE site_views")
    con.commit()
    assert cli.get("/", headers=NAV).status_code == 200
    _ps().descarregar()


# ------------------------------------------------------------------ 2. o painel
def _semear(con, agora):
    conta = inserir(con, "portal_accounts", email="ana.painel@example.com", pw_salt="x", pw_hash="x", name="Ana Painel",
                    birth_date="1980-01-01", terms_accepted_at=_iso(agora), created_at=_iso(agora - timedelta(days=2)))

    def pedido(status, valor, pago=None, criado=1, kind="carrinho", slug="carrinho", nome="Carrinho", qtd=1, dep=0.0, unit=None):
        return inserir(con, "store_orders", kind=kind, product_slug=slug, product_name=nome, quantity=qtd,
                       unit_price=unit if unit is not None else valor / qtd, amount=valor, delivery="retirada", status=status,
                       deposit=dep, created_at=_iso(agora - timedelta(days=criado)), stripe_session_id=f"cs_{status}_{valor}",
                       paid_at=_iso(agora - timedelta(days=pago)) if pago is not None else None,
                       amount_paid=valor if status == "pago" else None)
    o1 = pedido("pago", 1119.0, pago=1, dep=400.0)
    inserir(con, "store_order_items", order_id=o1, kind="sessao", name="Arrive and Drive 4-stroke · Tue", service_name="Arrive and Drive 4-stroke",
            quantity=1, unit_price=719.0, deposit=400.0, amount=1119.0)
    pedido("pago", 100.0, pago=3, kind="produto", slug="luva-teste", nome="Luva Teste", qtd=2, unit=45.0)   # + frete de 10
    pedido("aguardando", 50.0)
    pedido("expirado", 70.0)
    pedido("falhou", 10.0)
    inserir(con, "store_orders", kind="carrinho", product_slug="carrinho", product_name="Carrinho", quantity=1, unit_price=5,
            amount=5, delivery="retirada", status="aberto", created_at=_iso(agora - timedelta(days=1)))   # nunca chegou ao Stripe
    pedido("pago", 500.0, pago=40, criado=40)                       # o período anterior
    sid = um(con, "SELECT id FROM booking_services ORDER BY id LIMIT 1")["id"]
    inserir(con, "plan_orders", account_id=conta, service_id=sid, service_name="Academy 1 month", price=2756.9, months=1,
            start_month="2026-11", status="ativa", invoice_total=2756.9, paid_at=_iso(agora - timedelta(days=5)),
            utm=json.dumps({"utm_source": "instagram"}), created_at=_iso(agora - timedelta(days=6)))
    # sem a invoice gravada, conta a mensalidade (nunca o contrato de 6 meses inteiro)
    inserir(con, "plan_orders", account_id=conta, service_id=sid, service_name="Academy 6 months", price=689.0, months=6,
            start_month="2026-11", status="ativa", paid_at=_iso(agora - timedelta(days=5)), created_at=_iso(agora - timedelta(days=6)))
    futuro = (datetime.now(FL).date() + timedelta(days=9)).isoformat()
    inserir(con, "bookings", account_id=conta, date=futuro, period="manha", status="confirmada", origin="site",
            utm=json.dumps({"utm_source": "google"}), created_at=_iso(agora - timedelta(days=2)),
            invoice_total=1119.0, paid_at=_iso(agora - timedelta(days=2)))          # sessão paga pela invoice
    inserir(con, "bookings", account_id=conta, date=futuro, period="tarde", status="cancelada", origin="portal",
            created_at=_iso(agora - timedelta(days=2)))
    inserir(con, "bookings", account_id=conta, date=futuro, period="dia", status="pendente", origin="site", store_order_id=o1,
            utm=json.dumps({"utm_source": "nao-conta-de-novo"}), created_at=_iso(agora - timedelta(days=1)))   # o do carrinho
    inserir(con, "opportunities", name="Ana Painel", source="Site", stage="GANHO", campaign=json.dumps({"utm_source": "instagram"}),
            created_at=_iso(agora - timedelta(days=4)))
    opp_pedido = inserir(con, "opportunities", name="Ana Painel", source="Site", stage="GANHO", created_at=_iso(agora - timedelta(days=1)))
    con.execute("UPDATE store_orders SET opp_id=? WHERE id=?", (opp_pedido, o1))          # a venda do pedido: conta uma vez
    inserir(con, "opportunities", name="Bruno Fora", source="Indicação", stage="NOVO", created_at=_iso(agora - timedelta(days=4)))
    con.commit()


def test_o_painel_soma_o_que_o_sistema_tem(site, equipe):
    cli, con, *_ = site
    _semear(con, datetime.now(timezone.utc))
    cli.get("/", headers=NAV)
    cli.get("/cart/", headers={**NAV, "Sec-Fetch-Site": "same-origin"})
    _entra(equipe, "op.painel@example.com")
    r = equipe.get("/ops/api/site/painel?dias=30")
    assert r.status_code == 200, r.text
    d = r.json()
    v = d["vendas"]
    assert (v["loja_e_carrinho"], v["planos"], v["sessoes_invoice"]) == (1219.0, 3445.9, 1119.0)
    assert v["receita"] == 5783.9
    assert (v["pedidos_pagos"], v["planos_pagos"], v["sessoes_pagas_invoice"], v["deposito"], v["ticket_medio"]) == (2, 2, 1, 400.0, 609.5)
    assert (v["receita_ant"], v["pedidos_pagos_ant"]) == (500.0, 1), "o período anterior para comparar"
    c, b = d["pagamento"]["carrinho"], d["pagamento"]["buy_now"]
    assert (c["foram"], c["pago"], c["aguardando"], c["expirado"], c["falhou"], c["conversao"]) == (4, 1, 1, 1, 1, 25.0), \
        "o pedido que nunca chegou ao Stripe não conta"
    assert (b["foram"], b["pago"]) == (1, 1)
    assert [f["n"] for f in d["pagamento"]["funil"]] == [1, 4, 1]
    assert d["produtos"] == [{"nome": "Luva Teste", "qtd": 2, "receita": 90.0}], "sem o frete"
    assert d["servicos"] == [{"nome": "Arrive and Drive 4-stroke", "qtd": 1, "receita": 719.0}], "sem o depósito que volta"
    s = d["sessoes"]
    assert (s["marcadas"], s["canceladas"], s["pelo_site"], s["pela_area"], s["proximas"]) == (2, 1, 2, 0, 2)
    assert s["pelo_site"] + s["pela_area"] == s["marcadas"], "a divisão soma o total (o cancelado fica só em cancelados)"
    assert d["contas"]["novas"] == 1 and d["contas"]["sem_vinculo"] == 1
    assert (d["leads"]["novos"], d["leads"]["ganhos"]) == (2, 2), "só o que veio do site"
    # os 2 pedidos pagos sem campanha, o agendamento cancelado e o plano sem utm; o agendamento e a oportunidade do
    # pedido não contam de novo (uma vez por venda)
    assert d["campanhas"] == {"com_campanha": [{"fonte": "instagram", "n": 2}, {"fonte": "google", "n": 1}], "sem_campanha": 4}
    assert (d["visitas"]["total"], d["visitas"]["carrinho"], d["visitas"]["entradas"]) == (2, 1, 1)
    assert len(d["dias"]) == 30 and round(sum(x["receita"] for x in d["dias"]), 2) == 5783.9
    assert sum(x["pedidos"] for x in d["dias"]) == 2 and sum(x["visitas"] for x in d["dias"]) == 2
    assert d["atencao"]["contas_sem_vinculo"] == 1 and d["atencao"]["janela_dias"] == 30
    assert d["saude"]["paginas"]["n"] >= 2
    # 7 dias: o que é de até 6 dias atrás entra; o pedido de 40 dias não
    d7 = equipe.get("/ops/api/site/painel?dias=7").json()
    assert d7["periodo"]["dias"] == 7 and len(d7["dias"]) == 7 and d7["vendas"]["receita"] == 5783.9
    assert equipe.get("/ops/api/site/painel?dias=1000").json()["periodo"]["dias"] == 30, "período fora da lista vira 30"


def test_o_dia_e_o_da_florida(site):
    cli, con, *_ = site
    # 03:30 em UTC do dia 10 = 23:30 do dia 9 na Flórida (horário de verão)
    inserir(con, "store_orders", kind="produto", product_slug="x-teste", product_name="X Teste", quantity=1, unit_price=100.0,
            amount=100.0, delivery="retirada", status="pago", amount_paid=100.0, created_at="2026-10-10T03:20:00.000Z",
            paid_at="2026-10-10T03:30:00.000Z")
    # 23:59 do dia 3 na Flórida: fora do período de 7 dias que começa no dia 4
    inserir(con, "store_orders", kind="produto", product_slug="y-teste", product_name="Y Teste", quantity=1, unit_price=40.0,
            amount=40.0, delivery="retirada", status="pago", amount_paid=40.0, created_at="2026-10-04T03:50:00.000Z",
            paid_at="2026-10-04T03:59:00.000Z")
    con.commit()
    d = _ps().painel(con, 7, hoje=date(2026, 10, 10))
    assert (d["periodo"]["de"], d["periodo"]["ate"]) == ("2026-10-04", "2026-10-10")
    dia = {x["dia"]: x for x in d["dias"]}
    assert dia["2026-10-09"]["receita"] == 100.0 and dia["2026-10-10"]["receita"] == 0
    assert d["vendas"]["receita"] == 100.0 and d["vendas"]["receita_ant"] == 40.0


def test_periodo_anterior_medido_pela_metade_nao_compara(site):
    cli, con, *_ = site
    for dia, n in (("2026-10-05", 3), ("2026-10-08", 7)):
        con.execute("INSERT INTO site_views(day, path, n) VALUES(?, '/', ?)", (dia, n))
    con.commit()
    d = _ps().painel(con, 7, hoje=date(2026, 10, 10))
    assert d["visitas"]["total"] == 10 and d["visitas"]["desde"] == "2026-10-05"
    assert d["visitas"]["total_ant"] is None and d["visitas"]["parcial"], "começou a contar no meio: não inventa crescimento"
    d = _ps().painel(con, 7, hoje=date(2026, 10, 20))
    assert d["visitas"]["total_ant"] == 7 and not d["visitas"]["parcial"]


def test_pendencias_olham_os_ultimos_30_dias(site):
    cli, con, *_ = site
    agora = datetime.now(timezone.utc)
    o = inserir(con, "store_orders", kind="carrinho", product_slug="carrinho", product_name="Carrinho", quantity=1, unit_price=719,
                amount=719, delivery="retirada", status="pago", amount_paid=719, created_at=_iso(agora - timedelta(days=12)),
                paid_at=_iso(agora - timedelta(days=12)))
    inserir(con, "store_order_items", order_id=o, kind="sessao", name="Sessão", quantity=1, unit_price=719, amount=719, status="sem_vaga")
    inserir(con, "store_order_notices", order_id=o, result="pago", error="Gmail fora do ar", created_at=_iso(agora - timedelta(days=12)))
    con.commit()
    d = _ps().painel(con, 7)
    assert d["atencao"]["pedidos_sem_vaga"] == 1, "de 12 dias atrás e ainda sem solução: aparece mesmo na visão de 7 dias"
    assert d["atencao"]["avisos_falharam"] == 1
    con.execute("UPDATE store_order_items SET booking_id=(SELECT MIN(id) FROM bookings), status='marcada'")
    con.execute("UPDATE store_order_notices SET sent_at=?", (_iso(agora),))
    con.commit()
    d = _ps().painel(con, 7)
    assert d["atencao"]["pedidos_sem_vaga"] == 0 and d["atencao"]["avisos_falharam"] == 0, "resolveu: some"


def test_so_a_equipe_ve_o_painel_com_etag_e_sem_cache_compartilhado(site, equipe):
    assert equipe.get("/ops/api/site/painel").status_code == 401
    _entra(equipe, "ver.painel@example.com")
    assert equipe.get("/ops/api/site/painel").status_code == 403
    _entra(equipe, "op.painel@example.com")
    r = equipe.get("/ops/api/site/painel")
    assert r.status_code == 200 and r.headers.get("etag")
    assert "public" not in (r.headers.get("cache-control") or "")
    assert equipe.get("/ops/api/site/painel", headers={"If-None-Match": r.headers["etag"]}).status_code == 304


def test_vazio_e_zero_de_verdade(site, equipe):
    """NO FAKE DATA: sem pedido e sem visita, o painel mostra zero e "sem dado", nunca um número inventado."""
    _entra(equipe, "op.painel@example.com")
    d = equipe.get("/ops/api/site/painel").json()
    assert d["vendas"]["receita"] == 0 and d["vendas"]["ticket_medio"] is None
    assert d["pagamento"]["carrinho"]["conversao"] is None and d["pagamento"]["buy_now"]["foram"] == 0
    assert d["visitas"]["total"] == 0 and d["visitas"]["desde"] is None and d["visitas"]["total_ant"] is None
    assert d["produtos"] == [] and d["servicos"] == []


# ------------------------------------------------------------------ 3. o menu
def test_o_menu_tem_a_secao_site_com_uma_subsecao_por_painel():
    shell = (REPO / "command_center/web/src/components/Shell.tsx").read_text(encoding="utf-8")
    i = shell.index('<div className="grp">{tr("Site")}</div>')
    bloco = shell[i:shell.index('<div className="grp">', i + 10)]
    rotas = re.findall(r'<NL to="([^"]+)"', bloco)
    assert rotas == ["/site", "/site/pedidos", "/site/agendamentos", "/site/disponibilidade", "/site/servicos", "/site/cartoes",
                     "/site/produtos", "/site/estoque", "/site/editor", "/site/blog", "/site/contas", "/site/waiver",   # #309, #172
                     "/site/deposito"]   # #317
    assert "Agendamentos do site" not in shell, "o item antigo saiu da Logística"
    sub = (REPO / "command_center/web/src/pages/SitePublico.tsx").read_text(encoding="utf-8")
    assert re.findall(r"to: '(/site[^']*)'", sub) == rotas, "as abas da página são as mesmas subseções do menu"


# ------------------------------------------------------------------ 4. a campanha da venda do site
def test_a_venda_do_carrinho_e_do_buy_now_guarda_a_campanha_e_conta_uma_vez(site, equipe):
    """O carrinho manda o que o campanha.js guardou; o Buy now leva os campos escondidos. O pedido, o agendamento e a
    venda que ele gera ficam com a campanha, e o painel conta a venda uma vez."""
    cli, con, st, *_ = site
    from command_center.providers import servicos_site
    from command_center.tests.test_agenda_sessoes import abre, proximo
    from command_center.tests.test_carrinho import _entrar, _pagar, _sessao
    from command_center.tests.test_stripe_loja import _simples
    inserir(con, "qbo_items", id="11", name="Arrive and Drive 4T", price=719)
    sid = um(con, "SELECT id FROM booking_services WHERE site_kart='4-stroke'")["id"]
    servicos_site.mudar(con, None, sid, {"qbo_item": "Arrive and Drive 4T"})
    abre(con, cap=1)
    con.commit()
    conta, pid = _entrar(cli, con)
    r = cli.post("/ops/api/vitrine/carrinho/checkout", headers={"X-CSRF": cli.cookies.get("cp_csrf")},
                 json={"itens": [_sessao(sid, proximo(5), pid)], "entrega": "retirada",
                       "utm": {"utm_source": "instagram", "utm_campaign": "outubro", "email": "nao-entra@example.com"}})
    assert r.status_code == 200, r.text
    o = um(con, "SELECT * FROM store_orders")
    assert json.loads(o["utm"]) == {"utm_source": "instagram", "utm_campaign": "outubro"}, "só campanha, nada da pessoa"
    assert _pagar(cli, st, next(iter(st.sessoes))).json()["resultado"] == "pago"
    assert json.loads(um(con, "SELECT utm FROM bookings")["utm"])["utm_source"] == "instagram"
    assert json.loads(um(con, "SELECT campaign FROM opportunities")["campaign"])["utm_campaign"] == "outubro"
    # o Buy now: os campos escondidos do formulário
    p = _simples()
    r = cli.post("/ops/api/vitrine/checkout", data={"produto": p["slug"], "quantidade": "1", "entrega": "retirada",
                                                    "utm_source": "google", "gclid": "abc"}, follow_redirects=False)
    assert r.status_code == 303, r.text
    buy = um(con, "SELECT utm FROM store_orders WHERE kind='produto'")
    assert json.loads(buy["utm"]) == {"utm_source": "google", "gclid": "abc"}
    _entra(equipe, "op.painel@example.com")
    d = equipe.get("/ops/api/site/painel").json()
    assert d["campanhas"]["com_campanha"] == [{"fonte": "instagram", "n": 1}], \
        "a venda do carrinho conta uma vez (o agendamento e a oportunidade dela não contam de novo); o Buy now não pagou"
