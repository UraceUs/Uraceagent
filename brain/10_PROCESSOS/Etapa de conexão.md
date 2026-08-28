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

### 2. DocuSign
Não existe conector nenhum ainda. Sem ele, a subtarefa da waiver continua
manual. Ver [[DocuSign]].

### 3. Credenciais no VPS (para a IA rodar sozinha, fora desta sessão)
Os conectores desta sessão **não existem no VPS**. Para o agente do
OpenClaw trabalhar sozinho, cada um precisa de credencial própria:
[[Asana]] (Personal Access Token) · [[Gmail]] (as duas caixas) ·
[[Google Calendar]] · [[QuickBooks]].

Guardar sempre como variável de ambiente — **nunca dentro do código**.

---

## 🟡 Cliques do dono (não é credencial, mas só ele pode fazer)

| O quê | Onde | Por quê |
|---|---|---|
| Remover o campo `Order number` do SUITS | Asana → Personalizar → Campos | Enum quebrado; os dados já foram migrados para `Pedido` em 28/08. A API deu `Access denied` |
| Criar as 14 regras de sincronia status ↔ quadro | Asana → Personalizar → Regras | Não existe endpoint de API para criar regra. Ver [[Compra e envio]] |
| Opção "Folga" no campo `Race` (se quiser) | Asana → Personalizar → Campos | A API não cria opção de campo |

---

## 🟢 Depois que os acessos existirem

- Carregar as skills (`skills/`) no agente do OpenClaw no VPS
- Um **perfil/agente por área**, com só as ferramentas da sua área
  (quem cuida do [[Gmail]] não precisa de [[QuickBooks]]) — menor privilégio
- Agendar a rotina diária de [[Triagem de e-mail]] (sugestão: 07h)
- Rodar `asana_status_sync.py` e a higiene das colunas, que estão prontos
  e parados esperando token
