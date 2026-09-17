# D-2026-09-17 — Fluxo do closer, voz em todo o painel e a conta de acesso livre

**Decisão do dono (17/09/2026):** o fluxo de vendas que ele aprovou no canvas
(`Fluxo do Closer — Oportunidades no Command Center`) entra no sistema como está: **uma área de
vendas própria**, com o chat do Kommo dentro dela, a IA agindo por voz na própria oportunidade e
uma tela única de fechamento que dispara tudo. No mesmo pedido: *"essa ferramenta de falar, eu
preciso que ela seja implementada em basicamente todas as etapas que a gente tenha, para a gente
não ficar precisando digitar"*, e *"o usuário Eduardo F F Resende … não vai ter nenhum tipo de
nomenclatura … ele tem acesso livre e irrestrito"*.

## 1. Oportunidade não é cliente

O closer liga por fora (plataforma dele) e registra aqui. O que ele registra vive em
`opportunities` + `opp_events`, **separado de `clients`** — era a exigência explícita: *"eu não
quero misturar esses que estão próximos dos clientes que a gente já tem"*. O card de cliente só
nasce no fechamento; se já existir card com o mesmo e-mail ou telefone, o painel **liga no que
existe** em vez de duplicar.

Etapas: Novo → Em conversa → Proposta → Fechamento → Ganho / Perdido. **Ganho não sai pela mão**:
tanto a rota quanto a IA recusam mover para Ganho e mandam usar o fechamento (é o fechamento que
cria o cliente). Perdido exige motivo.

## 2. Fechar venda: uma tela, um botão

"Confirmou, o painel faz o resto." À esquerda o que foi vendido (tudo editável, tudo ditável); à
direita a lista do que vai acontecer, cada linha com switch para desligar:

| Passo | O que faz |
|---|---|
| `cliente` | cria/liga o card do cliente com responsável, piloto, contato e a anotação |
| `qbo` | acha ou cria o cliente no QuickBooks e manda a invoice do valor fechado |
| `waiver` | DocuSign no modelo certo (parental se o piloto é menor, adulto se não) |
| `asana` | tarefa no quadro U-RACE com a data do serviço |
| `kommo` | lead do chat → "Closed won" (quando a oportunidade veio do chat) |
| `extra:*` | **tarefa personalizada** que ele escrever: lembrete no painel ou tarefa no Asana |

Regras que ficam:
- **Falha de um passo não derruba os outros.** Cada passo é gravado com resultado e detalhe em
  `opportunities.closing` e na linha do tempo; depois de confirmar, a mesma tela vira
  acompanhamento, com "tentar de novo" por passo.
- **Valor fora da tabela fecha a venda, mas a invoice espera o dono.** A tela manda o preço de
  tabela junto; se o valor bate, a invoice sai; se difere, a venda fecha, o resto sai e a invoice
  fica pendente de aprovação (mesma regra das políticas da IA). ADMIN e MANAGER passam direto.
- **Sem e-mail não há promessa**: waiver e invoice recusam com texto claro em vez de fingir envio.
- Nada de e-mail livre: o Gmail do painel é leitura. "E-mail" aqui é waiver/invoice (que o próprio
  sistema envia) ou tarefa personalizada.

## 3. A IA dentro da venda (a "sandbox" que ele pediu)

Na ficha da oportunidade tem uma caixa "Falar com a IA": ele dita, ela age **naquela venda**.
Oito ações novas, com política: `venda_registrar_ligacao`, `venda_agendar_retorno`, `venda_anotar`,
`venda_mover_etapa`, `venda_tarefa` (SAFE) · `venda_enviar_waiver`, `venda_fechar`
(confirmação) · `venda_enviar_invoice` (aprovação do dono).

Para a IA não responder bonito sem agir, o comando que começa com `[oportunidade #N …]` leva um
**contexto da venda**: a ficha, os últimos registros, a data de hoje na Flórida e o formato exato
de cada `ACAO`. E a IA respeita a mesma trava da tela: **closer só alcança a oportunidade dele**,
mesmo pedindo pela IA.

## 4. Papéis: existe conta sem cargo (e o CLOSER foi desfeito no mesmo dia)

- `CLOSER` tem o **mesmo nível de escrita do OPERATOR**, mas só na área de vendas. O que ele não
  alcança está numa lista de caminhos no servidor (`FECHADO_AO_CLOSER` em `main.py`): usuários,
  auditoria, políticas, QuickBooks, invoices, Gmail, DocuSign, integrações, automação, contexto.
  O menu dele mostra apenas Vendas (Oportunidades, Agenda, Chat) e Inteligência (falar com a IA,
  o que a IA fez); ele entra direto em Oportunidades.
- **Conta de acesso livre**: e-mail listado em `auth.ACESSO_LIVRE` (hoje
  `eduardoffresende@gmail.com`, ajustável por `CC_ACESSO_LIVRE`) **não tem cargo**. O painel mostra
  "Acesso livre" no lugar do papel, `exige()` libera qualquer porta e ninguém consegue trocar o
  papel dessa conta (a rota recusa: "não tem cargo para mudar").

## 5. Voz em todo o painel

Reconhecimento e síntese de fala **do próprio navegador** (`components/Voz.tsx`): nenhuma chave
nova, nada sai para servidor nosso, funciona no computador e no celular (Chrome, Edge, Safari
14.5+). Onde o navegador não tem, o botão simplesmente não aparece.

- `Mic` — botão ao lado de campo de uma linha (nome, telefone, e-mail, serviço, busca…). No e-mail,
  "arroba" ditado vira `@` e os espaços caem.
- `TextoComVoz` — caixa de texto com microfone embutido, texto parcial aparecendo enquanto fala,
  Enter envia quando faz sentido (chat, anotação, IA).
- `Ouvir` — lê a resposta da IA em voz alta (pt-BR quando há voz instalada).
- Está em: AI Command, IA da venda, IA na tarefa (Asana) e no item de atenção, chat do Kommo
  (resposta e anotação), anotações de venda e de cliente, novo cliente, nova oportunidade, nova
  tarefa de serviço, corridas, equipamento, memória da IA, manual dos marcadores e no campo dos
  diálogos de confirmação.

## 6. Fuso: tudo na Flórida

Já era a ordem do dono; aqui virou código de verdade também no servidor: `vendas.hoje_local()`,
`dia_local()`, `fim_do_dia_local()` e `quando_pt()` — o dia do quadro, o contador do menu, a
agenda e o texto dos eventos usam `America/New_York`, não UTC (02:00Z de um dia ainda é o dia
anterior em Orlando).

## Como foi feito (para não desfazer sem querer)

- Banco: `opportunities`, `opp_events`, `users.role` com `CLOSER` (migração `_migrar_papeis`
  recria `users` quando o CHECK antigo não tem o papel) e as políticas `venda_*`.
- Backend: `api/vendas.py` (quadro, agenda, ficha, ligação, retorno, anotação, etapa, do chat,
  fechar, refazer passo), `api/acoes_painel.py` (as oito ações da IA), `api/motor.py`
  (`contexto_da_venda` + despacho do prefixo `venda`), guarda do closer em `api/main.py`,
  contador `sales_due` no dashboard.
- Frontend: `pages/Vendas.tsx` (quadro, ficha, registrar ligação, fechar venda, agenda, botão
  "Passar para o closer" no chat), `components/Voz.tsx`, rotas `/sales`, `/sales/agenda`,
  `/sales/:id`, grupo "Vendas" no menu e na barra de abas.
- 206 testes (16 novos em `tests/test_vendas.py`), build do frontend limpo, telas conferidas em
  desktop e celular com banco de demonstração.

[[Command Center]] · [[Italo Silveira]] · [[Kommo]] · [[QuickBooks]] · [[DocuSign]] · [[Asana]]
