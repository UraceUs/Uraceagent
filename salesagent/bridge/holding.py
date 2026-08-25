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


def waiting_message(lead_text: str, sent_before: int = 0) -> str:
    """A mensagem que o lead recebe quando a resposta depende de um humano.

    `sent_before` = quantas mensagens de espera este lead já recebeu nesta
    escalação (0 na primeira). Passa pelo mesmo `customer_facing()` que o
    texto do modelo -- a regra de dash vale para todo texto que sai daqui,
    não só para o que o modelo escreve.
    """
    lang = detect_language(lead_text)
    if sent_before > 0 and is_acknowledgement(lead_text):
        return textproc.customer_facing(_ACK[lang])
    variants = _WAITING[lang]
    return textproc.customer_facing(variants[min(sent_before, len(variants) - 1)])


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
