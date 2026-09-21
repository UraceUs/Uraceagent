---
tipo: decisao
data: 2026-09-14
fonte: dono
responsavel: Italo Silveira
status: ativo
---

# D-2026-09-14 — A IA sugere marcador novo, mas não cria

[[Taxonomia do Gmail]] · [[Triagem de e-mail]] · [[D-2026-09-11 - Manual dos marcadores do Gmail confirmado pelo dono]]

## O pedido

*"Monte um raciocínio lógico para a IA, conforme as instruções que já te dei, para
ela sugerir criação de novos marcadores quando for um e-mail de importância, de
acordo com o que a IA ler no corpo do e-mail e no título."*

## Por que isso não contradiz 11/09

Em 11/09 a regra foi **"a IA não cria marcador"**, e ela continua de pé sem uma
vírgula de mudança. O que entra agora é diferente: a IA **propõe**, o dono decide.
A proposta nasce `pendente`, com `in_gmail = 0` — ou seja, o marcador **não existe
na caixa**. Mesmo que alguém confirmasse por engano, o MCP recusaria aplicá-lo,
porque marcador inexistente é erro e nunca criação.

Para o marcador passar a valer são precisos **dois atos do dono**: confirmar no
painel e criar o marcador no Gmail com o mesmo nome. O painel diz isso na tela.

## A cadeia de decisão

É de exclusão: cada passo só é alcançado se o anterior falhar.

1. Existe marcador no manual que serve? Usa. **Fim, não sugere.**
2. Serve o marcador **pai** (`Finances` quando falta a pasta filha)? Usa o pai. Fim.
3. Nenhum serve. O e-mail é **importante**? Importante = dinheiro, contrato,
   obrigação legal, cliente, fornecedor, prazo — algo que, perdido, custa.
   Propaganda, newsletter, notificação e aviso automático **não são**, por maior
   que seja o volume.
4. Não é importante → `principal` null, fica na inbox para uma pessoa ver.
   **Não sugere.**
5. É importante → sugere **um** marcador: `nome` (dentro da hierarquia que já
   existe), `o_que` (o que vai nele daqui para frente), `por_que` (o que neste
   e-mail mostra que falta).

O passo 3 é o que impede a enxurrada. Sem ele, "não achei marcador" viraria
"proponha um", e a caixa ganharia dezenas de marcadores por semana.

## As travas em código, não no prompt

- **3 propostas por rodada** (`MAX_SUGESTOES`). Um modelo com dia ruim não enche o
  manual.
- **Nome que já existe é descartado**, sem diferenciar maiúscula. Proposta repetida
  também não duplica.
- **`Email Review` e `Years 2019-2023` são recusadas na origem.** A primeira não é
  do dono; a segunda é arquivo morto por ano.
- Tudo vai para a **auditoria** (`gmail.marcador.sugerido`) com o motivo.

A regra vale nos **dois** caminhos da triagem — tanto no que o filtro nativo já
marcou quanto no que chegou limpo. O filtro acerta a pasta pelo remetente, mas
quem percebe que **falta** uma pasta é quem lê o e-mail.

---

# Anexo — o manual passa a ser por caixa (14/09)

O pedido original do dono era *"leia as tags dos dois e-mails"*. O manual de 11/09
saiu inteiro da `urace@`: os 156 marcadores são de lá. A `support@` tem taxonomia
própria — `Customer Service/Leads`, `Customer Service/Service/New Order`,
`Curriculos`, `Canotops` — que ninguém leu, e por isso a triagem daquela caixa
trabalhava quase no vazio: só 2 marcadores existem nas duas.

## Por que `mailboxes` e não uma tabela nova

A alternativa era reconstruir `gmail_labels` com `UNIQUE(mailbox, name)`. Isso
mexeria numa tabela que guarda **as 145 confirmações do dono** — risco real de
perda por um ganho que não existe: o nome do marcador É a taxonomia, então `wNews`
na `urace@` e `wNews` na `support@` são a mesma coisa e merecem uma linha só.

Então cada marcador ganhou `mailboxes` (json: `["urace"]`, `["urace","support"]`).
Nenhuma linha reescrita, nenhuma confirmação em risco.

## O bug que isso descobriu

O `refresh` fazia `UPDATE gmail_labels SET in_gmail = CASE WHEN name IN (...)`.
Relê a `support@` e **todos** os marcadores da `urace@` viravam "não existe mais na
caixa", porque não estavam na lista daquela caixa. Ninguém tinha rodado ainda — o
bug estava esperando. Agora a presença é por caixa, e o que entra e sai vai para a
auditoria.

`confirmar tudo` também passou a respeitar a caixa: a tela é por caixa, e confirmar
olhando a `urace@` não pode confirmar marcador da `support@` que o dono nem viu.

## O que falta, e é dele

`adminai/ler_marcadores_caixa.py --conta support` produz o retrato da caixa —
marcador por marcador, com exemplos reais de quem manda e com que assunto. É a
mesma leitura de 11/09. Com esse retrato eu escrevo o que vai em cada marcador, e
ele confirma no painel, na aba `support@`. Enquanto não confirmar, a triagem da
`support@` não roda — a trava de 11/09 vale para as duas caixas.
