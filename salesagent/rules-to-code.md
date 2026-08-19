# Regras que viram código — Sales Agent URace

> Princípio herdado do projeto: **as garantias vivem abaixo do modelo, não no prompt.**
> Estas regras serão impostas pela ponte (sales-bridge) no VPS — o modelo conversa; o código protege.

## Portões (bloqueiam a ação independente do que o modelo quiser)

| # | Regra | Fonte | Implementação |
|---|---|---|---|
| G1 | **Nunca falar preço em chat — sempre a página do programa** (C1 refinado, 17/08) | Documento Chase §8; Voice Manual 8A | A tool `get_price()` devolve o **link configurado** (`program-links.json`), não um número, para uso em chat com leads A/B/C-Academy. O modelo nunca recebe o valor bruto para citar ao lead — mais forte que o portão original de qualificação. |
| G2 | **Competidor → Italo, sempre** | POP 6.3; Modo Operante P4 | Classificador de experiência no estado do lead; `experience=competes` força transição para HUMAN_HANDOFF com briefing; respostas de venda bloqueadas nesse estado. |
| G3 | **Conversa escalada não volta a vender** | Repo (roteador determinístico); missão §19 | Máquina de estados na ponte: `AI_ACTIVE → WAITING_HUMAN → HUMAN_HANDOFF → RESUMED → CLOSED`. Em WAITING_HUMAN/HUMAN_HANDOFF o agente não gera resposta comercial; retomada (RESUMED) só por comando do humano autorizado. |
| G4 | **Zero desconto pelo agente** | COS §18 | Nenhuma tool de desconto existe. Menção do lead a desconto fora da lista aprovada → gatilho de escalação. Lista aprovada (pendente C6) fica em config, exposta como INFORMAÇÃO apenas. |
| G5 | **Elegibilidade por idade** (faixas pendentes C7) | POP 5.3 | Validação na tool de recomendação/reserva: categoria incompatível com a idade → recusa com explicação, mesmo que o modelo tente. |
| G6 | **Kart próprio nunca aprovado pelo agente** | Handbook; Modo Operante 8 | Sem tool de aprovação. Intenção detectada → resposta processual (fotos → gestão → inspeção D-1) + escalação. |
| G7 | **Racing Team: explicar sim, aceitar não** | COS §12 | Sem tool de aceitação; interesse → escalação a Italo com briefing. |
| G8 | **Preços/links/horários nunca da memória do modelo** | POP 5.5; COS Authority | Prompt não contém nenhum preço/link/horário. Tudo vem de tools que leem config/DB (rate card table, links do ADM). Sem dado na base → tool devolve `unknown` e o agente diz que vai confirmar. |
| G9 | **Pagamento fecha venda, não invoice** | COS §19; POP 6.7 | Transição para "ganho" no Kommo só com evento de pagamento confirmado (ADM/QuickBooks), nunca por decisão do modelo. |
| G10 | **Refund/exceção de pagamento: nunca prometido** | COS §19; Handbook | Sem tool; pedido → escalação imediata. |
| G11 | **Opção D (compete atualmente) qualifica automaticamente, sem revisar página** | Documento Chase §10/12 | Classificação `experience=competes` já dispara G2 (escalação); a ponte não exige `program page reviewed` nem preço visto antes de oferecer a call — ao contrário de A/B/C-Academy. |
| G12 | **Nome/transparência do agente** | Documento Chase §2; decisão C8 | O agente se identifica como "Chase", assistente de IA da URace — texto fixo nas instruções, não decisão do modelo em tempo de conversa. |

## Comportamento imposto pela ponte (não confia no prompt)

| # | Regra | Fonte | Implementação |
|---|---|---|---|
| B1 | **Sem double-messaging** | POP 6.1; Modo Operante P2 | A ponte entrega no máximo 1 resposta por mensagem recebida; envios espontâneos só via agendador de follow-up. |
| B2 | **Cadência de follow-up — 3 trilhas** (C11) | Documento Chase §17 | Agendador com 3 trilhas conforme o estado: sem resposta à classificação (+2h/+24h/+3d/+7d, fecha); link enviado sem resposta (+10min/+24h/+3d/+7d); data pedida pelo lead (tarefa persistente, cancelada se ele responder antes). Nunca duas trilhas simultâneas no mesmo lead. |
| B3 | **Higiene de CRM obrigatória** | COS §35; POP seção 7 | Toda interação sincroniza Kommo (estágio, tags, notas, next action + due date). Lead sem owner/ação → corrigido automaticamente. |
| B4 | **Escalação = registrar e escalar, sem debater** | COS §38; Documento Chase §20/21 | Detector de gatilhos (desconto fora da lista — agora zero por C6, refund, lesão/segurança, ameaça legal, chargeback, custódia, patrocínio/mídia, reclamação, high-profile, Racing Team, programa custom, "quero falar com humano") → estado WAITING_HUMAN + mensagem no WhatsApp interno com o briefing padronizado do documento Chase §21 (Driver/Age/Parent/Location/Email/Phone/Experience/Class/Championship/Interest/Program/Reviewed?/Pricing?/Travel?/Start date/Links/Questions/Next action). |
| B5 | **SLA/alarme** (números pendentes C2) | POP 6.1; Handbook | Timer na ponte: escalação enviada sem resposta humana em N min → re-alerta. |
| B6 | **Check-in da pista** | Modo Operante P2/8 | Único texto literal permitido; template + links em config (fornecidos pelo ADM); disparo 48–24h antes da sessão. |
| B7 | **Auditoria** | Missão §8 | Toda mensagem (in/out), decisão de portão, escalação e autorização humana logadas no SQLite com timestamp — trilha completa por lead. |

## Segurança do agente (OpenClaw)

| # | Regra | Implementação |
|---|---|---|
| S1 | Sales Agent sem shell/terminal/filesystem | Agente OpenClaw separado, tools restritas à skill de vendas |
| S2 | Cliente ≠ humano autorizado | **Canal do cliente = Kommo, único canal de vendas** (via ponte, autenticada por API key). **WhatsApp é canal interno de escalação, nunca de vendas** — só Italo e Eduardo (ADM), nunca cliente. Confirmado por Italo em 19/08. O agente Chase não deve estar acessível por esse canal — ver bug aberto abaixo. |
| S3 | Segredos fora do alcance do agente | Tokens (Kommo, gateway) só na ponte/env do serviço; nunca em prompt, memória ou filesystem legível pelo agente |
| S4 | Sem acesso ao agente pessoal / futuro ADM Agent | Agentes isolados no OpenClaw; sessões e memórias separadas |

## Pendências que bloqueiam implementação plena destas regras

- ✅ C1–C7 decididos. Rate Card, links de check-in, plano Kommo e funil real resolvidos.
- **C9** — mapeamento estágios reais × conceitos do documento Chase: proposta em uso (tags), aguardando confirmação.
- **C10** — links de programa (`program-links.json`) ainda todos `null`: sem eles, G1 não consegue mandar a página ao lead; o agente vai dizer que confirma e escalar.
- **C11** — cadência de 3 trilhas: adotada por padrão, sinalizada para confirmação.
