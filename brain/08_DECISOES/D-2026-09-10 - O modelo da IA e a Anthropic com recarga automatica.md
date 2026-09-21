---
tipo: decisao
data: 2026-09-10
fonte: dono (chat)
tipo_info: DECISION
responsavel: Italo Silveira
status: ativo
---

# D-2026-09-10 — O modelo da IA é a Anthropic, com recarga automática

**Contexto:** o crédito da conta Anthropic zerou às 08:27 e o agente
parou ("credit balance is too low"). O dono achava que o OpenClaw era a
inteligência. Não é: o OpenClaw é o corpo (sessões, memória, sandbox,
ferramentas); quem pensa é o modelo do provedor configurado nele, a
Anthropic, pago por crédito.

**Decisão (dono):** opção 1 — manter a Anthropic como modelo e ligar a
**recarga automática** em console.anthropic.com → Plans & Billing. Sem
plano B por enquanto; se um dia houver segunda chave (OpenAI/Google),
configura-se failover no OpenClaw.

**O que não depende do modelo (segue com ou sem crédito):** sincronia,
avisos, regras de preço e vencimento, criação de tarefa pelo botão,
card, calendário, triagem por regras. **O que depende:** chat, eventos
que acordam a IA, triagem do Gmail pela IA, parecer de duplicados,
prévia de custo.

**Correção junto:** a triagem do Gmail rodava no laço da sincronia e,
sem crédito, segurava a sincronia. Agora roda em linha própria; a
sincronia nunca espera pela IA. O erro de crédito aparece no chat em
uma frase clara, com o lugar para repor.

Relacionado: [[Administrative AI]], [[D-2026-09-10 - Proposta da IA nao se repete e o valor do dono manda]].
