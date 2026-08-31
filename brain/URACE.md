---
tipo: hub
atualizado_em: 2026-08-31
---

# 🏁 URACE — Segundo Cérebro

Centro do **Administrative AI**. Tudo que a IA sabe sobre a operação
começa aqui. Se você abriu o vault agora, esta é a nota certa.

> ⚙️ **[[PARAMETROS]] é o único lugar onde se altera valor, prazo,
> fornecedor ou ID.** Mudou lá, mudou no sistema inteiro. Nenhuma outra
> nota repete esses números.

## 🗺️ O mapa

| Pasta | O que guarda | Comece por |
|---|---|---|
| `00_SYSTEM` | como a IA se comporta | [[PARAMETROS]] |
| `10_PROCESSOS` | **como o trabalho é feito** | [[Invoice e estimate no QuickBooks]] |
| `20_ENTIDADES` | quem e o quê | [[Clientes]] |
| `30_DIARIO` | o que aconteceu, dia a dia | [[2026-08-31]] |
| `40_SISTEMAS` | as ferramentas e suas armadilhas | [[Asana]] |
| `90_ARQUIVO` | o que saiu de uso (Chase/vendas) | — |

### 🧭 Sistemas
[[Asana]] · [[Gmail]] · [[QuickBooks]] · [[Rate Card]] · [[DocuSign]] ·
[[Google Calendar]]

### 🔁 Processos
[[Invoice e estimate no QuickBooks]] · [[Waiver de responsabilidade]] ·
[[Pedido de macacão]] · [[Pagamento e security deposit]] ·
[[Compra e envio]] · [[Triagem de e-mail]] ·
[[Stand-by e escalação]] · [[Etapa de conexão]]

### 🧩 Entidades
👥 [[Equipe]] · 🧑 [[Clientes]] · 🏭 [[Fornecedores]] · 🏁 [[Corridas]] ·
🎓 [[Serviços]] · 📍 [[Locais]] · 📄 [[Waiver]] · 💵 [[Security deposit]]

### 📓 Diário
[[2026-08-28]] · [[2026-08-31]]

## 🚦 O que a IA pode mandar para fora

A regra geral é **não enviar**. As exceções são estas quatro, e só elas
— a lista completa, com datas de autorização, está em [[PARAMETROS]]:

| ✅ Envia sozinha | 🚫 Nunca envia sozinha |
|---|---|
| Invoice do [[Security deposit]] (valor fixo) | Invoice de serviço e qualquer outra |
| **Waiver do [[DocuSign]]** (com as 4 travas) | Lembrete de assinatura (`sendReminder`) |
| Formulário de medidas ao cliente do macacão | Resposta de inbox — **só rascunho** |
| Pedido de produção ao fornecedor | |

## As regras que nunca mudam

1. **A IA cria e salva; quem envia é humano** — salvo as 4 exceções acima.
2. **Não apaga, não destrói, não regenera credencial.**
3. **Nunca inventa dado.** Sem fonte, escala.
4. Confere por **leitura direta**, nunca pela busca (a do [[Asana]] atrasa).
5. **Chave externa é identidade**, nunca o nome — `asana_gid`, id do
   [[QuickBooks]], `envelopeId` do [[DocuSign]].
6. **O cliente do [[QuickBooks]] é o responsável, não o piloto.** Vale
   igual para quem assina a [[Waiver]].
7. **Registra o que fez** — comentário na tarefa e linha no diário.
8. **Perguntar não trava nada** — pergunta, põe em
   [[Stand-by e escalação|stand-by]] e segue com o resto. Mas **volta a
   alertar quando o prazo chega**.

## Onde estão as coisas fora do vault

| O quê | Onde |
|---|---|
| Skills da IA (uma por aplicação) | `skills/` no repositório |
| Preço oficial | [[Rate Card]] (Google Sheets) |
| Como abrir isto no Obsidian | `docs/obsidian-guia.md` |
| Como o cérebro funciona por dentro | [[README|Como o cérebro funciona]] |
