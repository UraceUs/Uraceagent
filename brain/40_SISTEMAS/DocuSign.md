---
tipo: sistema
fonte: docusign
atualizado_em: 2026-08-31
tipo_info: FACT
responsavel: sonda ao vivo
status: ativo
---

# DocuSign

[[URACE]] · [[Waiver]] · [[Waiver de responsabilidade]] · [[Asana]] · [[Gmail]] · [[PARAMETROS]]

Conector **instalado e sondado ao vivo em 31/08/2026**. Tudo abaixo veio
da fonte, nada foi presumido.

| O quê | Valor |
|---|---|
| Conta | `4261a166-3a91-4fb7-97c5-30257d657c52` |
| Titular | Italo Jorge da Silveira |
| **E-mail da conta** | **`support@urace.us`** |
| Região | `https://na4.docusign.net` (remetente `dse_NA4@docusign.net`) |
| Brand | `d1d1d835-54ad-405f-8fb7-25bfc91ec350` (logo U-RACE no e-mail) |

## 🔓 O que isso destrava

A conta DocuSign **é a `support@`**. Então a IA enxerga o status de toda
waiver **direto na DocuSign**, sem precisar da caixa de e-mail.

O fluxo que estava travado — "waiver assinada chega no support@, que a IA
não tem" — **deixa de depender do e-mail**. A DocuSign passa a ser a
fonte de verdade da assinatura; o e-mail vira só notificação.
Ver [[Etapa de conexão]].

## Os templates

Quatro no total, mas **só dois são reais**:

| Template | ID | Quando |
|---|---|---|
| **Parental consent Waiver liability** | `6dbf2094-39da-4c21-95dd-feda7ac28022` | piloto **menor de idade** → vai para o **pai/mãe/responsável** |
| **Adult Waiver of Liability** | `c51aede4-bba5-40df-9f14-24c340e2bd3e` | piloto **maior de idade** → vai **direto para o piloto** |

**A idade decide qual dos dois.** Nome do papel (role) nos dois:
`Parental Consent Waiver Liability`.

Assunto do e-mail que o cliente recebe:
- Parental: `Please Complete the Docusign: Parental Consent, Release, and Waiver of Liability`
- Adult: `Action Needed: Event Release and Waiver of Liability Docusign`

### Dois templates vazios — ficam onde estão

`63dcf553-4b35-40cc-919a-c83f1db11ee5` e
`5441b464-d847-4402-bed0-7504ecf8a95b` — sem nome, sem assunto, 0
páginas. **Decisão do dono (31/08): não serão usados, e não precisam ser
apagados.**

Consequência para a IA: como eles continuam na conta e o Parental está
com `autoMatch: true`, **escolher template pelo ID é obrigatório** —
nunca por nome, nunca deixando o auto-match decidir. Só os dois IDs da
tabela acima existem para a automação; os outros dois **não existem**.

### O texto do Adult Waiver — fica como está

O `emailBlurb` do **Adult Waiver** é cópia do texto parental: fala em
*"your child's participation"*. Um piloto adulto recebe e-mail sobre o
filho dele.

**Decisão do dono (31/08): não mexer.** Registrado para que ninguém
"conserte" isso depois achando que é bug esquecido — é escolha
consciente. A IA **não edita template** em hipótese alguma.

### O prazo que o texto promete ao cliente

Os dois e-mails dizem: *"this consent will be valid for **one year from
the date of signing**"*. É isso que está escrito para o cliente. O
cérebro dizia "vale por temporada" — **o texto oficial é 1 ano a partir
da assinatura**, e é por ele que a IA deve conferir validade.

## Como um envelope é criado (fluxo do dono)

1. Seleciona o template (parental ou adult, **pela idade do piloto**).
2. Preenche **dois campos só: nome e e-mail** do signatário.
3. Envia. Abre a tela com o documento enviado.

Alguns contatos já ficam salvos no DocuSign. **Sempre conferir nome e
e-mail** antes de enviar — e **não mandar duas vezes** para quem já tem
waiver válida.

## Status de um envelope

`created` (rascunho) → `sent` (enviado, ainda não aberto) →
`delivered` (**aberto/visto**, ainda não assinado) → `completed`
(assinado) · `declined` · `voided`

**`delivered` não é assinado.** É "abriu e não assinou" — a situação que
mais engana. Só `completed` conta.

## Envelope expira

Todo envelope tem `expireDateTime` / `expireAfter` (dias restantes).
Waiver que expira sem assinatura **tem que ser reenviada do zero**. A
rotina diária precisa olhar isso também, não só o prazo do serviço.

## O DocuSign não é só waiver

Também passam por aqui **NDAs** e **Service Agreements** (vistos em
aberto: `Caio_Imperato_AgreementNDAdocx.pdf` e
`2026.2 Pablo Santiago_Service Agreement.pdf`). São outra classe de
documento, com outra criticidade — a rotina da waiver não deve tratá-los
como waiver, mas também não deve ignorá-los.

## O que o conector faz

**Lê:** `getUserInfo` · `getTemplates` · `getEnvelopes` · `getEnvelope` ·
`listRecipients` · `listEnvelopeDocuments` · `getAllAgreements` ·
`getAgreementDetails` · `getUsers`

**Escreve:** `createEnvelopeFromTemplate` (cria **e envia**) ·
`createEnvelope` · `sendReminder` · `updateEnvelope` ·
`updateEnvelopeRecipients` · `updateEnvelopeTabs` · `triggerWorkflow` ·
`resumeWorkflow` · `cancelWorkflowInstance` · `pauseNewWorkflowInstances`

> ⚠️ **`createEnvelopeFromTemplate` cria e ENVIA no mesmo passo** — não
> existe "salvar rascunho e alguém revisa depois", como acontece na
> invoice do [[QuickBooks]]. Chamar a ferramenta **é** mandar o e-mail.
>
> **O dono autorizou a IA a enviar a waiver em 31/08** — e, justamente
> porque não tem volta, o envio passa por **4 travas obrigatórias**
> (waiver válida já existente · envelope já em aberto · idade confirmada
> · nome e e-mail conferidos). Ver [[Waiver de responsabilidade]].


## ⚠️ Demo e produção são DUAS contas — a armadilha do mesmo e-mail

Desde 01/09/2026 existe **também uma conta de desenvolvedor (demo)**,
criada com o **mesmo e-mail e a mesma senha** da produção
(ver [[P-12 - Integration Key do DocuSign so nasce em demo]]).

São sistemas **completamente separados**. Compartilham só o e-mail — é
como ter conta no Gmail e no Outlook com o mesmo endereço.

| | **Produção** (a real) | **Demo** (a de teste) |
|---|---|---|
| Login | `account.docusign.com` | `account-d.docusign.com` |
| App | `apps.docusign.com` | `appdemo.docusign.com` |
| Admin | `admin.docusign.com` | `admindemo.docusign.com` |
| API | `na4.docusign.net` | `demo.docusign.net` |
| Conteúdo | 4 templates · 39 envelopes | **vazia** |
| `accountId` | `4261a166-3a91-4fb7-97c5-30257d657c52` | `d3cf672c-62f6-4c5c-bddb-7a3307a52123` |
| `userId` | `b3ef4ae4-917e-4394-96b4-e1e5498cc75b` | `4347151f-fe2a-4e6f-87df-e8457a00a7ff` |

Os GUIDs são **diferentes** nos dois ambientes: mesma pessoa, mesma
empresa, identidades distintas. O número curto da conta demo é
`50217403`, nome "Urace US" — não confundir com o `accountId`.

A **Integration Key** (o `client_id` da aplicação) é
`126393c2-ae7a-4b73-9585-fed7e13cafe7`, criada em 01/09/2026 no app
`URACE Administrative AI`. Ela **sobrevive ao go-live**: é a mesma chave
em demo e em produção. O que muda é para qual `accountId` ela aponta.
Ver [[P-12 - Integration Key do DocuSign so nasce em demo]].

### O susto de 01/09

Depois de criar a conta demo, o dono abriu o DocuSign e **não viu
template nem envelope nenhum** — parecia que a conta tinha sido
sobreposta e os dados perdidos.

**Nada foi perdido.** O navegador tinha ficado logado no **demo**, que
nasce vazio. Leitura da produção feita na mesma hora confirmou: os 4
templates com os mesmos IDs, 39 envelopes desde 01/06, 19 completos.

Para voltar à conta real: **`https://apps.docusign.com/send/home`**.

### O risco que fica

Waiver enviada do **demo não tem validade jurídica** — o documento sai
carimbado como teste. E como as duas contas têm a mesma senha, é fácil
mandar do ambiente errado sem perceber.

**Recomendação ao dono:** trocar a senha do demo para uma diferente. Não
é urgente, mas obriga a saber em qual ambiente se está antes de enviar.

⚠️ **Regra para a IA:** a conta de produção é
`4261a166-3a91-4fb7-97c5-30257d657c52`, base `https://na4.docusign.net`.
**Nunca enviar waiver por outro `accountId` ou outra base URI.** Se a
resposta da API vier de `demo.docusign.net`, está no ambiente errado —
parar e escalar.

## Como o Administrative AI fala com o DocuSign

Desde 02/09/2026, por **servidor MCP nosso** (`adminai/mcp/docusign_mcp.py`),
no [[VPS e OpenClaw]]. Autentica por **JWT com a chave RSA** de
`~/.urace/`, assinando com o `openssl` da máquina — sem biblioteca. O
agente recebe só as ferramentas; chave e token ficam no host.

O MCP oficial (`mcp-d.docusign.com`) exigiria Client ID + Secret, que o
OpenClaw não sabe usar. O servidor próprio trouxe o que o oficial não
daria: **as 4 travas rodam dentro da ferramenta de envio**, antes da
chamada. O modelo não tem como pular uma.

| Trava | Como o servidor garante |
|---|---|
| 1 · waiver válida (< 1 ano) | consulta os envelopes `completed` do e-mail e recusa |
| 2 · envelope em aberto | consulta `sent`/`delivered` do e-mail e recusa |
| 3 · idade confirmada | argumento `idade_confirmada=false` → recusa antes de qualquer API |
| 4 · nome/e-mail conferidos | argumento `nome_email_conferidos=false` → recusa antes de qualquer API |
| **5 · ambiente** | base `demo.docusign.net` → envio **sempre** recusado (sem validade jurídica) |
| template pelo ID | só os 2 de [[PARAMETROS]]; qualquer outro é recusado |
| `APLICAR=0` | passa pelas travas e devolve *"teria enviado"* |

Não existem: `voidEnvelope`, editar template, `sendReminder` (U-01 em
[[Conflitos e lacunas]]). Se precisar, é humano.

**Leitura:** `docusign_ambiente` (chame primeiro — diz se é demo ou
produção e se o JWT autentica) · `docusign_templates` ·
`docusign_envelopes` · `docusign_envelope` · `docusign_waivers_de`
(a consulta das travas 1 e 2 para um e-mail).

**Escrita:** `docusign_enviar_waiver`, só.

**Em produção desde 04/09/2026.** Base `na4.docusign.net`, conta
`4261a166-…`, 50 envelopes visíveis. A fase demo acabou; o que a IA lê
agora é a conta real. Envio continua atrás de `APLICAR=1`.

⚠️ O go-live promove a **Integration Key**, não o par RSA nem os
Redirect URIs — a produção nasce com `RSA: None`. Resolve-se com *Upload
RSA* da chave pública derivada da privada que já está no VPS. Nunca
*Generate*: isso invalidaria a chave instalada.

## Prazo

Assinada **2 dias antes** do serviço ([[PARAMETROS]]) — o dono falou "um
a dois dias"; fica valendo o mais rígido, 2 dias, que é o mesmo prazo do
pagamento.
