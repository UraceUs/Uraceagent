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

## Pendência conhecida

Italo referenciou um chat do Claude.ai com situações reais de leads/clientes
já atendidos, para usar como fonte de cenários realistas. O link
compartilhado não pôde ser lido automaticamente (página renderizada por
JavaScript) — pendente o conteúdo ser colado diretamente. Quando isso
acontecer, os cenários reais devem ser adicionados a `scenarios.json` com
`"source": "conversa real — [contexto]"` para diferenciá-los dos hipotéticos.
