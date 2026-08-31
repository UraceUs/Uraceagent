---
tipo: hub
tipo_info: CONTEXT
data: 2026-08-31
fonte: interno
responsavel: Italo Silveira
status: ativo
---

# 🏁 URACE — Cérebro Central

Memória de longo prazo da operação da [[URACE US INC]]. É daqui que a IA
parte para qualquer coisa, e é aqui que ela devolve o que aprendeu.

> ⚙️ **[[PARAMETROS]] é o único lugar onde se altera** valor, prazo,
> fornecedor ou ID. Mudou lá, mudou no sistema inteiro.

> 📖 Primeira vez aqui? [[COMECE AQUI]].

## 🧠 Como a IA pensa — leia antes de tudo

| Nota | Para quê |
|---|---|
| [[Tipos de informação]] | **FACT · DECISION · RULE · PROCESS · PREFERENCE · CONTEXT · OPEN_QUESTION · UNKNOWN.** Impede contexto virar regra |
| [[Protocolo de aprendizado]] | o que fazer quando chega informação nova |
| [[Conflitos e lacunas]] | **o que a IA não sabe** e o que ela sabe de dois jeitos |
| [[Escalonamento]] | quando parar e chamar humano — e para quem |
| [[Como o cérebro cresce]] | **a forma do grafo** — hubs, satélites e pontes. Como escrever nota nova |

## 🗺️ O mapa

| Pasta | O que guarda | Índice |
|---|---|---|
| `00_SYSTEM` | como a IA se comporta | [[PARAMETROS]] |
| `01_EMPRESA` | quem é a URACE e suas políticas | [[Empresa]] |
| `04_PROJETOS` | o que está sendo construído | [[Projetos]] |
| `08_DECISOES` | o que foi decidido, e por quê | [[Decisoes]] |
| `10_PROCESSOS` | **como o trabalho é feito** | [[Processos]] |
| `13_PROBLEMAS` | o que está quebrado ou arriscado | [[Problemas]] |
| `20_ENTIDADES` | quem e o quê | [[Clientes]] · [[Equipe]] |
| `30_DIARIO` | o que aconteceu, dia a dia | [[2026-08-31]] |
| `40_SISTEMAS` | as ferramentas e suas armadilhas | [[Sistemas]] |
| `90_ARQUIVO` | fora de uso (era Chase) | — |

## 🧭 Atalhos

**Sistemas** — [[Asana]] · [[Gmail]] · [[QuickBooks]] · [[Rate Card]] ·
[[DocuSign]] · [[Google Calendar]] · [[Taxonomia do Gmail]]

**Processos** — [[Invoice e estimate no QuickBooks]] ·
[[Waiver de responsabilidade]] · [[Pedido de macacão]] ·
[[Pagamento e security deposit]] · [[Compra e envio]] ·
[[Triagem de e-mail]] · [[Stand-by e escalação]] · [[Etapa de conexão]]

**Entidades** — 👥 [[Equipe]] · 🧑 [[Clientes]] · 🏭 [[Fornecedores]] ·
🏁 [[Corridas]] · 🎓 [[Serviços]] · 📍 [[Locais]] · 📄 [[Waiver]] ·
💵 [[Security deposit]]

**Estado de hoje** — [[Painel do Brain]]

## 🚦 O que a IA pode mandar para fora

A regra geral é **não enviar**. As exceções são quatro, e só elas —
lista completa com datas em [[PARAMETROS]]:

| ✅ Envia sozinha | 🚫 Nunca envia sozinha |
|---|---|
| Invoice do [[Security deposit]] | Invoice de serviço e qualquer outra |
| **Waiver do [[DocuSign]]** (com 4 travas) | Lembrete de assinatura |
| Formulário de medidas ao cliente do macacão | Resposta de inbox — só rascunho |
| Pedido de produção ao fornecedor | |

## As regras que nunca mudam

1. **A IA cria e salva; quem envia é humano** — salvo as 4 exceções.
2. **Se não souber, NÃO INVENTA.** Marca `UNKNOWN` e escala —
   [[Escalonamento]].
3. **Não apaga, não destrói, não regenera credencial.** Nada de
   credencial no cérebro, em nota nenhuma.
4. **Não escolhe lado em conflito** — registra os dois e marca
   `needs_human_confirmation`.
5. Confere por **leitura direta**, nunca pela busca (a do [[Asana]] atrasa).
6. **Chave externa é identidade**, nunca o nome — `asana_gid`, id do
   [[QuickBooks]], `envelopeId` do [[DocuSign]].
7. **O cliente do [[QuickBooks]] é o responsável, não o piloto.** Vale
   igual para quem assina a [[Waiver]].
8. **Registra o que fez** — comentário na tarefa e linha no diário.
9. **Perguntar não trava nada** — pergunta, põe em stand-by, segue com o
   resto. Mas **volta a alertar quando o prazo chega**.

## Fora do vault

| O quê | Onde |
|---|---|
| Skills da IA (uma por aplicação) | `skills/` no repositório |
| Preço oficial | [[Rate Card]] (Google Sheets) |
| Como abrir isto no Obsidian | `docs/obsidian-guia.md` |
| Como o cérebro funciona por dentro | [[README\|Como o cérebro funciona]] |
