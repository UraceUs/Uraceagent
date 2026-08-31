---
tipo: checklist
area: transversal
status: aguardando o dono abrir a etapa
atualizado_em: 2026-08-28
---

# 🔌 Etapa de conexão — o que precisa de credencial ou de clique do dono

[[URACE]] · Decisão do dono (28/08): **primeiro a especificação completa
de cada plataforma; credenciais e chaves só no final.** Esta lista existe
para nada se perder até lá. **Não abrir este assunto sem o dono pedir.**

---

## 🔴 Acessos que faltam

### 1. Caixa `support@urace.us` — pedido do dono (28/08)
**A IA precisa das duas caixas.** Hoje ela só tem a `urace@urace.us`.

Testado e comprovado em 28/08:
- `deliveredto:support@ -deliveredto:urace@` → **vazio**
- `to:support@` → 201 resultados, quase todos `SENT` (enviados *pela* urace@)

Ou seja: a IA só enxerga a support@ quando a urace@ está em cópia.

**Por que trava trabalho de verdade:** as **waivers assinadas chegam só na
support@** ([[DocuSign]]). Sem essa caixa, o fluxo "waiver chega → anexa na
tarefa → marca a subtarefa" **não funciona**. Busca feita em 28/08 na caixa
disponível não achou nenhuma waiver de cliente.

Dois caminhos:
- **a)** conectar `support@` como conector próprio; ou
- **b)** acesso delegado da support@ para a urace@ no Google Workspace
  (Configurações → Contas → Conceder acesso à sua conta) — aí a mesma
  conexão passa a ler as duas.

### 2. ✅ DocuSign — RESOLVIDO em 31/08
Conector instalado e sondado. **E a conta é a `support@urace.us`.**

Isso muda o item 1 acima: o fluxo "waiver assinada → anexa na tarefa →
marca a subtarefa" **não depende mais da caixa de e-mail** — a IA lê o
status direto na DocuSign, que é a fonte de verdade da assinatura.

A caixa `support@` continua fazendo falta para **o resto** (triagem,
outros e-mails que só chegam lá), mas **deixou de ser bloqueio da
waiver**. Ver [[DocuSign]] e [[Waiver]].

Falta credencial própria para o VPS (integration key + JWT) — item 3.

### 3. Credenciais no VPS (para a IA rodar sozinha, fora desta sessão)
Os conectores desta sessão **não existem no VPS**. Para o agente do
OpenClaw trabalhar sozinho, cada um precisa de credencial própria:
[[Asana]] (Personal Access Token) · [[Gmail]] (as duas caixas) ·
[[Google Calendar]] · [[QuickBooks]] · [[DocuSign]] (integration key +
JWT) · Google Drive (a [[Rate Card]]).

Guardar sempre como variável de ambiente — **nunca dentro do código**.

⚠️ **O token do [[Asana]] não é só "para o VPS".** O conector desta
sessão **não sobe arquivo** — tem `get_attachments` (ler) e nenhuma
ferramenta de escrita de anexo (verificado em 31/08). Anexar a waiver
assinada na tarefa da criança ([[Waiver de responsabilidade]]) depende do
PAT + REST `POST /attachments`. Enquanto isso a IA marca a subtarefa e
comenta com o link — o arquivo é que não sobe.

---

## 🟡 Cliques do dono (não é credencial, mas só ele pode fazer)

| O quê | Onde | Por quê |
|---|---|---|
| Remover o campo `Order number` do SUITS | Asana → Personalizar → Campos | Enum quebrado; os dados já foram migrados para `Pedido` em 28/08. A API deu `Access denied` |
| Criar as 14 regras de sincronia status ↔ quadro | Asana → Personalizar → Regras | Não existe endpoint de API para criar regra. Ver [[Compra e envio]] |
| Opção "Folga" no campo `Race` (se quiser) | Asana → Personalizar → Campos | A API não cria opção de campo |
| Corrigir as 4 células da [[Rate Card]] | Google Sheets | Mensal e sessão extra do 4T/Baby Kart. Ver [[Rate Card]] |

---

## 🟢 Depois que os acessos existirem

- Carregar as skills (`skills/`) no agente do OpenClaw no VPS
- Um **perfil/agente por área**, com só as ferramentas da sua área
  (quem cuida do [[Gmail]] não precisa de [[QuickBooks]]) — menor privilégio
- Agendar a rotina diária de [[Triagem de e-mail]] (sugestão: 07h)
- Rodar `asana_status_sync.py` e a higiene das colunas, que estão prontos
  e parados esperando token
