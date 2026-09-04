# Roadmap das 4 plataformas — MIGRADO

Este documento foi **migrado para o segundo cérebro** em 31/08/2026, na
construção do Cérebro Central. O conteúdo vive agora em:

- `brain/04_PROJETOS/Administrative AI.md` — o estado por aplicação, atualizado

⚠️ O conteúdo original está **desatualizado**: dizia que o QuickBooks
tinha "regra de negócio VAZIA" e o DocuSign estava "praticamente vazio".
Os dois foram especificados em 31/08.

O arquivo original fica aqui como registro do que foi levantado na
época. **A fonte de verdade é o vault** — se divergir, o vault vence.

---

<details>
<summary>Conteúdo original (28/08/2026)</summary>

# Roadmap das 4 plataformas — o que já temos e o que falta

Sequência definida pelo dono (28/08): **primeiro a especificação completa
de cada plataforma; credenciais e chaves só no final.** Não levantar o
assunto de token/conexão até o dono abrir.

## 1. Asana — ~90% especificado ✅

**Tenho:** os 4 projetos com IDs, seções e campos · colunas do U-RACE e
quem manda em cada uma · modelo de serviço com as 12 subtarefas
explicadas uma a uma · cronograma de corrida (chegada 2 dias antes) ·
campo `Race` obrigatório · marcadores de dia sem treino · SUITS com os 10
status e o checklist do macacão · Shipping Orders com os 7 status e a
sincronia status×quadro · ADM URACE somente leitura · dados sensíveis ·
autonomia para corrigir erro rastreado.

**Falta:** a **rotina operacional do SUITS** — a estrutura está mapeada
(status, fornecedor, checklist), mas não como o dia a dia funciona: o que
dispara o pedido, quem fala com o Usman, quando muda cada status, o que a
IA pode tocar ali.

## 2. E-mail — 100% especificado ✅

Fechado em 28/08: duas caixas, taxonomia de 130+ marcadores, arquivar só
propaganda, `Pending Invoices` = contas a pagar, rascunho só para
lead/orçamento e cliente atual, alimentação do Shipping Orders e do
calendário. Ver `app-gmail-triagem.md`.

## 3. QuickBooks — só sondado, regra de negócio VAZIA ⚠️

**Tenho (de sonda, não de regra):** 94 clientes ativos · US$ 478 mil YTD ·
catálogo de 896 itens (360 serviços, 536 peças) · as amarras já ditas
pelo dono: **a IA não envia invoice**, security deposit US$ 400, conferir
no QB antes de enviar depósito, devolver em 5 dias o depósito menos as
peças, pelo *merchant view*.

**Falta praticamente tudo do "como":**
- Como montar uma invoice: qual item do catálogo para cada serviço?
- `Pre race invoice` × `After race invoice`: o que entra em cada uma?
- Quem revisa antes do humano enviar? Onde a IA deixa a invoice pronta?
- Como a IA sabe que foi pago — só a notificação do e-mail, ou consulta?
- Reembolso do depósito: passo a passo real no *merchant view*.
- Peças usadas (Service Order do mecânico) → invoice: como precifica?

## 4. DocuSign — praticamente vazio ⚠️

**Tenho:** existe e já é usado (marcador `Platforms &
Subscriptions/Docusign`, 54 threads) · são **2 modelos** (responsável de
menor / *adult*) · a idade decide qual · assinado volta por e-mail → a IA
marca a subtarefa e **anexa o PDF na tarefa do Asana**.

**Falta:**
- Quais são os dois templates (nome/ID) e o que cada um pede.
- O que dispara o envio: serviço agendado? pagamento? confirmação?
- Quem assina além do responsável — alguém da URACE contrassina?
- Onde o PDF assinado deve ficar além do Asana (Drive? vault?).
- Waiver vale por temporada ou por sessão? (muda tudo: se vale por
  temporada, a IA precisa checar se já existe um assinado antes de pedir
  outro — mesma lógica do "conferir o depósito no QuickBooks antes").

</details>
