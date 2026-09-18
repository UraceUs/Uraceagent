---
tipo: projeto
tipo_info: FACT
status: ativo
owner: Italo Silveira
data: 2026-09-17
fonte: código do repositório, registros do cérebro e a prova real do deploy de 17/09
responsavel: Italo Silveira
---

# Administrative AI — Estado completo em 17/09/2026

[[URACE]] · [[Administrative AI]] · [[Painel do Brain]] ·
[[Administrative AI - Estado completo em 2026-09-04]] (a fotografia anterior)

> **O projeto está rodando.** Não é protótipo, não é ambiente de teste: o
> [[Command Center]] está publicado, as cinco fontes estão conectadas, a IA
> propõe dentro do painel e o humano aprova. Esta nota é a fotografia de hoje —
> o que está no ar, o que não está, e onde cada coisa vive.

**Manual de uso (humanos e IA):** `docs/manual-do-command-center.md`

---

## 1. O que está no ar

| Área | Estado hoje | Desde |
|---|---|---|
| **Command Center** `https://urace-bridge.duckdns.org/ops/` | no ar; login próprio, papéis, auditoria imutável, espelho das fontes | 04/09 |
| **Identidade visual** "Pit Wall Glass" | no painel inteiro; preto, branco, vermelho e **azul** | 17/09 |
| [[Asana]] | MCP próprio no VPS; quadro, calendário, lista e tarefa por dentro; ADM URACE e Matt tasks **só leitura** | 02/09 |
| [[DocuSign]] | **produção**: envia waiver com aprovação, baixa PDF, reenvia com correção, anula em aberto, lixeira | 04/09 |
| [[Gmail]] | as **duas caixas** (urace@ e support@); três colunas no painel; IA sugere marcador, botão Mover aplica; **sem envio livre** | 04/09 |
| [[QuickBooks]] | **produção liberada pela Intuit**; invoice criada e enviada **depois de aprovada**; lembretes recorrentes; espelho de invoices | 09/09 |
| [[Kommo]] | chat do lead dentro do painel: mensagem chega pelo webhook da conta, resposta sai pelo bot, dados do lead ao lado, favoritos | 16–17/09 |
| **Vendas (oportunidades)** | quadro por etapa, agenda de retornos, registro de ligação e **fechar venda em uma tela** disparando cliente, QuickBooks, waiver, Asana e Kommo | 17/09 |
| **Voz** | ditar em todo campo de texto e ouvir a resposta da IA, pelo próprio navegador | 17/09 |
| **Atualizar pelo painel** | botão em Integrações (path unit + service), log ao vivo; deploy sobrevive à queda do SSH | 17/09 |
| **Login novo** | foto da pista cortada na diagonal, linha vermelha, formulário à direita | 17/09 |

**Prova real do deploy de 17/09** (o script recusa subir sem isso): `/ops/` responde
200 com o SPA, `/ops/api/dashboard` sem sessão responde 401, as páginas legais seguem
200, e os testes passam antes de o serviço reiniciar.

## 2. O que NÃO está no ar

| O que | Por quê | De quem depende |
|---|---|---|
| **Pit Wall** em `/painel/` | **aposentado em 18/09** por decisão do dono: a rota sai do Caddy (`aposentar_painel.sh`) | — |
| **Foto do login** | o arquivo entrou no repositório em 17/09, depois do último deploy | rodar o deploy de novo |
| **Agente escrevendo sozinho** | o agente no OpenClaw roda em simulação (`APLICAR=0`); quem executa o aprovado é o painel, com APLICAR ligado só naquele clique | decisão do dono |
| **Azul oficial da marca** | **resolvido em 18/09: `#0057B4`**, dito pelo dono e aplicado no painel | — |
| **Usuário de vendas** | ninguém criado ainda; em 18/09 o dono disse que quem vai usar é outra pessoa (o Lucas, comercial) | URACE |

## 3. Como a operação funciona hoje

```
Asana · DocuSign · Gmail · QuickBooks · Kommo
   → espelho no banco do painel (a cada 15 min, ou no botão Sincronizar)
   → o que mudou vira evento e acorda o agente, com o contexto do cliente e a memória
   → o agente responde e declara as ações que faria
   → cada ação recebe a política da tabela `action_policies`
   → SAFE executa; confirmação/aprovação esperam uma pessoa
   → aprovar executa na hora, auditado; rejeitar registra o porquê
```

**Quem decide:** administrador, gerente e a conta de **acesso livre** decidem tudo;
o **operador** decide nos módulos dele — inclusive vendas; invoice e QuickBooks ficam
com gerente ou administrador; leitura não decide nada.

**Papéis:** Administrador · Gerente · Operador · Leitura, mais a conta de acesso
livre (sem cargo, alcança tudo). **Não existe papel "vendas"**: quem vende é
Operador — correção do dono em 17/09.

## 4. As travas que valem (impostas em código, não no prompt)

- A IA **não envia e-mail livre** e **nunca apaga** nada.
- **Waiver e invoice exigem aprovação humana**; aprovar = enviar, com prévia.
- **Invoice fora da tabela de preços** fecha a venda mas espera o dono.
- **Rate Card manda** acima do catálogo do QuickBooks.
- Ação sem política cadastrada cai em **confirmação obrigatória**.
- **ADM URACE** e **Matt tasks**: só leitura.
- `audit_logs` é **imutável** (gatilho no banco impede UPDATE e DELETE).
- Tudo no **fuso da Flórida**, no servidor e na tela.
- Segredo **nunca** no repositório: vive em `~/.urace/*.env` no VPS.

## 5. Números de hoje

- **308 commits** na branch `claude/configurar-open-claw-ooqo8x`
- **207 testes automatizados** do Command Center — o deploy para se um falhar
- **51 decisões** registradas em `08_DECISOES`
- **14 problemas** catalogados; 5 resolvidos (P-10, P-11, P-12, P-13, P-14)
- **5 fontes** conectadas: Asana, DocuSign, Gmail, QuickBooks, Kommo

## 6. Problemas ainda abertos (operação, não sistema)

[[P-01 - Modelo de tarefa fora do padrao]] · [[P-02 - Campos do modelo em branco]] ·
[[P-03 - Colunas dos dias com servico velho]] · [[P-04 - Contas a receber concentradas]] ·
[[P-05 - Security deposit quase nao aparece]] ·
[[P-06 - Precos defasados no catalogo do QuickBooks]] ·
[[P-07 - Waivers paradas desde junho]] · [[P-08 - Order Number guardando URL]] ·
[[P-09 - Conector do Asana nao sobe anexo]]

Nenhum deles impede o painel de operar: são coisas a limpar **na operação**.

## 7. Onde tudo está

| O que | Onde |
|---|---|
| Painel | https://urace-bridge.duckdns.org/ops/ |
| Manual de uso | `docs/manual-do-command-center.md` |
| Código | https://github.com/UraceUs/Uraceagent (branch `claude/configurar-open-claw-ooqo8x`) |
| Decisões | `brain/08_DECISOES/` |
| Diário | `brain/30_DIARIO/` |
| ADR do painel | `docs/adminai/command-center-adr.md` |
| Deploy | `adminai/deploy/command_center/servir_command_center.sh` |
| Páginas legais | https://urace-bridge.duckdns.org/legal/privacy.html |
| Asana (quadro U-RACE) | https://app.asana.com/0/1205450093098920/board |
| Tarefa do projeto no Asana | https://app.asana.com/0/0/1216893560116094/f |

## 8. O deploy, em um bloco

```bash
cd ~/Uraceagent && git fetch origin claude/configurar-open-claw-ooqo8x && git checkout claude/configurar-open-claw-ooqo8x && git pull origin claude/configurar-open-claw-ooqo8x && bash adminai/deploy/command_center/servir_command_center.sh
```

Ou, sem terminal: **Integrações → Atualizar agora** (só administrador).
