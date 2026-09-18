---
tipo: decisao
data: 2026-09-17
fonte: dono (revisão da lista de capacidades, item por item)
responsavel: Italo Silveira
status: ativo
---

# D-2026-09-17 — O que a IA pode fazer, revisado pelo dono

[[D-2026-09-04 - Invoice sai depois de aprovada no painel]] · [[D-2026-09-16 - Lembretes recorrentes de invoice e filtros do QuickBooks]] · [[DocuSign]] · [[Asana]]

Pedi a lista de tudo que a IA opera; ele devolveu a lista **corrigida**, mudando a fronteira
entre o que é da IA e o que é da mão dele. Cada item virou ferramenta, política e trava.

| Área | O que ele decidiu | Como ficou |
|---|---|---|
| **DocuSign** | *"reenviar/corrigir e-mail, anular, lixeira, ver/renomear/trocar PDF de modelo: isso a IA pode fazer"* | `docusign_reenviar_waiver` e `docusign_anular_envelope` (**com aprovação** — saem da empresa; assinado nunca é anulado) · `docusign_renomear_modelo` (confirmação) · `docusign_substituir_documento_modelo` (**aprovação**; cópia do antigo antes) · `painel_waiver_lixeira` (confirmação) |
| **QuickBooks** | *"a escolha de quais lembretes recorrentes são meus; o disparo é da IA"* | A rotina das 09:00 não envia mais: desliga os pagos e **entrega à IA** a lista devida; a IA dispara `qbo_lembrete_invoice` (SAFE); o executor **recusa** invoice sem lembrete ligado; o painel marca o próximo dia |
| **Asana** | nova tarefa pelo modelo e nova corrida pelo "New Race": *"a IA"* | `asana_criar_do_modelo` já era SAFE; entrou `asana_criar_corrida` (SAFE) — a corrida entra no calendário do painel como a do botão |
| **Clientes** | *"unir cards: a IA pode quando tiver informações duplicadas de responsável, número ou e-mail"* | `painel_unir_clientes` (SAFE) **só une com e-mail, telefone ou responsável exatamente iguais**; fora disso a ação falha e diz que é decisão humana |
| **Clientes** | *"varrer Gmail + DocuSign: a IA deve fazer isso"* | rotina `varredura_clientes` às **06:00**, todo dia, para todos os ativos; e `painel_varrer_cliente` (SAFE) para um cliente quando a IA precisar |
| **Kommo · Administração** | continuam da mão dele | responder no chat, mover etapa, tag, atribuir; aprovar, políticas, usuários |

## A página "O que a IA pode fazer"

Entrou no painel (Inteligência → *O que a IA pode fazer*), **lida do código**: as ferramentas
registradas nos cinco MCPs, a tabela de políticas, as ações do painel, as regras de
automação e o que é só humano. Se entrar ferramenta nova, aparece sozinha; se mudar uma
política, muda lá. É a resposta permanente à pergunta "o que a IA opera hoje".

## O que continua bloqueado

Enviar e-mail livre · apagar qualquer coisa (QuickBooks, cliente) · lembrete do DocuSign
(`sendReminder`, não decidido) · mexer em NDA e Service Agreement.
