---
tipo: problema
tipo_info: FACT
data: 2026-09-16
fonte: contagem real dos filtros da support@ pelo VPS
responsavel: Italo Silveira
status: aberto
---

# P-14 — Um filtro manda **todo** envelope do DocuSign para `Waivers`

[[Taxonomia do Gmail]] · [[D-2026-09-16 - Waiver por e-mail, DocuSign x Waivers e a subtarefa]]

## O que existe na caixa

Na `support@`, entre os 37 filtros nativos:

```
from = dse_na4@docusign.net OR richard@thinkinsurance.co.uk  ->  Waivers
```

`dse_na4@docusign.net` é o **endereço de envio da conta inteira do DocuSign** —
todo envelope sai dele, waiver ou não. Então esse filtro põe `Waivers` em coisa
que não é waiver.

## A prova, nas últimas 40 mensagens do remetente (16/09)

**34 waivers e 6 que não são**: um NDA do Caio Imperato, a *Intended Use Letter* da
URACE_AUTO_LLC, a *Invite Letter 2026* do Bryan Bernal (duas mensagens) e um
`UniversalNon-POD`. Todas com `Waivers` colado pelo filtro — 15% de erro, e cada
uma delas acordaria o fluxo da waiver em documento que não é waiver.

As 6 já estão marcadas na caixa: filtro só age na chegada, então apagar o filtro
não tira o marcador do que já passou.

## Por que isso importa mais do que um marcador errado

`Waivers` é o **gatilho do fluxo da waiver**: a IA baixa o PDF, lê para descobrir
de quem é, vincula ao cliente e fecha a subtarefa "Signed waiver?". Com esse
filtro, ela seria acordada por **todo** envelope do DocuSign — contrato,
aditivo, o que for — e tentaria achar cliente em documento que não é waiver.

Contradiz o que o dono ditou em 16/09: *"sempre tenha o marcador Software Apps
DocuSign. E só quando for uma waiver que foi enviada ou uma waiver que foi
recebida assinada, marcar com a waiver."*

## De onde ele veio — provavelmente meu

O formato (dois remetentes em `OR` sob um marcador) é o do gerador, e
`richard@thinkinsurance.co.uk` só aparece junto porque a amostragem o viu em
mensagens com `Waivers`. A trava que impede exatamente isso —
`sem_conflito_com_o_dono()`, que proíbe regra derivada de amostra em marcador que
o dono ditou — só entrou no commit `71afc50`. O XML que o dono importou pela
extensão na `support@` foi gerado **antes** dela. Ou seja: a trava existe, mas
chegou depois do estrago.

Isso também mostra um limite do gerador: ele evita criar de novo, **mas não vê o
que já está na caixa**. Filtro existente que conflita com regra ditada precisa
aparecer no relatório.

## O que falta

Decisão do dono para **apagar esse filtro** — o código só cria filtro, nunca
apaga nem edita, e apagar configuração da caixa dele não é coisa que eu faça
sozinho. Apagado, ficam valendo as duas regras que ele ditou, que já estão lá:
`from:(docusign.net OR docusign.com)` → `Softwares|Apps/Docusign` para tudo, e o
assunto de *Waiver of Liability* → `Waivers` só para waiver.
