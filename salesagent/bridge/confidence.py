"""Política de confiança — o agente reconhece quando NÃO sabe.

Princípio fundamental do brief de 25/08: o agente nunca inventa. Até aqui
isso era um pedido no prompt ("se não achar, diga que vai confirmar e
escale") -- e um pedido ao modelo não é uma garantia. Este módulo é a parte
determinística: olha o que o retrieval devolveu e classifica a base factual
do turno ANTES do modelo escrever qualquer coisa.

Cobre os Casos 1 a 4 do brief (os Casos 5 e 6 -- decisão comercial e
assunto sensível -- já são portão em gates.ESCALATION_PATTERNS, avaliados
antes do modelo ver a mensagem):

  Caso 1  NONE      nenhum documento relevante
  Caso 2  LOW       documento fraco demais para sustentar uma afirmação
  Caso 3  CONFLICT  dois documentos falam do MESMO topic e discordam em data
  Caso 4  STALE     o melhor documento está velho demais para ser afirmado

O limiar de score não foi chutado: veio de medição contra o vault real
(25/08). BM25 do SQLite é NEGATIVO e quanto MENOR, melhor. Perguntas com
resposta real no vault pontuaram entre -4.0 e -6.0; perguntas de ruído
("do you serve sushi", "rent a ferrari", "gift cards") pontuaram entre
-2.7 e -3.6. -3.8 separa as duas populações nessa amostra. É um ponto de
partida honesto, não uma verdade: `BRAIN_MIN_SCORE` no bridge.env recalibra
sem deploy, e toda decisão vai para o log de auditoria justamente para
permitir essa recalibragem com tráfego real.
"""
import datetime
import os

# Pior score aceitável (lembre: menor = melhor). Acima disso, o documento
# até apareceu na busca, mas é fraco demais para o agente afirmar algo.
MIN_SCORE = float(os.environ.get("BRAIN_MIN_SCORE", "-3.8"))
# Documento mais velho que isto entra como "confirmar antes de afirmar".
STALE_DAYS = int(os.environ.get("BRAIN_STALE_DAYS", "180"))

NONE, LOW, CONFLICT, STALE, OK = "none", "low", "conflict", "stale", "ok"

# Quais níveis exigem confirmação humana antes de virar afirmação ao lead.
NEEDS_HUMAN = {NONE, LOW, CONFLICT}


def _age_days(last_updated: str | None, today: datetime.date | None = None) -> int | None:
    if not last_updated:
        return None
    try:
        d = datetime.date.fromisoformat(str(last_updated).strip())
    except ValueError:
        return None
    return ((today or datetime.date.today()) - d).days


def assess(hits: list[dict], today: datetime.date | None = None) -> dict:
    """Classifica a base factual do turno.

    Devolve {'level', 'reason', 'needs_human', 'best_score'}. `level` é um
    dos NONE/LOW/CONFLICT/STALE/OK; `reason` é a frase que vai tanto para o
    log quanto para o briefing do humano (§7: ele precisa saber o que o
    agente encontrou e por que não bastou).
    """
    if not hits:
        return {"level": NONE, "needs_human": True, "best_score": None,
                "reason": "nenhum documento relevante no Brain para esta pergunta"}

    best = min(h.get("score", 0.0) for h in hits)
    if best > MIN_SCORE:
        return {"level": LOW, "needs_human": True, "best_score": best,
                "reason": (f"só documentos fracos (melhor score {best}, "
                           f"limiar {MIN_SCORE}) — relacionado, mas não "
                           f"suficiente para afirmar")}

    # Caso 3: dois documentos reivindicam o MESMO assunto (type+category+
    # topic iguais). O schema do vault existe justamente para tornar isso
    # detectável sem semântica -- ver brain/_meta/README.md.
    vistos: dict[tuple, dict] = {}
    for h in hits:
        chave = (h.get("type"), h.get("category"), h.get("topic"))
        if not all(chave):
            continue
        outro = vistos.get(chave)
        if outro is not None and outro.get("path") != h.get("path"):
            return {"level": CONFLICT, "needs_human": True, "best_score": best,
                    "reason": (f"dois documentos sobre o mesmo assunto "
                               f"({'/'.join(str(c) for c in chave)}): "
                               f"'{outro.get('title')}' e '{h.get('title')}' "
                               f"— qual vale precisa de decisão humana")}
        vistos[chave] = h

    # Caso 4: o melhor documento está velho. Não bloqueia a conversa, mas o
    # agente deve confirmar em vez de afirmar como fato corrente.
    melhor_doc = min(hits, key=lambda h: h.get("score", 0.0))
    idade = _age_days(melhor_doc.get("last_updated"), today)
    if idade is not None and idade > STALE_DAYS:
        return {"level": STALE, "needs_human": False, "best_score": best,
                "reason": (f"o documento mais relevante ('{melhor_doc.get('title')}') "
                           f"foi atualizado há {idade} dias — confirmar antes "
                           f"de afirmar como política vigente")}

    return {"level": OK, "needs_human": False, "best_score": best,
            "reason": f"conhecimento suficiente (melhor score {best})"}


def system_note(verdict: dict) -> str:
    """A instrução que vai DENTRO do bloco [SYSTEM] do turno, em português,
    dizendo ao agente o que ele pode ou não afirmar. É aqui que o princípio
    "não invente" deixa de ser um lembrete genérico no prompt e passa a ser
    uma instrução específica sobre ESTA pergunta."""
    nivel = verdict["level"]
    # Este aviso vale para AFIRMAÇÕES sobre a URACE -- não para conduzir a
    # conversa. Sem esta ressalva, um "hi, i've never raced before" (que não
    # pede fato nenhum e é o lead mais comum) viraria escalação, porque o
    # vault hoje não tem documento que case com essa frase. O fluxo de
    # classificação, o tom e o roteiro vivem nas instruções do agente, e
    # instrução É base sólida.
    _ESCOPO = ("Isto vale para AFIRMAR fatos sobre a URACE (preço, política, "
               "horário, disponibilidade, o que está incluso, capacidade). "
               "Não vale para conduzir a conversa: saudar, classificar A/B/C/D, "
               "perguntar, recomendar programa e seguir o roteiro das suas "
               "instruções continuam normais -- suas instruções são base "
               "sólida. Se o lead não pediu nenhum fato, siga normalmente.")
    if nivel == NONE:
        return ("ATENÇÃO: a busca no knowledge base não encontrou NADA sobre "
                "esta mensagem. Você não tem base para afirmar fatos aqui. "
                "Não deduza, não generalize, não use conhecimento geral sobre "
                "karting como se fosse sobre a URACE. Se o lead pediu um fato, "
                "diga que vai confirmar e emita [[unknown question=\"...\" "
                "found=\"nada\"]]. " + _ESCOPO)
    if nivel == LOW:
        return (f"ATENÇÃO: {verdict['reason']}. Trate como se não tivesse a "
                "informação: não afirme nada que não esteja literalmente "
                "escrito acima. Se a pergunta do lead depende disso, diga que "
                "vai confirmar e emita [[unknown question=\"...\" "
                "found=\"documento fraco\"]]. " + _ESCOPO)
    if nivel == CONFLICT:
        return (f"ATENÇÃO: {verdict['reason']}. NÃO escolha um dos dois por "
                "conta própria. Diga ao lead que vai confirmar e emita "
                "[[unknown question=\"...\" found=\"conflito\"]].")
    if nivel == STALE:
        return (f"CUIDADO: {verdict['reason']}. Pode usar o conteúdo, mas "
                "apresente como algo que você confirma antes de fechar "
                "qualquer coisa — nunca como política vigente garantida.")
    return ""


# --------------------------------------------------------------- self-test
def self_test() -> int:
    hoje = datetime.date(2026, 8, 25)
    falhas = []

    def check(label, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {label}" + ("" if cond else f"  {detail}"))
        if not cond:
            falhas.append(label)

    def doc(score, **kw):
        base = {"score": score, "title": "Doc", "type": "sales_knowledge",
                "category": "objection", "topic": "preco", "path": "a.md",
                "last_updated": "2026-08-20"}
        base.update(kw)
        return base

    v = assess([], hoje)
    check("Caso 1: sem hits => none", v["level"] == NONE and v["needs_human"])

    v = assess([doc(-2.7)], hoje)
    check("Caso 2: score fraco => low", v["level"] == LOW and v["needs_human"], str(v))

    v = assess([doc(-5.5, path="a.md", title="Antigo", last_updated="2026-01-01"),
                doc(-5.4, path="b.md", title="Novo")], hoje)
    check("Caso 3: mesmo topic em dois docs => conflict",
          v["level"] == CONFLICT and v["needs_human"], str(v))

    v = assess([doc(-5.5, last_updated="2025-01-01")], hoje)
    check("Caso 4: documento velho => stale", v["level"] == STALE, str(v))
    check("stale NÃO bloqueia a conversa", not v["needs_human"])

    v = assess([doc(-5.5)], hoje)
    check("conhecimento bom => ok", v["level"] == OK and not v["needs_human"], str(v))

    v = assess([doc(-5.5, path="a.md", topic="preco"),
                doc(-5.4, path="b.md", topic="inspecao")], hoje)
    check("topics diferentes não são conflito", v["level"] == OK, str(v))

    v = assess([doc(-5.5, last_updated=None)], hoje)
    check("sem last_updated não quebra nem vira stale", v["level"] == OK, str(v))
    v = assess([doc(-5.5, last_updated="data-invalida")], hoje)
    check("last_updated inválido não quebra", v["level"] == OK, str(v))

    check("limiar medido separa ruído real (-3.5) de acerto real (-4.0)",
          assess([doc(-3.535)], hoje)["level"] == LOW
          and assess([doc(-3.999)], hoje)["level"] == OK)

    for nivel in (NONE, LOW, CONFLICT):
        nota = system_note({"level": nivel, "reason": "x"})
        check(f"{nivel} manda usar [[unknown]]", "[[unknown" in nota)
    for nivel in (NONE, LOW):
        nota = system_note({"level": nivel, "reason": "x"})
        check(f"{nivel} nao escala conversa sem pergunta factual",
              "classificar" in nota and "siga normalmente" in nota)
    check("ok não gera instrução", system_note({"level": OK, "reason": "x"}) == "")
    check("stale orienta sem mandar escalar",
          "[[unknown" not in system_note({"level": STALE, "reason": "x"}))

    print()
    if falhas:
        print(f"SELF TEST FALHOU - {len(falhas)}")
        return 1
    print("SELF TEST PASSOU - Casos 1-4 do brief classificados, limiar "
          "conferido contra a medição real do vault")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(self_test())
