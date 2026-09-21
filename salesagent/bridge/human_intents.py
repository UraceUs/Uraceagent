"""O que Italo ou Eduardo disseram no WhatsApp, virando ação.

Fecha o último passo manual do ciclo do brief. Mas a PRIMEIRA versão disto
(26/08) exigia verbo -- "aprovar 31764961 <texto>" -- e o Italo apontou o
óbvio: ninguém quer decorar sintaxe para responder uma mensagem. Ele quer
usar o recurso de responder do WhatsApp e escrever normal.

Então a regra se inverteu:

    TEXTO NATURAL É RESPOSTA AO LEAD. Comando é a exceção.

Quem responde "pode trazer o kart, a gente inspeciona antes" está
respondendo o cliente -- não precisa dizer "aprovar", não precisa repetir o
número do lead. O número sai da mensagem CITADA (o reply do WhatsApp traz o
briefing junto, e o briefing tem o id) ou do único lead esperando.

Comandos só são reconhecidos no INÍCIO da mensagem, e isso é deliberado:
"diga que fechamos às 18h" é resposta ao lead, não ordem de fechar a
conversa. Ancorar no começo é o que separa as duas sem adivinhação.

Este módulo é só o PARSER. Quem executa é a ponte (app.py), com os portões
de sempre -- parsing de linguagem natural é onde erro acontece, e um parser
puro se testa exaustivamente sem tocar em CRM, lead ou estado.
"""
import re

# Comandos: só valem ancorados no INÍCIO. Ordem importa -- 'não salvar'
# antes de 'salvar', senão o "não" some.
_COMANDOS = [
    ("dont_save", r"^\s*(n[ãa]o\s+(salv|registr|guard|grav)\w*|"
                  r"n[ãa]o\s+p[õo]e\s+(isso\s+)?no\s+brain)"),
    ("save", r"^\s*(salv\w*|registr\w*|guard\w*)\s+(isso|essa|esse|este|esta|"
             r"isto|no\s+brain)"),
    ("close", r"^\s*(pode\s+)?(fech\w*|encerr\w*|finaliz\w*|arquiv\w*)\b"),
    ("resume", r"^\s*(retom\w*|devolv\w*|pode\s+continuar|segue\s+(o\s+)?"
               r"(fluxo|atendimento)|volta\s+pro\s+agente)\b"),
    # 'aprovar'/'aprovado' continua funcionando para quem já se acostumou --
    # mas agora é só um prefixo opcional, não um requisito.
    ("approve", r"^\s*(aprovad[oa]|aprov\w*|autoriz\w*|confirmad[oa]|confirm\w*|"
                r"liberad[oa]|liber\w*|pode\s+(mandar|responder|falar|dizer))\b"),
]
_COMANDOS_RE = [(nome, re.compile(p, re.IGNORECASE)) for nome, p in _COMANDOS]

# Id de lead do Kommo tem 6+ dígitos. Exigir isso evita que "10%" ou uma
# idade no meio da frase virem lead_id.
_LEAD_RE = re.compile(r"\b(\d{6,})\b")

# Linhas do briefing que a ponte mandou: voltam junto no reply do WhatsApp.
# Servem para IDENTIFICAR o lead, mas nunca são a resposta ao cliente.
_ECO_BRIEFING = re.compile(
    r"(🔺\s*ESCALA[ÇC][ÃA]O|⏰\s*(RE-)?ALERTA|[ÚU]LTIMO AVISO|🧪\s*TESTE|"
    r"^\s*Motivo:|^\s*Contexto:|Responda\s+'?aprovar|"
    r"^\s*N[ãa]o vou repetir|escalado h[áa]\s+\d+\s+min)",
    re.IGNORECASE | re.MULTILINE)

# Só concordância, sem conteúdo: autoriza, mas não dita resposta nenhuma.
_SO_CONCORDANCIA = re.compile(
    r"^\s*(ok(ay)?|isso|isso\s+mesmo|certo|exato|perfeito|sim|pode\s+ser|"
    r"beleza|blz|👍|✅|joia|jóia|tá|ta|ta\s+bom|tudo\s+certo)[\s.!]*$",
    re.IGNORECASE)


def _separar_eco(texto: str) -> tuple[str, str]:
    """Devolve (o que a pessoa escreveu, o briefing citado).

    O reply do WhatsApp cola a mensagem original junto. O briefing serve
    para achar o lead; o que a pessoa digitou é o que vale como resposta.
    """
    proprias, citadas = [], []
    for linha in texto.splitlines():
        (citadas if _ECO_BRIEFING.search(linha) else proprias).append(linha)
    return "\n".join(proprias).strip(), "\n".join(citadas).strip()


def parse(texto: str, lead_em_foco: int | None = None,
          quoted: str = "") -> dict:
    """Mensagem do WhatsApp → intenção.

    `quoted` = a mensagem que a pessoa respondeu (o reply do WhatsApp),
    quando o canal souber informar. É a forma mais confiável de saber de
    qual lead se trata: veio do briefing que a própria ponte mandou.

    `lead_em_foco` = o único lead esperando, quando só há um.

    Devolve:
      action   answer | approve | resume | close | save | dont_save | unclear
      lead_id  int ou None
      message  o que deve chegar ao LEAD (vazio = autorizou sem ditar texto)
      needs    o que falta para agir com segurança (vazio = pode agir)
    """
    bruto = (texto or "").strip()
    proprio, eco = _separar_eco(bruto)

    # Lead: da mensagem citada primeiro (é o briefing da ponte, mais
    # confiável), depois do que a pessoa escreveu, depois do foco.
    lead_id = None
    for fonte in (quoted or "", eco, proprio):
        m = _LEAD_RE.search(fonte)
        if m:
            lead_id = int(m.group(1))
            break
    if lead_id is None:
        lead_id = lead_em_foco

    acao, corpo = None, proprio
    for nome, rx in _COMANDOS_RE:
        m = rx.match(proprio)
        if m:
            acao = nome
            corpo = proprio[m.end():]
            break

    # Tira o número do lead e pontuação de ligação do começo do que sobrou.
    corpo = _LEAD_RE.sub("", corpo, count=1) if acao else corpo
    corpo = re.sub(r"^[\s:,.\-–—]+", "", corpo).strip()

    # A INVERSÃO: sem comando reconhecido, texto com conteúdo É a resposta
    # ao lead. Era isto que obrigava a decorar "aprovar" antes.
    if acao is None:
        if not proprio or _SO_CONCORDANCIA.match(proprio):
            acao, corpo = "approve", ""
        else:
            acao, corpo = "answer", proprio

    mensagem = "" if acao in ("close", "resume", "dont_save") else corpo

    needs = []
    if lead_id is None and acao != "dont_save":
        needs.append("qual lead")
    # 'answer' sem texto não existe (viraria approve); 'save' sem texto não
    # tem o que salvar.
    if acao == "save" and not mensagem:
        needs.append("o que exatamente devo salvar")

    return {"action": acao, "lead_id": lead_id, "message": mensagem,
            "needs": needs, "raw": bruto, "quoted_lead": bool(quoted)}


def confirmation_prompt(intent: dict) -> str:
    """O que responder quando não dá para agir com segurança."""
    return ("Não consegui identificar de qual lead você está falando "
            f"({'; '.join(intent['needs'])}).\n"
            "Responda a mensagem da escalação (usando o responder do "
            "WhatsApp) que eu identifico sozinho — ou diga o número do lead "
            "junto com a sua resposta.")


# --------------------------------------------------------------- self-test
def self_test() -> int:
    falhas = []

    def check(label, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {label}" + ("" if cond else f"  {detail}"))
        if not cond:
            falhas.append(label)

    BRIEF = ("🔺 ESCALAÇÃO — Eduardo F F Resende (lead 31764961)\n"
             "Motivo: kart próprio (inspeção/gestão)\n"
             "Contexto: Hi, can i bring my own kart?\n"
             "Responda 'aprovar 31764961 <instrução>' ou 'retomar 31764961'.")

    # --- O caso que motivou a mudança: responder normal, sem comando.
    i = parse("pode trazer o kart sim, a gente inspeciona 1 dia antes",
              quoted=BRIEF)
    check("texto natural vira resposta ao lead",
          i["action"] == "answer" and i["lead_id"] == 31764961, str(i))
    check("a resposta chega inteira, sem mutilar",
          i["message"] == "pode trazer o kart sim, a gente inspeciona 1 dia antes",
          i["message"])
    check("não pede nada a mais", i["needs"] == [], str(i))

    # --- Reply do WhatsApp que cola o briefing junto.
    i = parse(f"{BRIEF}\npode trazer sim")
    check("briefing colado no reply não vira resposta ao lead",
          i["message"] == "pode trazer sim", i["message"])
    check("e o lead sai do briefing colado", i["lead_id"] == 31764961, str(i))

    # --- Comandos, só no início.
    i = parse("fechar", quoted=BRIEF)
    check("fechar", i["action"] == "close" and i["message"] == "", str(i))
    i = parse("pode fechar esse", quoted=BRIEF)
    check("'pode fechar' é comando", i["action"] == "close", str(i))

    i = parse("diga que fechamos às 18h", quoted=BRIEF)
    check("'fechamos' no meio da frase NÃO fecha a conversa",
          i["action"] == "answer" and "18h" in i["message"], str(i))

    i = parse("retomar", quoted=BRIEF)
    check("retomar", i["action"] == "resume", str(i))
    i = parse("não salvar isso")
    check("'não salvar' não exige lead",
          i["action"] == "dont_save" and not i["needs"], str(i))

    # --- Concordância seca autoriza mas não dita texto.
    for palavra in ("ok", "isso mesmo", "perfeito", "aprovado", "sim"):
        i = parse(palavra, lead_em_foco=31764961)
        check(f"'{palavra}' autoriza sem inventar resposta",
              i["action"] == "approve" and i["message"] == "", str(i))

    # --- 'aprovar' antigo continua funcionando.
    i = parse("aprovar 31764961 pode trazer sim")
    check("sintaxe antiga não quebrou",
          i["action"] == "approve" and i["lead_id"] == 31764961
          and i["message"] == "pode trazer sim", str(i))

    # --- Sem lead identificável.
    i = parse("pode trazer sim")
    check("sem lead e sem foco, pede o lead", "qual lead" in " ".join(i["needs"]))
    check("a pergunta ensina o caminho fácil",
          "responder do WhatsApp" in confirmation_prompt(i))

    # --- O lead citado tem precedência sobre o foco (evita responder o errado).
    i = parse("pode trazer sim", lead_em_foco=999999, quoted=BRIEF)
    check("lead da mensagem citada vence o foco", i["lead_id"] == 31764961, str(i))

    # --- Resposta multilinha, como gente escreve.
    i = parse("pode trazer sim.\nSó precisa chegar 1 dia antes pra inspeção.",
              quoted=BRIEF)
    check("resposta em várias linhas chega inteira",
          "1 dia antes" in i["message"] and "pode trazer" in i["message"],
          i["message"])

    # --- Só reencaminhar o briefing não é resposta.
    i = parse(BRIEF)
    check("reencaminhar o aviso não vira resposta ao lead",
          i["message"] == "" and i["action"] == "approve", str(i))

    print()
    if falhas:
        print(f"SELF TEST FALHOU - {len(falhas)}: {', '.join(falhas)}")
        return 1
    print("SELF TEST PASSOU - texto natural é resposta, comando é exceção "
          "ancorada no início, e o lead sai da mensagem citada")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(self_test())
