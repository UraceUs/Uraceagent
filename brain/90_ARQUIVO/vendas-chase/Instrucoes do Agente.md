---
type: system
category: pointer
topic: instrucoes-canonicas
priority: high
status: active
source: internal
last_updated: 2026-08-25
tags: [sistema, instrucoes, chase]
---

# Instruções do Agente (ponteiro — não duplicar aqui)

As instruções operacionais completas do Chase — identidade, voz,
classificação A/B/C/D, roteamento, escalação, follow-up, protocolo de
diretivas — vivem em **um único lugar canônico**:

`salesagent/instructions/urace-sales-agent.md`

Elas NÃO são duplicadas no Brain de propósito: são o prompt do agente
(sincronizado pro workspace do OpenClaw via
`salesagent/tools/sync_agent_instructions.sh`), não conhecimento
retrievável. Duplicar criaria duas verdades.

O Brain complementa as instruções com o conhecimento que NÃO cabe (nem
deve caber) no prompt: detalhes de programa, respostas a objeções
específicas, políticas, aprendizados. O retrieval entrega isso por demanda.

**Se você quer mudar como o Chase se comporta** → edite as instruções
canônicas e rode o sync no servidor.
**Se você quer mudar o que o Chase sabe** → edite/adicione documentos aqui
no Brain.
