"""Ponte de e-mail dos Suits (#153): o fluxo que o Ítalo montou no ChatGPT, rodando no VPS.

Ítalo (áudio de 08/10, pelo dono): *"entrou uma venda de macacão, ali pelo site ... manda um
e-mail automaticamente para o cliente agradecendo pela compra ... manda por favor as medidas, e
entregar o PDF ... e falar para o cliente mandar o design que ele quer ou a inspiração ... Quando
o cliente responde ... sem dar a informação do cliente ... extrai tudo e manda para o Matheus ...
se o Matheus tiver alguma pergunta, a IA faz aquele meio de campo ... Quando o Matheus entregar a
arte, a IA pega a arte, extrai a informação do Matheus e manda para o cliente ... eu pedi para
tudo passar por minha aprovação por isso que eu fui o gargalo"*. Dono: *"rode na nossa mente de
testes, faça simulações"*.

Como funciona, a cada ciclo do painel (15 min):
1. **Venda nova** no site (o e-mail "[Urace]: You've got a new order" com macacão) → abre o pedido.
2. **Resposta** na conversa do cliente, do designer ou do fornecedor de um pedido aberto.
3. **Marcador `Suits`** do Gmail numa conversa que ainda não é de pedido nenhum.
Cada mensagem é lida uma vez (`suit_email_seen`). Para cada evento a IA do AI Command (#152) lê
o pedido e o e-mail (com os anexos baixados) e age pelas ferramentas `suits_*`.

**Quem recebe é o painel que decide**, não o modelo: `enviar()` só manda para o cliente, o
designer ou o fornecedor DAQUELE pedido. O designer nunca recebe e-mail, telefone, endereço ou
nome completo do cliente; o cliente nunca recebe o nome ou o contato do designer.

**Simulação primeiro**: com `envio_automatico` desligado (o padrão), nada sai — o e-mail que a IA
mandaria fica na linha do tempo do pedido, para a equipe conferir. Ligou, sai sem aprovação
(era o gargalo). Teste nunca manda: `CC_EMAIL_FAKE=<arquivo>` grava em vez de enviar.
"""
import contextvars
import json
import mimetypes
import os
import re
import threading

from command_center.db import agora, auditar, conectar, inserir, todos, um

CONTA = "urace"
NOSSOS = ("urace@urace.us", "support@urace.us", "noreply@urace.us", "info@urace.us")
ANEXO_MAX = 15 * 1024 * 1024
ENVIO_MAX = 20 * 1024 * 1024          # o Gmail aceita 25 MB somados
POR_CICLO = int(os.environ.get("CC_SUITS_POR_CICLO", "5"))
SIMULAR = contextvars.ContextVar("suits_simular", default=False)

BOAS_VINDAS = """Hi {first name}, thank you for your order! We're excited to build your custom suit.

To get started: do you have a design, colors, or references in mind? Send any inspiration and your logos in high resolution.

For the fit, please fill in the attached sizing form, it has diagrams showing exactly how to take each measurement. Also send the driver's name as you want it on the suit, nationality, a frontal body photo, and note if he wears a rib protector.

A few things that make the measurements go faster: use a flexible tailor tape and have someone help you; take them against bare skin, with the muscles relaxed; if a number looks off, measure three times and use the average.

Before production, three rounds of design revisions are included at no charge. Because every suit is made to order, custom suits are not eligible for voluntary returns or refunds. If anything is wrong on our side, we fix it at no cost; if a measurement error makes the suit unusable, we offer 50% off a replacement, and if a design you provided requires a new suit, 33% off a replacement. All subject to the terms of your purchase.

Once I have the design and measurements, I'll send the mockup for approval and confirm the timeline!"""

# Contexto do robô do Ítalo (Mio, 08/10, #156): a política que ele passou para os macacões. Vale para os
# pedidos novos, sujeita aos termos da compra e aos direitos do cliente; conflito sobe para a equipe.
POLITICA = """Três rodadas de revisão do design antes da produção, sem custo.
Macacão personalizado não tem devolução voluntária nem reembolso.
Erro causado pela URACE: corrigido sem custo.
Erro de medida do cliente que torne o macacão inutilizável: 50% de desconto na troca.
Erro do design fornecido pelo cliente que exija macacão novo: 33% de desconto na troca.
Tudo sujeito aos termos da compra e aos direitos do cliente; conflito com isso sobe para a equipe."""

PADROES = {
    "ponte_ligada": "1",
    "envio_automatico": "0",
    # Mio do Ítalo: "Mateus (carvalhovisual1@gmail.com) é designer de suits, não deve ser apresentado ao cliente como fabricante"
    "designer_nome": "Mateus",
    "designer_email": "carvalhovisual1@gmail.com",
    # Mio do Ítalo: "replicate Eduardo Resende's URACE signature exactly except for the display name George"
    "assinatura": "Best regards,\nGeorge\n\nUrace\n+1(407)2502291\nurace@urace.us\nwww.urace.us\n10724 Cosmonaut Blvd, Orlando, FL 32824, USA",
    "boas_vindas": BOAS_VINDAS,
    "politica": POLITICA,
}


class Recusado(ValueError):
    """O e-mail não pode sair como está; a mensagem diz por quê (a IA lê e corrige)."""


# ------------------------------------------------------------------ configuração
def config(con):
    c = dict(PADROES)
    for r in todos(con, "SELECT key, value FROM suit_settings"):
        if r["key"] in c:
            c[r["key"]] = r["value"] if r["value"] is not None else ""
    return c


def salvar_config(con, dados, uid=None):
    for k, v in dados.items():
        if k not in PADROES or v is None:
            continue
        v = str(v) if k in ("boas_vindas", "assinatura", "politica") else str(v).strip()
        if k in ("ponte_ligada", "envio_automatico"):
            v = "1" if v in ("1", "true", "True") else "0"
        if k == "designer_email" and v and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
            raise Recusado("e-mail do designer inválido")
        con.execute("""INSERT INTO suit_settings (key, value, updated_at, updated_by) VALUES (?,?,?,?)
                       ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at,
                       updated_by=excluded.updated_by""", (k, v, agora(), uid))
    return config(con)


def raiz():
    caminho = os.path.join(os.environ.get("URACE_DIR", os.path.expanduser("~/.urace")), "suits")
    os.makedirs(caminho, exist_ok=True)
    return caminho


def pasta(pid):
    caminho = os.path.join(raiz(), "anexos", str(int(pid)))
    os.makedirs(caminho, exist_ok=True)
    return caminho


def manual_pdf():
    return os.path.join(raiz(), "manual-medidas.pdf")


def anexos_do_pedido(pid):
    p = pasta(pid)
    return sorted(n for n in os.listdir(p) if os.path.isfile(os.path.join(p, n)))


def _nome_seguro(nome):
    base = re.sub(r"[^\w.\- ]+", "_", os.path.basename(nome or "anexo")).strip() or "anexo"
    return base[:120]


def guardar_anexo(pid, nome, dados):
    """Grava o arquivo na pasta do pedido sem sobrescrever outro; devolve o nome usado."""
    nome = _nome_seguro(nome)
    raiz_n, ext = os.path.splitext(nome)
    destino, n = os.path.join(pasta(pid), nome), 1
    while os.path.exists(destino):
        n += 1
        nome = f"{raiz_n}-{n}{ext}"
        destino = os.path.join(pasta(pid), nome)
    with open(destino, "wb") as f:
        f.write(dados)
    return nome


# ------------------------------------------------------------------ o envio
def _digitos(s):
    return re.sub(r"\D", "", s or "")


def _guardas(pedido, papel, texto, cfg):
    """O designer não vê dado do cliente; o cliente não vê o designer."""
    t = (texto or "").lower()
    if papel == "designer":
        problemas = []
        if pedido.get("customer_email") and pedido["customer_email"].lower() in t:
            problemas.append("o e-mail do cliente")
        tel = _digitos(pedido.get("customer_phone"))
        if len(tel) >= 7 and tel[-7:] in _digitos(texto):
            problemas.append("o telefone do cliente")
        end = (pedido.get("ship_address") or "").strip().splitlines()
        if end and len(end[0]) >= 8 and end[0].lower() in t:
            problemas.append("o endereço do cliente")
        nome = (pedido.get("customer_name") or "").strip()
        if len(nome.split()) >= 2 and nome.lower() in t:
            problemas.append("o nome completo do cliente")
        if problemas:
            raise Recusado("O designer não pode receber " + ", ".join(problemas) + ". Reescreva só com o design "
                           f"e o número do pedido (Suits #{pedido['id']}).")
    if papel == "cliente":
        for dado in (cfg.get("designer_email"), cfg.get("designer_nome")):
            if dado and len(dado) >= 3 and dado.lower() in t:
                raise Recusado("O cliente não pode ver o nome nem o contato do designer: fale como a URACE.")


def destinatario(con, pedido, papel, cfg):
    if papel == "cliente":
        return pedido.get("customer_email")
    if papel == "designer":
        return cfg.get("designer_email") or None
    if papel == "fornecedor":
        f = um(con, "SELECT email FROM suit_suppliers WHERE id=?", (pedido["supplier_id"],)) if pedido.get("supplier_id") \
            else um(con, "SELECT email FROM suit_suppliers WHERE is_current=1")
        return f["email"] if f else None
    raise Recusado("para quem? cliente, designer ou fornecedor")


def _arquivos(pid, nomes):
    saida, total = [], 0
    for nome in nomes or []:
        if nome == "manual_medidas":
            caminho, nome_final = manual_pdf(), "GUIDE TO FILLING IN SIZING - URACE FORM.pdf"
        else:
            nome_final = os.path.basename(nome)
            caminho = os.path.join(pasta(pid), nome_final)
        if not os.path.isfile(caminho):
            raise Recusado(f"anexo não encontrado: {nome}" + (" (o manual de medidas ainda não foi carregado na aba Suits › Ponte de e-mail)"
                                                               if nome == "manual_medidas" else ""))
        with open(caminho, "rb") as f:
            dados = f.read()
        total += len(dados)
        if total > ENVIO_MAX:
            raise Recusado("anexos passam de 20 MB: mande em dois e-mails")
        saida.append((nome_final, dados, mimetypes.guess_type(nome_final)[0] or "application/octet-stream"))
    return saida


def _marcas_do_designer(cfg):
    m = []
    email = (cfg.get("designer_email") or "").strip().lower()
    if email:
        m += [email, email.split("@")[0]]
    nome = (cfg.get("designer_nome") or "").strip().lower()
    if len(nome) >= 3:
        m.append(nome)
    return [x for x in m if len(x) >= 3]


def _sem_metadados(nome, dados, mime):
    """Imagem e PDF saem sem autor, EXIF, comentário ou XMP. O resto passa como está (e é conferido)."""
    import io
    ext = os.path.splitext(nome)[1].lower()
    try:
        if mime in ("image/jpeg", "image/png", "image/webp"):
            from PIL import Image
            im = Image.open(io.BytesIO(dados))
            im.load()
            im.info = {}
            fmt = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}[mime]
            if fmt == "JPEG" and im.mode not in ("RGB", "L", "CMYK"):
                im = im.convert("RGB")
            saida = io.BytesIO()
            extra = {"quality": 95} if fmt in ("JPEG", "WEBP") else {"optimize": True}
            im.save(saida, fmt, **extra)
            return saida.getvalue()
        if mime == "application/pdf" or ext == ".pdf":
            from pypdf import PdfReader, PdfWriter
            r, w = PdfReader(io.BytesIO(dados)), PdfWriter()
            for pg in r.pages:
                w.add_page(pg)
            w.add_metadata({"/Producer": "URACE"})
            saida = io.BytesIO()
            w.write(saida)
            return saida.getvalue()
    except Exception:
        return dados                    # não deu para limpar: a conferência abaixo decide
    return dados


def limpar_para_cliente(arquivos, cfg):
    """Mio do Ítalo: nunca expor ao cliente o endereço, a assinatura ou os METADADOS do designer. O nome do
    arquivo também não leva o designer; e se o conteúdo ainda carregar o nome ou o e-mail dele, não sai."""
    marcas = _marcas_do_designer(cfg)
    saida = []
    for i, (nome, dados, mime) in enumerate(arquivos, 1):
        if nome.startswith("GUIDE TO FILLING IN SIZING"):
            saida.append((nome, dados, mime))
            continue
        dados = _sem_metadados(nome, dados, mime)
        if any(m in nome.lower() for m in marcas):
            nome = f"URACE-design-{i}{os.path.splitext(nome)[1].lower()}"
        baixo = dados.lower()
        if any(m.encode() in baixo for m in marcas):
            raise Recusado(f"o arquivo {nome} ainda carrega o nome ou o contato do designer: peça a arte exportada de novo "
                           "(ou em PNG/JPG/PDF) antes de mandar ao cliente.")
        saida.append((nome, dados, mime))
    return saida


def _envio_real(para, assunto, corpo, anexos, thread_id, em_resposta_a):
    falso = os.environ.get("CC_EMAIL_FAKE")
    if falso:
        with open(falso, "a", encoding="utf-8") as f:
            f.write(json.dumps({"to": para, "subject": assunto, "text": corpo, "anexos": [a[0] for a in anexos],
                                "thread_id": thread_id, "em_resposta_a": em_resposta_a}) + "\n")
        n = os.path.getsize(falso)
        return {"id": f"fake-msg-{n}", "thread_id": thread_id or f"fake-thread-{n}"}
    from command_center.providers import modulo
    return modulo("gmail").enviar_sistema(CONTA, para, assunto, corpo, anexos, thread_id, em_resposta_a)


def enviar(con, pid, papel, assunto, corpo, anexos=None, responder=True, user_id=None):
    """O único caminho de e-mail da ponte. Simulação (padrão ou forçada): vira nota e não sai."""
    from command_center.providers import suits
    pedido = dict(um(con, "SELECT * FROM suit_orders WHERE id=?", (pid,)) or {})
    if not pedido:
        raise Recusado("pedido não encontrado")
    cfg = config(con)
    para = destinatario(con, pedido, papel, cfg)
    if not para:
        raise Recusado({"cliente": "o pedido não tem o e-mail do cliente",
                        "designer": "o e-mail do designer não está configurado (aba Suits › Ponte de e-mail)",
                        "fornecedor": "o fornecedor não tem e-mail"}[papel])
    assunto, corpo = (assunto or "").strip(), (corpo or "").strip()
    if not assunto or not corpo:
        raise Recusado("assunto e corpo são obrigatórios")
    _guardas(pedido, papel, assunto + "\n" + corpo, cfg)
    arquivos = _arquivos(pid, anexos)
    if papel == "cliente":
        arquivos = limpar_para_cliente(arquivos, cfg)
    thread = pedido.get(f"gmail_thread_{papel}") if responder else None
    simulado = SIMULAR.get() or cfg["envio_automatico"] != "1"
    lista = ", ".join(a[0] for a in arquivos)
    resumo = f"para {papel} ({para}) — {assunto}" + (f" · anexos: {lista}" if lista else "") + f"\n\n{corpo}"
    if simulado:
        nid = suits.anotar(con, pid, "SIMULAÇÃO — a IA mandaria este e-mail " + resumo, "email", pedido["status"], user_id=user_id)
        return {"simulado": True, "nota": nid, "para": para}
    em_resposta_a = None
    if thread:
        try:
            from command_center.providers import modulo
            msgs = modulo("gmail").mensagens_da_thread(CONTA, thread, limite=200)["mensagens"]
            em_resposta_a = msgs[-1].get("message_id_header") if msgs else None
        except Exception:
            em_resposta_a = None
        if not assunto.lower().startswith("re:"):
            assunto = "Re: " + assunto
    r = _envio_real(para, assunto, corpo, arquivos, thread, em_resposta_a)
    if r.get("id"):                                   # o que nós mandamos não volta como evento
        con.execute("INSERT OR IGNORE INTO suit_email_seen (message_id, order_id, thread_id, papel) VALUES (?,?,?,?)",
                    (r["id"], pid, r.get("thread_id"), papel))
    if r.get("thread_id") and not pedido.get(f"gmail_thread_{papel}"):
        con.execute(f"UPDATE suit_orders SET gmail_thread_{papel}=? WHERE id=?", (r["thread_id"], pid))
    suits.anotar(con, pid, "E-mail enviado " + resumo, "email", pedido["status"], user_id=user_id)
    auditar(con, "suit.email.sent", "ai:suits_ponte", user_id=user_id, entity_type="suit_order", entity_id=pid,
            detail={"papel": papel, "para": para, "assunto": assunto, "anexos": [a[0] for a in arquivos]})
    return {"simulado": False, "para": para, "id": r.get("id"), "thread_id": r.get("thread_id")}


def precisa_humano(con, pid, motivo, user_id=None):
    from command_center.providers import suits
    p = um(con, "SELECT title, status FROM suit_orders WHERE id=?", (pid,))
    if not p:
        raise Recusado("pedido não encontrado")
    suits.anotar(con, pid, f"Precisa de alguém da equipe: {motivo}", "ia", p["status"], user_id=user_id)
    if not um(con, "SELECT id FROM ai_events WHERE kind='suit.humano' AND entity_id=? AND status='NEW'", (pid,)):
        inserir(con, "ai_events", kind="suit.humano", entity_type="suit_order", entity_id=pid,
                summary=f"Suits #{pid} ({p['title']}): {motivo}"[:300], status="NEW")
    return {"ok": True}


# ------------------------------------------------------------------ os eventos
def _nosso(de):
    """A URACE: as caixas da lista e qualquer pessoa da equipe com e-mail @urace.us (#182)."""
    d = (de or "").lower()
    return any(n in d for n in NOSSOS) or _email_de(d).endswith("@urace.us")


def _visto(con, mid):
    return um(con, "SELECT 1 AS x FROM suit_email_seen WHERE message_id=?", (mid,)) is not None


def _marcar(con, msgs, pid, thread, papel):
    for m in msgs:
        con.execute("INSERT OR IGNORE INTO suit_email_seen (message_id, order_id, thread_id, papel) VALUES (?,?,?,?)",
                    (m["message_id"], pid, thread, papel))


RX_VENDA = re.compile(r"\bsuits?\b|macac", re.I)


def novas_vendas(con, gm):
    """O e-mail do WooCommerce de pedido novo, com macacão, que ainda não virou pedido."""
    eventos = []
    r = gm.gmail_buscar(CONTA, 'subject:"new order" newer_than:3d', so_inbox=False, maximo=20)
    for t in r.get("threads") or []:
        msgs = gm.mensagens_da_thread(CONTA, t["thread_id"])["mensagens"]
        novas = [m for m in msgs if not _visto(con, m["message_id"]) and "new order" in (m.get("assunto") or "").lower()]
        if not novas:
            continue
        m = novas[0]
        if not RX_VENDA.search(m.get("corpo") or ""):
            _marcar(con, novas, None, t["thread_id"], "venda")    # venda sem macacão: não é da ponte
            continue
        num = re.search(r"#\s?(\d{3,})", m.get("assunto") or "")
        site = num.group(1) if num else None
        ja = um(con, "SELECT id FROM suit_orders WHERE site_order=?", (site,)) if site else None
        pid = ja["id"] if ja else inserir(con, "suit_orders", title=f"Pedido do site #{site or '?'}", source="site",
                                          site_order=site, status="standby", updated_at=agora())
        if not ja:
            from command_center.providers import suits
            suits.anotar(con, pid, f"Venda no site{f' #{site}' if site else ''}: a IA abre o pedido e manda as boas-vindas.",
                         "etapa", "standby")
        eventos.append({"tipo": "venda", "pedido_id": pid, "thread_id": t["thread_id"], "mensagens": novas})
    return eventos


def respostas(con, gm):
    """Mensagem nova nas conversas de um pedido aberto, de quem não é a URACE."""
    eventos = []
    for p in todos(con, """SELECT id, gmail_thread_cliente, gmail_thread_designer, gmail_thread_fornecedor
                           FROM suit_orders WHERE closed=0 AND (gmail_thread_cliente IS NOT NULL
                           OR gmail_thread_designer IS NOT NULL OR gmail_thread_fornecedor IS NOT NULL)"""):
        for papel in ("cliente", "designer", "fornecedor"):
            th = p[f"gmail_thread_{papel}"]
            if not th:
                continue
            try:
                msgs = gm.mensagens_da_thread(CONTA, th)["mensagens"]
            except Exception:
                continue
            novas = [m for m in msgs if not _visto(con, m["message_id"]) and not _nosso(m.get("de"))]
            nossas = [m for m in msgs if not _visto(con, m["message_id"]) and _nosso(m.get("de"))]
            _marcar(con, nossas, p["id"], th, papel)               # o que a equipe mandou à mão não é evento
            if novas:
                eventos.append({"tipo": papel, "pedido_id": p["id"], "thread_id": th, "mensagens": novas})
    return eventos


RX_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def _email_de(de):
    m = RX_EMAIL.search(de or "")
    return m.group(0).lower() if m else ""


def _nome_de(de):
    n = (de or "").split("<")[0].strip().strip('"')
    return n if n and "@" not in n else ""


def _pedido_do_fornecedor(con, assunto):
    """'SUIT - Bennie Schneider (…)' → o pedido aberto cujo título ou piloto aparece no assunto."""
    a = (assunto or "").lower()
    for p in todos(con, "SELECT id, title, driver_name FROM suit_orders WHERE closed=0 ORDER BY id DESC"):
        for nome in (p["title"], p["driver_name"]):
            if nome and len(nome) >= 4 and nome.lower() in a:
                return p["id"]
    return None


def conversas_novas(con, gm):
    """Conversa nova que ainda não é de pedido nenhum: com o marcador Suits, do designer, ou de um
    cliente com pedido aberto. Quem mandou decide o papel; o pedido é achado antes da IA."""
    eventos = []
    cfg = config(con)
    ligadas = {r["t"] for r in todos(con, """SELECT gmail_thread_cliente AS t FROM suit_orders WHERE gmail_thread_cliente IS NOT NULL
                                              UNION SELECT gmail_thread_designer FROM suit_orders WHERE gmail_thread_designer IS NOT NULL
                                              UNION SELECT gmail_thread_fornecedor FROM suit_orders WHERE gmail_thread_fornecedor IS NOT NULL""")}
    fornecedores = {r["email"].lower() for r in todos(con, "SELECT email FROM suit_suppliers WHERE email IS NOT NULL")}
    clientes = {r["e"].lower(): r["id"] for r in todos(con, """SELECT lower(customer_email) AS e, MAX(id) AS id FROM suit_orders
                                                              WHERE closed=0 AND customer_email IS NOT NULL GROUP BY lower(customer_email)""")}
    consultas = ["label:Suits newer_than:3d"]
    if cfg.get("designer_email"):
        consultas.append(f"from:{cfg['designer_email']} newer_than:3d")
    emails = sorted(clientes)
    for i in range(0, len(emails), 15):
        consultas.append("from:(" + " OR ".join(emails[i:i + 15]) + ") newer_than:3d")
    vistas = set()
    for q in consultas:
        for t in (gm.gmail_buscar(CONTA, q, so_inbox=False, maximo=20).get("threads") or []):
            th = t["thread_id"]
            if th in ligadas or th in vistas:
                continue
            vistas.add(th)
            msgs = gm.mensagens_da_thread(CONTA, th)["mensagens"]
            _marcar(con, [m for m in msgs if not _visto(con, m["message_id"]) and _nosso(m.get("de"))], None, th, "conversa")
            novas = [m for m in msgs if not _visto(con, m["message_id"]) and not _nosso(m.get("de"))]
            if not novas:
                continue
            de, assunto = _email_de(novas[-1].get("de")), novas[0].get("assunto") or ""
            if de in fornecedores:
                pid = _pedido_do_fornecedor(con, assunto)
                if pid and not um(con, "SELECT gmail_thread_fornecedor FROM suit_orders WHERE id=?", (pid,))["gmail_thread_fornecedor"]:
                    con.execute("UPDATE suit_orders SET gmail_thread_fornecedor=? WHERE id=?", (th, pid))
                eventos.append({"tipo": "fornecedor", "pedido_id": pid, "thread_id": th, "mensagens": novas})
            elif cfg.get("designer_email") and de == cfg["designer_email"].lower():
                m = re.search(r"#\s?(\d+)", assunto + " " + (novas[-1].get("corpo") or "")[:500])
                pid = int(m.group(1)) if m and um(con, "SELECT 1 AS x FROM suit_orders WHERE id=?", (int(m.group(1)),)) else None
                if pid:
                    con.execute("UPDATE suit_orders SET gmail_thread_designer=coalesce(gmail_thread_designer, ?) WHERE id=?", (th, pid))
                eventos.append({"tipo": "designer", "pedido_id": pid, "thread_id": th, "mensagens": novas})
            elif de in clientes:
                pid = clientes[de]
                con.execute("UPDATE suit_orders SET gmail_thread_cliente=coalesce(gmail_thread_cliente, ?) WHERE id=?", (th, pid))
                eventos.append({"tipo": "cliente", "pedido_id": pid, "thread_id": th, "mensagens": novas, "historico": msgs})
            else:
                # #182 (dono, 09/10: "quando for um pedido de suit, ele adiciona lá"): o marcador Suits de quem
                # não tem pedido NÃO abre pedido. A IA lê primeiro e só cria se for pedido de macacão. Sem
                # pedido, a conversa não fica ligada a nada: se não couber neste ciclo, volta no próximo do
                # mesmo jeito (antes, voltava como "resposta do cliente" e o pedido ficava).
                eventos.append({"tipo": "marcador", "pedido_id": None, "thread_id": th, "mensagens": novas, "historico": msgs,
                                "remetente": {"nome": _nome_de(novas[-1].get("de")) or None, "email": de or None}})
    return eventos


def baixar_anexos(gm, pid, msg):
    """Os anexos da mensagem (e as imagens coladas no corpo) vão para a pasta do pedido."""
    nomes = []
    for a in msg.get("anexos") or []:
        if (a.get("bytes") or 0) > ANEXO_MAX:
            nomes.append(f"(não baixado, grande demais: {a.get('nome')})")
            continue
        try:
            nomes.append(guardar_anexo(pid, a.get("nome"), gm.anexo_bytes(CONTA, msg["message_id"], a["attachment_id"])))
        except Exception as e:
            nomes.append(f"(não baixado: {a.get('nome')}: {str(e)[:80]})")
    return nomes


# ------------------------------------------------------------------ a IA
QUE_FAZER = {
    "venda": ("VENDA NOVA NO SITE. Preencha o pedido com os dados da venda (suits_atualizar_pedido: title = nome do cliente, "
              "customer_name, customer_email, customer_phone, ship_address, driver_name se houver, product, quantity, "
              "paid_at se pago, language pelo país e pelo idioma do cliente). Depois mande ao cliente (suits_email "
              "para=\"cliente\", anexos=[\"manual_medidas\"]) as boas-vindas no idioma dele, a partir do MODELO DE "
              "BOAS-VINDAS, e mova para awaiting_measurements."),
    "cliente": ("O CLIENTE RESPONDEU. Leia tudo, inclusive as imagens e PDFs baixados. Grave as medidas que vierem "
                "(suits_atualizar_pedido medidas, na unidade que ele usou), o design (ideia, cores, logos, posicao_logos, nome, "
                "bandeira, observacoes) e o nome do piloto. Se faltar algo, responda pedindo SÓ o que falta. Quando houver "
                "design suficiente para começar, mande ao designer (para=\"designer\") um briefing claro, com os anexos de "
                "inspiração e logos e a referência \"Suits #{id}\" — sem nome completo, e-mail, telefone, endereço ou "
                "pagamento do cliente — e mova para design_pending. Aprovou o design: mova para approved e agradeça. Pediu "
                "ajuste: leve o ajuste ao designer."),
    "designer": ("O DESIGNER RESPONDEU. Pergunta: leve ao cliente com as suas palavras, como a URACE (sem nome nem contato do "
                 "designer). Arte entregue (anexo): mande a arte ao cliente (anexos com os arquivos baixados) pedindo aprovação "
                 "ou ajustes, e mova para design_review."),
    "fornecedor": ("O FORNECEDOR ESCREVEU. Anote o que ele disse (suits_anotar); se avisou produção ou envio, mova a etapa "
                   "(in_production / in_transit, com o rastreio). Se pedir decisão ou houver problema (medida errada, cor), "
                   "suits_precisa_humano."),
    "marcador": ("E-MAIL COM O MARCADOR SUITS DE QUEM NÃO TEM PEDIDO ABERTO. NENHUM PEDIDO FOI CRIADO: classifique antes "
                 "(dono, 09/10: \"quando for um pedido de suit, ele adiciona lá\"). Leia a conversa inteira.\n"
                 "1) É PEDIDO DE MACACÃO só quando a pessoa (cliente, não a equipe nem fornecedor) quer comprar um macacão "
                 "novo: pede orçamento ou preço para fazer o dela, manda medidas ou design para encomendar, confirma que quer "
                 "fazer, ou pagou. Aí: veja em suits_pedidos se ela já tem pedido aberto (mesmo e-mail ou nome); se tem, "
                 "suits_atualizar_pedido nele com gmail_thread_cliente=\"{thread}\" e siga do ponto em que está; se não tem, "
                 "suits_criar_pedido com title e customer_name (o nome dela), customer_email, gmail_thread_cliente=\"{thread}\" "
                 "e o que ela já mandou, e responda com as boas-vindas (anexos=[\"manual_medidas\"]) ou com o próximo passo.\n"
                 "2) NÃO É PEDIDO (e não crie nada): fornecedor ou fábrica, homologação/FIA, nota fiscal, frete, propaganda, "
                 "newsletter, conversa interna da equipe, dúvida geral sem intenção de comprar, agradecimento, assunto de outro "
                 "serviço, ou qualquer dúvida sobre ser pedido. Na dúvida, NÃO crie: responda só \"não é pedido: <motivo>\" "
                 "e pare. Não responda e-mail para quem não fez pedido."),
    "simulacao": ("SIMULAÇÃO NESTE PEDIDO (nada sai: os e-mails viram nota). Leia o pedido e as conversas abaixo e faça o próximo "
                  "passo do processo como se fosse de verdade."),
}


def prompt(con, ev, cfg, anexos_baixados):
    pid = ev.get("pedido_id")
    linhas = []
    for m, nomes in zip(ev["mensagens"], anexos_baixados):
        linhas.append(f"--- de: {m.get('de')} · {m.get('data')} · assunto: {m.get('assunto')}\n{m.get('corpo') or ''}"
                      + (f"\nAnexos baixados (leia com Read em {pasta(pid) if pid else '—'}): {', '.join(nomes)}" if nomes else ""))
    historico = ""
    if ev.get("historico"):
        historico = "\nCONVERSA ANTERIOR (contexto):\n" + "\n".join(
            f"- {m.get('de')} · {m.get('data')}: {(m.get('corpo') or '')[:800]}" for m in ev["historico"] if m not in ev["mensagens"])
    designer = cfg.get("designer_nome") or "o designer"
    return (f"[PONTE DE E-MAIL DOS SUITS] Você é o meio de campo entre o cliente, {designer} e o fornecedor, no lugar da equipe "
            "(processo: 10_PROCESSOS/Pedido de macacão.md). "
            + (f"Pedido Suits #{pid}: leia com suits_pedido e os anexos com suits_anexos. " if pid else "")
            + f"Thread do Gmail: {ev.get('thread_id')}.\n\n"
            + QUE_FAZER[ev["tipo"]].replace("{id}", str(pid or "?")).replace("{thread}", str(ev.get("thread_id") or ""))
            + (f"\nRemetente: {ev['remetente'].get('nome') or '—'} <{ev['remetente'].get('email') or '—'}>." if ev.get("remetente") else "")
            + "\n\nSEMPRE: no idioma do cliente, educado e comercial (ainda é venda), respeitando o que ele pediu; não prometa "
              "preço, prazo ou desconto que não esteja no pedido ou na POLÍTICA; assine com a ASSINATURA. Se a conversa já tem "
              "as boas-vindas da URACE (agradecimento + manual de medidas), não mande de novo: siga do ponto em que está; e em "
              "pedido que começou antes da ponte não mande adendo de política por conta própria. O designer é designer, não "
              "fabricante: nunca diga ao cliente quem desenha nem quem fabrica, nem repasse texto, assinatura ou conversa dele. "
              "Na dúvida (reclamação, reembolso, cancelamento, troca, mudança de preço, conflito com a política, algo estranho), "
              "não responda: suits_precisa_humano com o motivo. No fim, se houver pedido, suits_anotar com o que fez em uma linha."
            + ("" if cfg.get("designer_email") else "\nO e-mail do designer ainda não foi configurado: se precisar falar com ele, "
               "use suits_precisa_humano dizendo o que mandaria.")
            + f"\n\nPOLÍTICA DOS MACACÕES (do dono):\n{cfg['politica']}"
            + f"\n\nMODELO DE BOAS-VINDAS (referência; adapte ao idioma e ao pedido):\n{cfg['boas_vindas']}"
            + f"\n\nASSINATURA:\n{cfg['assinatura']}"
            + "\n\nMENSAGENS NOVAS:\n" + "\n".join(linhas) + historico)


def _admin(con):
    a = um(con, "SELECT id FROM users WHERE role='ADMIN' AND active=1 ORDER BY id LIMIT 1")
    return a["id"] if a else None


def _executar_padrao(con, cid, texto, sk, uid, pr):
    from command_center.api import ia
    ia._executa(cid, texto, sk, uid, pr)


def tratar(con, ev, gm=None, executar=None, simular=False):
    """Um evento → um comando da IA (na conversa automática), com o pedido e os anexos. Bloqueia."""
    from command_center.providers import modulo, suits
    gm = gm or modulo("gmail")
    cfg = config(con)
    pid = ev.get("pedido_id")
    baixados = [baixar_anexos(gm, pid, m) if pid else [] for m in ev["mensagens"]]
    pr = prompt(con, ev, cfg, baixados)
    uid = _admin(con)
    if uid is None:
        return None
    texto = f"EVENTO AUTOMÁTICO — Suits{f' #{pid}' if pid else ''}: {ev['tipo']}"
    cid = inserir(con, "ai_commands", user_id=uid, text=texto, prompt=pr, session_key=f"suits-{pid or ev.get('thread_id')}")
    if pid:
        st = um(con, "SELECT status FROM suit_orders WHERE id=?", (pid,))["status"]
        suits.anotar(con, pid, {"venda": "A IA está abrindo o pedido da venda do site.", "cliente": "Chegou e-mail do cliente: a IA está tratando.",
                                "designer": "Chegou e-mail do designer: a IA está tratando.", "fornecedor": "Chegou e-mail do fornecedor.",
                                "simulacao": "Simulação da ponte neste pedido (nada sai)."}.get(ev["tipo"], "A IA está tratando."),
                     "ia", st, command_id=cid)
    marca = SIMULAR.set(bool(simular))
    try:
        (executar or _executar_padrao)(con, cid, texto, f"suits-{pid or ev.get('thread_id')}", uid, pr)
    finally:
        SIMULAR.reset(marca)
    return cid


def rodar(con, gm=None, executar=None):
    """Um ciclo da ponte. Devolve o resumo (vai para a auditoria)."""
    from command_center.api import ia
    from command_center.providers import modulo
    cfg = config(con)
    if cfg["ponte_ligada"] != "1":
        return {"pulada": "ponte desligada"}
    if executar is None and ia.motor_da_ia() != "sdk":
        return {"pulada": "a IA não está no motor novo (falta a chave da Anthropic no serviço)"}
    gm = gm or modulo("gmail")
    eventos, erros = [], []
    for fonte in (novas_vendas, respostas, conversas_novas):
        try:
            eventos += fonte(con, gm)
        except Exception as e:
            erros.append(f"{fonte.__name__}: {type(e).__name__}: {str(e)[:160]}")
    feitos = []
    for ev in eventos[:POR_CICLO]:
        _marcar(con, ev["mensagens"], ev.get("pedido_id"), ev.get("thread_id"), ev["tipo"])   # antes: se a IA cair, não repete em laço
        try:
            feitos.append({"tipo": ev["tipo"], "pedido": ev.get("pedido_id"), "comando": tratar(con, ev, gm, executar)})
        except Exception as e:
            erros.append(f"{ev['tipo']} #{ev.get('pedido_id')}: {type(e).__name__}: {str(e)[:160]}")
    res = {"eventos": len(eventos), "tratados": feitos, "ficaram_para_o_proximo": max(0, len(eventos) - POR_CICLO),
           "simulacao": cfg["envio_automatico"] != "1", "erros": erros}
    if eventos or erros:
        auditar(con, "suit.bridge.round", "system", detail=res)
    return res


def simular_pedido(con, pid, gm=None, executar=None):
    """Roda a ponte num pedido, com as conversas ligadas a ele, sem mandar nada (dono: "faça simulações")."""
    from command_center.providers import modulo
    p = um(con, "SELECT * FROM suit_orders WHERE id=?", (pid,))
    if not p:
        raise Recusado("pedido não encontrado")
    gm = gm or modulo("gmail")
    msgs = []
    for papel in ("cliente", "designer", "fornecedor"):
        if p[f"gmail_thread_{papel}"]:
            msgs += [dict(m, de=f"{m.get('de')} [{papel}]") for m in gm.mensagens_da_thread(CONTA, p[f"gmail_thread_{papel}"])["mensagens"]]
    if not msgs:
        msgs = [{"message_id": "-", "de": "(sem conversa ligada)", "data": "", "assunto": "", "corpo": "Ainda não há e-mail ligado a este "
                 "pedido. Faça o próximo passo com o que está no pedido (por exemplo, as boas-vindas se ainda não houve)."}]
    return tratar(con, {"tipo": "simulacao", "pedido_id": pid, "thread_id": p["gmail_thread_cliente"], "mensagens": msgs}, gm,
                  executar, simular=True)


_LOCK = threading.Lock()


def rodar_em_segundo_plano():
    """Chamado pelo ciclo do painel: um ciclo por vez, sem travar a sincronia."""
    if not _LOCK.acquire(blocking=False):
        return False

    def _vai():
        con = conectar()
        try:
            rodar(con)
        except Exception as e:
            try:
                auditar(con, "suit.bridge.failed", "system", detail={"erro": f"{type(e).__name__}: {str(e)[:300]}"})
            except Exception:
                pass
        finally:
            con.close()
            _LOCK.release()
    threading.Thread(target=_vai, daemon=True, name="cc-suits-ponte").start()
    return True
