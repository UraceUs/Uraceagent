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

## Impacto: está no CAMINHO CRÍTICO

Eu tinha classificado como "sem impacto hoje", com o argumento de que o
faturamento funciona pelo conector do Claude. **O dono corrigiu, e a
correção é estrutural:**

> "o quickbooks tem que estar na vps, o claude não vai operar esse
> agente de ia"

É a mesma decisão de sempre —
[[D-2026-08-28 - Construir por partes e por aplicacao]]: o sistema é o
[[VPS e OpenClaw]]; o Claude Code é ambiente de desenvolvimento e
backup, **não o destino**. Medir impacto pelo que o conector do Claude
cobre é medir pelo backup.

Sem chave de produção, o agente no VPS só alcança **sandbox** — não a
[[URACE US INC]] real. Ou seja: **o faturamento não migra para o VPS
enquanto isto não for resolvido.**

## O que fazer

**Destravar.** O passo a passo com **as respostas de cada campo já
prontas** está em `docs/adminai/intuit-app-review.md` — inclusive o
questionário de compliance.

O único pré-requisito que dependia do dono já está resolvido: as duas
páginas exigidas (**política de privacidade** e **EULA**) foram escritas
em `adminai/deploy/legal/`, e há um script que as publica pelo Caddy do
próprio VPS (`servir_legal.sh`), com prova por `curl` no fim. Ele só
precisa **ler e assumir o texto** — quem responde pelas cláusulas é a
empresa.

⚠️ **Não confundir com prazo de token:** o refresh token do QuickBooks
vale **100 dias** e rotaciona a cada uso — diferente do token permanente
do [[Asana]].

⚠️ **Não confundir com acesso de usuário.** Dar acesso a alguém para
emitir invoice (ex.: `lucas@urace.us`) é *gear → Manage users* dentro do
QuickBooks, e **não tem relação** com o app de desenvolvedor. Esse
caminho está livre.
