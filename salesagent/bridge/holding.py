"""Nunca deixe um lead sem resposta.

Causa raiz do incidente de 25/08 (lead 31764961, "can i bring my own
kart?"): `process_inbound` tinha DOIS caminhos que davam `return` sem
mandar nada ao lead -- gatilho de escalação B4 disparado (o lead some no
exato momento em que pergunta algo sensível) e mensagem chegando em
conversa já escalada (G3, silêncio em toda mensagem seguinte). Um terceiro
caminho fazia o mesmo quando o próprio agente falhava. O log daquele dia
mostra `inbound` + `transition` sem nenhum `outbound` correspondente: o
Eduardo perguntou e o Chase simplesmente não respondeu.

Regra que este módulo existe para garantir: **toda mensagem de lead produz
uma mensagem de volta**. Quando a resposta certa depende de um humano, o
lead recebe um reconhecimento honesto -- que não inventa, não promete prazo
que não controlamos, e mantém a conversa aberta -- em vez de silêncio.

Por que texto estático e não o modelo: os caminhos que este módulo cobre
são justamente aqueles em que o modelo não pode (B4: desconto/refund não
passam pelo modelo, por design) ou não conseguiu responder (OpenClaw fora
do ar, timeout). Uma mensagem de espera que depende do mesmo componente
que falhou não é garantia nenhuma.
"""
import re

import textproc

# ------------------------------------------------------------------ idioma
# Heurística deliberadamente simples: o lead escreve poucas palavras e só
# precisamos escolher entre três conjuntos de frases. Marcadores exclusivos
# de cada idioma (palavras que praticamente não aparecem no outro) valem
# mais que palavras compartilhadas -- "para"/"tem" existem em PT e ES e por
# isso ficam de fora.
_PT_MARKERS = re.compile(
    r"\b(não|nao|você|voce|vocês|voces|vcs|obrigad[oa]|quanto|custa|preço|preco|"
    r"posso|meu|minha|olá|ola|oi|bom dia|boa tarde|boa noite|qual|quero|"
    r"gostaria|criança|crianca|filho|filha|aulas?|corrida)\b", re.IGNORECASE)
_ES_MARKERS = re.compile(
    r"\b(hola|gracias|cuánto|cuanto|cuesta|puedo|quiero|quisiera|ustedes|"
    r"niñ[oa]|nino|hij[oa]|clases?|carrera|buenos días|buenas tardes|"
    r"precio|dónde|donde|cómo|como está)\b", re.IGNORECASE)
_PT_ONLY_CHARS = re.compile(r"[ãõçâê]")
_ES_ONLY_CHARS = re.compile(r"[ñ¿¡]")


def detect_language(text: str) -> str:
    """'pt' | 'es' | 'en'. Inglês é o default -- a maioria dos leads da
    URACE escreve em inglês, e uma frase de espera em inglês para um lead
    lusófono é muito menos ruim que o contrário."""
    pt = len(_PT_MARKERS.findall(text)) + 2 * len(_PT_ONLY_CHARS.findall(text))
    es = len(_ES_MARKERS.findall(text)) + 2 * len(_ES_ONLY_CHARS.findall(text))
    if pt == 0 and es == 0:
        return "en"
    return "pt" if pt >= es else "es"


# ------------------------------------------------------- frases de espera
# Rotacionadas por número de mensagens já respondidas assim: um lead que
# manda três mensagens seguidas enquanto espera não pode ouvir a MESMA
# frase três vezes -- isso é o que denuncia um robô. A última frase da
# lista se repete se a espera se estender (e o re-alerta ao humano, a cada
# 15min, é o que de fato resolve a espera -- ver scheduler.py).
_WAITING = {
    "pt": [
        "Boa pergunta - essa eu prefiro confirmar com a equipe pra te "
        "passar a informação certa. Volto aqui com a resposta.",
        "Já pedi a confirmação pra equipe pra não te passar nada errado. "
        "Assim que tiver a resposta, te falo por aqui.",
        "Continuo com a equipe nessa sua pergunta. Não te esqueci - assim "
        "que tiver a resposta certa, te aviso aqui mesmo.",
    ],
    "es": [
        "Buena pregunta - prefiero confirmarla con el equipo para darte la "
        "información correcta. Vuelvo por aquí con la respuesta.",
        "Ya pedí la confirmación al equipo para no darte información "
        "equivocada. En cuanto la tenga, te aviso por aquí.",
        "Sigo con el equipo revisando tu pregunta. No te olvidé - apenas "
        "tenga la respuesta correcta, te aviso aquí mismo.",
    ],
    "en": [
        "Good question - I'd rather confirm that with our team so I give "
        "you the right answer. I'll come back to you right here.",
        "I've asked the team to confirm so I don't give you the wrong "
        "info. As soon as I have it, I'll let you know here.",
        "Still with the team on your question. I haven't forgotten you - "
        "as soon as I have the right answer, I'll let you know right here.",
    ],
}

# Lead só mandou "ok"/"thanks" enquanto espera: responder "vou confirmar"
# de novo soa robótico. Um humano só agradeceria de volta.
_ACK_RE = re.compile(
    r"^\W*(ok(ay)?|k|thanks?|thank you|ty|obrigad[oa]|valeu|vlw|blz|"
    r"beleza|gracias|perfect|great|cool|sure|👍|🙏|❤️?)\W*$", re.IGNORECASE)
_ACK = {
    "pt": "Combinado. Te falo assim que tiver a confirmação.",
    "es": "Perfecto. Te aviso apenas tenga la confirmación.",
    "en": "Sounds good. I'll get back to you as soon as I have it.",
}


def is_acknowledgement(text: str) -> bool:
    """Mensagem que não faz pergunta nenhuma ('ok', 'thanks', 'valeu')."""
    return bool(_ACK_RE.match(text.strip()))


# Ping: saudação ou checagem de presença -- o lead cutucando, não
# perguntando algo novo. Distinção importa duas vezes: um ping durante a
# espera deve citar a PERGUNTA ORIGINAL (é sobre ela que ele quer notícia),
# e um ping NÃO deve reavisar os humanos no WhatsApp (a pergunta continua a
# mesma). Uma pergunta nova faz o oposto nos dois pontos.
_SAUDACAO = (r"(oi+|ol[áa]+|hi+|hey+|hello+|hola+|opa|e\s?a[íi]|bom dia|"
             r"boa tarde|boa noite|good (morning|afternoon|evening)|"
             r"buenos d[íi]as|buenas (tardes|noches))")
_PRESENCA = (r"(are you (still )?there|you there|anyone( there)?|still there|"
             r"alg[uú][ée]m( a[íi])?|ta a[íi]|t[áa] a[íi]|cad[êe]( voc[êe])?)")
# saudações e/ou checagem de presença, em qualquer combinação ("hello? are
# you there?"), e nada além disso.
_PING_RE = re.compile(
    r"^\W*(" + _SAUDACAO + r"[\s!,.?]*|" + _PRESENCA + r"[\s!,.?]*)+$"
    r"|^\W*\?+[\s!,.?]*$",
    re.IGNORECASE)


def is_substantive(text: str) -> bool:
    """Mensagem com conteúdo próprio (pergunta/informação nova) -- por
    oposição a ping e agradecimento."""
    limpo = (text or "").strip()
    if not limpo or len(limpo) < 3:
        return False
    return not (_PING_RE.match(limpo) or _ACK_RE.match(limpo))


# Espera COM contexto: cita a pergunta do lead de volta. É o que separa
# "Still with the team on your question" (qual pergunta? soa robô) de
# 'About "can I bring my own kart?" - still confirming with the team'. A
# citação é verbatim, então funciona em qualquer idioma sem tradução -- e
# prova ao lead que a pergunta dele foi lida, não engolida por um sistema.
_WAITING_REF = {
    "pt": [
        'Sobre "{q}" - essa eu confirmo com a equipe pra te passar a '
        'informação certa. Volto aqui com a resposta.',
        'Sua pergunta "{q}" está com a equipe. Não te esqueci - assim que '
        'tiver a resposta certa, te aviso aqui mesmo.',
        'Sigo atrás da resposta pra "{q}". Assim que confirmar, te falo '
        'por aqui.',
    ],
    "es": [
        'Sobre "{q}" - eso lo confirmo con el equipo para darte la '
        'información correcta. Vuelvo por aquí con la respuesta.',
        'Tu pregunta "{q}" está con el equipo. No te olvidé - apenas tenga '
        'la respuesta correcta, te aviso aquí mismo.',
        'Sigo con la respuesta para "{q}". En cuanto la confirme, te aviso '
        'por aquí.',
    ],
    "en": [
        'About "{q}" - I\'m confirming that with our team so I give you '
        'the right answer. I\'ll come back to you right here.',
        'Your question "{q}" is with the team. I haven\'t forgotten you - '
        'as soon as I have the right answer, I\'ll let you know here.',
        'Still working on the answer to "{q}". As soon as I have it '
        'confirmed, I\'ll tell you right here.',
    ],
}


def _citavel(pergunta: str | None, limite: int = 70) -> str:
    """Encurta a pergunta para caber numa citação sem virar um parágrafo."""
    q = " ".join((pergunta or "").split())
    if len(q) > limite:
        q = q[:limite].rsplit(" ", 1)[0] + "..."
    return q


# Primeiro contato: o lead não faz ideia de quem está falando com ele. Isto
# acontece de verdade -- se a PRIMEIRA mensagem do lead bate num gatilho B4
# ("can i bring my own kart?" bateu), a conversa escala antes do agente
# rodar, e o lead levaria um "vou confirmar" de um estranho sem nome. A
# apresentação segue o mesmo texto do template de abertura das instruções
# do Chase, para o lead ouvir sempre a mesma voz.
_APRESENTACAO = {
    "pt": "Oi{nome}, aqui é o Chase, assistente da URACE.",
    "es": "Hola{nome}, soy Chase, asistente de URACE.",
    "en": "Hi{nome}, this is Chase, URACE's assistant.",
}


def _primeiro_nome(contact_name: str | None) -> str:
    """', Eduardo' ou '' -- nunca deixa um nome faltando travar a mensagem
    (regra das instruções: nome ausente não bloqueia nada)."""
    if not contact_name:
        return ""
    primeiro = contact_name.strip().split()
    return f" {primeiro[0]}" if primeiro else ""


def waiting_message(lead_text: str, sent_before: int = 0,
                    contact_name: str | None = None,
                    first_contact: bool = False,
                    pending_question: str | None = None) -> str:
    """A mensagem que o lead recebe quando a resposta depende de um humano.

    `sent_before` = quantas mensagens de espera este lead já recebeu nesta
    escalação (0 na primeira). `first_contact` = a ponte nunca falou com
    este lead antes, então a mensagem se apresenta. `pending_question` = a
    pergunta que está esperando o humano; quando existe, a espera CITA a
    pergunta de volta -- se a mensagem atual é substantiva, ela mesma é a
    pergunta a citar; se é só um ping ("oi", "are you there?"), cita a
    pendente. Passa pelo mesmo `customer_facing()` que o texto do modelo --
    a regra de dash vale para todo texto que sai daqui.
    """
    lang = detect_language(lead_text)
    if sent_before > 0 and is_acknowledgement(lead_text):
        return textproc.customer_facing(_ACK[lang])
    ref = _citavel(lead_text if is_substantive(lead_text) else pending_question)
    if ref:
        variants = _WAITING_REF[lang]
        texto = variants[min(sent_before, len(variants) - 1)].format(q=ref)
    else:
        variants = _WAITING[lang]
        texto = variants[min(sent_before, len(variants) - 1)]
    if first_contact:
        texto = (_APRESENTACAO[lang].format(nome=_primeiro_nome(contact_name))
                 + " " + texto)
    return textproc.customer_facing(texto)


# --------------------------------------------------------------- self-test
def self_test() -> int:
    failures = []

    def check(label, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {label}" + ("" if cond else f"  {detail}"))
        if not cond:
            failures.append(label)

    check("inglês é o default", detect_language("can i bring my own kart?") == "en")
    check("detecta português", detect_language("posso levar meu kart próprio?") == "pt")
    check("detecta espanhol", detect_language("¿puedo llevar mi kart?") == "es")
    check("PT não vira ES por palavra compartilhada",
          detect_language("qual o valor para meu filho?") == "pt")
    check("texto vazio não quebra", detect_language("") == "en")

    first = waiting_message("can i bring my own kart?", 0)
    second = waiting_message("any news?", 1)
    third = waiting_message("hello?", 2)
    fourth = waiting_message("hello?", 9)
    check("sempre devolve texto", all(m.strip() for m in (first, second, third)))
    check("não repete a mesma frase em sequência", first != second != third)
    check("estabiliza na última variante depois de esgotar", third == fourth)
    check("nunca promete prazo",
          not re.search(r"\b(\d+\s*(min|hour|hora|day|dia)|today|hoje|hoy)\b",
                        " ".join(_WAITING["en"] + _WAITING["pt"] + _WAITING["es"]),
                        re.IGNORECASE))
    check("nunca expõe arquitetura",
          not re.search(r"\b(bridge|ponte|escala|escalat|agent|bot|sistema|error|erro)\b",
                        " ".join(_WAITING["en"] + _WAITING["pt"] + _WAITING["es"]),
                        re.IGNORECASE))
    check("sem em/en dash depois do customer_facing",
          not re.search(r"[–—]", first + second + third))

    check("reconhece agradecimento", is_acknowledgement("thanks!") and
          is_acknowledgement("valeu") and is_acknowledgement("ok"))
    check("pergunta real não é agradecimento",
          not is_acknowledgement("ok but how much is it?"))
    check("agradecimento na espera recebe resposta curta",
          waiting_message("thanks!", 1) == textproc.customer_facing(_ACK["en"]))
    check("primeira mensagem nunca é a resposta curta",
          waiting_message("thanks!", 0) == textproc.customer_facing(_WAITING["en"][0]))

    # Primeiro contato: o lead precisa saber com quem está falando.
    ap = waiting_message("can i bring my own kart?", 0,
                         contact_name="Eduardo F F Resende", first_contact=True)
    check("primeiro contato se apresenta", "Chase" in ap and "URACE" in ap, ap)
    check("primeiro contato usa o primeiro nome", "Hi Eduardo," in ap, ap)
    check("apresentação não repete nas mensagens seguintes",
          "Chase" not in waiting_message("hello?", 1, contact_name="Eduardo",
                                         first_contact=False))
    check("sem nome não quebra a apresentação",
          "Chase" in waiting_message("hola", 0, first_contact=True))
    check("apresentação segue o idioma do lead",
          "asistente" in waiting_message("¿puedo llevar mi kart?", 0,
                                         first_contact=True))
    check("apresentação em pt usa 'aqui é o Chase'",
          "aqui é o Chase" in waiting_message("posso levar meu kart?", 0,
                                              first_contact=True))

    # Nexo: a espera cita a pergunta que está pendente.
    check("ping detectado", not is_substantive("Oi") and not is_substantive("Hi")
          and not is_substantive("hello? are you there?")
          and not is_substantive("???"))
    check("pergunta real é substantiva",
          is_substantive("Can i bring my own kart?")
          and is_substantive("do you rent helmets"))

    m = waiting_message("Can i bring my own kart?", 1,
                        pending_question="Can i bring my own kart?")
    check("pergunta repetida é citada de volta",
          '"Can i bring my own kart?"' in m, m)
    m = waiting_message("Hi", 2, pending_question="Can i bring my own kart?")
    check("ping durante a espera cita a pergunta ORIGINAL",
          "own kart" in m, m)
    m = waiting_message("posso levar meu kart próprio?", 0,
                        pending_question="posso levar meu kart próprio?")
    check("citação segue o idioma do lead (pt)", "Sobre" in m and "kart" in m, m)
    m1 = waiting_message("Hi", 0, pending_question="Can i bring my own kart?")
    m2 = waiting_message("Hi", 1, pending_question="Can i bring my own kart?")
    check("citação também rotaciona (não repete a frase)", m1 != m2, f"{m1!r}")
    longa = "can i bring my own kart and also my own tires and my own fuel and my mechanic team"
    m = waiting_message(longa, 0, pending_question=longa)
    check("pergunta longa é encurtada na citação", "..." in m and len(m) < 220, m)
    m = waiting_message("Hi", 0, pending_question=None)
    check("sem pergunta pendente cai no texto genérico", "team" in m, m)

    print()
    if failures:
        print(f"SELF TEST FALHOU - {len(failures)}")
        return 1
    print("SELF TEST PASSOU - idioma, rotação, ausência de prazo/arquitetura "
          "e reconhecimento de agradecimento verificados")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(self_test())
