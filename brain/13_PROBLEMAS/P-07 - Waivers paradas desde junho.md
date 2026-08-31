---
tipo: problema
tipo_info: FACT
data: 2026-08-31
fonte: sonda ao vivo no DocuSign, 31/08/2026
responsavel: Italo Silveira
status: ativo
---

# P-07 — Três waivers paradas desde junho

[[DocuSign]] · [[Waiver]] · [[Problemas]]

## O problema
Três envelopes do [[DocuSign]] sem assinatura há mais de dois meses:

| Signatário | Enviada | Status |
|---|---|---|
| Matthew Hubbard | 01/06 | `sent` — nunca abriu · **expira 29/09** |
| Leticia Bittencourt | 16/06 | `delivered` — abriu e não assinou |
| Austin | 30/06 | `sent` — nunca abriu |

## Evidência
`getEnvelopes` + `listRecipients` na conta do [[DocuSign]], 31/08/2026.

## Impacto
Sem waiver assinada o piloto não entra na pista. E envelope que expira **tem que ser reenviado do zero**.

## O que fazer
Entram na varredura diária de [[Waiver de responsabilidade]]. O do Matthew Hubbard tem prazo: expira em 29/09.

## Fonte
sonda ao vivo no DocuSign, 31/08/2026
