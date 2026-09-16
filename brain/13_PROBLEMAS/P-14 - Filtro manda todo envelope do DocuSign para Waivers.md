---
tipo: problema
tipo_info: FACT
data: 2026-09-16
fonte: contagem real dos filtros da support@ pelo VPS
responsavel: Italo Silveira
status: resolvido
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

## Resolvido no mesmo dia (16/09)

O dono apagou o filtro com a própria mão — o comando conferia que era **exatamente
um** e abortava se achasse outro. `ANe1BmgC3X5ET_S_ey3-D_g9jvTnEhqVwLcD1g`, fora.
A `support@` ficou com **36** filtros.

Valem agora só as duas regras que ele ditou: `from:(docusign.net OR docusign.com)`
→ `Softwares|Apps/Docusign` para todo envelope, e o assunto de *Waiver of
Liability* → `Waivers` só para waiver.

## O estrago real era maior: 32 mensagens, e metade era a corretora

Varrendo tudo o que tinha `Waivers` (**87 mensagens**), o que não tinha cara de
waiver eram **32** — e o filtro tinha **dois braços**, não um:

- `richard@thinkinsurance.co.uk` → **22 mensagens "Test Day"**: a corretora de
  seguro inteira virava waiver (13 do Richard + 9 respostas do próprio `support@`
  nas mesmas conversas). Elas já tinham o marcador certo,
  `Customer Service/Venda fechada`, pelo outro filtro dele.
- `dse_NA4@docusign.net` → **10 documentos que não são waiver**: `URACE Employment
  Letter`, `Employment Offer Letter Hernan`, `Invite Letter 2026` (Hernan ×2,
  Alfredo, Brayan), `OKC Letter 2026`, `LETTER OF INTENT AND SPONSORSHIP`,
  `Contrato_Marketing_Digital`, `UniversalNon-POD`. Carta de emprego e contrato
  de marketing a um passo de serem baixados e colados em card de cliente.

Conferido o remetente de cada uma antes de tirar: **nenhuma tinha sido marcada pela
mão dele**. O dono tirou o marcador em duas passadas (23 + 9), mensagem por
mensagem, com teto de segurança e sem apagar nada. `Waivers` ficou com **55**,
todas com *waiver* ou *consent* no assunto.

## Efeito da regra ditada que vale saber

O assunto *"Nya Amankwa viewed **Please Complete** the Docusign: Parental
Consent…"* casa com a regra dele, então aviso de **visualizou** e de **anulado**
também recebe `Waivers`. Não quebra: `waiver_do_email` só baixa PDF e mexe em
tarefa quando o registro no DocuSign está `completed`; "visualizou" no máximo
liga o e-mail ao cliente certo. Só aparece na lista. Apertar é decisão dele.

## O que mudou no código

`conflitos_na_caixa()` no gerador (`fa6cd38`): antes de escrever o relatório, ele lê
os filtros que **já existem** e abre o relatório com o conflito, além de avisar no
terminal. A trava antiga só impedia criar de novo; essa enxerga o que já está lá.
