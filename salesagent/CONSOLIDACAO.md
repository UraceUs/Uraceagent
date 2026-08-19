# Consolidação das fontes — Sales Agent URace

> Fase 1 (Discovery) da implementação do Sales Agent no OpenClaw.
> Data: 2026-08-14, atualizado em 2026-08-17. O Benchmark
> (URACE_COMMERCIAL_BENCHMARK.md) foi **excluído por decisão do Italo**.

## Fontes e hierarquia adotada

| # | Fonte | Data | Papel |
|---|---|---|---|
| 1 | Repositório Uraceagent (prompts, modos, cenários, portões) | 10/08 | Comportamento do agente e arquitetura de segurança |
| 2 | POP_Comercial_URACE_v3 | 03/08 | Processo comercial (etapas, prazos, funil, follow-up) |
| 3 | URace_Handbook (parte comercial) | 30/07 | Função, rotinas e interfaces entre áreas |
| 4 | URACE_Modo_Operante_AI_Sales_Agent | 28/07 | Método de conversa, scripts, objeções |
| 5 | Commercial Operating System v4.0 | 25/07 | Autoridade (Rate Card/ADM/Italo), políticas de desconto, CRM, QA |
| 6 | Italo AI Voice Training Manual | 17/08 | Voz e tom do agente em todos os contextos — **fonte primária de estilo de escrita** |
| 7 | "URACE Automated Lead Qualification System" (documento "Chase", colado por Italo no chat) | 17/08 | Comportamento operacional do agente de vendas — **fonte de maior autoridade** para fluxo de conversa, classificação do lead, script de desvio de preço, cadência de follow-up e regras de escalação, por ser mais recente, mais detalhada, e ter sido revisada por Italo linha a linha antes de gerada |

**Hierarquia de autoridade operacional** (do COS v4.0, mantida): 1º Rate Card vigente (preço) → 2º contrato assinado (termos) → 3º ADM (disponibilidade, horários, links de pagamento/pista) → 4º Italo Silveira (Racing Team, programas fora do padrão, exceções comerciais).

**Hierarquia de comportamento do agente (nova, 17/08):** para *como o agente conversa* (identidade, script, follow-up, escalação), as fontes 6 e 7 têm precedência sobre 2/3/4 quando houver conflito — são mais recentes e foram desenhadas especificamente para automação por IA, não para atendimento humano. Para *política comercial* (preço, depósito, cancelamento, elegibilidade), a hierarquia original (POP/COS/Rate Card) continua valendo — as fontes 6/7 não tratam desses números.

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

### C1 — nota de refinamento (17/08)
O documento "Chase" pede a classificação A/B/C/D como **primeira pergunta**
(substitui a pergunta livre de "experiência"), e a pergunta de origem
(local/traveler) deixa de ser sempre-obrigatória-antes-do-preço: ela só aparece
depois, dentro do sub-fluxo de qualificação da Academy, para checar
disponibilidade de viagem de quem é de fora. **A decisão original do C1
continua valendo em espírito** (nunca cotar preço sem qualificar antes) — o
que muda é o mecanismo: agora é o menu A/B/C/D + a regra "nunca falar preço em
chat, sempre linkar a página" (seção 8 do documento Chase), que é uma barreira
ainda mais forte que abrir/fechar um número. Ver instruções atualizadas.

### C8. Identidade do agente — anônimo × nomeado e transparente
- **Modo Operante (28/07):** "Prefira 'this is URace' a assinar um nome individual" — agente sem nome próprio, para não confundir quando outro atendente responde.
- **Documento Chase (17/08, mais recente):** agente nomeado, que se apresenta como IA de forma transparente: "Hi [NAME], I'm [nome] 🤖, URACE's AI assistant."
- **DECISÃO (Italo, 17/08): o nome é "Chase".** Adotado o modelo de transparência do documento — o agente se apresenta como assistente de IA da URace, não como atendente anônimo. Esta decisão **substitui** a regra 9 original das instruções (que dizia o oposto).

### C9. Estágios do funil — conceituais (documento Chase) × reais (conta Kommo)
- O documento Chase lista 14 estágios conceituais (New Inquiry → ... → Closed).
- A API real do Kommo (lida em 14/08) tem 20 estágios no pipeline "Sales funnel" (ver `salesagent/config/kommo-pipeline.json`), com nomes bem diferentes.
- **Reconciliação proposta (não é decisão unilateral — pendente confirmação):** o agente move o lead pelos **estágios reais** do Kommo (a fonte de verdade, por decisão C3), e registra os **conceitos** do documento Chase (price-aware, qualified, checkout sent etc.) como **tags**, já que o funil real não tem uma etapa por conceito. Se Italo preferir reconfigurar o funil real do Kommo para bater com os nomes do documento, é só avisar — a ponte lê os estágios direto da API, então uma mudança lá se reflete automaticamente.
- **PENDENTE: confirmação do Italo.**

### C10. Links de programa — ainda não fornecidos
- O documento Chase referencia `[1-DAY PROGRAM LINK]`, `[ACADEMY LINK]`, `[TRAINING CAMP LINK]`, `[CHECKOUT LINK]`, `[PROGRAM LINK]` — nenhuma URL real foi passada ainda.
- Sem elas, a regra "nunca falar preço no chat, sempre mandar a página" fica incompleta — o agente vai dizer que vai confirmar em vez de mandar o link.
- Placeholders registrados em `salesagent/config/program-links.json`.
- **PENDENTE: Italo fornecer as URLs reais** (páginas do site com fotos, vídeos, descrição e preço de cada programa, e o link de checkout do 1-Day).

### C11. Cadência de follow-up — POP × documento Chase
- **POP v3:** mínimo 4 tentativas, intervalo progressivo D0→D+1→+3d→+1 semana, um único fluxo para todo lead.
- **Documento Chase (mais novo, desenhado para automação):** três trilhas distintas conforme o estado da conversa — (a) sem resposta à mensagem inicial: 2h/24h/3d/7d, fecha ao fim; (b) link de programa enviado sem resposta: 10min/24h/3d/7d; (c) cliente pediu para retornar em data específica: tarefa persistente na data pedida, cancelada se ele responder antes.
- **Adotado por padrão o modelo do documento Chase** (mais granular e específico para automação) — é refinamento operacional dentro do espírito já decidido em C1/C2, não inversão de política crítica. Sinalizando aqui para visibilidade; avise se preferir manter a cadência única do POP.

## Lacunas — status (atualizado 17/08)

1. **Rate Card** ✅ — planilha Google Sheets `160efDlmavKKGbtGfJKCTOV_3Q9JEO3Lc6xA1mEMMNyo` ("Rate Card 2026"). Snapshot estruturado em `salesagent/config/ratecard-2026.json`. Pontos a confirmar com o Italo: (a) valores dos contratos 6/12 meses (células "detailed below" da planilha); (b) Baby Kart Rental avulso diz idade 5–8, demais tabelas dizem 4–7.
2. **Links do check-in** ✅ — template literal em `salesagent/config/checkin-template.md`. Pendente: confirmar o link do formulário de registro (formato atípico) e se o link de driver pass vale para todos os dias.
3. **Plano Kommo** ✅ — **Advanced** (confirma o caminho Salesbot + widget_request).
4. **Playbook Comercial v3** (scripts) — linkado no POP; complementa mas não foi extraído nesta fase.
5. Política de crédito/validade para cancelamento ≥48h ("a definir" no próprio POP).

## Classificação do conteúdo (destino de cada tipo)

| Tipo | Destino | Exemplos |
|---|---|---|
| Instruções de comportamento | Prompt do agente | 1 pergunta por vez; 1–3 linhas; espelhar idioma; "drivers"; responder e parar |
| Conhecimento comercial | Knowledge files (consulta) | Programas e posicionamento; segmentação de perfis; objeções e scripts; interfaces entre áreas |
| Políticas | Prompt (resumo) + código (enforcement) | Descontos; segurança (nunca negar risco); reviews; não-promessas |
| Regras invioláveis | **Código na ponte** (ver rules-to-code.md) | Portão de preço; roteamento competidor→Italo; estado de escalação; sem desconto |
| Dados voláteis | Config/DB, nunca prompt | Rate Card, preços, links de pagamento/pista, horários, disponibilidade |
| Scripts literais permitidos | Templates em config | Check-in da pista (único texto canned autorizado) |
