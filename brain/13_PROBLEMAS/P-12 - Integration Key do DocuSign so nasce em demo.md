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

## O padrão que apareceu duas vezes no mesmo dia

[[P-11 - Producao do app QuickBooks travada]] e este são o **mesmo tipo
de obstáculo**: SaaS corporativo não deixa um servidor falar com a conta
real sem passar por revisão ou promoção. Não existe "app privado" que
pule a fila, nem na Intuit nem no DocuSign.

**Consequência para a fila:** das três credenciais que faltam, só a do
**Google** não tem portão de revisão — e é justamente a que destrava a
[[Triagem de e-mail]] diária. Passa a ser a próxima.
