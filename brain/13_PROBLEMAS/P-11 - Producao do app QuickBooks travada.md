---
tipo: problema
tipo_info: FACT
data: 2026-09-01
fonte: sonda no developer.intuit.com pela extensão de navegador
responsavel: Italo Silveira
status: ativo
---

# P-11 — Chaves de produção do app QuickBooks travadas

[[QuickBooks]] · [[Conector do QuickBooks]] · [[Etapa de conexão]] ·
[[Problemas]]

## O problema

O app **"ia app"** existe no workspace `Urace` do Intuit Developer
(AppID `94f253e1…`), mas está **`IN DEVELOPMENT`**. As credenciais de
**Production** aparecem com cadeado — a Intuit só libera depois de:

| Exigência | Esforço | Estado |
|---|---|---|
| **App details** — perfil, e-mail verificado, **URL de EULA e de política de privacidade**, host domain, launch/disconnect/connect URL, categoria, indústrias reguladas, hospedagem | ~10 min | 0% |
| **Compliance** — questionário de conformidade | ~40 min | 0% |
| Perfil da conta — endereço, estado, telefone | — | incompleto |

As chaves de **Development** estão liberadas, mas só funcionam com
empresa **sandbox** — não com a [[URACE US INC]] real.

## Evidência

Sonda de 01/09/2026 pela extensão de navegador, logada na conta do dono.
Ela parou ao ver que destravar exigiria mudar configuração além do que
tinha sido autorizado — comportamento correto.

## Impacto

**Nenhum, hoje.** É importante entender por quê:

- **Nenhuma das 4 rotinas do [[VPS e OpenClaw]] usa o QuickBooks.**
  Sincronia do [[Asana]], [[Triagem de e-mail]],
  [[Waiver de responsabilidade|varredura de waivers]] e saúde do cérebro
  não tocam em QBO.
- O faturamento acontece **pelo conector do Claude**, que já tem acesso à
  empresa real — foi por ele que se leu a invoice paga de $2.756,90, o
  A/R de $185.887 e as 896 linhas do catálogo.

O bloqueio só passa a doer quando o faturamento migrar para o VPS, e a
IA precisar conferir pagamento e devolução de depósito sozinha.

## O que fazer

**Decisão de 01/09: adiar.** A ordem passa a ser [[DocuSign]] →
Google/[[Gmail]] → QuickBooks. As duas primeiras têm rotina diária
falhando **agora**; esta não.

Quando for a hora, os dois itens que **dependem do dono** e que ninguém
pode inventar por ele:

1. uma página de **política de privacidade** no site da URACE;
2. uma página de **EULA** (termos de uso do app).

O resto do formulário e o questionário de compliance podem ser
preenchidos com acompanhamento.

⚠️ **Não confundir com acesso de usuário.** Dar acesso a alguém para
emitir invoice (ex.: `lucas@urace.us`) é *gear → Manage users* dentro do
QuickBooks, e **não tem relação** com o app de desenvolvedor. Esse
caminho está livre.
