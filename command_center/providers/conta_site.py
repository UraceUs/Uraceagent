"""A conta do site criada no carrinho e os e-mails dela (#305).

Dono, 16/10: *"para ela conseguir … seguir para o checkout, ela vai ter que preencher as informações dela … Quando
for para o checkout, já cria a conta dela no Erase automaticamente"*; *"toda vez que criar a conta, a pessoa recebe
o um e-mail com a nossa identidade … o login dela, a senha que ela … criou ali, o cliente ID dela, link para ela poder
acessar a área dela"*. Decisões do dono (16/10): a senha **vai** no e-mail; o cliente ID é o **número do card**; o
piloto da sessão entra só com o nome e a pessoa **completa depois**, com **lembretes por e-mail até completar**.

- `boas_vindas`: o e-mail na hora em que a conta nasce (no carrinho ou na tela de cadastro), com login, senha, o
  número de cliente quando o card já existe e o link da área do cliente. A senha só existe nesta hora, na memória:
  nunca é guardada nem logada.
- `rodar` (a cada ciclo do laço do servidor):
  1. **número de cliente**: o card do piloto nasce (a sessão paga cria ou liga) ou a equipe liga a conta → um e-mail
     curto com o número, uma vez por piloto. Só para as contas que receberam as boas-vindas (as de antes não recebem
     nada de surpresa);
  2. **completar o piloto**: sessão marcada com o piloto incompleto (`bookings.pilot_pending`) → um lembrete a cada
     24 h, até completar, no máximo 7, e só enquanto a sessão não passou.
"""
from datetime import date, datetime, timezone

from command_center.db import agora, atualizar, todos, um
from command_center.providers import email_marca

INTERVALO_H = 24
MAX_LEMBRETES = 7


def _area(caminho=""):
    from command_center import enderecos
    return f"https://{enderecos.CLIENTE}/ops/portal{caminho}"


def _enviar(enviar, para, assunto, texto, html):
    from command_center.providers import email_envio
    (enviar or email_envio.enviar)(para, assunto, texto, html=html)


def _telefone():
    from command_center.vitrine import conteudo as C
    return C.SITE["telefone"]


def _dia(iso, lang="en"):
    """A data da sessão como a pessoa lê: "Tue, Oct 20" (en) ou "20/10" (pt)."""
    try:
        d = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return str(iso)
    return d.strftime("%d/%m") if lang == "pt" else d.strftime("%a, %b %d").replace(" 0", " ")


def _primeiro(nome):
    return (nome or "").split()[0] if (nome or "").strip() else ""


def _numeros(con, conta_id):
    """[(piloto, número do card)] de quem já tem card nesta conta."""
    return [(p["name"], p["client_id"]) for p in todos(con, """SELECT name, client_id FROM portal_pilots
                                                                WHERE account_id=? AND active=1 AND client_id IS NOT NULL
                                                                ORDER BY is_self DESC, id""", (conta_id,))]


# ------------------------------------------------------------------ 1. boas-vindas
def texto_boas_vindas(conta, senha, numeros, lang="en"):
    """(assunto, texto, html) do e-mail da conta nova."""
    pt = lang == "pt"
    ola = (f"Olá, {_primeiro(conta['name'])}" if pt else f"Hi {_primeiro(conta['name'])}").strip()
    if numeros:
        cid = "; ".join(f"{n}: {c}" for n, c in numeros) if len(numeros) > 1 else str(numeros[0][1])
        cid_txt = cid
    else:
        cid_txt = ("chega por e-mail assim que o seu card estiver pronto" if pt else
                   "arrives by email as soon as your card is ready")
    linhas = ([("Login", conta["email"]), ("Senha" if pt else "Password", senha),
               ("Número de cliente" if pt else "Customer ID", cid_txt)])
    if pt:
        assunto = "Bem-vindo à URACE: a sua conta está pronta"
        corpo = ["A sua conta na URACE está pronta. Com ela você vê os seus pedidos, os seus pilotos, as waivers e as reservas."]
        botao = ("Abrir a minha área URACE", _area())
        depois = ["Guarde este e-mail com cuidado: ele tem a sua senha. Você pode trocar a senha quando quiser, em Conta.",
                  f"Esqueceu a senha? Peça uma nova em {_area('/forgot')}",
                  f"Dúvidas? Ligue ou mande WhatsApp para {_telefone()}."]
    else:
        assunto = "Welcome to URACE: your account is ready"
        corpo = ["Your URACE account is ready. It keeps your orders, your drivers, waivers and bookings in one place."]
        botao = ("Open my URACE area", _area())
        depois = ["Keep this email private: it has your password. You can change the password any time in Account.",
                  f"Forgot your password? Ask for a new one at {_area('/forgot')}",
                  f"Questions? Call or WhatsApp {_telefone()}."]
    texto = (f"{ola},\n\n{corpo[0]}\n\n" + "\n".join(f"{r}: {v}" for r, v in linhas)
             + f"\n\n{botao[0]}: {botao[1]}\n\n" + "\n".join(depois) + "\n\nURACE — the Champion's Factory")
    html = email_marca.html(f"{ola}!", corpo, linhas, botao, depois, lang=lang)
    return assunto, texto, html


def boas_vindas(con, conta_id, senha, lang="en", enviar=None):
    """Manda o e-mail de boas-vindas e marca a conta (os avisos seguintes só vão para quem recebeu este)."""
    c = um(con, "SELECT * FROM portal_accounts WHERE id=?", (conta_id,))
    if not c or c["welcome_sent_at"]:
        return False
    assunto, texto, html = texto_boas_vindas(c, senha, _numeros(con, conta_id), lang)
    try:
        _enviar(enviar, c["email"], assunto, texto, html)
    except Exception as e:                              # noqa: BLE001 — a conta existe; a equipe vê o erro
        atualizar(con, "portal_accounts", conta_id, welcome_error=str(e)[:300], updated_at=agora())
        return False
    atualizar(con, "portal_accounts", conta_id, welcome_sent_at=agora(), welcome_error=None, welcome_lang=lang,
              updated_at=agora())
    con.execute("UPDATE portal_pilots SET client_id_sent_at=? WHERE account_id=? AND client_id IS NOT NULL", (agora(), conta_id))
    return True


def boas_vindas_bg(conta_id, senha, lang="en"):
    """Em segundo plano (a resposta ao cliente não espera o Gmail)."""
    from command_center.db import conectar
    con = conectar()
    try:
        boas_vindas(con, conta_id, senha, lang)
        con.commit()
    finally:
        con.close()


# ------------------------------------------------------------------ 2. o número de cliente
def texto_numero(conta, piloto, numero, lang="en"):
    pt = lang == "pt"
    ola = f"Olá, {_primeiro(conta['name'])}" if pt else f"Hi {_primeiro(conta['name'])}"
    if pt:
        assunto = f"O seu número de cliente URACE: {numero}"
        corpo = [f"O card de {piloto} na URACE está pronto. Este é o número de cliente: use quando falar com a equipe."]
        linhas = [("Piloto", piloto), ("Número de cliente", str(numero)), ("Login", conta["email"])]
        botao = ("Abrir a minha área URACE", _area("/drivers"))
    else:
        assunto = f"Your URACE customer ID: {numero}"
        corpo = [f"{piloto}'s card at URACE is ready. This is the customer ID: use it when you talk to our team."]
        linhas = [("Driver", piloto), ("Customer ID", str(numero)), ("Login", conta["email"])]
        botao = ("Open my URACE area", _area("/drivers"))
    texto = f"{ola},\n\n{corpo[0]}\n\n" + "\n".join(f"{r}: {v}" for r, v in linhas) + f"\n\n{botao[0]}: {botao[1]}\n\nURACE — the Champion's Factory"
    return assunto, texto, email_marca.html(f"{ola}!", corpo, linhas, botao, lang=lang)


# ------------------------------------------------------------------ 3. completar o piloto
ROTULO = {"en": {"name": "full name", "birth_date": "date of birth", "height_in": "height", "weight_lb": "weight",
                 "chest_in": "chest", "waist_in": "waist", "experience": "karting experience"},
          "pt": {"name": "nome completo", "birth_date": "data de nascimento", "height_in": "altura", "weight_lb": "peso",
                 "chest_in": "peito", "waist_in": "cintura", "experience": "experiência no kart"}}


def texto_lembrete(conta, piloto, falta, data_sessao, lang="en"):
    pt = lang == "pt"
    data_sessao = _dia(data_sessao, lang)
    rot = ROTULO["pt" if pt else "en"]
    itens = ", ".join(dict.fromkeys(rot.get(k, k) for k in falta)) or ("as medidas" if pt else "the measurements")
    ola = f"Olá, {_primeiro(conta['name'])}" if pt else f"Hi {_primeiro(conta['name'])}"
    if pt:
        assunto = f"Falta pouco: complete o cadastro de {piloto['name']} para a sessão de {data_sessao}"
        corpo = [f"A sessão de {piloto['name']} em {data_sessao} está paga e reservada. Para a equipe preparar o kart e o "
                 f"equipamento certos, complete: {itens}. Leva dois minutos."]
        botao = ("Completar agora", _area("/drivers"))
        depois = ["Mandamos este lembrete até o cadastro ficar completo."]
    else:
        assunto = f"Almost there: complete {piloto['name']}'s profile for the {data_sessao} session"
        corpo = [f"{piloto['name']}'s session on {data_sessao} is paid and booked. So our team can prepare the right kart and "
                 f"gear, please add: {itens}. It takes two minutes."]
        botao = ("Complete it now", _area("/drivers"))
        depois = ["We'll send this reminder until the profile is complete."]
    texto = f"{ola},\n\n{corpo[0]}\n\n{botao[0]}: {botao[1]}\n\n{depois[0]}\n\nURACE — the Champion's Factory"
    return assunto, texto, email_marca.html(f"{ola}!", corpo, (), botao, depois, lang=lang)


def _horas_desde(iso):
    if not iso:
        return None
    t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - (t if t.tzinfo else t.replace(tzinfo=timezone.utc))).total_seconds() / 3600


def rodar(con, enviar=None):
    """Os avisos devidos agora: número de cliente e lembrete de completar o piloto. Devolve as contagens."""
    from command_center.providers import portal
    numeros = lembretes = 0
    # 1. o número de cliente (o card ficou pronto depois das boas-vindas)
    for p in todos(con, """SELECT p.id, p.name, p.client_id, a.id AS conta, a.email, a.name AS conta_nome, a.welcome_lang
                             FROM portal_pilots p JOIN portal_accounts a ON a.id=p.account_id
                            WHERE p.client_id IS NOT NULL AND p.client_id_sent_at IS NULL AND p.active=1
                              AND a.welcome_sent_at IS NOT NULL AND a.active=1 LIMIT 50"""):
        conta = {"name": p["conta_nome"], "email": p["email"]}
        try:
            _enviar(enviar, p["email"], *texto_numero(conta, p["name"], p["client_id"], p["welcome_lang"] or "en"))
        except Exception:                               # noqa: BLE001 — tenta de novo no próximo ciclo
            continue
        atualizar(con, "portal_pilots", p["id"], client_id_sent_at=agora())
        numeros += 1
    # 2. completar o piloto: a sessão está paga e o cadastro do piloto não
    hoje = portal.hoje().isoformat()
    for b in todos(con, """SELECT b.pilot_id, MIN(b.date) AS data, b.account_id FROM bookings b
                            WHERE b.pilot_pending=1 AND b.status IN ('pendente','confirmada') AND b.date>=?
                            GROUP BY b.pilot_id, b.account_id LIMIT 100""", (hoje,)):
        p = next((x for x in portal.pilotos(con, b["account_id"]) if x["id"] == b["pilot_id"]), None)
        if not p:
            continue
        if p["measures_status"] not in ("faltando", "vencida"):
            con.execute("UPDATE bookings SET pilot_pending=0 WHERE pilot_id=? AND pilot_pending=1", (p["id"],))
            continue
        r = um(con, "SELECT remind_at, COALESCE(remind_n, 0) AS n FROM portal_pilots WHERE id=?", (p["id"],))
        horas = _horas_desde(r["remind_at"])
        if r["n"] >= MAX_LEMBRETES or (horas is not None and horas < INTERVALO_H):
            continue
        a = um(con, "SELECT name, email, welcome_lang FROM portal_accounts WHERE id=? AND active=1", (b["account_id"],))
        if not a:
            continue
        falta = p["missing"] or ["height_in", "weight_lb", "chest_in", "waist_in"]
        try:
            _enviar(enviar, a["email"], *texto_lembrete(a, p, falta, b["data"], a["welcome_lang"] or "en"))
        except Exception:                               # noqa: BLE001
            continue
        atualizar(con, "portal_pilots", p["id"], remind_at=agora(), remind_n=r["n"] + 1)
        lembretes += 1
    return {"numeros": numeros, "lembretes": lembretes}


def piloto_pendente(con, pid):
    """O piloto ainda não está pronto para a pista (faltam dados ou as medidas venceram)?"""
    from command_center.providers import portal
    p = um(con, "SELECT account_id FROM portal_pilots WHERE id=?", (pid,))
    if not p:
        return False
    x = next((q for q in portal.pilotos(con, p["account_id"]) if q["id"] == pid), None)
    return bool(x and x["measures_status"] in ("faltando", "vencida"))

