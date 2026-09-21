# Mapa de agentes — quem é quem na operação URACE

Documento operacional, não técnico — para orientar qualquer sessão nova (Claude
ou humano) que entre no meio do trabalho e precise entender rápido quem faz o
quê. Para a arquitetura de software do agente de vendas em si, ver
`docs/urace-ai-agent-arquitetura.md`.

## As sessões de chat (Claude Code)

| Sessão | Onde roda | Papel |
|---|---|---|
| **U RACE** | Nuvem (claude.ai/code) | Infraestrutura e operação manual: código do repositório, Asana, QuickBooks, Docusign, Gmail. Não conversa com lead. |
| **CRM** | MacBook | **Organiza** o Kommo — higiene do funil, tags, campos customizados, monta o Salesbot nativo do Kommo (visual, na tela deles). |
| **COMERCIAL** | Windows | **Dispara** — mexe no Dialpad, manda SMS, qualifica ao vivo quem responde. |
| **AGREGADOR** | Windows (dupla do Comercial) | Administrativo — monta a lista de quem o Comercial vai disparar, cuida de waiver/QuickBooks/Docusign do lado de lá. |

## O Orchestrator — não é uma sessão

`agent/orchestrator.py`, no repositório. É código, não um chat separado: o
motor que, quando estiver plugado nos canais reais, vai conversar com o lead
sozinho — decide o modo da conversa de forma determinística (`escalation`,
`qualification`, `faq`, `scheduling`, `followup`), monta o prompt, chama o
Claude com tools, executa as tools, salva no Postgres.

Status real (ver `README.md`): **ainda não conversou com lead nenhum de
verdade** — só roda em `--dry-run`. É o "cérebro" que falta plugar no Kommo
(ler/escrever card) e no Dialpad (mandar mensagem).

## Encaixando no fluxo

```
CRM (Mac)  organiza o Kommo
    │
    ▼
Orchestrator (código)  decide o que fazer com cada lead
    │
    ▼
COMERCIAL (Windows)  dispara a mensagem pelo Dialpad
```

`AGREGADOR` corre em paralelo ao Comercial, alimentando a fila de disparo.
`U RACE` (esta sessão) fica de fora desse fluxo — é quem constrói e mantém a
infraestrutura que os outros três usam.
