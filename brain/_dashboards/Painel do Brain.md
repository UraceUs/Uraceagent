---
tipo: painel
atualizado_em: 2026-09-17
tipo_info: CONTEXT
fonte: interno
responsavel: Italo Silveira
status: ativo
---

# ⭐ Painel do Cérebro URACE

> Abra [[URACE]] para o mapa completo. Este painel é o **estado de hoje**:
> o que está no ar, o que falta, o que está travado.
> **Fotografia inteira do projeto:**
> [[Administrative AI - Estado completo em 2026-09-17]].
> **Manual de uso do painel** (humanos e IA): `docs/manual-do-command-center.md`.

## 🟢 O projeto está rodando

`https://urace-bridge.duckdns.org/ops/` — [[Command Center]] no ar desde 04/09, com
login próprio, papéis, auditoria imutável e o espelho das **cinco** fontes.

| Fonte | Estado | Desde |
|---|---|---|
| [[Asana]] | MCP próprio; ADM URACE e Matt tasks só leitura | 02/09 |
| [[DocuSign]] | produção; envia waiver com aprovação | 04/09 |
| [[Gmail]] | as duas caixas, sem envio livre | 04/09 |
| [[QuickBooks]] | **produção liberada** (P-11 resolvido); invoice só após aprovação | 09/09 |
| [[Kommo]] | chat do lead dentro do painel | 16–17/09 |

**17/09 — três coisas novas:** a **área de vendas** (oportunidade não é cliente;
fechar venda em uma tela dispara cliente, QuickBooks, waiver, Asana e Kommo), a
**voz** em todo campo de texto, e o **login novo** com a foto da pista. Mais o botão
**Atualizar agora**, que faz o deploy sem terminal. Ver [[2026-09-17]].

**Papéis:** Administrador · Gerente · Operador · Leitura, e a conta de **acesso livre**
(sem cargo, alcança tudo). Não existe papel "vendas": quem vende é Operador.

## 📊 O Pit Wall

O Pit Wall (`/painel/`) está pronto mas **não publicado** — hoje responde 404. O
Command Center (`/ops/`) cobre o que ele mostrava. Decisão pendente: publicar ou
aposentar. Ver [[VPS e OpenClaw]].

## ⚙️ Como a IA escreve

O agente no [[VPS e OpenClaw]] roda em **simulação** (`APLICAR=0`): ele propõe. Quem
executa o que foi aprovado é o **painel**, e o APLICAR liga só naquele clique. Nada
apaga, waiver e invoice exigem aprovação, e tudo fica em `audit_logs`.

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
