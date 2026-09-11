---
name: urace-gmail
description: Triagem das caixas urace@urace.us e support@urace.us — lê cada e-mail novo, classifica com os marcadores do MANUAL confirmado pelo dono (MANUAL.md, nunca de memória), cria rascunho de resposta (nunca envia), alimenta o quadro Shipping Orders do Asana com compras e envios, e registra tudo no segundo cérebro. Use na rotina de e-mail ou quando precisar classificar/entender um e-mail da URACE.
---

# Triagem das caixas `urace@urace.us` e `support@urace.us`

## 📖 A taxonomia não está aqui — está em `MANUAL.md`

**Leia `MANUAL.md` (ao lado deste arquivo) antes de classificar qualquer
e-mail.** São os 156 marcadores reais da caixa, com o que vai em cada um,
escritos pela IA e **confirmados marcador por marcador pelo dono em
11/09/2026** (145 confirmados, 11 deixados de fora).

Este arquivo já teve uma tabela própria, de 28/08. Ela saiu: duas listas
divergem, e a que mandava era a errada. Agora existe **uma fonte só** —
`command_center/providers/taxonomia_gmail.py` — de onde saem o `MANUAL.md`,
a tela do painel (Gmail → Manual dos marcadores) e o prompt da triagem.

A caixa está organizada há anos: **manter, não reinventar.**

## 🚫 Regras invioláveis

1. **NUNCA enviar e-mail nesta rotina.** Só rascunho — enviar é do
   humano. (As duas únicas exceções autorizadas vivem no processo do
   macacão, não aqui: pedido de medidas ao cliente e pedido de produção
   ao fornecedor. Ver `brain/00_SYSTEM/PARAMETROS.md`.)
2. **NUNCA criar marcador.** A taxonomia é do dono, não da IA. O MCP
   recusa marcador que não existe — e essa recusa é proposital, não é bug
   para contornar. Se faltou marcador para um caso, **relate**, não invente.
3. **Só usar marcador confirmado no `MANUAL.md`.** Marcador que apareça na
   caixa e não esteja lá **não existe** para a IA — inclusive os 11
   `Email Review/…`, que não são do dono. Novidade entra como `pendente` e
   espera a confirmação dele no painel.
4. **Não apagar e não marcar spam.** Arquivar, só propaganda (item 6).
5. **Na dúvida, perguntar** — deixa na inbox e relata. Chute errado custa
   mais caro que pergunta.
6. **Arquivar só `wNews`.** Propaganda sai da inbox ao ser etiquetada;
   **todo o resto fica visível na inbox**, mesmo já classificado. A IA
   limpa o ruído, não esconde o que precisa de decisão do dono.
7. **Rascunho só para lead/orçamento e cliente atual.** Parceria e
   financeiro o dono responde pessoalmente — a IA classifica e para por
   aí. Nunca enviar, em nenhum dos casos.
8. **Tom:** a caixa recebe pedido de orçamento e mensagem de parceiro.
   Responder com calma e cordialidade; a relação vale mais que a pressa.

## Quem roda a triagem hoje

Desde 09/09 quem classifica é o **Command Center** (regra `gmail_triagem`,
07:00 / 13:00 / 21:00), que aplica os marcadores e move a thread para o
marcador principal. O timer antigo `urace-triagem-email` está desligado —
dois agentes na mesma caixa derrubam o VPS.

Esta skill vale para o trabalho **sob demanda**: entender um e-mail,
classificar um caso pontual, investigar uma thread. As regras são as mesmas.

> A triagem **se recusa a rodar** enquanto nenhum marcador estiver
> confirmado. Isso é a trava que o dono pediu — não force.

## Rotina

1. Ler cada thread nova da inbox (assunto, remetente, corpo).
2. Consultar o `MANUAL.md` e aplicar o marcador. Propaganda → `wNews`.
3. Se for **compra nossa** → atualizar o Asana (abaixo).
4. **Rascunho** se for lead/orçamento ou cliente atual — nunca envio.
   Parceria e financeiro: só classificar, o dono responde.
5. Propaganda etiquetada como `wNews` → **arquivar** (tirar da inbox).
   Qualquer outro e-mail **permanece na inbox**.
6. Dúvida → perguntar.
7. Relatar: quantos e-mails, quais marcadores, quantos arquivados,
   quais rascunhos criados e o que ficou em dúvida — e registrar no
   diário do Obsidian (`urace-obsidian`).

## Waiver assinada → tarefa do Asana

**As waivers assinadas sempre chegam em `support@urace.us`.**

Desde 04/09 a IA tem **as duas caixas** conectadas (`urace@` e `support@`),
cada uma com seu próprio consentimento. O aviso antigo de que ela só via a
`support@` por cópia não vale mais.

Ao encontrar uma waiver na triagem:

1. Identificar **de qual piloto** é (nome no PDF/assunto).
2. Achar a tarefa de serviço dele no U-RACE.
3. **Anexar o PDF na tarefa** e marcar a subtarefa `Signed waiver?`.
4. Etiquetar a thread (`Platforms & Subscriptions/Docusign`).
5. Registrar no diário.

O Command Center faz isso sozinho a cada tarefa criada (regra
`waiver_na_tarefa`): procura a waiver do cliente e anexa na tarefa e no
card. Esta skill cobre o que escapar da automação.

A waiver **vale por temporada**. Antes de pedir uma nova, procurar nos
dois lugares: anexos de tarefas anteriores do piloto **e** a caixa
`support@`. Pedir de novo a quem já assinou é atrito à toa com o cliente.

## Compra → quadro Shipping Orders (`1215968721507536`)

E-mail de pedido feito, envio, atualização de status ou entrega alimenta
a tarefa:

| Campo | O que entra |
|---|---|
| nome da tarefa | nome da peça / item comprado |
| `Supplier` `1215973949234112` | de onde comprou |
| `Order Number` `1215973949234125` | número do pedido |
| `Created at` `1215973949234129` | data da compra |
| `Tracking Number` `1215973949234127` | **link** de rastreio que abre |
| `Status da ordem` `1215973949424917` | Order Created → Shipped → Arrived |
| descrição | previsão de entrega |

**Dedupe pelo número do pedido.** E-mail de atualização do mesmo pedido
**atualiza** a tarefa existente — nunca cria outra. Mover a tarefa para o
quadro correspondente ao status (ver `urace-asana`).

## Armadilhas já vistas nesta caixa

- Link de e-mail (`google.com/url?q=…`) **expira** — guardar o destino real.
- URL de notificação com token de sessão (Alibaba) não serve como link
  estável: extrair o número do pedido e montar o link do portal.
- Código de rastreio solto não é link. `1Z…` é UPS →
  `https://www.ups.com/track?track=yes&trackNums=<código>`.
  Transportadora desconhecida → **não inventar**: escalar.
- Remetente frio se passando por assunto sério (ex.: "taxes owed" de
  domínio aleatório) é propaganda/spam, não `ITALO`.
- `Finances/Pending Invoices ❗` é **conta a PAGAR**. Cobrança que a URACE
  emitiu não vai aí — erro já cometido, decisão do dono em 28/08.
