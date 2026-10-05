---
tipo: decisao
tipo_info: DECISION
data: 2026-10-05
fonte: [[Administrative AI]]
responsavel: Liga ou não a assinatura de waiver na área do cliente, sem DocuSign.
status: ativo (nasce desligada)
---

# D-2026-10-05 — Waiver assinada na área do cliente, em paralelo ao DocuSign

issue #85, 05/10/2026

## O que foi decidido
[[Waiver]] · [[DocuSign]]

O Command Center ganha a assinatura de waiver **dentro da área do cliente**, sem DocuSign.
Ela roda **em paralelo**: nasce desligada, o ADMIN liga em *Site público → Waiver*, e o
DocuSign continua como está (envio pela IA, espelho, lembretes).

## Por quê
Dono, 05/10: *"conseguimos replicar a plataforma do docusign nativa na vps?"* — *"por causa de custo"*.

## Como fica
- **O texto legal é o mesmo**: os dois modelos (Adult e Parental) são **lidos** do DocuSign
  e guardados como vieram, com o SHA-256. Ninguém redigita waiver. Se o texto mudar lá,
  importa de novo.
- **Quem assina** é o responsável logado (conta 18+). Piloto menor → parental; maior → adult.
- Para assinar, ele marca duas caixas ("li e concordo" e "concordo em assinar
  eletronicamente"), digita o nome completo e desenha a assinatura.
- **Prova**: o PDF original mais uma página de assinatura e certificado (hora da Flórida e
  UTC, IP, aparelho, conta, hashes do modelo e da assinatura). O hash do PDF final também
  fica guardado.
- **Vale 1 ano** ([[D-2026-08-31 - Waiver vale um ano]]).
- Grava na **mesma tabela** das do DocuSign (`source='urace'`): o card do cliente, o
  download e a contagem de "waiver assinada" tratam as duas iguais.

## Antes de ligar
O advogado confirma que a assinatura eletrônica com essa página de certificado vale para a
waiver de menor na Flórida (ESIGN/UETA; Fla. Stat. 744.301).

## Quem decidiu
[[Italo Silveira]] pediu; a ligação é do ADMIN.

## Fonte
issue #85 · `command_center/providers/waiver_nativa.py`
