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
