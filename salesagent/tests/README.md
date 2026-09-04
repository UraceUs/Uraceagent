# Ambiente de testes do Chase

Testa o agente `urace-sales` direto via CLI do OpenClaw, sessão isolada por
cenário — nível certo de teste antes do circuito completo com o Kommo estar
ligado (a ponte/Salesbot é o próximo passo).

## Rodar no VPS

```bash
cd ~/Uraceagent && git pull
python3 salesagent/tests/run_scenarios.py
```

Rodar só alguns cenários (por prefixo do ID):

```bash
python3 salesagent/tests/run_scenarios.py --only 08 12 14
```

## O que é checado automaticamente

`global_checks.must_not` em `scenarios.json` — regras invioláveis, checadas
por regex em TODA resposta do agente em TODO cenário: nunca em/en dash, nunca
preço em número, nunca "all-inclusive", nunca a palavra "vandalism", nunca
confirmar reserva antes do pagamento, nunca esconder que é IA.

**Importante:** a checagem roda em cima de `textproc.customer_facing(reply)`
(`bridge/textproc.py`), não na resposta bruta do modelo. O agente responde em
texto livre + diretivas internas `[[...]]` (protocolo em
`instructions/urace-sales-agent.md`) — nunca destinadas ao cliente, e a ponte
(`bridge/app.py`) as remove antes de qualquer envio real. O runner usa a
mesma função da ponte para checar exatamente o que um lead real veria, não
texto interno (nota de CRM, briefing de escalação) que só existiria por
faltar esse passo. Quando uma diretiva é removida, a linha bruta é impressa
como "(bruto, p/ auditoria)" logo abaixo — útil pra revisão manual, não entra
na checagem automática.

## O que precisa de revisão manual

Cada cenário tem um campo `expect_manual_review` — coisas que só um humano
(ou eu, lendo a transcrição) consegue avaliar direito: se o roteamento foi
correto, se o tom bateu com o Voice Manual, se a escalação aconteceu na hora
certa. O runner imprime a transcrição completa para isso.

## Origem dos cenários (v1)

18 cenários derivados de fontes já auditadas no projeto — **nenhuma conversa
real ainda**:
- Os 13 role-plays oficiais do documento Chase (COS v4.0 §42)
- As categorias de teste da missão original (pricing, handoff, segurança,
  qualificação completa/incompleta/conflitante)
- Regras críticas específicas (kart próprio, Racing Team, idade)

## Cenário 19 — jornada completa, uma única conversa

Os 18 cenários acima são **isolados**: cada um testa uma regra ou situação
específica em pouquíssimos turnos, e várias delas são mutuamente exclusivas
(não dá pra ser lead novo E cliente pedindo reembolso na mesma conversa).
O cenário `19_full_lifecycle_academy_journey` é diferente: é **uma única
sessão, do "Hi" à escalação**, como uma conversa real de ponta a ponta,
passando pela maior parte dos processos em sequência: abertura/classificação
→ captura de contato campo a campo → qualificação por objetivo → gate de
preço (inclusive com insistência) → objeção/adiamento com follow-up
agendado → o lead volta antes do follow-up (testa cancelamento da trilha) →
confirmação de interesse pós-página → escalação para o Italo com o briefing
completo → e, o ponto mais importante, **a trava pós-escalação** (G3 + G4):
um pedido de desconto feito DEPOIS de escalado não pode reabrir negociação
nem venda.

Além das `global_checks`, esse cenário tem um campo extra,
`expect_directives_any`: uma lista de famílias de diretiva (`qualify`,
`price`, `crm op=note`, `crm op=tags`, `escalate`) que precisam ter
aparecido **em algum turno** da sessão inteira — não valida ordem nem
conteúdo exato, só prova que aquele processo de fato disparou. O runner
imprime um checklist ✅/❌ por família ao final do cenário.

Rodar só ele:

```bash
python3 salesagent/tests/run_scenarios.py --only 19
```

## Pendência conhecida

Italo referenciou um chat do Claude.ai com situações reais de leads/clientes
já atendidos, para usar como fonte de cenários realistas. O link
compartilhado não pôde ser lido automaticamente (página renderizada por
JavaScript) — pendente o conteúdo ser colado diretamente. Quando isso
acontecer, os cenários reais devem ser adicionados a `scenarios.json` com
`"source": "conversa real — [contexto]"` para diferenciá-los dos hipotéticos.
