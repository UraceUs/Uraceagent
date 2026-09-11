# Missão — Sales Brain (Obsidian como knowledge base central do agente)

> Brief completo do Italo, recebido em 25/08/2026, preservado verbatim.
> Status: **aguardando início** — decisão do Italo em 25/08: fechar o
> go-live do circuito Kommo/Chase primeiro, depois começar pela FASE 1
> (auditoria) desta missão. NÃO implementar nada antes da auditoria e do
> plano aprovado.

## Contexto de quem recebeu

O projeto já tem: agente Chase (OpenClaw, sem tools) + sales-bridge
(FastAPI: gates/state/directives/textproc/scheduler) + Kommo (funil
dedicado, Salesbot, widget v2) + conhecimento em arquivos MD/JSON no repo
(instructions/, config/, discovery/). A missão abaixo pede uma camada de
knowledge base estruturada (Obsidian como interface humana), retrieval
seletivo, separação knowledge/memory/learning e um learning loop com
aprovação humana. A auditoria (FASE 1) deve mapear o que disso já existe
parcialmente no projeto atual antes de propor qualquer coisa.

## Brief original (verbatim)

Você é um engenheiro de software sênior especializado em agentes de IA, automação, knowledge bases, RAG, GitHub, Obsidian e sistemas de vendas.
Estamos trabalhando em um projeto de um Agente de IA de Vendas e quero transformar o Obsidian em uma espécie de "cérebro"/knowledge base central do agente, mantendo o código e a infraestrutura do projeto versionados no GitHub.
Sua missão é analisar o projeto atual e implementar essa integração de forma profissional, modular e escalável.

### 1. REGRA MAIS IMPORTANTE: ANALISE ANTES DE ALTERAR
Antes de criar ou modificar qualquer arquivo:
1. Analise completamente o repositório atual.
2. Identifique: linguagem utilizada; framework; arquitetura; entry points; agentes existentes; banco de dados; APIs; integrações; arquivos de configuração; sistema atual de prompts; sistema atual de memória; sistema de RAG/embeddings, caso exista; estrutura de testes; variáveis de ambiente; documentação existente.
3. Leia o README e os arquivos de configuração.
4. Identifique se já existe alguma estrutura relacionada a: knowledge base; memory; vector database; embeddings; prompts; CRM; leads; sales; conversations; agents.
5. NÃO recrie algo que já exista.
6. NÃO substitua uma arquitetura existente sem antes explicar por quê.
7. Preserve o funcionamento atual do projeto.
Primeiro gere um diagnóstico da arquitetura atual e uma proposta de implementação. Depois disso, execute as alterações.

### 2. OBJETIVO DA ARQUITETURA
GitHub → Código do Agente → Obsidian Vault → Knowledge / Sales Brain → Retrieval / Search / RAG → AI Sales Agent → CRM / Leads / Conversations → Feedback → Atualização do Brain
O Obsidian não deve ser tratado simplesmente como um aplicativo de notas. Ele deve funcionar como uma Knowledge Base estruturada para o agente de vendas.

### 3. GITHUB
O projeto deve continuar tendo o GitHub como fonte oficial do código. Configure/verifique: Git repository; branches; .gitignore; README; documentação; configuração segura de secrets; estrutura de commits; versionamento das alterações.
NUNCA coloque API keys, tokens, senhas, credenciais, informações privadas de clientes ou secrets dentro do repositório. Use .env / secret manager quando apropriado. Crie ou atualize .env.example com todas as variáveis necessárias, mas SEM valores reais.

### 4. OBSIDIAN COMO "SALES BRAIN"
Estrutura inicial de Vault (adaptar ao projeto existente caso já possua organização melhor):
Sales-Brain/ com: 00_SYSTEM (Agent Instructions, Agent Rules, Agent Personality, Retrieval Rules) · 01_COMPANY (Company Overview, Products, Services, Pricing, Policies, FAQs) · 02_SALES (Sales Process, Qualification, Objections, Closing, Follow Ups, Sales Playbook) · 03_CUSTOMERS · 04_LEADS · 05_CONVERSATIONS · 06_PRODUCTS · 07_KNOWLEDGE · 08_CASES · 09_LEARNINGS · 10_PROMPTS · 99_ARCHIVE

### 5. TIPOS DE CONHECIMENTO
Company Knowledge (empresa, posicionamento, diferenciais, políticas, processos, institucional) · Product Knowledge (produto, descrição, preço, benefícios, limitações, requisitos, FAQs, comparações) · Sales Knowledge (abordagem, qualificação, objeções, respostas, fechamento, follow-up, scripts, exemplos de conversas) · Customer Knowledge (perfil, histórico, preferências, interações, estágio do funil) · Learning Knowledge (o que funcionou/não funcionou, objeções novas, perguntas frequentes, padrões, melhorias).

### 6. FRONTMATTER PADRONIZADO
Padrão de Markdown com frontmatter consistente e documentado. Exemplo: type, category, topic, priority, status, source, last_updated, tags. Não inventar campos desnecessários. Documentar cada campo e como o agente deve utilizá-lo.

### 7. SISTEMA DE RETRIEVAL
O agente não deve carregar o Vault inteiro no contexto. Camada de retrieval: (1) receber pergunta/contexto; (2) identificar o que precisa ser conhecido; (3) buscar documentos relevantes; (4) ranquear; (5) enviar apenas o contexto necessário ao LLM; (6) gerar a resposta.
Se já houver RAG, adaptar. Avaliar: Markdown search, full-text search, embeddings, vector database, hybrid search, metadata filtering. **Preferir a solução mais simples que funcione bem com a arquitetura existente.**

### 8. OBSIDIAN → AGENTE
Avaliar: Vault local, filesystem, Obsidian Local REST API, plugin, Git sync, indexação periódica, webhook/event-based sync. Escolher considerando segurança, simplicidade, velocidade, manutenção, escalabilidade e execução em servidor. Não criar dependência do Obsidian que impeça rodar em produção. Ideal: **Obsidian é a interface humana do conhecimento; o retrieval é a interface da IA.**

### 9. FLUXO DE ATUALIZAÇÃO DO CÉREBRO
Conversa → resposta → resultado registrado → identificação de informação relevante → Learning Queue → revisão/aprovação → documento atualizado no Obsidian → reindexação → agente usa o novo conhecimento.
O agente NÃO pode alterar conhecimento crítico sem controle. Níveis de confiança: candidate → review_required → approved → active.

### 10. SALES MEMORY VS KNOWLEDGE
Knowledge = conhecimento geral e estável ("o produto custa $500"). Memory = específico de conversa/cliente ("John só pode começar em setembro"). Learning = descoberto pelo sistema ("clientes desse segmento reclamam do preço quando não entendem o benefício X"). Não misturar.

### 11. CONTEXTO PARA O AGENTE
Camada de montagem de contexto, ordem: SYSTEM INSTRUCTIONS → AGENT PERSONALITY → CURRENT CONVERSATION → CUSTOMER MEMORY → RELEVANT SALES KNOWLEDGE → PRODUCT KNOWLEDGE → RELEVANT LEARNINGS → TASK. Controlar tokens, relevância, prioridade, recência, confiança.

### 12. CONFLITOS DE INFORMAÇÃO
Política: (1) mais recente; (2) maior prioridade; (3) approved; (4) fonte mais confiável. Persistindo a dúvida, o agente NÃO inventa — sinaliza falta de informação ou pede confirmação humana.

### 13. SALES AGENT
O Brain é a camada de conhecimento, não o agente. Separar: Agent · Memory · Knowledge · Retrieval · CRM · Integrations.

### 14. OBSIDIAN COMO INTERFACE HUMANA
Uma pessoa abre o Obsidian e entende: o que o agente sabe, o que está ativo, o que precisa de revisão, objeções aparecendo, aprendizados, atualizações, desatualizações. Dashboards/indexes em Markdown se fizer sentido.

### 15. DOCUMENTAÇÃO
Arquitetura, estrutura do Vault, como adicionar conhecimento, como o agente busca, RAG, memória, learning loop, execução local, configuração, testes, deploy. Atualizar README principal.

### 16. TESTES
Conexão com o Brain, leitura de Markdown, parsing de frontmatter, retrieval, ranking, filtros, geração de contexto, memory, conflitos, documentos inexistentes, knowledge desatualizado, falha de conexão. Exemplos reais de perguntas de vendas.

### 17. OBSERVABILIDADE
Registrar: query, documentos recuperados, score, contexto usado, resposta, tempo de retrieval, falhas. Não registrar dados sensíveis sem necessidade.

### 18. PERFORMANCE
Evitar: ler todo o Vault a cada mensagem, enviar o Vault inteiro ao LLM, embeddings desnecessários, duplicação, reindexação total por mudança de um arquivo. Preferir: incremental indexing, cache, metadata, hashes, timestamps, event-based updates.

### 19. SEGURANÇA
Revisar secrets, permissões, arquivos privados, dados de clientes, logs, acesso ao Vault, endpoints, autenticação. Não expor o Vault inteiro por API pública.

### 20. GIT WORKFLOW
Após alterações: mostrar arquivos criados/modificados com motivo, executar testes, corrigir, revisão final, confirmar ausência de secrets no diff, resumo. NÃO commitar/pushar sem informar primeiro, salvo pedido explícito.

### 21. PRINCÍPIO ARQUITETURAL
GitHub = código e versionamento · Obsidian = interface humana do conhecimento · Knowledge Base = conhecimento estruturado · Memory = contexto de clientes/conversas · Retrieval = ponte conhecimento↔IA · Agent = raciocínio e execução · CRM = estado comercial · Learning System = evolução do cérebro.

### 22. FASES
FASE 1 AUDITORIA (arquitetura atual, tecnologias, estrutura, agentes, memória, banco, integrações, problemas, reutilizável, a criar, proposta) → FASE 2 PLANO → FASE 3 IMPLEMENTAÇÃO → FASE 4 TESTES → FASE 5 DOCUMENTAÇÃO → FASE 6 RELATÓRIO FINAL.
IMPORTANTE: não fazer suposições sobre a arquitetura atual. Inspecionar o código primeiro e adaptar a solução ao que já existe.
