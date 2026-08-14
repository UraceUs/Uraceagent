# Consolidação das fontes — Sales Agent URace

> Fase 1 (Discovery) da implementação do Sales Agent no OpenClaw.
> Data: 2026-08-14. O Benchmark (URACE_COMMERCIAL_BENCHMARK.md) foi **excluído por decisão do Italo**.

## Fontes e hierarquia adotada

| # | Fonte | Data | Papel |
|---|---|---|---|
| 1 | Repositório Uraceagent (prompts, modos, cenários, portões) | 10/08 | Comportamento do agente e arquitetura de segurança |
| 2 | POP_Comercial_URACE_v3 | 03/08 | Processo comercial (etapas, prazos, funil, follow-up) |
| 3 | URace_Handbook (parte comercial) | 30/07 | Função, rotinas e interfaces entre áreas |
| 4 | URACE_Modo_Operante_AI_Sales_Agent | 28/07 | Método de conversa, scripts, objeções |
| 5 | Commercial Operating System v4.0 | 25/07 | Autoridade (Rate Card/ADM/Italo), políticas de desconto, CRM, QA |

**Hierarquia de autoridade operacional** (do COS v4.0, mantida): 1º Rate Card vigente (preço) → 2º contrato assinado (termos) → 3º ADM (disponibilidade, horários, links de pagamento/pista) → 4º Italo Silveira (Racing Team, programas fora do padrão, exceções comerciais).

Extrações integrais: `salesagent/discovery/`.

## ⚠️ CONFLITOS ENTRE FONTES — exigem decisão do Italo

Estes pontos divergem entre documentos e **não foram resolvidos por conta própria**:

### C1. Portão de preço — o mais importante
- **POP v3:** qualificação completa (7 itens) antes de qualquer valor.
- **Modo Operante:** 2 perguntas obrigatórias (experiência + origem) antes do preço.
- **COS v4.0 §21:** "Do not hide price when the lead asks directly" — responder o starting point e seguir qualificando.
- **DECISÃO (Italo, 14/08): as 2 perguntas** (experiência + origem) são o portão de código. Lead que pede preço direto ouve as 2 perguntas antes do valor.

### C2. SLA de primeira resposta
- POP v3: 10 minutos. Handbook: 30 minutos. COS: sem número.
- Para um agente automático o SLA real será segundos; a decisão importa para o **alerta de escalação** (quando humano precisa assumir e não responde).
- **DECISÃO (Italo, 14/08):** alarme de escalação com re-alerta em **10–30 min**, ativo apenas em **horário comercial 9h–18h, fuso de Orlando (America/New_York)**. Fora do horário, a escalação fica enfileirada e alarma às 9h.

### C3. Funil do Kommo
- POP v3: 14 estágios em PT (1 Contato … Ganho/Perdido). COS v4.0: 10 estágios em EN (New Lead … Future Opportunity).
- **DECISÃO (Italo, 14/08):** seguir o pipeline real da conta, de nome **"sales funnel"** — a ser lido via API do Kommo na Fase 3 (o acesso à API será feito a partir do VPS; a rede desta sessão de desenvolvimento bloqueia kommo.com). Os estágios lidos da conta substituem as listas do POP e do COS.

### C4. "Produto único" × produtos distintos
- Handbook (30/07): "produto único de treinamento personalizado; nomes antigos como camps/programs abandonados".
- POP v3 (03/08, mais novo) e COS: vendem 1-Day, Camp, Academy, Racing Team como ofertas distintas.
- **DECISÃO (Italo, 14/08): usar o POP** — ofertas comerciais distintas (1-Day, Camp, Academy; Racing Team via escalação). A comunicação continua explicando o treinamento como personalizado, sem despejar cardápio.

### C5. Cancelamento/reagendamento <48h
- POP v3: taxa fixa de $95. COS v4.0: análise individual caso a caso.
- **DECISÃO (Italo, 14/08):** taxa fixa de **$95 como regra padrão**, comunicada pelo agente; se o cliente apresentar condições/justificativa, o caso **escala para o humano** analisar — o agente nunca dispensa a taxa sozinho.

### C6. Descontos
- POP v3: silente. Modo Operante: negociação → dono. COS §18: lista fechada (2º filho 10%; contrato 6m 4%; 12m 8%; L&F 5-pack 10%) + resto escala Italo.
- **DECISÃO (Italo, 14/08): sem descontos, ponto.** Preços fixos conforme a tabela (Rate Card). Qualquer desconto — inclusive os que o COS listava — só com **aprovação humana explícita** via escalação. O agente nunca menciona desconto por iniciativa própria.

### C7. Elegibilidade por idade
- Só o POP define faixas, e só para Summer Camp (Baby Kart 4–7; 4t 7+; 2t 7+). Nenhuma fonte define idade mínima para 1-Day/Academy.
- **DECISÃO (Italo, 14/08): mesma regra de idade para todos os serviços** — as faixas por categoria valem universalmente (1-Day, Academy, Camp): **Baby Kart 4–7 anos; Kart 4 tempos 7+; Kart 2 tempos 7+**. Portão de código: idade < 4 = inelegível; 4–6 = só Baby Kart; 7+ = 4t/2t conforme experiência.

## Lacunas confirmadas em todas as fontes

1. **Rate Card** — citado como fonte única de preço por todas as fontes, mas o documento em si não foi localizado no Drive com esse nome. Onde vive e como o agente consulta?
2. **Links do check-in da pista** (mensagem literal permitida) — não constam em nenhum doc; obter com ADM.
3. **Playbook Comercial v3** (scripts) — linkado no POP; complementa mas não foi extraído nesta fase.
4. Política de crédito/validade para cancelamento ≥48h ("a definir" no próprio POP).

## Classificação do conteúdo (destino de cada tipo)

| Tipo | Destino | Exemplos |
|---|---|---|
| Instruções de comportamento | Prompt do agente | 1 pergunta por vez; 1–3 linhas; espelhar idioma; "drivers"; responder e parar |
| Conhecimento comercial | Knowledge files (consulta) | Programas e posicionamento; segmentação de perfis; objeções e scripts; interfaces entre áreas |
| Políticas | Prompt (resumo) + código (enforcement) | Descontos; segurança (nunca negar risco); reviews; não-promessas |
| Regras invioláveis | **Código na ponte** (ver rules-to-code.md) | Portão de preço; roteamento competidor→Italo; estado de escalação; sem desconto |
| Dados voláteis | Config/DB, nunca prompt | Rate Card, preços, links de pagamento/pista, horários, disponibilidade |
| Scripts literais permitidos | Templates em config | Check-in da pista (único texto canned autorizado) |
