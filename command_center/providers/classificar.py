"""Sugere o marcador de destino de cada thread da inbox.

Duas camadas, sempre com o "por quê":
1. regras — baratas e explicáveis: marcador do usuário já aplicado pelo
   filtro do Gmail; remetente/assunto que casam com a taxonomia do dono
   (brain/40_SISTEMAS/Taxonomia do Gmail.md).
2. IA — o agente urace-admin recebe o resto em lote e responde JSON com
   UM marcador da lista real da caixa. Nunca inventa marcador: a resposta
   é validada contra os nomes existentes.

Nada aqui escreve no Gmail. Mover é um clique humano (rotas.py).
"""
import json
import re

SISTEMA = {"INBOX", "UNREAD", "STARRED", "IMPORTANT", "SENT", "DRAFT", "SPAM", "TRASH", "CHAT",
           "CATEGORY_PERSONAL", "CATEGORY_SOCIAL", "CATEGORY_PROMOTIONS", "CATEGORY_UPDATES", "CATEGORY_FORUMS"}

# (regex no remetente | regex no assunto) -> marcador preferido, motivo
REGRAS = [
    (r"docusign", None, "Softwares|Apps/Docusign", "remetente DocuSign"),
    (r"bankofamerica|bofa", None, "Banks/Bank of America", "remetente Bank of America"),
    (r"americanexpress|amex", None, "Banks/American Express", "remetente American Express"),
    (None, r"new message from .urace", "Marketing & Sales/Comercial/Formulario do site", "formulário do site"),
    (r"rdstation|rd station|resultadosdigitais", None, "Marketing/RD Station", "remetente RD Station"),
    (None, r"\b(tracking|shipped|shipment|delivery|entrega|rastreio)\b", "Shipping Status", "assunto de envio"),
    (None, r"\b(payment received|payment confirmation|pagamento recebido|you (?:ve |have )?got paid|deposit(?:ed)? into)\b", "Finances", "confirmação de pagamento recebido"),
    (None, r"\b(statement|extrato) (?:is )?(?:ready|available|dispon)", "Finances", "extrato disponível"),
    (None, r"\b(invoice|fatura|faturamento|boleto|payment request|cobran)", "Finances/Pending Invoices ❗", "assunto de cobrança"),
    (r"google\.com|no-reply@accounts\.google", None, "Platforms & Subscriptions/Google", "remetente Google"),
    (None, r"\b(newsletter|unsubscribe|promo|sale|% off|oferta|desconto)\b", "wNews", "assunto de propaganda"),
    (r"noreply|no-reply|newsletter|marketing@|news@|promo", None, "wNews", "remetente de envio em massa"),
]


def _acha(nomes, alvo):
    """Nome real do marcador na caixa (tolerante a caixa alta/baixa e a prefixo)."""
    if not alvo:
        return None
    baixo = {n.lower(): n for n in nomes}
    if alvo.lower() in baixo:
        return baixo[alvo.lower()]
    ult = alvo.split("/")[-1].lower()
    for n in nomes:
        if n.lower().endswith("/" + ult) or n.lower() == ult:
            return n
    return None


def por_regras(email, nomes_marcadores):
    """Devolve (marcador, motivo, origem) ou None."""
    try:
        atuais = json.loads(email.get("labels") or "[]")
    except ValueError:
        atuais = []
    usuario = [l for l in atuais if l and l.upper() not in SISTEMA and not l.startswith("CATEGORY_")]
    if usuario:
        return usuario[0], f"já tem o marcador '{usuario[0]}' (filtro do Gmail)", "label"
    de = (email.get("sender") or "").lower()
    assunto = (email.get("subject") or "").lower()
    for rx_de, rx_ass, alvo, motivo in REGRAS:
        if rx_de and re.search(rx_de, de) or rx_ass and re.search(rx_ass, assunto):
            real = _acha(nomes_marcadores, alvo)
            if real:
                return real, motivo, "rules"
    return None


def prompt_ia(emails, nomes_marcadores, caixa):
    """Um pedido só para o agente, com resposta em JSON estrito."""
    linhas = [f"- id={e['id']} | de: {e.get('sender') or ''} | assunto: {e.get('subject') or ''} | trecho: {(e.get('snippet') or '')[:160]}"
              for e in emails]
    return (f"TAREFA: classificar {len(emails)} threads da inbox de {caixa}@urace.us no marcador de destino, "
            "seguindo brain/10_PROCESSOS/Triagem de e-mail.md e brain/40_SISTEMAS/Taxonomia do Gmail.md. "
            "Use SOMENTE marcadores desta lista (nome exato): " + json.dumps(nomes_marcadores, ensure_ascii=False) + ". "
            "Não leia as threads, não rotule, não mova, não escreva nada: só classifique pelo que está aqui. "
            "RESPONDA APENAS com um JSON no formato {\"itens\":[{\"id\":<int>,\"marcador\":\"<nome exato ou null>\",\"motivo\":\"<até 12 palavras>\"}]} "
            "e nada mais.\n" + "\n".join(linhas))


def parse_ia(texto, nomes_marcadores):
    """Extrai o JSON da resposta e valida cada marcador contra a lista real."""
    m = re.search(r"\{.*\}", texto or "", re.S)
    if not m:
        return {}
    try:
        dados = json.loads(m.group(0))
    except ValueError:
        return {}
    saida = {}
    for it in dados.get("itens", []):
        try:
            i = int(it.get("id"))
        except (TypeError, ValueError):
            continue
        real = _acha(nomes_marcadores, it.get("marcador"))
        saida[i] = (real, (it.get("motivo") or "")[:200]) if real else (None, "IA não achou marcador válido")
    return saida


# Marcadores cujo e-mail não pede humano: notificação de sistema, propaganda, banco.
NOTIFICACAO_PREFIXOS = ("softwares|apps/", "platforms & subscriptions/", "marketing/rd station", "banks/", "wnews", "shipping status")
NOSSOS_DOMINIOS = ("@urace.us",)
AVISO_DOCUSIGN = re.compile(r"\b(completed|conclu[ií]do|viewed|visualizou|anulado|voided|please complete the docusign|declined)\b", re.I)


# Resposta automática de ausência: ninguém precisa responder de volta.
AUSENCIA = re.compile(r"\b(out of (?:the )?office|ooo|unavailable|automatic reply|auto[- ]?reply|resposta autom|"
                      r"estarei fora|f[ée]rias|vacation|away from (?:my )?(?:desk|email)|no escrit[óo]rio somente)\b", re.I)


def auto_tratar(email, sugestao):
    """Motivo pelo qual este e-mail NÃO precisa de humano, ou None.

    A IA se corrige aqui: o que é notificação, propaganda ou coisa que nós
    mesmos mandamos não vira item de atenção — vira 'tratado automaticamente'.
    """
    de = (email.get("sender") or "").lower()
    assunto = (email.get("subject") or "").lower()
    if any(d in de for d in NOSSOS_DOMINIOS):
        return "enviado por nós (urace.us)"
    if AUSENCIA.search(assunto) or AUSENCIA.search((email.get("snippet") or "")[:160]):
        return "resposta automática de ausência (não pede resposta)"
    if "docusign" in de or AVISO_DOCUSIGN.search(assunto) and "docusign" in assunto:
        return "notificação do DocuSign (o status vem do próprio DocuSign)"
    if sugestao:
        lab = sugestao.lower()
        for pref in NOTIFICACAO_PREFIXOS:
            if lab.startswith(pref):
                return f"notificação/propaganda ({sugestao})"
    if re.search(r"\b(nova convers[aã]o|new lead|rdstation)\b", assunto) or "rdstation" in de:
        return "lead do RD Station (vai para o funil, não para a inbox)"
    if re.search(r"\b(your tickets|here's your pass|pit & driver pass|receipt|recibo)\b", assunto):
        return "confirmação automática (ingresso/recibo)"
    return None
