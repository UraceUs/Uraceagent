"""O painel do site (#306): as métricas do site público num lugar só, com os números de verdade do sistema.

Dono, 16/10: *"uma sessão dedicada exclusiva somente para o site … uma seção com subseções de cada painel de lá … E aí
também do site um dashboard com as métricas dele"*.

De onde vem cada número (nada inventado: o que não existe ainda aparece como "sem dado"):
- **recebido**: os pedidos do site pagos no Stripe (`store_orders`, carrinho e loja), os planos mensais (a mensalidade
  paga, `plan_orders`) e as sessões da área do cliente pagas pela invoice (`bookings` sem pedido do carrinho);
- **pagamento**: o caminho do carrinho (abriram → foram ao Stripe → pagaram) e, à parte, o Buy now da loja;
- **sessões**: os agendamentos que vieram do site e da área do cliente (`bookings.origin`);
- **contas, contatos e campanhas**: `portal_accounts`, as oportunidades com origem Site e o `utm` de cada venda (uma
  vez por venda: a oportunidade e o agendamento que um pedido gera não contam de novo);
- **visitas**: contadas aqui mesmo, a cada página do site aberta (sem IP, sem cookie, sem quem é: só o endereço, o
  dia e de onde veio a entrada). Robôs não contam. Ficam na memória e vão para o banco de uma vez, a cada 30 s
  (gravar a cada visita travaria o banco do painel). Começa a contar no dia do deploy;
- **saúde**: as requisições e os erros das páginas do site desde o último reinício do servidor.
"""
import atexit
import json
import re
import sqlite3
import threading
import time as relogio
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from command_center.db import todos, um

FUSO = ZoneInfo("America/New_York")
PERIODOS = (7, 30, 90)
JANELA_PENDENCIAS = 30          # dias: o que ainda pede a equipe, qualquer que seja o período escolhido
DESCARREGAR_S = 30
MAX_FONTES_DIA = 40             # passou disso, a fonte nova entra como "outros" (ninguém enche a tabela)
MAX_POR_IP_HORA = 300           # uma conexão que abre mais do que isso numa hora não é gente
# robôs e bibliotecas (o celular CUBOT tem "bot" no nome e é gente; o navegador do Telegram também)
ROBO = re.compile(r"[a-z]bot\b|bot/|\bbot\b|crawl|spider|slurp|googleother|google-inspectiontool|-user/|python|curl|wget|"
                  r"httpx|go-http|axios|node-fetch|okhttp|scrapy|headless|lighthouse|pingdom|uptime|monitor|preview|"
                  r"facebookexternalhit|whatsapp/|embedly", re.I)
CONHECIDAS = (("google", "google."), ("instagram", "instagram.com"), ("facebook", "facebook.com"), ("bing", "bing.com"),
              ("youtube", "youtube.com"), ("tiktok", "tiktok.com"), ("chatgpt", "chatgpt.com"), ("chatgpt", "openai.com"),
              ("duckduckgo", "duckduckgo.com"), ("yahoo", "yahoo."), ("whatsapp", "whatsapp."), ("kommo", "kommo.com"))
APPS = {"com.google.android.gm": "gmail", "com.instagram.android": "instagram", "com.facebook.katana": "facebook",
        "com.google.android.googlequicksearchbox": "google", "com.whatsapp": "whatsapp"}
DA_JORNADA = ("stripe.com",)    # a volta do pagamento não é uma entrada nova
FIXAS = {n for n, _ in CONHECIDAS} | set(APPS.values()) | {"direto", "outro site", "app", "outros"}

_TRAVA = threading.Lock()
_VISTAS, _FONTES = Counter(), Counter()                     # (dia, caminho) | (dia, fonte) → n, ainda não gravados
_POR_IP = {}                                                # ip → (hora, n): só na memória, some a cada hora
_ULTIMA = [relogio.monotonic()]


# ------------------------------------------------------------------ 1. contar as visitas
def fonte_da_entrada(referer, utm_source, hosts, sec_fetch_site=None):
    """De onde a pessoa ENTROU no site: a campanha (`utm_source`), o site ou o app que mandou, ou "direto". None quando
    ela já estava no site. O site manda `Referrer-Policy: no-referrer`, então dentro dele o navegador não diz de onde
    veio: quem diz é o `Sec-Fetch-Site` (same-origin = navegando no site)."""
    sfs = (sec_fetch_site or "").lower()
    if sfs == "same-origin":
        return None
    u = re.sub(r"[^a-z0-9._-]", "", (utm_source or "").strip().lower())[:60]
    if u:
        return u
    if sfs == "none" or not referer:
        return "direto" if sfs in ("none", "") else "outro site"
    try:
        partes = urlsplit(referer)
        h = (partes.hostname or "").lower()
    except ValueError:
        return None
    if partes.scheme == "android-app":                      # o app que abriu o link (o Gmail, o Instagram…)
        return APPS.get(h, "app")
    if not h or h in hosts:
        return None
    if any(h == d or h.endswith("." + d) for d in DA_JORNADA):
        return None
    h = re.sub(r"^(www|m|l|lm|out)\.", "", h)
    for nome, dominio in CONHECIDAS:
        if h.startswith(dominio) or ("." + dominio) in "." + h:
            return nome
    return h[:60]


def conta(request, metodo, status):
    """Esta abertura de página entra na contagem? Só GET que deu certo, de navegador, abrindo a página (não
    pré-carregamento, não um pedaço dela), de quem não é robô."""
    if metodo != "GET" or status not in (200, 304):
        return False
    h = request.headers
    if (h.get("sec-purpose") or h.get("purpose") or "").lower().startswith("prefetch"):
        return False
    if h.get("sec-fetch-dest") and h.get("sec-fetch-dest") != "document":
        return False
    if h.get("sec-fetch-mode") and h.get("sec-fetch-mode") != "navigate":
        return False
    ua = (h.get("user-agent") or "").lower().replace("cubot", "")
    return bool(ua) and not ROBO.search(ua)


def _demais(ip):
    hora = int(relogio.time() // 3600)
    if len(_POR_IP) > 20000:                                # nunca cresce sem limite
        _POR_IP.clear()
    h, n = _POR_IP.get(ip, (hora, 0))
    n = n + 1 if h == hora else 1
    _POR_IP[ip] = (hora, n)
    return n > MAX_POR_IP_HORA


def anotar(caminho, fonte, ip=None, quando=None):
    """+1 na página (e na entrada, quando é uma), na memória. Devolve True quando já é hora de gravar."""
    dia = (quando or datetime.now(FUSO)).astimezone(FUSO).date().isoformat()
    with _TRAVA:
        if ip and _demais(ip):
            return False
        _VISTAS[(dia, (caminho or "/")[:200])] += 1
        if fonte:
            _FONTES[(dia, fonte)] += 1
        return relogio.monotonic() - _ULTIMA[0] >= DESCARREGAR_S


def descarregar():
    """Grava o que está na memória numa transação só, sem esperar o banco ocupado (tenta de novo depois)."""
    from command_center.db import conectar
    with _TRAVA:
        vistas, fontes = dict(_VISTAS), dict(_FONTES)
        _VISTAS.clear()
        _FONTES.clear()
        _ULTIMA[0] = relogio.monotonic()
    if not vistas and not fontes:
        return 0
    con = None
    try:
        con = conectar()
        con.execute("PRAGMA busy_timeout = 300")
        con.execute("BEGIN IMMEDIATE")
        for (dia, caminho), n in vistas.items():
            con.execute("""INSERT INTO site_views(day, path, n) VALUES(?, ?, ?)
                           ON CONFLICT(day, path) DO UPDATE SET n = n + excluded.n""", (dia, caminho, n))
        for (dia, fonte), n in fontes.items():
            ja = um(con, "SELECT 1 AS x FROM site_sources WHERE day=? AND source=?", (dia, fonte))
            if not ja and fonte not in FIXAS and um(con, f"""SELECT COUNT(*) AS n FROM site_sources WHERE day=?
                                                            AND source NOT IN ({",".join("?" * len(FIXAS))})""",
                                                         (dia, *sorted(FIXAS)))["n"] >= MAX_FONTES_DIA:
                fonte = "outros"
            con.execute("""INSERT INTO site_sources(day, source, n) VALUES(?, ?, ?)
                           ON CONFLICT(day, source) DO UPDATE SET n = n + excluded.n""", (dia, fonte, n))
        con.execute("COMMIT")
        return sum(vistas.values())
    except sqlite3.Error:
        if con is not None and con.in_transaction:
            con.execute("ROLLBACK")
        with _TRAVA:                                        # banco ocupado: fica para a próxima (nada se perde)
            _VISTAS.update(vistas)
            _FONTES.update(fontes)
        return 0
    finally:
        if con is not None:
            con.close()


atexit.register(descarregar)


def zerar():
    """Para os testes."""
    with _TRAVA:
        _VISTAS.clear()
        _FONTES.clear()
        _POR_IP.clear()
        _ULTIMA[0] = relogio.monotonic()


# ------------------------------------------------------------------ 2. o painel
def _limites(dias, hoje=None):
    """(primeiro dia, último dia, início em UTC, fim em UTC) do período, no fuso da Flórida."""
    hoje = hoje or datetime.now(FUSO).date()
    de = hoje - timedelta(days=dias - 1)
    ini = datetime.combine(de, time.min, FUSO).astimezone(timezone.utc)
    fim = datetime.combine(hoje + timedelta(days=1), time.min, FUSO).astimezone(timezone.utc)
    return de, hoje, ini.strftime("%Y-%m-%dT%H:%M:%S"), fim.strftime("%Y-%m-%dT%H:%M:%S")


def _dia_fl(iso):
    """A data na Flórida de um instante gravado em UTC."""
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(FUSO).date().isoformat()


def _valor(o):
    return float(o["amount_paid"] if o["amount_paid"] is not None else o["amount"] or 0)


def _pct(a, b):
    return round(100 * a / b, 1) if b else None


def _fonte_utm(utm):
    try:
        d = json.loads(utm) if utm else {}
    except ValueError:
        d = {}
    if not isinstance(d, dict):
        return None
    if d.get("utm_source"):
        return str(d["utm_source"]).strip().lower()[:60]
    if d.get("gclid"):
        return "google ads"                             # o gclid só vem de anúncio do Google
    if d.get("campaign_id") or d.get("adset_id"):
        return "meta ads"                               # o id de campanha e de conjunto vêm do anúncio do Meta
    if d.get("fbclid") or d.get("fbc"):
        return "facebook/instagram"                     # um clique no Facebook ou no Instagram (pode ser post orgânico)
    return None


def _recebido(con, ini, fim):
    """Tudo o que entrou de dinheiro pelo site no período, cada um com o dia (Flórida) em que entrou."""
    pagos = todos(con, """SELECT o.id, o.kind, o.amount, o.amount_paid, o.paid_at,
                                 COALESCE(o.deposit, (SELECT SUM(i.deposit) FROM store_order_items i WHERE i.order_id=o.id), 0) AS dep
                            FROM store_orders o WHERE o.status='pago' AND o.paid_at>=? AND o.paid_at<?""", (ini, fim))
    # o plano: a mensalidade paga (invoice_total; sem ela, o preço de um mês — nunca o contrato inteiro)
    planos = todos(con, """SELECT COALESCE(NULLIF(invoice_total, 0), price, 0) AS valor, paid_at FROM plan_orders
                            WHERE paid_at IS NOT NULL AND paid_at>=? AND paid_at<?""", (ini, fim))
    # a sessão da área do cliente paga pela invoice do QuickBooks (a do carrinho já está no pedido)
    sessoes = todos(con, """SELECT COALESCE(NULLIF(invoice_total, 0), price, 0) AS valor, paid_at FROM bookings
                             WHERE origin IN ('site','portal') AND store_order_id IS NULL AND paid_at IS NOT NULL
                               AND paid_at>=? AND paid_at<? AND status<>'recusada'""", (ini, fim))
    loja = round(sum(_valor(o) for o in pagos), 2)
    rec_planos = round(sum(float(p["valor"]) for p in planos), 2)
    rec_sessoes = round(sum(float(s["valor"]) for s in sessoes), 2)
    resumo = {"receita": round(loja + rec_planos + rec_sessoes, 2), "loja_e_carrinho": loja, "planos": rec_planos,
              "sessoes_invoice": rec_sessoes, "pedidos_pagos": len(pagos), "planos_pagos": len(planos),
              "sessoes_pagas_invoice": len(sessoes), "deposito": round(sum(float(o["dep"] or 0) for o in pagos), 2),
              "ticket_medio": round(loja / len(pagos), 2) if pagos else None}
    entradas = ([(o["paid_at"], _valor(o), 1) for o in pagos] + [(p["paid_at"], float(p["valor"]), 0) for p in planos]
                + [(s["paid_at"], float(s["valor"]), 0) for s in sessoes])
    return entradas, resumo


def _pagamento(con, ini, fim, carrinho_aberto):
    """O carrinho (abriram → foram ao Stripe → pagaram) e o Buy now, cada um com a sua conta."""
    def por(kind):
        out = {s: 0 for s in ("pago", "aguardando", "falhou", "expirado", "aberto")}
        for r in todos(con, """SELECT status, COUNT(*) AS n FROM store_orders WHERE kind=? AND stripe_session_id IS NOT NULL
                                 AND created_at>=? AND created_at<? GROUP BY status""", (kind, ini, fim)):
            out[r["status"]] = r["n"]
        out["foram"] = sum(out.values())
        out["conversao"] = _pct(out["pago"], out["foram"])
        return out
    carrinho, direto = por("carrinho"), por("produto")
    return {"carrinho": carrinho, "buy_now": direto,
            "funil": [{"etapa": "carrinho", "n": carrinho_aberto}, {"etapa": "checkout", "n": carrinho["foram"]},
                      {"etapa": "pago", "n": carrinho["pago"]}]}


def _itens_vendidos(con, ini, fim):
    """Os produtos e as sessões vendidos no período (carrinho e Buy now). O valor é o do item (preço × quantidade),
    sem o depósito que volta, o frete e o add-on; o mesmo produto (ou serviço) numa linha só."""
    prods, sess = {}, {}

    def soma(alvo, chave, nome, q, v):
        d = alvo.setdefault(chave, {"nome": nome or "—", "qtd": 0, "receita": 0.0})
        d["qtd"] += q
        d["receita"] = round(d["receita"] + v, 2)
    for x in todos(con, """SELECT i.kind, i.name, i.service_name, i.service_id, i.product_slug, i.quantity, i.unit_price
                             FROM store_order_items i JOIN store_orders o ON o.id=i.order_id
                            WHERE o.status='pago' AND o.paid_at>=? AND o.paid_at<?""", (ini, fim)):
        q = int(x["quantity"] or 1)
        v = float(x["unit_price"] or 0) * q
        if x["kind"] == "produto":
            nome = re.sub(r"\s*\([^)]*\)$", "", x["name"] or "")       # "Produto (Opção)" → o produto
            soma(prods, x["product_slug"] or nome, nome, q, v)
        else:
            soma(sess, x["service_id"] or x["service_name"] or x["name"], x["service_name"] or x["name"], q, v)
    for o in todos(con, """SELECT product_slug, product_name, quantity, unit_price FROM store_orders
                            WHERE kind='produto' AND status='pago' AND paid_at>=? AND paid_at<?""", (ini, fim)):
        q = int(o["quantity"] or 1)
        soma(prods, o["product_slug"] or o["product_name"], o["product_name"], q, float(o["unit_price"] or 0) * q)
    ordem = lambda d: sorted(d.values(), key=lambda x: (-x["receita"], -x["qtd"], x["nome"]))[:8]  # noqa: E731
    return ordem(prods), ordem(sess)


def _sessoes(con, ini, fim, hoje):
    r = um(con, """SELECT COUNT(*) AS n,
                          SUM(CASE WHEN status IN ('recusada','cancelada') THEN 1 ELSE 0 END) AS canceladas,
                          SUM(CASE WHEN origin='site' AND status NOT IN ('recusada','cancelada') THEN 1 ELSE 0 END) AS pelo_site,
                          SUM(CASE WHEN origin='portal' AND status NOT IN ('recusada','cancelada') THEN 1 ELSE 0 END) AS pela_area
                     FROM bookings WHERE origin IN ('site','portal') AND created_at>=? AND created_at<?""", (ini, fim))
    prox = um(con, """SELECT COUNT(*) AS n FROM bookings WHERE origin IN ('site','portal') AND status IN ('pendente','confirmada')
                       AND date>=?""", (hoje.isoformat(),))
    pend = um(con, "SELECT COUNT(*) AS n FROM bookings WHERE status='pendente' AND date>=?", (hoje.isoformat(),))
    return {"marcadas": (r["n"] or 0) - (r["canceladas"] or 0), "canceladas": r["canceladas"] or 0,
            "pelo_site": r["pelo_site"] or 0, "pela_area": r["pela_area"] or 0, "proximas": prox["n"], "pendentes": pend["n"]}


def _contas_e_leads(con, ini, fim):
    novas = um(con, "SELECT COUNT(*) AS n FROM portal_accounts WHERE created_at>=? AND created_at<?", (ini, fim))["n"]
    # a mesma conta de Contas de clientes (filtro "sem vínculo") e da Atenção: a conta sem card ligado
    sem_vinculo = um(con, "SELECT COUNT(*) AS n FROM portal_accounts WHERE active=1 AND client_id IS NULL")["n"]
    leads = um(con, """SELECT COUNT(*) AS n, SUM(CASE WHEN stage='GANHO' THEN 1 ELSE 0 END) AS ganhos,
                              SUM(CASE WHEN stage='PERDIDO' THEN 1 ELSE 0 END) AS perdidos
                         FROM opportunities WHERE source='Site' AND created_at>=? AND created_at<?""", (ini, fim))
    return ({"novas": novas, "sem_vinculo": sem_vinculo},
            {"novos": leads["n"] or 0, "ganhos": leads["ganhos"] or 0, "perdidos": leads["perdidos"] or 0})


def _campanhas(con, ini, fim):
    """De onde vieram as vendas e os contatos (o `utm` que cada um guardou), uma vez por venda: o agendamento e a
    oportunidade que um pedido do site gera não contam de novo."""
    linhas = (todos(con, """SELECT utm FROM bookings WHERE origin IN ('site','portal') AND store_order_id IS NULL
                             AND created_at>=? AND created_at<?""", (ini, fim))
              + todos(con, "SELECT utm FROM plan_orders WHERE created_at>=? AND created_at<?", (ini, fim))
              + todos(con, """SELECT campaign AS utm FROM opportunities op WHERE source='Site' AND created_at>=? AND created_at<?
                               AND NOT EXISTS (SELECT 1 FROM store_orders o WHERE o.opp_id=op.id)
                               AND NOT EXISTS (SELECT 1 FROM store_order_items i WHERE i.opp_id=op.id)""", (ini, fim)))
    linhas += todos(con, "SELECT utm FROM store_orders WHERE status='pago' AND paid_at>=? AND paid_at<?", (ini, fim))
    cont, sem = Counter(), 0
    for x in linhas:
        f = _fonte_utm(x["utm"])
        if f:
            cont[f] += 1
        else:
            sem += 1
    top = sorted(({"fonte": k, "n": v} for k, v in cont.items()), key=lambda x: (-x["n"], x["fonte"]))[:8]
    return {"com_campanha": top, "sem_campanha": sem}


def _visitas(con, de, ate):
    a, b = de.isoformat(), ate.isoformat()
    total = um(con, "SELECT COALESCE(SUM(n), 0) AS n FROM site_views WHERE day>=? AND day<=?", (a, b))["n"]
    paginas = todos(con, """SELECT path AS caminho, SUM(n) AS n FROM site_views WHERE day>=? AND day<=?
                             GROUP BY path ORDER BY n DESC, path LIMIT 10""", (a, b))
    fontes = todos(con, """SELECT source AS fonte, SUM(n) AS n FROM site_sources WHERE day>=? AND day<=?
                            GROUP BY source ORDER BY n DESC, source LIMIT 10""", (a, b))
    entradas = um(con, "SELECT COALESCE(SUM(n), 0) AS n FROM site_sources WHERE day>=? AND day<=?", (a, b))["n"]
    carrinho = um(con, "SELECT COALESCE(SUM(n), 0) AS n FROM site_views WHERE day>=? AND day<=? AND path='/cart/'", (a, b))["n"]
    return {"total": total, "entradas": entradas, "carrinho": carrinho, "paginas": paginas, "fontes": fontes}


ESTATICO = re.compile(r"^/(_s|_f|store/img|static|assets|\.well-known)/|\.(css|js|png|jpe?g|webp|svg|ico|txt|xml|webmanifest|map)$")
COMPRA = ("/ops/api/vitrine/checkout", "/ops/api/vitrine/carrinho", "/ops/api/stripe/", "/cart/thanks/", "/store/thanks/",
          "/order/")


def _saude():
    """As páginas do site desde o último reinício (a medição de cada requisição, #20): só as rotas de página do
    site, de todas as rotas medidas (não só as 60 da tela de Integrações)."""
    from command_center.api import observabilidade
    m = observabilidade.metricas(limite=None)

    def caminho(x):
        return x["rota"].split(" ", 1)[-1]
    site = [x for x in m["rotas"] if not caminho(x).startswith("/ops") and caminho(x) != "(fora)" and not ESTATICO.search(caminho(x))]
    compra = [x for x in m["rotas"] if caminho(x).startswith(COMPRA)]

    def soma(xs):
        return {"n": sum(x["n"] for x in xs), "erros_5xx": sum(x["erros_5xx"] for x in xs),
                "p95_ms": max((x["p95_ms"] or 0 for x in xs), default=None) if xs else None}
    return {"desde": m["desde"], "paginas": soma(site), "compra": soma(compra)}


def _atencao(con, hoje, sessoes, contas):
    """O que ainda pede a equipe, nos últimos 30 dias (não muda com o período escolhido)."""
    desde = _limites(JANELA_PENDENCIAS, hoje)[2]
    sem_vaga = um(con, """SELECT COUNT(DISTINCT i.order_id) AS n FROM store_order_items i JOIN store_orders o ON o.id=i.order_id
                           WHERE i.status='sem_vaga' AND i.booking_id IS NULL AND o.status='pago' AND o.created_at>=?""", (desde,))["n"]
    # #309: pago sem estoque (ou com o produto em estoque sem item ligado): a equipe separa à mão ou fala com o cliente.
    # O que ela marcou como Resolvido (Pedidos do site) sai da conta
    sem_estoque = um(con, """SELECT COUNT(*) AS n FROM store_orders o WHERE o.status='pago' AND o.created_at>=?
                              AND ((o.stock_note LIKE 'sem estoque%' AND o.stock_resolved_at IS NULL)
                                   OR EXISTS (SELECT 1 FROM store_order_items i WHERE i.order_id=o.id
                                              AND i.stock_note LIKE 'sem estoque%' AND i.stock_resolved_at IS NULL))""",
                     (desde,))["n"]
    avisos = (um(con, "SELECT COUNT(*) AS n FROM store_orders WHERE notify_error IS NOT NULL AND created_at>=?", (desde,))["n"]
              + um(con, "SELECT COUNT(*) AS n FROM store_order_notices WHERE sent_at IS NULL AND error IS NOT NULL AND created_at>=?",
                   (desde,))["n"]
              + um(con, "SELECT COUNT(*) AS n FROM plan_orders WHERE notify_error IS NOT NULL AND created_at>=?", (desde,))["n"])
    return {"pedidos_sem_vaga": sem_vaga, "pedidos_sem_estoque": sem_estoque, "avisos_falharam": avisos, "agendamentos_pendentes": sessoes["pendentes"],
            "contas_sem_vinculo": contas["sem_vinculo"], "janela_dias": JANELA_PENDENCIAS}


def painel(con, dias=30, hoje=None):
    descarregar()                                       # as visitas da memória entram antes de somar
    dias = dias if dias in PERIODOS else 30
    hoje = hoje or datetime.now(FUSO).date()
    de, ate, ini, fim = _limites(dias, hoje)
    ate_a = de - timedelta(days=1)
    de_a, _, ini_a, fim_a = _limites(dias, ate_a)
    entradas, vendas = _recebido(con, ini, fim)
    _, vendas_ant = _recebido(con, ini_a, fim_a)
    produtos, servicos = _itens_vendidos(con, ini, fim)
    contas, leads = _contas_e_leads(con, ini, fim)
    visitas = _visitas(con, de, ate)
    desde = um(con, "SELECT MIN(day) AS d FROM site_views")["d"]
    visitas["desde"] = desde
    # o período anterior só compara quando foi medido inteiro (antes do deploy, as visitas não eram contadas)
    visitas["total_ant"] = _visitas(con, de_a, ate_a)["total"] if desde and desde <= de_a.isoformat() else None
    visitas["parcial"] = bool(desde) and desde > de.isoformat()
    pagamento = _pagamento(con, ini, fim, visitas["carrinho"])
    serie = {(de + timedelta(days=i)).isoformat(): {"receita": 0.0, "pedidos": 0, "visitas": 0} for i in range(dias)}
    for quando, valor, pedido in entradas:
        d = serie.get(_dia_fl(quando))
        if d:
            d["receita"] = round(d["receita"] + valor, 2)
            d["pedidos"] += pedido
    for v in todos(con, "SELECT day, SUM(n) AS n FROM site_views WHERE day>=? AND day<=? GROUP BY day", (de.isoformat(), ate.isoformat())):
        if v["day"] in serie:
            serie[v["day"]]["visitas"] = v["n"]
    sessoes = _sessoes(con, ini, fim, ate)
    return {"periodo": {"dias": dias, "de": de.isoformat(), "ate": ate.isoformat(), "anterior": [de_a.isoformat(), ate_a.isoformat()]},
            "vendas": {**vendas, "receita_ant": vendas_ant["receita"], "pedidos_pagos_ant": vendas_ant["pedidos_pagos"]},
            "pagamento": pagamento, "sessoes": sessoes, "contas": contas, "leads": leads,
            "produtos": produtos, "servicos": servicos, "campanhas": _campanhas(con, ini, fim), "visitas": visitas,
            "dias": [{"dia": k, **v} for k, v in serie.items()], "atencao": _atencao(con, hoje, sessoes, contas), "saude": _saude()}
