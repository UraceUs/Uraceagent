---
tipo: decisao
tipo_info: DECISION
status: ativo
owner: Italo Silveira
data: 2026-09-22
fonte: dono, 22/09/2026 — página editável das decisões do portão
---

# D-2026-09-22 — As três que ficaram de fora em 21/09

[[URACE]] · [[Command Center - Proximos passos]] · [[DocuSign]] · [[Gmail]]

## A pergunta

Na revisão das 42 ações (21/09) o dono respondeu tudo, mas três respostas eu **não
apliquei**: duas eram condicionais ("pode, mas só se…") e uma mexia em apagar, que
não tem volta. Em 22/09 ele fechou as três, mais as cinco que eu tinha devolvido
para confirmação.

## O que decidiu

| Ação | Decisão | Condição |
|---|---|---|
| `apagar_cliente` | **manter** `BLOCKED` | — |
| `qbo_apagar` | **manter** `BLOCKED` | — |
| `venda_tarefa` | **manter** `SAFE` | o toque estranho no painel era dele mesmo |
| `apagar_qualquer_coisa` | `REQUIRES_APPROVAL` | volta a valer como **piso** de todo apagar |
| `gmail_rotular` | `SAFE` | arquivar só com marcador **confirmado** no painel |
| `docusign_send_reminder` | `SAFE` | **2x**, só com serviço marcado, 3 e 1 dia antes |
| Estoque: tipos | **dois** | chassi/motor com ficha e número de série; pneu/peça por quantidade |
| Estoque: locais | **dois** | sede e trailer |

## Por que importa

**Política é porta, condição é trava.** Abrir uma política sem escrever a condição
entregaria mais do que ele autorizou. Cada condição virou código, com teste:

- **Lembrete de waiver** (`adminai/mcp/docusign_mcp.py::avaliar_lembrete`): recusa
  quem não é cliente do painel, quem não tem serviço marcado no futuro, qualquer dia
  que não seja 3 ou 1 antes, a mesma janela duas vezes, e o terceiro lembrete. A
  contagem mora em `waiver_reminders` — sem banco do painel, recusa tudo.
- **Arquivar no Gmail** (`adminai/mcp/gmail_mcp.py::_pode_arquivar`): tirar da inbox
  só se a thread ficar com um marcador `confirmado` em `gmail_labels`, da caixa
  certa. Sem banco, volta à regra estreita de antes (só `wNews`). O filtro nativo
  (`criar_filtro_humano`) continua estreito de propósito: filtro é regra permanente.

## O buraco que isso fechou

`apagar_qualquer_coisa` era o guarda-chuva que dizia "a IA nunca apaga" — e até
22/09 ele não guardava nada. Uma ação nova chamada, por exemplo,
`asana_apagar_tarefa` não tinha política própria, caía no padrão (pergunta antes) e
passava **por baixo** do guarda-chuva. Agora `ia._politica` aplica o piso a qualquer
nome com apagar/excluir/deletar/remover — e o piso nunca rebaixa quem já é mais
severo: `apagar_cliente` continua `BLOCKED`.

## Onde está no código

- `command_center/api/ia.py` — `piso_de_apagar`, `_politica`
- `command_center/db/__init__.py` — `REVISAO_21_09` (rodada de 22/09 no fim)
- `command_center/db/schema.sql` — tabela `waiver_reminders`
- `adminai/mcp/docusign_mcp.py` — `avaliar_lembrete`, `docusign_send_reminder`
- `adminai/mcp/gmail_mcp.py` — `_confirmados_no_painel`, `_pode_arquivar`
- `command_center/tests/test_travas_decididas.py` — 23 testes das três travas
