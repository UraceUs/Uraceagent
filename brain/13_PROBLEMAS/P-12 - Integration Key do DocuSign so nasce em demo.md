---
tipo: problema
tipo_info: FACT
data: 2026-09-01
fonte: sonda em apps.docusign.com/admin/apps-and-keys pela extensão
responsavel: Italo Silveira
status: ativo
---

# P-12 — Integration Key do DocuSign só nasce em conta demo

[[DocuSign]] · [[Waiver de responsabilidade]] · [[Etapa de conexão]] ·
[[Problemas]] · [[P-11 - Producao do app QuickBooks travada]]

## O problema

A conta de **produção** `support@urace.us` (Account #152293148) **não
permite criar Integration Key**. A própria página diz:

> *"You cannot create an integration key in production. To create an IK,
> use your developer account."*
> *"All apps and integration keys are created in developer accounts and
> migrated through the go-live process."*

**Não existe nenhum app na conta hoje** — "No Integration Keys found".
Não é limitação de plano: é regra estrutural do DocuSign.

## Evidência

Sonda de 01/09/2026. Confirmados na mesma tela, e batem com o que já
estava no cérebro:

| Campo | Valor |
|---|---|
| API Account ID | `4261a166-3a91-4fb7-97c5-30257d657c52` |
| Account Base URI | `https://na4.docusign.net` |
| User ID | `b3ef4ae4-917e-4394-96b4-e1e5498cc75b` |

## Impacto

A varredura diária de waivers (`urace-waivers`, 07h30) **falha todo dia**
por falta de credencial. E há prazo real: a waiver do Matthew Hubbard
**expira em 29/09** ([[P-07 - Waivers paradas desde junho]]).

## O caminho

1. Criar **conta de desenvolvedor (demo)** — separada da produção, mesmo
   com o mesmo e-mail. `developers.docusign.com`
2. Criar o app e a Integration Key em `admindemo.docusign.com`
3. Gerar o **RSA keypair** e guardar a chave privada (aparece uma vez)
4. **~20 chamadas de API bem-sucedidas** no demo — é o requisito do
   go-live
5. Solicitar o **go-live**: promove a Integration Key para a conta de
   produção
6. Dar o **consent** do JWT uma vez, no navegador

⏳ O passo 4 é espera que corre sozinha — vale **começar cedo** mesmo
priorizando outra coisa.

### A conta demo foi criada em 01/09 — e deu um susto

Criada com o **mesmo e-mail e a mesma senha** da produção. O dono abriu
o DocuSign depois e não viu template nem envelope: parecia perda total.
**Não era** — o navegador tinha ficado no demo, que nasce vazio. Leitura
da produção na mesma hora confirmou tudo intacto: 4 templates, 39
envelopes, 19 completos.

A armadilha e como não cair nela de novo estão em [[DocuSign]].

## O padrão que apareceu duas vezes no mesmo dia

[[P-11 - Producao do app QuickBooks travada]] e este são o **mesmo tipo
de obstáculo**: SaaS corporativo não deixa um servidor falar com a conta
real sem passar por revisão ou promoção. Não existe "app privado" que
pule a fila, nem na Intuit nem no DocuSign.

**Consequência para a fila:** das três credenciais que faltam, só a do
**Google** não tem portão de revisão — e é justamente a que destrava a
[[Triagem de e-mail]] diária. Passa a ser a próxima.

## 02/09 — o caminho até o go-live está aberto

Integration Key `126393c2-…`, par RSA instalado, consentimento dado,
JWT autenticando na conta demo. O que falta é o próprio go-live: as ~20
chamadas bem-sucedidas e o pedido em *Apps and Keys → Go Live*. Depois,
trocar `DOCUSIGN_BASE_URI` para `na4` e os IDs para os de produção.
Passo a passo em `docs/adminai/docusign-go-live.md`.

## ~~Pausado~~ 02/09 14:43 — formulário assinado, em revisão

Go Live Status: **"Pending approval"**, com link *"Submit verification
form"*. Já feito: Integration Type = *Private custom integration*, link
da privacidade, Terms & Conditions aceitos, conta de produção
selecionada (`Italo Jorge da Silveira – 152293148`, que é a `4261a166-…`).

**O que falta é uma coisa só:** o formulário de verificação, que é um
**envelope assinado pelo Italo** (nome tem que bater com documento).
Não é tarefa de extensão. Campos e valores em
`docs/adminai/docusign-go-live.md`, passo 6. Depois de assinado, até 48h
de revisão manual da DocuSign.

Enquanto isso o VPS fica como está: base `demo`, varredura rodando no
demo vazio, envio recusado pelo servidor. Nada quebra por esperar.

## ✅ Go-Live Form assinado — 02/09/2026 11:43 PT

Envelope `53FB5A34-CFDE-4BBC-8747-92A57BAC813B`. Assinado pelo
[[Italo Silveira]] no celular, com **verificação de identidade por
documento (carteira de motorista, EUA) — aprovada**. Os três campos que
recusam foram conferidos no PDF: Production API Account ID
`4261a166-…`, Integration Key `126393c2-…`, signatário `support@urace.us`.

Seguiu para *"Go Live Execution — Dev Support Engineer II"*. **Até 48h.**
Quando aprovar: o bloco de virada está em
`docs/adminai/docusign-go-live.md`, passo 7. Até lá o VPS fica em demo.

## ✅ Resolvido — 04/09/2026

Go-live aprovado em menos de 48h. Virada feita: env em `na4`, IDs de
produção, consentimento de produção dado, e a prova pela ferramenta:
`"ambiente": "PRODUÇÃO"`, **50 envelopes** nos últimos 120 dias.

**O que o go-live NÃO carrega — e eu tinha dito que carregava:** a
Integration Key é a mesma, mas **o par RSA e os Redirect URIs não vêm
junto**. A produção nasceu com `RSA Keypairs: None`. Resolvido com
**Upload RSA** da chave pública derivada da privada do VPS
(`openssl rsa -pubout`) — sem gerar par novo, sem tocar na privada. O par
de produção ficou com ID próprio (`bb92d17c-…`), mesma chave.

Outra pegadinha: o primeiro Allow de produção deu *"Não existem URI de
redirecionamento registados"* mesmo com a URI salva — propagação. Cinco
minutos depois funcionou.
