# Regras que viram código — Sales Agent URace

> Princípio herdado do projeto: **as garantias vivem abaixo do modelo, não no prompt.**
> Estas regras serão impostas pela ponte (sales-bridge) no VPS — o modelo conversa; o código protege.

## Portões (bloqueiam a ação independente do que o modelo quiser)

| # | Regra | Fonte | Implementação |
|---|---|---|---|
| G1 | **Preço só após qualificação** (mínimo: experiência + origem — pendente C1) | POP 6.2/6.4; Modo Operante P3; COS §18 | A tool `get_price()` NÃO devolve valor enquanto os campos de qualificação do lead não estiverem preenchidos no estado. Um modelo que não recebe o número não pode dizê-lo. |
| G2 | **Competidor → Italo, sempre** | POP 6.3; Modo Operante P4 | Classificador de experiência no estado do lead; `experience=competes` força transição para HUMAN_HANDOFF com briefing; respostas de venda bloqueadas nesse estado. |
| G3 | **Conversa escalada não volta a vender** | Repo (roteador determinístico); missão §19 | Máquina de estados na ponte: `AI_ACTIVE → WAITING_HUMAN → HUMAN_HANDOFF → RESUMED → CLOSED`. Em WAITING_HUMAN/HUMAN_HANDOFF o agente não gera resposta comercial; retomada (RESUMED) só por comando do humano autorizado. |
| G4 | **Zero desconto pelo agente** | COS §18 | Nenhuma tool de desconto existe. Menção do lead a desconto fora da lista aprovada → gatilho de escalação. Lista aprovada (pendente C6) fica em config, exposta como INFORMAÇÃO apenas. |
| G5 | **Elegibilidade por idade** (faixas pendentes C7) | POP 5.3 | Validação na tool de recomendação/reserva: categoria incompatível com a idade → recusa com explicação, mesmo que o modelo tente. |
| G6 | **Kart próprio nunca aprovado pelo agente** | Handbook; Modo Operante 8 | Sem tool de aprovação. Intenção detectada → resposta processual (fotos → gestão → inspeção D-1) + escalação. |
| G7 | **Racing Team: explicar sim, aceitar não** | COS §12 | Sem tool de aceitação; interesse → escalação a Italo com briefing. |
| G8 | **Preços/links/horários nunca da memória do modelo** | POP 5.5; COS Authority | Prompt não contém nenhum preço/link/horário. Tudo vem de tools que leem config/DB (rate card table, links do ADM). Sem dado na base → tool devolve `unknown` e o agente diz que vai confirmar. |
| G9 | **Pagamento fecha venda, não invoice** | COS §19; POP 6.7 | Transição para "ganho" no Kommo só com evento de pagamento confirmado (ADM/QuickBooks), nunca por decisão do modelo. |
| G10 | **Refund/exceção de pagamento: nunca prometido** | COS §19; Handbook | Sem tool; pedido → escalação imediata. |

## Comportamento imposto pela ponte (não confia no prompt)

| # | Regra | Fonte | Implementação |
|---|---|---|---|
| B1 | **Sem double-messaging** | POP 6.1; Modo Operante P2 | A ponte entrega no máximo 1 resposta por mensagem recebida; envios espontâneos só via agendador de follow-up. |
| B2 | **Cadência de follow-up** | POP 6.5 | Agendador: mínimo 4 tentativas antes de perder; intervalo progressivo (D+1, +3d, +7d), máximo 1 semana; após cada tentativa, criar a próxima task no Kommo. Nenhum lead ativo sem próxima ação. |
| B3 | **Higiene de CRM obrigatória** | COS §35; POP seção 7 | Toda interação sincroniza Kommo (estágio, tags, notas, next action + due date). Lead sem owner/ação → corrigido automaticamente. |
| B4 | **Escalação = registrar e escalar, sem debater** | COS §38 | Detector de gatilhos (desconto fora da lista, refund, lesão/segurança, ameaça legal, chargeback, custódia, patrocínio, high-profile, Racing Team, programa custom) → estado WAITING_HUMAN + mensagem no WhatsApp interno com briefing padronizado (formato Modo Operante P9). |
| B5 | **SLA/alarme** (números pendentes C2) | POP 6.1; Handbook | Timer na ponte: escalação enviada sem resposta humana em N min → re-alerta. |
| B6 | **Check-in da pista** | Modo Operante P2/8 | Único texto literal permitido; template + links em config (fornecidos pelo ADM); disparo 48–24h antes da sessão. |
| B7 | **Auditoria** | Missão §8 | Toda mensagem (in/out), decisão de portão, escalação e autorização humana logadas no SQLite com timestamp — trilha completa por lead. |

## Segurança do agente (OpenClaw)

| # | Regra | Implementação |
|---|---|---|
| S1 | Sales Agent sem shell/terminal/filesystem | Agente OpenClaw separado, tools restritas à skill de vendas |
| S2 | Cliente ≠ humano autorizado | Canal do cliente = Kommo (via ponte, autenticada por API key); canal de autorização = WhatsApp interno com allowlist (só +1 407 487 8143) |
| S3 | Segredos fora do alcance do agente | Tokens (Kommo, gateway) só na ponte/env do serviço; nunca em prompt, memória ou filesystem legível pelo agente |
| S4 | Sem acesso ao agente pessoal / futuro ADM Agent | Agentes isolados no OpenClaw; sessões e memórias separadas |

## Pendências que bloqueiam implementação destas regras

- C1, C2, C5, C6, C7 do CONSOLIDACAO.md (decisões do Italo)
- Rate Card: localização e formato (para popular a tabela de preços da ponte)
- Links oficiais (pagamento/pista/waiver) fornecidos pelo ADM
- Funil real da conta Kommo (C3) para mapear os estágios
