"""Suits (Alpha Line): as regras dos pedidos de macacão (#153). As rotas moram em `api/suits.py`.

Dono, 08/10: *"na aba de suítes ... registrar novo pedido ... Sempre dê a oportunidade ali de eu
adicionar uma nota, às vezes um screenshot para IA poder entender, já avançar com aquilo ali no
status que estiver"* e *"O envio ao Usman ... tem um padrão de envio. Salva esse padrão como
template"*. Processo: `brain/10_PROCESSOS/Pedido de macacão.md`.

- **Etapas**: as nove do quadro SUITS do Asana mais "Approved" (o "aprovado, podemos mandar para
  produção?" que o dono descreveu) — dez ao todo.
- **Medidas**: as 29 do formulário (+ 6bis, só mulheres), na ordem que o fornecedor lê. O valor
  fica como o cliente deu (número e unidade); o e-mail mostra as duas unidades. O tamanho do pé
  é texto: EUR ↔ US não tem conta exata, e NO FAKE DATA.
- **E-mail do fornecedor**: o padrão dos e-mails já enviados ao Usman, guardado como modelo
  editável (`suit_templates`).
- **Importar do Asana**: o projeto SUITS, só leitura, sem duplicar se rodar de novo.
"""
import json
import re

from command_center.db import agora, inserir, todos, um

ETAPAS = [
    ("standby", "Standby", "pedido criado, esperando o próximo passo"),
    ("awaiting_measurements", "Awaiting Measurements", "esperando o cliente mandar as medidas"),
    ("design_pending", "Design Pending", "pago, com as ideias de design: o designer trabalha"),
    ("design_review", "Design Under Client Review", "o cliente está revisando o design"),
    ("approved", "Approved", "cliente aprovou o design e as medidas: pode ir para produção"),
    ("sent_to_supplier", "Order sent to supplier", "pedido enviado ao fornecedor"),
    ("in_production", "In Production", "o fornecedor está produzindo"),
    ("in_transit", "In Transit", "o fornecedor despachou"),
    ("delivered", "Delivered", "entregue ao cliente"),
    ("canceled", "Canceled", "cancelado"),
]
CODIGOS = [e[0] for e in ETAPAS]
FECHADAS = ("delivered", "canceled")

# status do Asana (campo "Status" do projeto SUITS) → etapa daqui
DO_ASANA = {"Standby": "standby", "Awaiting Measurements": "awaiting_measurements", "Design Pending": "design_pending",
            "Design Under Client Review": "design_review", "Order sent to Usman": "sent_to_supplier",
            "In Production": "in_production", "In Transit": "in_transit", "Delivered": "delivered", "Canceled": "canceled"}

# (chave, número no formulário, nome em inglês — como o fornecedor lê, tipo)
MEDIDAS = [
    ("head", "1", "Head circumference", "comp"),
    ("forehead_neck", "2", "Distance from forehead to neck", "comp"),
    ("neck", "3", "Neck circumference", "comp"),
    ("chin_neck", "4", "Distance from chin to neck", "comp"),
    ("shoulder", "5", "Shoulder width", "comp"),
    ("chest", "6", "Chest circumference", "comp"),
    ("bust", "6bis", "Bust circumference", "comp"),          # só mulheres
    ("waist", "7", "Waist circumference", "comp"),
    ("hip", "8", "Hip circumference", "comp"),
    ("neck_back", "9", "Distance from neck to back", "comp"),
    ("neck_tailbone", "10", "Distance from neck to tail bone", "comp"),
    ("arm", "11", "Arm length", "comp"),
    ("elbow_wrist", "12", "Distance from elbow to wrist", "comp"),
    ("biceps", "13", "Biceps circumference", "comp"),
    ("elbow", "14", "Elbow circumference", "comp"),
    ("forearm", "15", "Forearm circumference", "comp"),
    ("wrist", "16", "Wrist circumference", "comp"),
    ("thigh", "17", "Thigh circumference", "comp"),
    ("knee", "18", "Knee circumference", "comp"),
    ("calf", "19", "Calf circumference", "comp"),
    ("ankle", "20", "Ankle circumference", "comp"),
    ("waist_ankle", "21", "Distance from waist to ankle", "comp"),
    ("groin_ankle", "22", "Distance from groin to ankle", "comp"),
    ("knee_ankle", "23", "Distance from knee to ankle", "comp"),
    ("trapezius_ankle", "24", "Distance from trapezius to ankle", "comp"),
    ("trapezius_floor", "25", "Distance from trapezius to floor", "comp"),
    ("nipple_ankle", "26", "Distance from nipple to ankle", "comp"),
    ("height", "27", "Height", "comp"),
    ("weight", "28", "Weight", "peso"),
    ("foot", "29", "Foot size", "texto"),
]
CHAVES = {m[0] for m in MEDIDAS}
OBRIGATORIAS = [m[0] for m in MEDIDAS if m[0] != "bust"]

DESIGN = [("ideia", "Ideia / mockup de referência"), ("cores", "Cores (Pantone, se tiver)"), ("logos", "Logos"),
          ("posicao_logos", "Onde vai cada logo"), ("nome", "Nome a aplicar"), ("bandeira", "Bandeira"),
          ("observacoes", "Observações do cliente")]


class Invalido(ValueError):
    """Dado que não dá para gravar; a mensagem vai para a tela."""


# ------------------------------------------------------------------ medidas
def _num(v):
    if isinstance(v, bool):
        raise Invalido("medida inválida")
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d+)?", s):
        raise Invalido(f"'{v}' não é um número")
    return float(s)


def normalizar_medidas(valores, unidade="cm", unidade_peso="kg"):
    """{chave: valor} da tela → {chave: {"v": número, "u": unidade}} (ou {"t": texto} para o pé).
    Vazio some (não vira zero). Chave desconhecida é recusada."""
    if unidade not in ("cm", "in") or unidade_peso not in ("kg", "lb"):
        raise Invalido("unidade inválida")
    saida = {}
    for chave, valor in (valores or {}).items():
        if chave not in CHAVES:
            raise Invalido(f"medida desconhecida: {chave}")
        if valor is None or str(valor).strip() == "":
            continue
        tipo = next(m[3] for m in MEDIDAS if m[0] == chave)
        if tipo == "texto":
            saida[chave] = {"t": str(valor).strip()[:40]}
        else:
            n = _num(valor)
            if n <= 0 or n > 400:
                raise Invalido(f"{chave}: valor fora do razoável ({valor})")
            saida[chave] = {"v": n, "u": unidade_peso if tipo == "peso" else unidade}
    return saida


def _fmt(n):
    return f"{n:.1f}".rstrip("0").rstrip(".")


def _pes_polegadas(pol):
    meio = round(pol * 2) / 2
    pes, resto = int(meio // 12), meio - 12 * int(meio // 12)
    return f"{pes}'{_fmt(resto)}\"" if pes else f"{_fmt(resto)}\""


def texto_medida(chave, m):
    """'59 cm / 1'11"' — as duas unidades, como o fornecedor lê."""
    if not m:
        return ""
    if "t" in m:
        return m["t"]
    v, u = m["v"], m["u"]
    if u == "kg":
        return f"{_fmt(v)} kg / {_fmt(round(v * 2.20462, 1))} lb"
    if u == "lb":
        return f"{_fmt(round(v / 2.20462, 1))} kg / {_fmt(v)} lb"
    cm, pol = (v, v / 2.54) if u == "cm" else (round(v * 2.54, 1), v)
    return f"{_fmt(cm)} cm / {_pes_polegadas(pol)}"


def faltando(medidas):
    return [m[0] for m in MEDIDAS if m[0] in OBRIGATORIAS and m[0] not in (medidas or {})]


def bloco_medidas(medidas):
    linhas = []
    for chave, num, nome, _ in MEDIDAS:
        m = (medidas or {}).get(chave)
        if chave == "bust" and not m:
            continue
        linhas.append(f"{num} – {nome} — {texto_medida(chave, m) if m else '(missing)'}")
    return "\n".join(linhas)


# ------------------------------------------------------------ e-mail ao fornecedor
MODELO_PADRAO = {
    "subject": "SUIT - {piloto}",
    "body": ("Hi {fornecedor},\n\nWe have a new order:\n\n{medidas}\n\n{design}"
             "Best regards,\n{assinatura}\nUrace\n+1(407)2502291\nurace@urace.us\nwww.urace.us\n"
             "10724 Cosmonaut Blvd, Orlando, FL 32824, USA"),
}
CAMPOS_MODELO = ("{piloto}", "{fornecedor}", "{medidas}", "{design}", "{assinatura}", "{quantidade}")


def modelo(con):
    m = um(con, "SELECT subject, body, updated_at FROM suit_templates WHERE key='fornecedor'")
    return dict(m) if m else dict(MODELO_PADRAO, updated_at=None)


def email_fornecedor(con, pedido, fornecedor, quem):
    """O e-mail do pedido de produção, montado pelo modelo. `faltam` lista o que impede enviar."""
    med = json.loads(pedido.get("measurements") or "{}")
    des = json.loads(pedido.get("design") or "{}")
    faltam = []
    if faltando(med):
        faltam.append(f"{len(faltando(med))} medida(s)")
    if not fornecedor or not fornecedor.get("email"):
        faltam.append("e-mail do fornecedor")
    linhas_design = []
    if des.get("cores"):
        linhas_design.append(f"Colors: {des['cores']}")
    if (pedido.get("quantity") or 1) > 1:
        linhas_design.append(f"Quantity: {pedido['quantity']} suits")
    design = ("\n".join(linhas_design) + "\nThe final mockup is attached.\n\n") if linhas_design else "The final mockup is attached.\n\n"
    piloto = pedido.get("driver_name") or pedido.get("customer_name") or pedido.get("title") or ""
    nome_forn = (fornecedor or {}).get("contact") or (fornecedor or {}).get("name") or "there"
    valores = {"{piloto}": piloto, "{fornecedor}": nome_forn.split()[0] if nome_forn else "", "{medidas}": bloco_medidas(med),
               "{design}": design, "{assinatura}": (quem or {}).get("name") or "", "{quantidade}": str(pedido.get("quantity") or 1)}
    m = modelo(con)
    assunto, corpo = m["subject"], m["body"]
    for k, v in valores.items():
        assunto, corpo = assunto.replace(k, v), corpo.replace(k, v)
    return {"para": (fornecedor or {}).get("email"), "assunto": assunto, "corpo": corpo, "faltam": faltam}


# ------------------------------------------------------------ vincular ao cliente (#158)
# Dono, 08/10: "Todo lugar que a gente for fazer inserção manual, sempre coloque um para vincular com o
# cliente ... para poder vincular e puxar as informações pré-definidas ali daquele cliente."
# Medidas da área do cliente (portal) que são as MESMAS do formulário do macacão. Inseam e manga não
# entram: não são nenhuma das 29 (NO FAKE DATA).
DO_PORTAL = {"height_in": ("height", "in"), "weight_lb": ("weight", "lb"), "chest_in": ("chest", "in"),
             "waist_in": ("waist", "in"), "hips_in": ("hip", "in")}


def _endereco(conta):
    if not conta or not conta["address_line1"]:
        return None
    cidade = ", ".join(x for x in (conta["city"], " ".join(x for x in (conta["state"], conta["zip"]) if x)) if x)
    linhas = [conta["address_line1"], conta["address_line2"], cidade,
              conta["country"] if conta["country"] and conta["country"] != "US" else None]
    return "\n".join(x for x in linhas if x)


def dados_do_cliente(con, cid):
    """O que o cadastro já sabe deste cliente, para preencher o pedido: o card, a conta do site
    (endereço) e o piloto da área do cliente (medidas). Só o que existe; nada inventado."""
    c = um(con, "SELECT * FROM clients WHERE id=?", (cid,))
    if not c:
        return None
    piloto = um(con, "SELECT * FROM portal_pilots WHERE client_id=? AND active=1", (cid,))
    conta = um(con, "SELECT * FROM portal_accounts WHERE client_id=?", (cid,)) or (
        um(con, "SELECT * FROM portal_accounts WHERE id=?", (piloto["account_id"],)) if piloto else None)
    if conta and not piloto:
        pilotos = todos(con, "SELECT * FROM portal_pilots WHERE account_id=? AND active=1", (conta["id"],))
        if len(pilotos) == 1:
            piloto = pilotos[0]
    medidas = {}
    if piloto and piloto["measures"]:
        try:
            md = json.loads(piloto["measures"])
        except ValueError:
            md = {}
        for k, (chave, _) in DO_PORTAL.items():
            if isinstance(md.get(k), (int, float)) and md[k] > 0:
                medidas[chave] = md[k]
    return {"client_id": c["id"], "customer_name": c["name"], "customer_email": c["email"] or (conta["email"] if conta else None),
            "customer_phone": c["phone"] or (conta["phone"] if conta else None),
            "driver_name": c["pilot_name"] or (piloto["name"] if piloto and not piloto["is_self"] else None),
            "ship_address": _endereco(conta),
            "medidas": {"valores": medidas, "unidade": "in", "unidade_peso": "lb"} if medidas else None,
            "de_onde": {"card": True, "conta_do_site": bool(conta), "piloto": piloto["name"] if piloto else None}}


def vincular_por_email(con, pid):
    """Pedido sem cliente, com e-mail: liga sozinho quando há EXATAMENTE um cliente com aquele e-mail."""
    p = um(con, "SELECT client_id, customer_email FROM suit_orders WHERE id=?", (pid,))
    if not p or p["client_id"] or not p["customer_email"]:
        return None
    achados = todos(con, "SELECT id FROM clients WHERE lower(email)=lower(?) OR lower(coalesce(email_alt,''))=lower(?)",
                    (p["customer_email"].strip(), p["customer_email"].strip()))
    if len(achados) != 1:
        return None
    con.execute("UPDATE suit_orders SET client_id=? WHERE id=?", (achados[0]["id"], pid))
    return achados[0]["id"]


# ------------------------------------------------------------------- pedidos
def etapa_valida(s):
    if s not in CODIGOS:
        raise Invalido(f"etapa desconhecida: {s}")
    return s


def detalhe(con, pid):
    p = um(con, """SELECT o.*, s.name AS fornecedor, s.email AS fornecedor_email, u.name AS criado_por,
                          c.name AS cliente_nome, c.pilot_name AS cliente_piloto
                   FROM suit_orders o LEFT JOIN suit_suppliers s ON s.id=o.supplier_id
                   LEFT JOIN users u ON u.id=o.created_by LEFT JOIN clients c ON c.id=o.client_id WHERE o.id=?""", (pid,))
    if not p:
        return None
    p = dict(p)
    p["measurements"] = json.loads(p.get("measurements") or "{}")
    p["design"] = json.loads(p.get("design") or "{}")
    p["medidas_texto"] = {k: texto_medida(k, v) for k, v in p["measurements"].items()}
    p["faltam_medidas"] = faltando(p["measurements"])
    p["notas"] = [dict(n) for n in todos(con, """SELECT n.id, n.status, n.kind, n.text, n.image_path IS NOT NULL AS tem_imagem,
                                                        n.command_id, n.created_at, u.name AS autor
                                                 FROM suit_notes n LEFT JOIN users u ON u.id=n.user_id
                                                 WHERE n.order_id=? ORDER BY n.id""", (pid,))]
    return p


def anotar(con, pid, texto=None, kind="nota", status=None, imagem=None, user_id=None, command_id=None):
    return inserir(con, "suit_notes", order_id=pid, status=status, kind=kind, text=(texto or None) and texto[:4000],
                   image_path=imagem, user_id=user_id, command_id=command_id)


def mudar_etapa(con, pid, nova, user_id=None, motivo=None):
    """Troca a etapa e deixa o rastro na linha do tempo. Entregue/cancelado fecham o pedido."""
    etapa_valida(nova)
    p = um(con, "SELECT status FROM suit_orders WHERE id=?", (pid,))
    if not p or p["status"] == nova:
        return False
    extra = {"sent_to_supplier_at": agora()} if nova == "sent_to_supplier" else {}
    sets = ", ".join(f"{k}=?" for k in extra)
    con.execute(f"UPDATE suit_orders SET status=?, closed=?, updated_at=?{', ' + sets if sets else ''} WHERE id=?",
                (nova, 1 if nova in FECHADAS else 0, agora(), *extra.values(), pid))
    nome = dict((e[0], e[1]) for e in ETAPAS)
    anotar(con, pid, f"{nome[p['status']]} → {nome[nova]}" + (f": {motivo}" if motivo else ""), "etapa", nova, user_id=user_id)
    return True


# ------------------------------------------------------------ importar do Asana
SECOES_PEDIDO = {"Order", "Standby", "Seção sem título"}


def _produto(nome):
    n = nome.lower()
    if "t-shirt" in n or "tshirt" in n:
        return "T-shirt"
    if "table cover" in n:
        return "Table cover"
    if "sample" in n:
        return "Sample"
    return "Suit"


def _campos(t):
    return {c.get("name"): c.get("display_value") for c in t.get("custom_fields") or []}


_ROTULOS_FORN = {"contato": "contact", "e-mail": "email", "telefone": "phone", "tem fia": "has_fia", "status": "status",
                 "valor por macacão": "price", "frete por macacão": "shipping", "frete do sample": "shipping",
                 "forma de pagamento": "payment", "prazos internos": "lead_time", "comentários": "comments"}


def fornecedor_das_notas(notas):
    """'Contato: Asrar\\nE-mail: x@y\\nTem FIA: Não…' (a ficha do Asana) → campos. '—' é vazio."""
    saida = {}
    for linha in (notas or "").splitlines():
        if ":" not in linha:
            continue
        rot, val = linha.split(":", 1)
        campo = _ROTULOS_FORN.get(rot.strip().lower())
        val = val.strip()
        if not campo or not val or val in ("—", "-"):
            continue
        if campo == "has_fia":
            saida[campo] = 1 if val.lower().startswith("sim") else 0 if val.lower().startswith("n") else None
        elif campo == "email":
            saida[campo] = val.split(",")[0].strip()
            if "," in val:
                saida["comments"] = ((saida.get("comments") or "") + f" Outros e-mails: {val}").strip()
        else:
            saida[campo] = val
    return saida


def _fornecedor_por_nome(con, nome):
    if not nome:
        return None
    f = um(con, "SELECT id FROM suit_suppliers WHERE lower(name)=lower(?)", (nome.strip(),))
    if f:
        return f["id"]
    return inserir(con, "suit_suppliers", name=nome.strip())


def importar(con, tarefas):
    """As tarefas do projeto SUITS (com seção, campos e notas) → pedidos, leads e fornecedores.
    Já importada (mesmo gid) não é tocada: o que a equipe mudou aqui vale mais que o Asana."""
    res = {"pedidos": 0, "leads": 0, "fornecedores": 0, "ja_tinha": 0, "ignoradas": 0}
    for t in tarefas:
        gid, nome = t.get("gid"), (t.get("name") or "").strip()
        secao = next((m.get("section", {}).get("name") for m in t.get("memberships") or [] if m.get("section")), None)
        if not gid or not nome or nome.startswith("📋"):
            res["ignoradas"] += 1
            continue
        tabela = ("suit_orders" if secao in SECOES_PEDIDO else "suit_leads" if secao == "SUIT LEADS"
                  else "suit_suppliers" if secao == "Seleção de fornecedores" and nome != "Links" else None)
        if not tabela:
            res["ignoradas"] += 1
            continue
        if um(con, f"SELECT id FROM {tabela} WHERE asana_gid=?", (gid,)):
            res["ja_tinha"] += 1
            continue
        c = _campos(t)
        if tabela == "suit_suppliers":
            inserir(con, "suit_suppliers", name=nome, asana_gid=gid, **fornecedor_das_notas(t.get("notes")))
            res["fornecedores"] += 1
        elif tabela == "suit_leads":
            notas = (t.get("notes") or "").strip()
            email = next(iter(re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", notas)), None)
            extra = "; ".join(f"{k}: {v}" for k, v in c.items() if v and k in ("Status", "Obs", "Pedido"))
            inserir(con, "suit_leads", name=nome, email=email, notes="\n".join(x for x in (notas, extra) if x) or None,
                    status="perdido" if c.get("Status") == "Canceled" else "aberto", asana_gid=gid)
            res["leads"] += 1
        else:
            asana_status = c.get("Status")
            status = DO_ASANA.get(asana_status or "", "standby")
            fechado = 1 if t.get("completed") or status in FECHADAS else 0
            forn = c.get("Fornecedor") or c.get("Supplier")
            inserir(con, "suit_orders", title=nome, product=_produto(nome), customer_name=nome, status=status,
                    order_date=(c.get("Order Date") or "")[:10] or None, due_on=t.get("due_on"),
                    supplier_id=_fornecedor_por_nome(con, forn), source="asana", asana_gid=gid,
                    asana_notes=(t.get("notes") or None), asana_status=asana_status, closed=fechado,
                    created_at=t.get("created_at") or agora())
            res["pedidos"] += 1
    return res
