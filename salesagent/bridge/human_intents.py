"""O que Italo ou Eduardo disseram no WhatsApp, virando ação.

Fecha o último passo manual do ciclo do brief: hoje a escalação chega no
WhatsApp com "Responda 'aprovar <lead> <instrução>' ou 'retomar <lead>'"
— e a resposta cai no vazio, porque ninguém lê. O Italo respondeu
"aprovado" numa escalação real em 26/08 e não aconteceu nada.

Este módulo é só o PARSER: texto livre em português → intenção estruturada.
Quem executa é a ponte (app.py), com os mesmos portões de sempre. Separado
de propósito: parsing de linguagem natural é onde erro acontece, e um
parser puro se testa exaustivamente sem tocar em CRM, lead ou estado.

Princípio: na dúvida, NÃO age. Uma intenção mal lida que aprova algo
errado custa muito mais caro que uma que pede para repetir a frase.
"""
import re

# Verbos por ação. A ordem importa: 'não salvar' precisa ser testado antes
# de 'salvar', senão o "não" some.
_ACOES = [
    ("dont_save", r"\b(n[ãa]o\s+salv|n[ãa]o\s+registr|n[ãa]o\s+guard|"
                  r"n[ãa]o\s+p[õo]e\s+no\s+brain)\w*"),
    ("save", r"\b(salv\w*|registr\w*|guard\w*)\s+(isso|essa|esse|este|esta|"
             r"a\s+informa|no\s+brain|isto)"),
    ("correct", r"\b(corrig\w*|est[áa]\s+errad|o\s+certo\s+[ée]|"
                r"na\s+verdade\s+[ée])"),
    ("close", r"\b(fech\w*|encerr\w*|finaliz\w*|pode\s+fechar)\b"),
    ("approve", r"\b(aprov\w*|autoriz\w*|pode\s+(sim|mandar|falar|responder)|"
                r"confirm\w*|libera\w*)\b"),
    ("resume", r"\b(retom\w*|devolv\w*|volta\s+pro\s+agente|"
               r"pode\s+continuar|segue)\b"),
]
_ACOES_RE = [(nome, re.compile(padrao, re.IGNORECASE)) for nome, padrao in _ACOES]

# Um id de lead do Kommo tem 6+ dígitos. Exigir isso evita que "aprovar 10%"
# ou uma idade no meio da frase vire lead_id.
_LEAD_RE = re.compile(r"\b(\d{6,})\b")

# A frase de comando que a ponte manda no briefing — se o humano der reply
# citando a mensagem inteira, ela volta junto e o lead_id dela é o certo,
# mas o texto dela NÃO é a resposta ao lead.
_ECO_BRIEFING = re.compile(
    r"(🔺\s*ESCALA[ÇC][ÃA]O|⏰\s*(RE-)?ALERTA|ÚLTIMO AVISO|"
    r"Responda\s+'?aprovar|Motivo:|Contexto:)", re.IGNORECASE)


def _limpar(texto: str) -> str:
    """Tira o eco do briefing citado, deixando só o que a pessoa escreveu."""
    linhas = [ln for ln in texto.splitlines() if not _ECO_BRIEFING.search(ln)]
    return "\n".join(linhas).strip()


def parse(texto: str, lead_em_foco: int | None = None) -> dict:
    """Texto do WhatsApp → intenção.

    `lead_em_foco` é o lead que a ponte escalou por último para esta pessoa:
    permite responder só "aprovado" sem repetir o número, que é como gente
    de verdade responde. Só é usado quando o texto não traz um id.

    Devolve sempre um dict com:
      action    approve | resume | close | correct | save | dont_save | unclear
      lead_id   int ou None
      message   o que deve chegar ao LEAD (vazio se a pessoa não ditou texto)
      needs     o que falta para poder agir (lista, vazia = pode agir)
    """
    bruto = (texto or "").strip()
    limpo = _limpar(bruto)
    # Se sobrou nada depois de tirar o eco, a pessoa só reencaminhou o aviso.
    base = limpo or bruto

    acao = "unclear"
    match_acao = None
    for nome, rx in _ACOES_RE:
        m = rx.search(base)
        if m:
            acao, match_acao = nome, m
            break

    m_lead = _LEAD_RE.search(base) or (_LEAD_RE.search(bruto) if limpo else None)
    lead_id = int(m_lead.group(1)) if m_lead else lead_em_foco

    # A mensagem ao lead é o que sobra depois do verbo e do número. Um
    # "aprovado" seco não carrega texto -- e isso é informação, não erro:
    # significa que o humano autorizou mas não ditou a resposta.
    mensagem = ""
    if match_acao and acao in ("approve", "resume", "correct", "save"):
        resto = base[match_acao.end():]
        if m_lead and m_lead.start() >= match_acao.end():
            resto = base[m_lead.end():]
        mensagem = re.sub(r"^[\s:,.\-–—]+", "", resto).strip()

    needs = []
    if acao == "unclear":
        needs.append("não entendi a ação (aprovar, retomar, fechar, corrigir)")
    # 'não salvar' é uma recusa: agir é NÃO fazer nada. Exigir um lead para
    # isso faria a ponte pedir esclarecimento para poder não fazer nada.
    if lead_id is None and acao != "dont_save":
        needs.append("qual lead")
    if acao == "correct" and not mensagem:
        needs.append("qual é a informação correta")

    return {"action": acao, "lead_id": lead_id, "message": mensagem,
            "needs": needs, "raw": bruto}


def confirmation_prompt(intent: dict) -> str:
    """O que responder no WhatsApp quando não dá para agir com segurança."""
    faltando = "; ".join(intent["needs"])
    return (f"Não consegui agir com segurança: {faltando}.\n"
            f"Exemplos que funcionam:\n"
            f"  aprovar 31764961 pode trazer o kart, inspecionamos antes\n"
            f"  retomar 31764961\n"
            f"  fechar 31764961")


# --------------------------------------------------------------- self-test
def self_test() -> int:
    falhas = []

    def check(label, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {label}" + ("" if cond else f"  {detail}"))
        if not cond:
            falhas.append(label)

    i = parse("aprovar 31764961 pode trazer o kart, a gente inspeciona antes")
    check("aprovar com lead e texto",
          i["action"] == "approve" and i["lead_id"] == 31764961
          and i["message"].startswith("pode trazer o kart"), str(i))

    i = parse("aprovado", lead_em_foco=31764961)
    check("'aprovado' seco usa o lead em foco",
          i["action"] == "approve" and i["lead_id"] == 31764961 and not i["needs"],
          str(i))
    check("'aprovado' seco não inventa mensagem ao lead", i["message"] == "")

    i = parse("retomar 31764961")
    check("retomar", i["action"] == "resume" and i["lead_id"] == 31764961)

    i = parse("pode fechar 31764961")
    check("fechar", i["action"] == "close" and i["lead_id"] == 31764961, str(i))

    i = parse("não salvar isso no brain", lead_em_foco=1)
    check("'não salvar' não vira 'salvar'", i["action"] == "dont_save", str(i))

    i = parse("não salvar isso")
    check("'não salvar' não exige lead (agir é não fazer nada)",
          i["action"] == "dont_save" and not i["needs"], str(i))

    i = parse("salvar isso no brain", lead_em_foco=1)
    check("salvar", i["action"] == "save", str(i))

    i = parse("corrigir 31764961 o certo é que o kart precisa chegar 1 dia antes")
    check("corrigir carrega a informação certa",
          i["action"] == "correct" and "1 dia antes" in i["message"], str(i))

    i = parse("corrigir 31764961")
    check("corrigir sem conteúdo pede o conteúdo",
          "qual é a informação correta" in " ".join(i["needs"]), str(i))

    i = parse("obrigado, valeu")
    check("conversa fiada não vira ação", i["action"] == "unclear", str(i))
    check("conversa fiada diz o que falta", bool(i["needs"]))

    i = parse("aprovar")
    check("aprovar sem lead e sem foco pede o lead",
          "qual lead" in " ".join(i["needs"]), str(i))

    i = parse("aprovar desconto de 10% para 31764961")
    check("número pequeno não vira lead_id", i["lead_id"] == 31764961, str(i))

    eco = ("🔺 ESCALAÇÃO — Eduardo F F Resende (lead 31764961)\n"
           "Motivo: kart próprio (inspeção/gestão)\n"
           "Contexto: Hi, can i bring my own kart?\n"
           "Responda 'aprovar 31764961 <instrução>' ou 'retomar 31764961'.\n"
           "aprovar 31764961 pode trazer sim")
    i = parse(eco)
    check("reply citando o briefing não confunde o parser",
          i["action"] == "approve" and i["lead_id"] == 31764961
          and i["message"] == "pode trazer sim", str(i))

    i = parse("🔺 ESCALAÇÃO — Eduardo (lead 31764961)\nMotivo: x")
    check("só reencaminhar o aviso não é ação", i["action"] == "unclear", str(i))

    print()
    if falhas:
        print(f"SELF TEST FALHOU - {len(falhas)}: {', '.join(falhas)}")
        return 1
    print("SELF TEST PASSOU - intenções lidas, eco do briefing ignorado, "
          "e na dúvida não age")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(self_test())
