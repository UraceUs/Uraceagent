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

## 04/09 — o que a primeira varredura completa mostrou

Leitura real do DocuSign em produção ([[2026-09-04]]):

- **Matthew Hubbard**: o envelope de 27/05 foi para
  `misterhub**bb**ard@gmail.com` e **devolveu** (`550 no such user`). O
  reenvio de 01/06 para `misterhubbard@gmail.com` está certo, mas segue
  `sent` — nunca aberto. Expira **29/09**.
- **Leticia Bittencourt**: `delivered` desde 16/06 — abriu, não assinou.
  Expira 14/10.
- **Austin**: `sent` desde 30/06, nunca aberto. Expira 28/10.
- Nenhum dos três tem serviço no quadro. Não são alerta; são limpeza.

O que muda: `autoresponded` passa a ser tratado como **falha de
entrega**, não como espera. Pergunta para o dono: cutucar (`sendReminder`,
U-01) ou deixar expirar e reenviar do zero quando houver serviço?
