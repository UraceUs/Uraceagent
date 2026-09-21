---
tipo: decisao
data: 2026-09-09
fonte: dono (chat)
tipo_info: DECISION
responsavel: Italo Silveira
status: ativo
---

# D-2026-09-09 — Design para cognição rápida: cada link no seu item, nada jogado ao vento

**Dono, 09/09/2026:** o card do cliente tinha uma fila de "asana ↗" no
topo (um por tarefa ligada) e o e-mail aparecia como
`email%3apablosantiago@outlook.com , bryanlsantiago@outlook.com`. Pedido:
*"cada link na frente do seu respectivo serviço, na linha do tempo, e
não lá em cima"*; *"atue como um designer renomado de plataformas; somos
do automobilismo; tudo muito intuitivo, rápido, para cognição rápida —
pilotos e donos de equipe vão usar"*; *"não só no card, no sistema como
um todo; não ter links jogados ao vento; informação a mais preenchida
possível"*.

**Regras que valem para o sistema inteiro a partir de hoje:**
1. **Um link vive ao lado do item que ele abre.** Tarefa → "Asana ↗" na
   linha da tarefa; envelope → "DocuSign ↗"; thread → "Gmail ↗"; invoice
   → "QuickBooks ↗". Nunca uma fila de links no cabeçalho. Componente
   `SysLink` (nome do sistema, cor discreta do sistema).
2. **Cabeçalho responde "quem é" em um olhar:** nome do piloto grande,
   status com ponto, plano, VIP, ★ Pro; abaixo, responsável, idade
   (menor = waiver parental), e-mail e telefone clicáveis. Ações: uma
   primária (Perguntar à IA), Tornar Pro, Editar, e o resto no "⋯".
3. **Faixa de cinco números** antes de qualquer tabela: próximo serviço,
   último serviço, waiver, serviços abertos/total, valor em aberto no
   QBO (gerente) — cada um com o link do seu item.
4. **Linha do tempo agrupada por mês**, tipo colorido, título, status,
   detalhe (coluna, subtarefas feitas, quem assinou, saldo) e o link do
   item à direita. Invoices entram na linha do tempo para gerente.
5. **Dado limpo na origem:** e-mail da descrição do Asana passa por
   `normaliza_email` (tira `mailto:`/`email:` codificados, separa
   principal e alternativo); telefone legível (`305-609-7845`). A régua
   passa nos cards já espelhados a cada sincronia (`limpar_contatos`).
6. "Dados completos" viram um bloco dobrável — o que importa já está
   acima.

Relacionado: [[D-2026-09-04 - O que e cliente, ativo, e um card por pessoa]], [[Preferencias do dono]].
