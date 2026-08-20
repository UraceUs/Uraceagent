"""Processamento do texto do modelo antes de qualquer coisa ir ao cliente.

O agente responde em texto livre + diretivas `[[...]]` (protocolo descrito em
`instructions/urace-sales-agent.md`, seção "System protocol"). As diretivas
são para a ponte ler e agir (CRM, escalação, follow-up) -- nunca para o
cliente ver. Este módulo é o único lugar onde "texto do modelo" vira "texto
que pode ir para um lead real", tanto na ponte (app.py) quanto nos testes
(tests/run_scenarios.py) -- as duas pontas checam a MESMA função, para o que
passa no teste ser exatamente o que o cliente veria em produção.

Fase atual: as diretivas são só REMOVIDAS do texto visível (e logadas à
parte). EXECUTAR as diretivas (chamar tools/crm, tools/escalate etc a partir
do texto do agente) é trabalho de Fase 3, ainda não implementado -- hoje as
tools já são chamadas via endpoints separados quando aplicável (ex.:
tool_qualify chamando escalate() diretamente), não pelo parser de diretivas.
"""
import re

# Diretiva: `[[palavra ...resto até o fechamento na mesma linha ou bloco]]`.
# Não-guloso, multilinha (algumas diretivas como [[crm op=note text="..."]]
# podem ter texto longo) -- para em `]]`.
_DIRECTIVE_RE = re.compile(r"\[\[.*?\]\]", re.DOTALL)

# B1-adjacent: regra de escrita "nunca em dash" garantida no código, não só no
# prompt (rule 15 das instrucoes) -- um modelo que derivar nao passa o sinal
# adiante.
_DASH_RE = re.compile(r"[–—]")  # en dash (–) e em dash (—)


def extract_directives(text: str) -> list[str]:
    """Devolve a lista de blocos `[[...]]` encontrados, na ordem em que aparecem."""
    return _DIRECTIVE_RE.findall(text)


def strip_directives(text: str) -> str:
    """Remove todo bloco `[[...]]` do texto, sem deixar espaços duplos/soltos."""
    without = _DIRECTIVE_RE.sub("", text)
    # Colapsa espaços em branco deixados pela remoção (linhas em branco extras,
    # espaços duplos dentro da linha) sem mexer em quebras de parágrafo
    # intencionais.
    without = re.sub(r"[ \t]+\n", "\n", without)
    without = re.sub(r"[ \t]{2,}", " ", without)
    without = re.sub(r"\n{3,}", "\n\n", without)
    return without.strip()


def sanitize_dashes(text: str) -> str:
    """Remove em/en dash de qualquer texto que vá para o cliente."""
    return _DASH_RE.sub(",", text)


def customer_facing(text: str) -> str:
    """Único ponto de verdade: o que um lead real veria, dado o texto bruto
    do modelo. Usado pela ponte (antes de enviar ao Kommo) e pelos testes
    (antes de checar as regras) -- para os dois lados nunca divergirem."""
    return sanitize_dashes(strip_directives(text))
