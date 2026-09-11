---
tipo: decisao
tipo_info: DECISION
data: 2026-08-31
fonte: [[Administrative AI]]
responsavel: Falhou qualquer trava → escala em vez de enviar. Depois de enviar, registra template, signatário, e-mail e `envelopeId`. **`sendReminder` continua não autorizado.**
status: ativo
---

# D-2026-08-31 — A IA pode enviar a waiver, com 4 travas

conversa com o dono, 31/08/2026

## O que foi decidido
[[Waiver]] · [[Waiver de responsabilidade]] · [[DocuSign]] · [[PARAMETROS]]

## Por quê
A IA **envia a waiver** do [[DocuSign]]. É a **4ª exceção** da regra "a IA não manda e-mail". Antes de cada envio, quatro travas obrigatórias: waiver `completed` com menos de 1 ano · envelope já em aberto para o mesmo signatário · idade confirmada · nome e e-mail conferidos contra [[Asana]] e [[QuickBooks]].

## Impacto
É o documento que libera o piloto a entrar na pista, e o gargalo é humano. As travas existem porque `createEnvelopeFromTemplate` **cria e envia no mesmo passo** — não há rascunho para revisar, e não tem volta.

## Quem decidiu
Falhou qualquer trava → escala em vez de enviar. Depois de enviar, registra template, signatário, e-mail e `envelopeId`. **`sendReminder` continua não autorizado.**

## Projeto relacionado
[[Italo Silveira]]

## Fonte
[[Administrative AI]]
