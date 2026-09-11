---
tipo: processo
area: Gmail
fonte: humano
atualizado_em: 2026-09-11
tipo_info: PROCESS
responsavel: Italo Silveira
status: ativo
---

# Processo — triagem de e-mail

Rotina diária nas caixas do [[Gmail]] (`urace@` e `support@`).

## A regra que manda: o manual confirmado (11/09)
A IA **só classifica com os marcadores que o dono confirmou**, um a um, no
manual — 145 dos 156. Marcador que não está lá **não existe** para ela, e
ela **nunca cria marcador**. Sem manual confirmado, a triagem **não roda**.
Fonte: `command_center/providers/taxonomia_gmail.py`; o agente lê
`skills/urace-gmail/MANUAL.md`; o dono confere no painel (Gmail → Manual dos
marcadores). Ver [[Taxonomia do Gmail]].

## Passos
1. Ler cada thread nova da inbox.
2. Classificar e aplicar o marcador **do manual confirmado** ([[Taxonomia do Gmail]]).
3. Propaganda → `wNews` **e arquivar**. Todo o resto **fica na inbox**.
4. Compra nossa → alimentar [[Compra e envio]] no [[Asana]].
5. **Rascunho** para lead/orçamento e cliente atual. Parceria e
   financeiro: [[Italo Silveira]] responde pessoalmente.
6. Dúvida → perguntar.
7. Registrar no diário ([[2026-08-28]]).

## Desde 09/09: quem roda é o Command Center
A triagem roda **07:00, 13:00 e 21:00** pelo painel (regra
`gmail_triagem`): a IA lê cada thread, aplica os marcadores e **move
para o marcador principal** da hierarquia — o passo 3 acima vale só
para a ferramenta `gmail_rotular` do agente solto. O que ela não decide
fica na inbox; o que pede resposta vai para *Precisa de atenção*. Ver
[[D-2026-09-09 - Triagem do Gmail pela IA e sondagem so de manha e a noite]].

## Regra
A IA **não envia** nesta rotina. As duas exceções autorizadas estão em
[[Pedido de macacão]] e [[Security deposit]] — ver [[PARAMETROS]].
