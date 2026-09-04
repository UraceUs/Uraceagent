---
tipo: painel
atualizado_em: 2026-08-31
tipo_info: CONTEXT
fonte: interno
responsavel: Italo Silveira
status: ativo
---

# ⭐ Painel do Cérebro URACE

> Abra [[URACE]] para o mapa completo. Este painel é o **estado de hoje**:
> o que está pendente, o que está decidido, o que está travado.

## ✅ No ar desde 01/09/2026

4 timers rodando no [[VPS e OpenClaw]], 6 skills ligadas, [[Asana]]
testado e respondendo. Ver [[2026-09-01]].

**`APLICAR=0`** — simulação. Nada é escrito em sistema nenhum até você
ler os logs em `~/.urace/logs/` e liberar.

**02/09 — o agente leu o [[Asana]] pela primeira vez.** Servidor MCP
nosso, regras do dono em código, relatório conferido na fonte: Enzo
05/09 com waiver assinada, nenhum alerta. Ver [[2026-09-02]].

**04/09 — [[DocuSign]] em produção.** Go-live aprovado, 50 envelopes
visíveis ao agente. Envio ainda atrás de `APLICAR=0`. Ver [[2026-09-04]].
**[[Gmail]] conectado 04/09** — as duas caixas, sem envio. Falta só
[[QuickBooks]] — lista em [[Etapa de conexão]].

## 🔴 Pendente de clique do dono

Coisas que a IA **não consegue fazer** — só o Italo, na interface.

| O quê | Onde | Por quê |
|---|---|---|
| Corrigir 4 células de preço | [[Rate Card]] (Sheets) | mensal e sessão extra do 4T/Baby Kart. Valor válido já está no cérebro |
| Remover campo `Order number` do SUITS | [[Asana]] | enum quebrado; API deu `Access denied` |
| Criar as 14 regras de status ↔ quadro | [[Asana]] | não existe endpoint de API |
| Criar o marcador `wNews` na caixa `support@` | [[Gmail]] | sem ele a IA não arquiva propaganda lá — e ela não cria marcador por regra |
| Credenciais para o VPS | — | [[Asana]] · [[Gmail]] · [[QuickBooks]] · [[DocuSign]] · Drive |

## ⏳ Decisões que faltam

- **`sendReminder` do [[DocuSign]]**: a IA pode cutucar quem recebeu a
  waiver e não assinou? Hoje ela alerta o dono, não o cliente.

## 🚦 O que a IA já faz sozinha

| Área | Pode |
|---|---|
| [[QuickBooks]] | criar invoice, estimate, cliente e item de catálogo · **não envia** |
| [[DocuSign]] | ler status, varredura diária, **enviar waiver** (4 travas), marcar subtarefa |
| [[Asana]] | ler tudo, criar e mover tarefa, comentar · **não sobe anexo** (falta token) |
| [[Gmail]] | triar e rascunhar · **não envia**, salvo as exceções de [[PARAMETROS]] |

## 🔧 Problemas abertos

Nove, em [[Problemas]]. Os de maior risco:
[[P-04 - Contas a receber concentradas]] ·
[[P-07 - Waivers paradas desde junho]] ·
[[P-05 - Security deposit quase nao aparece]]

## ⚠️ Números que a operação precisa olhar

- **US$ 185.887 a receber**, 84% em duas invoices de 2025 (Juan Pacino
  $101.445 · Stephen Collins $55.070). Ver [[QuickBooks]].
- **3 waivers paradas desde junho** — Matthew Hubbard, Leticia
  Bittencourt, Austin. Ver [[DocuSign]] e [[2026-08-31]].
- Invoice em aberto **≠ inadimplência**: existe parcelamento
  ([[Leandro Cesar]]).

## 🧠 As armadilhas que mais custaram

1. **O cliente do [[QuickBooks]] é o responsável, não o piloto.** Vale
   também para quem assina a [[Waiver]].
2. **A busca do [[Asana]] atrasa** — conferir por leitura direta.
3. **`delivered` no [[DocuSign]] não é assinado.** Só `completed` conta.
4. **O preço não sai do catálogo do QBO** — sai da [[Rate Card]].
5. **Pacote se calcula do mensal**, nunca multiplicando a unitária.

## 🧠 Para a IA se orientar

| Antes de agir | Nota |
|---|---|
| Que peso tem essa informação? | [[Tipos de informação]] |
| Chegou coisa nova, e agora? | [[Protocolo de aprendizado]] |
| **O que eu não sei?** | [[Conflitos e lacunas]] |
| Devo chamar humano? | [[Escalonamento]] |

Índices: [[Empresa]] · [[Projetos]] · [[Decisoes]] · [[Processos]] ·
[[Problemas]] · [[Sistemas]] · [[Clientes]] · [[Equipe]]

## Como este vault funciona

Estrutura, convenções e ciclo do conhecimento:
[[README|Como o cérebro funciona]].

O que saiu de uso (o agente de vendas Chase) está em `90_ARQUIVO/`, e
fica lá como registro — não como referência.
