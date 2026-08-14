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
- **Proposta:** portão de código = as 2 perguntas do Modo Operante (mínimo verificável); se o lead pedir preço direto antes disso, o agente faz as 2 perguntas antes de cotar ("para te passar o valor certo, me diz…"). Starting point só com decisão explícita do Italo.
- **DECISÃO: ______**

### C2. SLA de primeira resposta
- POP v3: 10 minutos. Handbook: 30 minutos. COS: sem número.
- Para um agente automático o SLA real será segundos; a decisão importa para o **alerta de escalação** (quando humano precisa assumir e não responde).
- **Proposta:** meta do agente <2 min; alarme de escalação sem resposta humana: 10 min.
- **DECISÃO: ______**

### C3. Funil do Kommo
- POP v3: 14 estágios em PT (1 Contato … Ganho/Perdido). COS v4.0: 10 estágios em EN (New Lead … Future Opportunity).
- **Qual está configurado hoje na conta Kommo real?** O agente deve seguir o funil real da conta.
- **DECISÃO: ______**

### C4. "Produto único" × produtos distintos
- Handbook (30/07): "produto único de treinamento personalizado; nomes antigos como camps/programs abandonados".
- POP v3 (03/08, mais novo) e COS: vendem 1-Day, Camp, Academy, Racing Team como ofertas distintas.
- **Proposta:** ler o Handbook como diretriz de comunicação (explicar o treinamento como personalizado, não como cardápio), mantendo as ofertas comerciais distintas do POP/COS.
- **DECISÃO: ______**

### C5. Cancelamento/reagendamento <48h
- POP v3: taxa fixa de $95. COS v4.0: análise individual caso a caso.
- **DECISÃO: ______**

### C6. Descontos
- POP v3: silente. Modo Operante: negociação → dono. COS §18: lista fechada (2º filho 10%; contrato 6m 4%; 12m 8%; L&F 5-pack 10%) + resto escala Italo.
- **Proposta:** adotar a lista do COS como única fonte de desconto permitido, com aplicação **somente informativa** pelo agente (quem aplica é o ADM na invoice); qualquer pedido fora da lista = escalação.
- **DECISÃO: ______**

### C7. Elegibilidade por idade
- Só o POP define faixas, e só para Summer Camp (Baby Kart 4–7; 4t 7+; 2t 7+). Nenhuma fonte define idade mínima para 1-Day/Academy.
- **Necessário o Italo definir:** idade mínima geral (se houver) e as faixas por categoria para o portão de código.
- **DECISÃO: ______**

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
