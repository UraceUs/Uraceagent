-- URACE Command Center — esquema (SQLite, WAL).
-- Lido por command_center/db/__init__.py em toda subida; cada bloco é
-- idempotente (IF NOT EXISTS). Mudança de forma vai em migrations/.
--
-- Princípios (docs/adminai/command-center-adr.md):
--   * identidade é chave externa: entity_links liga o id interno ao id
--     de cada sistema. Nome e e-mail nunca são identidade.
--   * audit_logs é append-only por TRIGGER — nem bug nem tela apagam.
--   * nada aqui guarda credencial. Tokens ficam em ~/.urace/, fora do banco.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------ pessoas
CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY,
  email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
  name          TEXT NOT NULL,
  role          TEXT NOT NULL CHECK (role IN ('ADMIN','MANAGER','OPERATOR','VIEWER')),
  pw_salt       TEXT NOT NULL,            -- base64
  pw_hash       TEXT NOT NULL,            -- base64 scrypt
  active        INTEGER NOT NULL DEFAULT 1,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  last_login_at TEXT
);

-- ------------------------------------------------------------------ chat interno
-- Dono, 21/09: unificar o que hoje se fala no WhatsApp (mecânicos, coach, designers,
-- fornecedor de suit) e no Google Chat (staff adm, financeiro, comercial). A decisão está
-- em D-2026-09-21: o painel é o hub, os dois viram canais — o Google Chat com ponte
-- completa, o WhatsApp com o que a API permite (janela de 24 h, grupo de no máximo 8).
--
-- Por isso a mensagem nasce com `origem` e `external_id`: a mesma tabela guarda o que foi
-- escrito aqui e o que veio de fora, e a ponte sabe o que já espelhou. Sem isso, ligar as
-- pontes depois significaria migrar dados — e migração de conversa é perda de conversa.
CREATE TABLE IF NOT EXISTS team_channels (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  kind        TEXT NOT NULL DEFAULT 'EQUIPE'      -- EQUIPE | CORRIDA | SERVICO | CLIENTE | DIRETO
              CHECK (kind IN ('EQUIPE','CORRIDA','SERVICO','CLIENTE','DIRETO')),
  -- a que isto se refere: corrida, serviço ou cliente. Conversa solta vira conversa perdida.
  entity_type TEXT,
  entity_id   INTEGER,
  topic       TEXT,
  created_by  INTEGER REFERENCES users(id),
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  archived_at TEXT,
  -- ponte: espaço do Google Chat ou grupo do WhatsApp que este canal espelha
  bridge      TEXT,                               -- gchat | whatsapp | NULL (só painel)
  bridge_id   TEXT,
  UNIQUE (bridge, bridge_id)
);
CREATE INDEX IF NOT EXISTS team_channels_entidade ON team_channels(entity_type, entity_id);

CREATE TABLE IF NOT EXISTS team_messages (
  id          INTEGER PRIMARY KEY,
  channel_id  INTEGER NOT NULL REFERENCES team_channels(id),
  user_id     INTEGER REFERENCES users(id),       -- NULL quando veio de fora por alguém sem conta
  author      TEXT NOT NULL,                      -- nome de quem escreveu, sempre legível
  text        TEXT NOT NULL,
  at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  origem      TEXT NOT NULL DEFAULT 'painel',     -- painel | gchat | whatsapp
  external_id TEXT,                               -- id da mensagem no sistema de origem
  reply_to    INTEGER REFERENCES team_messages(id),
  edited_at   TEXT,
  deleted_at  TEXT,                               -- some da tela; o registro fica
  UNIQUE (channel_id, origem, external_id)
);
CREATE INDEX IF NOT EXISTS team_messages_canal ON team_messages(channel_id, at);

-- Quem participa e até onde já leu. `last_read_id` em vez de data: mensagem tem ordem,
-- relógio de celular não é confiável, e "3 não lidas" tem de bater com o que a pessoa vê.
CREATE TABLE IF NOT EXISTS team_members (
  channel_id   INTEGER NOT NULL REFERENCES team_channels(id),
  user_id      INTEGER NOT NULL REFERENCES users(id),
  joined_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  last_read_id INTEGER NOT NULL DEFAULT 0,
  muted        INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (channel_id, user_id)
);

-- Notificação no celular (dono, 21/09). O painel instalado na tela inicial avisa mesmo
-- fechado — é o que faz a equipe usar o chat de dentro em vez do WhatsApp.
-- Uma linha por PESSOA e por APARELHO: o mesmo mecânico no celular e no tablet são duas
-- assinaturas, e tirar uma não derruba a outra.
CREATE TABLE IF NOT EXISTS push_subscriptions (
  id          INTEGER PRIMARY KEY,
  user_id     INTEGER NOT NULL REFERENCES users(id),
  endpoint    TEXT NOT NULL UNIQUE,      -- o endereço que o navegador deu; identifica o aparelho
  p256dh      TEXT NOT NULL,             -- chaves da assinatura: sem elas o navegador não abre o aviso
  auth        TEXT NOT NULL,
  user_agent  TEXT,
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  last_ok_at  TEXT,
  falhas      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS push_subscriptions_user ON push_subscriptions(user_id);

-- Chave de API: outro sistema falando com o Command Center sem navegador (dono, 21/09).
-- O SEGREDO NUNCA FICA AQUI: só o hash (scrypt, como senha). Perdeu a chave, cria outra.
-- Toda chave age como uma PESSOA e tem um papel, e o papel dela nunca passa do papel da
-- pessoa — chave não é porta dos fundos para privilégio que o dono da chave não tem.
CREATE TABLE IF NOT EXISTS api_keys (
  id           TEXT PRIMARY KEY,          -- prefixo público: aparece no log e não abre nada sozinho
  name         TEXT NOT NULL,
  salt         TEXT NOT NULL,
  hash         TEXT NOT NULL,
  role         TEXT NOT NULL CHECK (role IN ('ADMIN','MANAGER','OPERATOR','VIEWER')),
  user_id      INTEGER NOT NULL REFERENCES users(id),   -- a chave age como esta pessoa
  created_by   INTEGER REFERENCES users(id),
  created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  expires_at   TEXT,                      -- NULL = não expira
  last_used_at TEXT,
  last_ip      TEXT,
  uses         INTEGER NOT NULL DEFAULT 0,
  revoked_at   TEXT,
  note         TEXT,                      -- para que serve, escrito por quem criou
  -- Papel diz O QUE a chave alcança; isto diz se ela pode MEXER. Um agente de IA pode
  -- precisar ver o financeiro inteiro e não ter direito de mandar mensagem para cliente
  -- nem reescrever preço. Padrão 1 (só leitura) de propósito: escrever é a exceção.
  read_only    INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS ix_api_keys_user ON api_keys(user_id);

CREATE TABLE IF NOT EXISTS sessions (
  id          TEXT PRIMARY KEY,           -- token aleatório (só o hash fica aqui)
  user_id     INTEGER NOT NULL REFERENCES users(id),
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  expires_at  TEXT NOT NULL,
  revoked_at  TEXT,
  ip          TEXT,
  user_agent  TEXT
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id, revoked_at);

CREATE TABLE IF NOT EXISTS login_attempts (
  id        INTEGER PRIMARY KEY,
  key       TEXT NOT NULL,                -- ip ou email (normalizado)
  at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  ok        INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS login_attempts_key ON login_attempts(key, at);

-- ------------------------------------------------------------ clientes
CREATE TABLE IF NOT EXISTS client_stages (
  id      INTEGER PRIMARY KEY,
  code    TEXT NOT NULL UNIQUE,           -- LEAD, QUALIFIED, ... REPEAT_CUSTOMER
  label   TEXT NOT NULL,
  ord     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS clients (
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL,            -- responsável (quem paga/assina)
  company       TEXT,
  email         TEXT COLLATE NOCASE,
  phone         TEXT,
  pilot_name    TEXT,                     -- o piloto, quando é outra pessoa
  pilot_dob     TEXT,                     -- AAAA-MM-DD; decide a waiver
  vip           INTEGER NOT NULL DEFAULT 0,
  status        TEXT NOT NULL DEFAULT 'ACTIVE'
                CHECK (status IN ('ACTIVE','INACTIVE','NEW','AT_RISK','COMPLETED','PENDING')),
  stage_code    TEXT REFERENCES client_stages(code),
  owner_user_id INTEGER REFERENCES users(id),
  source        TEXT,                     -- de onde veio o registro (asana, brain, qbo, manual)
  notes         TEXT,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS clients_email ON clients(email);
CREATE INDEX IF NOT EXISTS clients_status ON clients(status, stage_code);

-- ---------------------------------------------------- vínculos externos
-- Um registro interno ↔ um id em um sistema. É a ÚNICA identidade válida.
CREATE TABLE IF NOT EXISTS entity_links (
  id           INTEGER PRIMARY KEY,
  entity_type  TEXT NOT NULL,             -- client, task, invoice, waiver, email, event
  entity_id    INTEGER NOT NULL,
  system       TEXT NOT NULL,             -- asana, quickbooks, docusign, gmail, gcal
  external_id  TEXT NOT NULL,
  deep_link    TEXT,
  created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (system, external_id, entity_type)
);
CREATE INDEX IF NOT EXISTS entity_links_entity ON entity_links(entity_type, entity_id);

-- --------------------------------------------- espelhos dos sistemas
-- Cópias leves do que os providers leem, para busca/dashboard rápidos.
-- A fonte de verdade continua sendo o sistema de origem.
CREATE TABLE IF NOT EXISTS tasks (
  id            INTEGER PRIMARY KEY,
  client_id     INTEGER REFERENCES clients(id),
  title         TEXT NOT NULL,
  project       TEXT,                     -- U-RACE, SUITS, Shipping Orders
  section       TEXT,
  status        TEXT,                     -- open, completed
  due_on        TEXT,
  assignee      TEXT,
  subtasks_total INTEGER,
  subtasks_done  INTEGER,
  synced_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS tasks_due ON tasks(due_on, status);

CREATE TABLE IF NOT EXISTS waivers (
  id            INTEGER PRIMARY KEY,
  client_id     INTEGER REFERENCES clients(id),
  signer_name   TEXT,
  signer_email  TEXT COLLATE NOCASE,
  template      TEXT,                     -- parental | adult | other
  status        TEXT,                     -- sent, delivered, completed, declined, voided, autoresponded
  sent_at       TEXT,
  completed_at  TEXT,
  expires_at    TEXT,
  synced_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS waivers_email ON waivers(signer_email, status);

CREATE TABLE IF NOT EXISTS invoices (
  id            INTEGER PRIMARY KEY,
  client_id     INTEGER REFERENCES clients(id),
  doc_number    TEXT,
  amount        REAL,
  balance       REAL,
  status        TEXT,                     -- draft, sent, paid, overdue
  issued_on     TEXT,
  due_on        TEXT,
  ai_generated  INTEGER NOT NULL DEFAULT 0,
  synced_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- Lembretes recorrentes de invoice em aberto (dono, 16/09): um por invoice, cadência em dias.
CREATE TABLE IF NOT EXISTS invoice_reminders (
  id            INTEGER PRIMARY KEY,
  invoice_id    INTEGER NOT NULL UNIQUE REFERENCES invoices(id),
  client_id     INTEGER REFERENCES clients(id),
  cadence       TEXT NOT NULL CHECK (cadence IN ('daily','weekly','custom')),
  every_days    INTEGER NOT NULL DEFAULT 7,
  enabled       INTEGER NOT NULL DEFAULT 1,
  next_on       TEXT,                     -- AAAA-MM-DD (dia local de Orlando) do próximo envio
  last_sent_at  TEXT,
  sent_count    INTEGER NOT NULL DEFAULT 0,
  note          TEXT,
  created_by    INTEGER REFERENCES users(id),
  updated_by    INTEGER REFERENCES users(id),
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS invoice_reminders_due ON invoice_reminders(enabled, next_on);

-- Lembretes de waiver (dono, 22/09). A política virou SAFE, mas com condição:
-- só para quem tem serviço marcado, 3 dias antes e 1 dia antes, no máximo 2 por
-- envelope. A política abre a porta; a condição mora aqui e no servidor — é a
-- contagem desta tabela que impede o terceiro lembrete.
CREATE TABLE IF NOT EXISTS waiver_reminders (
  id            INTEGER PRIMARY KEY,
  envelope_id   TEXT NOT NULL,
  signer_email  TEXT COLLATE NOCASE,
  days_before   INTEGER,                  -- 3 ou 1: qual das duas janelas foi
  service_at    TEXT,                     -- o serviço que justificou o lembrete
  sent_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS waiver_reminders_env ON waiver_reminders(envelope_id);

CREATE TABLE IF NOT EXISTS emails (
  id            INTEGER PRIMARY KEY,
  client_id     INTEGER REFERENCES clients(id),
  mailbox       TEXT NOT NULL,            -- urace | support
  subject       TEXT,
  sender        TEXT,
  last_at       TEXT,
  labels        TEXT,                     -- json
  priority      TEXT,                     -- CRITICAL, HIGH, NORMAL, LOW
  intent        TEXT,
  handled       INTEGER NOT NULL DEFAULT 0,
  synced_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS calendar_events (
  id            INTEGER PRIMARY KEY,
  client_id     INTEGER REFERENCES clients(id),
  title         TEXT,
  starts_at     TEXT,
  ends_at       TEXT,
  location      TEXT,
  synced_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- ------------------------------------------------------------- CRM (Kommo)
-- Espelho do funil comercial. A fonte de verdade continua sendo o Kommo;
-- aqui fica o que a tela precisa mostrar rápido e ligar ao card do cliente.
CREATE TABLE IF NOT EXISTS crm_leads (
  id             INTEGER PRIMARY KEY,
  external_id    TEXT NOT NULL UNIQUE,      -- id do lead no Kommo
  client_id      INTEGER REFERENCES clients(id),
  name           TEXT,
  pipeline_id    TEXT,
  pipeline_name  TEXT,
  stage_id       TEXT,
  stage_name     TEXT,
  stage_order    INTEGER,
  price          REAL,
  source         TEXT,                      -- Instagram, Facebook, WhatsApp, site…
  tags           TEXT,                      -- json
  responsible    TEXT,
  contact_name   TEXT,
  contact_email  TEXT COLLATE NOCASE,
  contact_phone  TEXT,
  link           TEXT,
  created_at_src TEXT,
  updated_at_src TEXT,
  last_message_at TEXT,
  needs_reply    INTEGER NOT NULL DEFAULT 0,
  synced_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS crm_leads_stage ON crm_leads(pipeline_id, stage_order);
CREATE INDEX IF NOT EXISTS crm_leads_client ON crm_leads(client_id);

CREATE TABLE IF NOT EXISTS crm_messages (
  id          INTEGER PRIMARY KEY,
  lead_id     INTEGER NOT NULL REFERENCES crm_leads(id),
  external_id TEXT,
  direction   TEXT,                         -- entrada | saida | nota
  author      TEXT,
  text        TEXT,
  at          TEXT,
  source      TEXT,                          -- kommo | webhook | painel
  UNIQUE (lead_id, external_id)
);
CREATE INDEX IF NOT EXISTS crm_messages_lead ON crm_messages(lead_id, at);

-- ---------------------------------------------------- telefonia (Dialpad)
-- 18/09: a URACE tem UM número de empresa que recebe todas as ligações. O evento chega por
-- webhook (JSON ou JWT assinado), casa pelo telefone com cliente/oportunidade/lead, e a
-- gravação e a transcrição entram porque o aviso de consentimento já toca na chamada.
CREATE TABLE IF NOT EXISTS calls (
  id              INTEGER PRIMARY KEY,
  external_id     TEXT UNIQUE,               -- call_id no Dialpad
  direction       TEXT,                      -- entrada | saida
  state           TEXT,                      -- ringing | connected | hangup | missed | voicemail…
  external_number TEXT,                      -- o número de fora (E.164)
  internal_number TEXT,                      -- o número da empresa
  contact_name    TEXT,                      -- nome que o Dialpad conhece
  who             TEXT,                      -- quem atendeu ou discou do nosso lado
  started_at      TEXT,
  ended_at        TEXT,
  seconds         INTEGER,
  answered        INTEGER NOT NULL DEFAULT 0,
  voicemail       INTEGER NOT NULL DEFAULT 0,
  recording_url   TEXT,
  transcript      TEXT,
  client_id       INTEGER REFERENCES clients(id),
  opportunity_id  INTEGER REFERENCES opportunities(id),
  lead_id         INTEGER REFERENCES crm_leads(id),
  handled         INTEGER NOT NULL DEFAULT 0, -- perdida já tratada
  raw             TEXT,                       -- o evento como chegou (campo novo não se perde)
  at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS calls_quando ON calls(started_at);
CREATE INDEX IF NOT EXISTS calls_client ON calls(client_id);
CREATE INDEX IF NOT EXISTS calls_opp ON calls(opportunity_id);

-- ---------------------------------------------------- vendas (closer): oportunidade NÃO é cliente
-- Pedido do dono (17/09): o closer liga por fora e registra tudo aqui. Só vira cliente no Ganho.
CREATE TABLE IF NOT EXISTS opportunities (
  id             INTEGER PRIMARY KEY,
  name           TEXT NOT NULL,             -- quem decide/paga (responsável)
  email          TEXT COLLATE NOCASE,
  phone          TEXT,
  pilot_name     TEXT,
  pilot_age      INTEGER,
  service        TEXT,                      -- o que ele quer (interesse)
  service_date   TEXT,                      -- AAAA-MM-DD do serviço combinado
  service_time   TEXT,                      -- HH:MM (opcional)
  amount         REAL,                      -- valor fechado/estimado
  stage          TEXT NOT NULL DEFAULT 'NOVO'
                 CHECK (stage IN ('NOVO','CONVERSA','PROPOSTA','FECHAMENTO','GANHO','PERDIDO')),
  source         TEXT,                      -- Instagram, Facebook, WhatsApp, Ligação, Site, Indicação
  closer_user_id INTEGER REFERENCES users(id),
  client_id      INTEGER REFERENCES clients(id),      -- preenchido no Ganho
  crm_lead_id    INTEGER REFERENCES crm_leads(id),    -- quando veio do chat
  next_at        TEXT,                      -- retorno agendado (ISO)
  next_what      TEXT,
  lost_reason    TEXT,
  notes          TEXT,
  closing        TEXT,                      -- json: passos do fechamento e resultado de cada um
  starred        INTEGER,
  created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS opp_stage ON opportunities(stage, next_at);
CREATE INDEX IF NOT EXISTS opp_closer ON opportunities(closer_user_id, stage);

CREATE TABLE IF NOT EXISTS opp_events (
  id       INTEGER PRIMARY KEY,
  opp_id   INTEGER NOT NULL REFERENCES opportunities(id),
  kind     TEXT NOT NULL,                   -- call|email|note|stage|waiver|invoice|asana|kommo|client|task|next|ia
  title    TEXT,
  detail   TEXT,
  at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  actor    TEXT,
  ok       INTEGER                          -- 1 feito · 0 falhou · NULL informativo
);
CREATE INDEX IF NOT EXISTS opp_events_opp ON opp_events(opp_id, at);

-- ------------------------------------------- manual de marcadores do Gmail
-- O dono (11/09): "leia marcador por marcador, entenda o que vai em cada um, me
-- dê o manual e eu confirmo — só daí ela sabe como agir". A triagem só usa
-- marcador com status 'confirmado'; enquanto não houver nenhum, ela não roda.
CREATE TABLE IF NOT EXISTS gmail_labels (
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL UNIQUE,     -- nome EXATO no Gmail
  family        TEXT,                     -- raiz (Finances, Banks, RACES…)
  what          TEXT,                     -- o que vai aqui (o manual)
  threads       INTEGER,                  -- volume lido da conta
  status        TEXT NOT NULL DEFAULT 'pendente'
                CHECK (status IN ('pendente','confirmado','fora')),
  in_gmail      INTEGER NOT NULL DEFAULT 1,   -- ainda existe na caixa?
  confirmed_by  TEXT,
  confirmed_at  TEXT,
  synced_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS gmail_labels_status ON gmail_labels(status, family);

-- ---------------------------------------------------------- integrações
CREATE TABLE IF NOT EXISTS integrations (
  system            TEXT PRIMARY KEY,     -- asana, docusign, gmail, quickbooks
  status            TEXT NOT NULL DEFAULT 'DISCONNECTED'
                    CHECK (status IN ('CONNECTED','SYNCING','DEGRADED','ERROR','DISCONNECTED')),
  last_success_at   TEXT,
  last_attempt_at   TEXT,
  error_count       INTEGER NOT NULL DEFAULT 0,
  last_error        TEXT,
  detail            TEXT                  -- json: contas, ambiente (demo/prod), etc.
);

CREATE TABLE IF NOT EXISTS sync_logs (
  id          INTEGER PRIMARY KEY,
  system      TEXT NOT NULL,
  started_at  TEXT NOT NULL,
  finished_at TEXT,
  ok          INTEGER,
  items       INTEGER,
  message     TEXT
);

-- ------------------------------------------------------------------ IA
CREATE TABLE IF NOT EXISTS ai_commands (
  id           INTEGER PRIMARY KEY,
  user_id      INTEGER NOT NULL REFERENCES users(id),
  text         TEXT NOT NULL,
  session_key  TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'QUEUED'
               CHECK (status IN ('QUEUED','RUNNING','DONE','FAILED','CANCELLED')),
  started_at   TEXT,
  finished_at  TEXT,
  output       TEXT,                      -- resposta do agente (texto)
  error        TEXT,
  created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS ai_commands_user ON ai_commands(user_id, created_at);

CREATE TABLE IF NOT EXISTS ai_workflows (
  id           INTEGER PRIMARY KEY,
  command_id   INTEGER REFERENCES ai_commands(id),
  client_id    INTEGER REFERENCES clients(id),
  kind         TEXT NOT NULL,             -- onboarding, follow_up, ...
  status       TEXT NOT NULL DEFAULT 'RUNNING'
               CHECK (status IN ('RUNNING','WAITING','DONE','FAILED','BLOCKED','CANCELLED')),
  started_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  finished_at  TEXT,
  summary      TEXT
);

CREATE TABLE IF NOT EXISTS ai_workflow_steps (
  id           INTEGER PRIMARY KEY,
  workflow_id  INTEGER NOT NULL REFERENCES ai_workflows(id),
  ord          INTEGER NOT NULL,
  title        TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'PENDING'
               CHECK (status IN ('PENDING','RUNNING','WAITING','DONE','FAILED','BLOCKED','SKIPPED')),
  detail       TEXT,
  started_at   TEXT,
  finished_at  TEXT
);

-- Cada ação que a IA propôs ou executou. Enquanto APLICAR=0, tudo é proposta.
CREATE TABLE IF NOT EXISTS ai_actions (
  id           INTEGER PRIMARY KEY,
  command_id   INTEGER REFERENCES ai_commands(id),
  workflow_id  INTEGER REFERENCES ai_workflows(id),
  action       TEXT NOT NULL,             -- asana_comentar, docusign_enviar_waiver, ...
  system       TEXT,
  policy       TEXT NOT NULL              -- classificação no momento da proposta
               CHECK (policy IN ('SAFE','REQUIRES_CONFIRMATION','REQUIRES_APPROVAL','BLOCKED')),
  status       TEXT NOT NULL DEFAULT 'PROPOSED'
               CHECK (status IN ('PROPOSED','APPROVED','REJECTED','RUNNING','DONE','FAILED','BLOCKED')),
  payload      TEXT,                      -- json com os argumentos (sem segredo)
  result       TEXT,
  reason       TEXT,                      -- "por quê" — transparência
  created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  finished_at  TEXT
);
CREATE INDEX IF NOT EXISTS ai_actions_status ON ai_actions(status, created_at);

CREATE TABLE IF NOT EXISTS approvals (
  id           INTEGER PRIMARY KEY,
  action_id    INTEGER NOT NULL REFERENCES ai_actions(id),
  requested_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  decided_at   TEXT,
  decided_by   INTEGER REFERENCES users(id),
  decision     TEXT CHECK (decision IN ('APPROVED','REJECTED','EDITED')),
  comment      TEXT
);

CREATE TABLE IF NOT EXISTS automation_rules (
  id           INTEGER PRIMARY KEY,
  name         TEXT NOT NULL,
  enabled      INTEGER NOT NULL DEFAULT 1,
  trigger      TEXT NOT NULL,             -- json: {event: "waiver.completed"}
  conditions   TEXT,                      -- json
  actions      TEXT NOT NULL,             -- json
  created_by   INTEGER REFERENCES users(id),
  created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- Política de ações: o que a IA pode, com que gate. Só ADMIN altera.
CREATE TABLE IF NOT EXISTS action_policies (
  action       TEXT PRIMARY KEY,
  policy       TEXT NOT NULL CHECK (policy IN ('SAFE','REQUIRES_CONFIRMATION','REQUIRES_APPROVAL','BLOCKED')),
  note         TEXT,
  updated_by   INTEGER REFERENCES users(id),
  updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- ----------------------------------------------------- notificações/alertas
CREATE TABLE IF NOT EXISTS notifications (
  id          INTEGER PRIMARY KEY,
  user_id     INTEGER REFERENCES users(id),   -- NULL = todos
  level       TEXT NOT NULL CHECK (level IN ('LOW','MEDIUM','HIGH','CRITICAL')),
  title       TEXT NOT NULL,
  body        TEXT,
  link        TEXT,
  read_at     TEXT,
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- ------------------------------------------------------------- auditoria
CREATE TABLE IF NOT EXISTS audit_logs (
  id          INTEGER PRIMARY KEY,
  at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  user_id     INTEGER,                    -- NULL = sistema/IA
  actor       TEXT NOT NULL,              -- 'user:italo', 'ai:urace-admin', 'system'
  event       TEXT NOT NULL,              -- auth.login, auth.fail, ai.command, action.approve, ...
  entity_type TEXT,
  entity_id   TEXT,
  detail      TEXT,                       -- json, sem segredo
  ip          TEXT
);
CREATE INDEX IF NOT EXISTS audit_logs_at ON audit_logs(at);
CREATE INDEX IF NOT EXISTS audit_logs_event ON audit_logs(event, at);

-- Append-only. Não é convenção: é o banco recusando.
CREATE TRIGGER IF NOT EXISTS audit_logs_no_update BEFORE UPDATE ON audit_logs
BEGIN SELECT RAISE(ABORT, 'audit_logs is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_logs_no_delete BEFORE DELETE ON audit_logs
BEGIN SELECT RAISE(ABORT, 'audit_logs is append-only'); END;

-- --------------------------------------------------------- dados fixos
INSERT OR IGNORE INTO client_stages (code, label, ord) VALUES
  ('LEAD','Lead',1), ('QUALIFIED','Qualified',2), ('CONTACTED','Contacted',3),
  ('PROPOSAL','Proposal',4), ('INVOICE','Invoice',5), ('PAYMENT','Payment',6),
  ('WAIVER','Waiver',7), ('SCHEDULED','Scheduled',8), ('SERVICE','Service',9),
  ('COMPLETED','Completed',10), ('REPEAT_CUSTOMER','Repeat customer',11);

INSERT OR IGNORE INTO integrations (system, status) VALUES
  ('asana','DISCONNECTED'), ('docusign','DISCONNECTED'),
  ('gmail','DISCONNECTED'), ('quickbooks','DISCONNECTED'), ('kommo','DISCONNECTED');

-- A política inicial vem do cérebro (PARAMETROS + decisões de 04/09).
INSERT OR IGNORE INTO action_policies (action, policy, note) VALUES
  ('asana_buscar','SAFE','leitura'),
  ('asana_tarefa','SAFE','leitura'),
  ('asana_criar_tarefa','SAFE','criar tarefa: autorizado pelo dono (31/08)'),
  ('asana_criar_do_modelo','SAFE','tarefa de serviço pelo modelo oficial, na coluna do dia (dono, 04/09)'),
  ('qbo_criar_item','SAFE','a IA cria o produto no catálogo com descrição e valor; só o envio da invoice pede aprovação (dono, 10/09)'),
  ('asana_comentar','SAFE','comentário com prefixo [IA ADM]'),
  ('asana_mover_para_secao','REQUIRES_CONFIRMATION','muda o quadro'),
  ('asana_mover_para_finished','SAFE','só para Finished Services, tarefa de dia passado e concluída: autocorreção (dono, 08/09)'),
  ('asana_concluir','REQUIRES_CONFIRMATION','Signed waiver? etc.'),
  ('asana_anexar_arquivo','SAFE','waiver assinada na tarefa'),
  ('gmail_rascunho','SAFE','rascunho nunca envia'),
  ('gmail_rotular','REQUIRES_CONFIRMATION','arquivar só com wNews (no servidor)'),
  ('gmail_enviar','BLOCKED','regra: a IA não envia e-mail livre'),
  ('docusign_enviar_waiver','REQUIRES_APPROVAL','4 travas no servidor + aprovação humana'),
  ('docusign_void','BLOCKED','nunca'),
  ('docusign_send_reminder','BLOCKED','U-01: não decidido'),
  ('qbo_criar_invoice','REQUIRES_CONFIRMATION','pode criar (31/08); preço pela Rate Card'),
  ('qbo_enviar_invoice','REQUIRES_APPROVAL','D-2026-09-04: envia depois de aprovada no painel'),
  ('qbo_criar_e_enviar_invoice','REQUIRES_APPROVAL','cria e envia num clique: aprovar = enviar (dono, 09/09); prévia obrigatória na aprovação'),
  ('qbo_enviar_invoice_deposito','REQUIRES_APPROVAL','exceção de 28/08, agora com aprovação'),
  ('qbo_apagar','BLOCKED','a IA nunca apaga'),
  ('apagar_qualquer_coisa','BLOCKED','a IA nunca apaga'),
  ('apagar_cliente','BLOCKED','a IA nunca apaga');

-- ------------------------------------------------- itens de atenção ocultos
-- "Excluir" um aviso não apaga a fonte (a tarefa, o envelope, o e-mail
-- continuam onde estão). Só esconde o aviso, com quem e por quê. Restaurável.
CREATE TABLE IF NOT EXISTS attention_dismissals (
  key           TEXT PRIMARY KEY,         -- regra:tipo:id — estável entre coletas
  level         TEXT,
  title         TEXT,
  reason        TEXT,
  dismissed_by  INTEGER NOT NULL REFERENCES users(id),
  dismissed_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- ------------------------------------------------------ uniões de cliente
-- Um card por pessoa. Quando dois registros são a mesma pessoa, o duplicado
-- sai do espelho e fica aqui, inteiro, com quem uniu e por quê.
CREATE TABLE IF NOT EXISTS client_merges (
  id         INTEGER PRIMARY KEY,
  keep_id    INTEGER NOT NULL,
  drop_id    INTEGER NOT NULL,
  drop_name  TEXT,
  drop_json  TEXT,
  merged_by  TEXT NOT NULL,                -- sync | user:<id>
  reason     TEXT,
  merged_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- ------------------------------------------------------ memória da IA
-- O que o dono ensinou pelo balão de instrução. Entra em todo prompt
-- relevante (global, por cliente ou por tipo de item). Desativável, nunca
-- apagado: é a trilha de como a IA aprendeu.
CREATE TABLE IF NOT EXISTS ai_learnings (
  id          INTEGER PRIMARY KEY,
  scope       TEXT NOT NULL DEFAULT 'global',   -- global | client:<id> | entity:<type>
  text        TEXT NOT NULL,
  source_key  TEXT,                              -- chave do item de atenção que originou
  created_by  INTEGER REFERENCES users(id),
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  active      INTEGER NOT NULL DEFAULT 1
);

-- ------------------------------------------------------ eventos que acordam a IA
CREATE TABLE IF NOT EXISTS ai_events (
  id           INTEGER PRIMARY KEY,
  kind         TEXT NOT NULL,             -- task.created | email.received | waiver.bounced | waiver.completed
  entity_type  TEXT,
  entity_id    INTEGER,
  client_id    INTEGER REFERENCES clients(id),
  summary      TEXT,
  detected_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  status       TEXT NOT NULL DEFAULT 'NEW'
               CHECK (status IN ('NEW','RUNNING','DONE','FAILED','SKIPPED')),
  command_id   INTEGER REFERENCES ai_commands(id),
  handled_at   TEXT,
  note         TEXT
);
CREATE INDEX IF NOT EXISTS ai_events_status ON ai_events(status, detected_at);
CREATE UNIQUE INDEX IF NOT EXISTS ai_events_unico ON ai_events(kind, entity_type, entity_id);

CREATE UNIQUE INDEX IF NOT EXISTS automation_rules_name ON automation_rules(name);
INSERT OR IGNORE INTO automation_rules (name, enabled, trigger, conditions, actions) VALUES
  ('mensalidade_dia_1', 1, '{"event":"billing.monthly"}', NULL, '{"ia":"montar a invoice mensal de cada cliente com plano e deixar pronta para aprovação (aprovar = enviar)"}'),
  ('tarefa_vencida',   1, '{"event":"task.overdue"}',   NULL, '{"ia":"conferir se o serviço aconteceu e mover para Finished Services"}'),
  ('novo_servico',     1, '{"event":"task.created"}',   '{"sections":"dias"}', '{"ia":"preparar waiver e invoice do serviço; propor ações"}'),
  ('email_cliente',    1, '{"event":"email.received"}', '{"client_known":true}', '{"ia":"ler a thread, classificar, propor resposta em rascunho"}'),
  ('waiver_devolvida', 1, '{"event":"waiver.bounced"}', NULL, '{"ia":"achar e-mail correto no Asana/Gmail e propor reenvio"}'),
  ('pagamento_confirmado', 1, '{"event":"invoice.paid"}', NULL, '{"sistema":"fechar a subtarefa de pagamento da tarefa do serviço e comentar o que foi pago"}'),
  ('waiver_assinada',  1, '{"event":"waiver.completed"}', NULL, '{"ia":"comentar na tarefa do Asana que a waiver chegou"}');

-- ------------------------------------------------- fontes de contexto da IA
-- Planilhas, arquivos e links que o dono cadastra para a IA consultar.
-- Arquivos ficam em ~/.urace/context/ (fora do repo) e são copiados para o
-- workspace do agente (contexto/), onde ele consegue ler.
CREATE TABLE IF NOT EXISTS context_sources (
  id            INTEGER PRIMARY KEY,
  kind          TEXT NOT NULL CHECK (kind IN ('sheet','file','link')),
  title         TEXT NOT NULL,
  description   TEXT,                     -- para que serve / quando usar
  url           TEXT,                     -- link original (planilha, doc)
  sheet_id      TEXT,                     -- id da planilha do Google
  sheet_range   TEXT,                     -- aba/intervalo sugerido
  path          TEXT,                     -- arquivo no disco (~/.urace/context/...)
  text_path     TEXT,                     -- texto extraído (PDF -> .txt)
  mime          TEXT,
  size          INTEGER,
  active        INTEGER NOT NULL DEFAULT 1,
  added_by      INTEGER REFERENCES users(id),
  added_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  last_check_at TEXT,
  last_check_ok INTEGER,
  last_check_msg TEXT
);
INSERT OR IGNORE INTO context_sources (id, kind, title, description, url, sheet_id, sheet_range)
  VALUES (1, 'sheet', 'Rate Card 2026', 'Fonte de verdade dos preços (acima do catálogo do QuickBooks). Serviços, corridas, Academy, mecânico, aluguel.',
          'https://docs.google.com/spreadsheets/d/160efDlmavKKGbtGfJKCTOV_3Q9JEO3Lc6xA1mEMMNyo', '160efDlmavKKGbtGfJKCTOV_3Q9JEO3Lc6xA1mEMMNyo', 'A1:F80');

-- Regra do dono (09/09) sobre como ler a Rate Card: vale mesmo em banco já criado
UPDATE context_sources SET description = 'Fonte de verdade dos preços (acima do catálogo do QuickBooks). CORRIDA → aba "Racing team". TREINO (Urace Daily, Academy, Arrive and Drive, Summer Camp, Test Drive) → aba "Academy". Ler a aba certa antes de dar qualquer valor.', sheet_range = 'Academy!A1:F80'
  WHERE sheet_id = '160efDlmavKKGbtGfJKCTOV_3Q9JEO3Lc6xA1mEMMNyo' AND (description NOT LIKE '%Racing team%' OR sheet_range = 'A1:F80');
INSERT OR IGNORE INTO ai_learnings (id, scope, text, source_key) VALUES
  (1, 'global', 'Preço: corrida usa a aba "Racing team" da Rate Card; treino (Urace Daily, Academy, Arrive and Drive, Summer Camp, Test Drive) usa a aba "Academy". Nunca dê valor sem ler a aba certa.', 'dono-2026-09-09'),
  (2, 'global', 'Produtos do quadro: "Urace Daily" = treino avulso (Practice e Professional Coaching são Daily); "Academy" = mensal com 4 sessões, nome da tarefa leva [1/4]…[4/4]; "Corrida" = Race Support / Trackside Support. O nome da tarefa segue Piloto_Produto_Categoria [n/total].', 'dono-2026-09-09');

-- Regras de preço ditadas pelo dono em 09/09 (Rate Card, aba Academy) — memória inicial da IA
INSERT OR IGNORE INTO ai_learnings (id, scope, text, source_key) VALUES
  (3, 'global', 'Diária (Urace Daily / Arrive and Drive, tudo incluso: mecânico, coaching e equipamento de segurança): Using Own Kart $500 (4 anos ou mais); Baby Kart $719 (4 a 7 anos); 4 stroke $719 (7 ou mais); 2 stroke $819 (7 ou mais); Adult Shifter $899 (14 ou mais, só com experiência). Conferir na aba Academy antes de usar.', 'dono-2026-09-09'),
  (4, 'global', 'Lead and Follow coaching (o coach vai para a pista junto com o piloto, 2T): fechado com antecedência é SEMPRE $769 por piloto. Os "last minute deals" ($395 um piloto, $245 cada com dois) só o operador fecha na pista; os mecânicos avisam depois para montar a invoice. Pacote de 5 sessões: $3.460,50 (10% off, $692,10 por sessão).', 'dono-2026-09-09'),
  (5, 'global', 'Mensal Academy sem contrato (4 sessões por mês; sessão extra = mensal ÷ 4): kart próprio + mecânico $1.200 (extra $300); kart próprio $1.800 (extra $450); Baby Kart $2.756,90 (extra $689,23); 4 stroke $2.756,90 (extra $689,23); 2 stroke $3.156,90 (extra $789,23). Contratos de 6 meses (27 sessões, 4% off) e 12 meses (54 sessões, 8% off) estão detalhados na aba Academy.', 'dono-2026-09-09'),
  (6, 'global', 'Treino fora do Orlando Kart Center (ex.: semana em Jacksonville ou Homestead) cobra $250 extra POR SESSÃO de hotel, comida e transporte.', 'dono-2026-09-09'),
  (7, 'global', 'Invoice ligada a esses produtos NUNCA sai sozinha: proponha qbo_criar_e_enviar_invoice com cliente, linhas e valores exatos, e ela vai para Aprovações com prévia. Aprovar = enviar. Mensalidade recorrente é montada no dia 1 do mês, uma por cliente com plano, e fica pronta esperando aprovação.', 'dono-2026-09-09');

INSERT OR IGNORE INTO ai_learnings (id, scope, text, source_key) VALUES
  (8, 'global', 'Waiver assinada vale UM ANO a partir da assinatura (decisão de 31/08). Se o piloto tem waiver assinada há menos de um ano, NÃO pergunte e NÃO peça de novo; só peça quando não houver ou estiver vencida.', 'dono-2026-09-10'),
  (10, 'global', 'Invoice de serviço: vencimento (due date) SEMPRE 2 dias antes da data do serviço (serviço dia 13 → vence dia 11). A nota ao cliente (Note to customer) e o memo interno (Memo on statement) são IGUAIS e trazem produto, categoria, piloto e a data do serviço, ex.: "Urace Daily | Using Own Kart | David Pera | Service date: 09/13/2026".', 'dono-2026-09-10'),
  (9, 'global', '"Mesmo esquema" / "mesma coisa da última vez" = repita o último serviço do piloto: mesmo produto, categoria e pista, mesmo valor da última invoice do responsável no QuickBooks, na coluna do dia pedido. Não pergunte o que o histórico já responde: crie a tarefa e proponha a invoice de uma vez, com os ids que vêm no CONTEXTO DO PAINEL.', 'dono-2026-09-10');

-- Regras antigas do dono que a IA do painel também precisa saber (revisão de 10/09)
INSERT OR IGNORE INTO ai_learnings (id, scope, text, source_key) VALUES
  (11, 'global', 'Security deposit é UM POR CLIENTE enquanto estiver retido. Antes de cobrar depósito, confira no QuickBooks: nunca teve → cobra; já foi devolvido → cobra de novo; ainda retido → NÃO cobra; não deu para determinar → escale para o dono (decisão de 28/08).', 'dono-2026-08-28'),
  (12, 'global', 'Peça: preço do fornecedor + 15%, sempre, por peça (decisão de 31/08).', 'dono-2026-08-31'),
  (13, 'global', 'Cobrança de invoice atrasada é POR LOTE: só invoice OVERDUE, no máximo a cada 2 dias, e com "ok" do dono a cada lote — "ok" num lote não vale para o próximo. Saldo em aberto não é inadimplência (pode ser parcelamento).', 'dono-2026-08-31'),
  (14, 'global', 'Não existe modelo de e-mail de invoice: o envio sai do próprio QuickBooks, no botão de enviar. O trabalho da IA termina na invoice salva com número, link e memo certos. Nunca mande a invoice por Gmail.', 'dono-2026-08-31'),
  (15, 'global', 'Preço: o valor que o dono disser manda; depois a Rate Card; o catálogo do QuickBooks é só referência. NUNCA repita o valor da última invoice sem conferir a Rate Card — o painel marca a proposta com "confira o preço" quando o valor não veio do dono nem do catálogo.', 'dono-2026-09-10');

-- catálogo do QuickBooks (espelho, só leitura): a IA recebe os ids no comando e o painel resolve item pelo nome
CREATE TABLE IF NOT EXISTS qbo_items (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  full_name   TEXT,
  price       REAL,
  type        TEXT,
  active      INTEGER NOT NULL DEFAULT 1,
  synced_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- ------------------------------------------------- equipamento (editável pelo dono)
CREATE TABLE IF NOT EXISTS catalog_chassis (
  id          INTEGER PRIMARY KEY,
  brand       TEXT NOT NULL,             -- Tony Kart, Parolin, OTK, CRG, Birel ART, Kosmic…
  model       TEXT,
  size        TEXT,                      -- Cadet / Mini / Junior / Senior / Shifter
  tire_front  TEXT,                      -- ex.: 10x4.60-5
  tire_rear   TEXT,                      -- ex.: 11x7.10-5
  notes       TEXT,
  image_path  TEXT,
  active      INTEGER NOT NULL DEFAULT 1,
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS catalog_engines (
  id          INTEGER PRIMARY KEY,
  brand       TEXT NOT NULL,             -- IAME, Tillotson, Rotax, Vortex, Briggs…
  model       TEXT NOT NULL,             -- KA100, X30, T225RS, Mini Swift, 206
  stroke      TEXT,                      -- 2T / 4T
  category    TEXT,                      -- Cadet, Junior, Senior, Shifter
  notes       TEXT,
  image_path  TEXT,
  active      INTEGER NOT NULL DEFAULT 1,
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS catalog_parts (
  id          INTEGER PRIMARY KEY,
  engine_id   INTEGER REFERENCES catalog_engines(id),
  name        TEXT NOT NULL,
  part_number TEXT,
  price       REAL,                      -- referência; a Rate Card/QBO mandam
  notes       TEXT,
  active      INTEGER NOT NULL DEFAULT 1
);
INSERT OR IGNORE INTO catalog_chassis (id, brand, model, size, tire_front, tire_rear, notes) VALUES
  (1, 'Tony Kart', 'Racer 401RR', 'Senior', '10x4.60-5', '11x7.10-5', 'OTK; o mais usado nos EUA'),
  (2, 'Tony Kart', 'Rookie', 'Cadet', '10x4.00-5', '11x5.00-5', 'OTK cadet'),
  (3, 'Parolin', 'Le Mans', 'Senior', '10x4.60-5', '11x7.10-5', ''),
  (4, 'Parolin', 'Rocky', 'Cadet', '10x4.00-5', '11x5.00-5', ''),
  (5, 'Kosmic', 'Mercury', 'Senior', '10x4.60-5', '11x7.10-5', 'OTK'),
  (6, 'CRG', 'KT2', 'Senior', '10x4.60-5', '11x7.10-5', ''),
  (7, 'Birel ART', 'RY30', 'Senior', '10x4.60-5', '11x7.10-5', '');
INSERT OR IGNORE INTO catalog_engines (id, brand, model, stroke, category, notes) VALUES
  (1, 'IAME', 'KA100', '2T', 'Junior/Senior', '100cc, partida elétrica; peças IAME'),
  (2, 'IAME', 'X30', '2T', 'Junior/Senior', '125cc TaG'),
  (3, 'IAME', 'Mini Swift', '2T', 'Cadet', '60cc'),
  (4, 'IAME', 'SSE 175', '2T', 'Shifter', 'shifter'),
  (5, 'Tillotson', 'T225RS', '4T', 'Junior/Senior', '4 tempos'),
  (6, 'Briggs & Stratton', 'LO206', '4T', 'Junior/Senior', '4 tempos lacrado'),
  (7, 'Rotax', 'MAX EVO', '2T', 'Junior/Senior', '125cc'),
  (8, 'Vortex', 'ROK GP', '2T', 'Senior', 'ROK Cup');

-- ------------------------------------------------- corridas e convites (Pro Racing Drivers)
CREATE TABLE IF NOT EXISTS races (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  series      TEXT,                      -- SKUSA, ROK, USPKS, FWT…
  track       TEXT,
  city        TEXT,
  date_start  TEXT,
  date_end    TEXT,
  notes       TEXT,
  source      TEXT,                      -- asana | manual
  active      INTEGER NOT NULL DEFAULT 1,
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS race_invites (
  id            INTEGER PRIMARY KEY,
  race_id       INTEGER NOT NULL REFERENCES races(id),
  client_id     INTEGER NOT NULL REFERENCES clients(id),
  status        TEXT NOT NULL DEFAULT 'invited' CHECK (status IN ('invited','confirmed','declined','done')),
  estimate_text TEXT,                    -- prévia de custo dada pela IA (não é invoice)
  estimate_cmd  INTEGER REFERENCES ai_commands(id),
  invited_by    INTEGER REFERENCES users(id),
  invited_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (race_id, client_id)
);

-- ------------------------------------------------- contratos (Academy) por cliente
CREATE TABLE IF NOT EXISTS contracts (
  id           INTEGER PRIMARY KEY,
  client_id    INTEGER NOT NULL REFERENCES clients(id),
  kind         TEXT NOT NULL DEFAULT 'academy',
  source       TEXT NOT NULL,            -- docusign | upload
  envelope_id  TEXT,
  status       TEXT,                     -- completed, sent…
  signed_at    TEXT,
  file_path    TEXT,
  title        TEXT,
  added_by     INTEGER REFERENCES users(id),
  added_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS contracts_client ON contracts(client_id);

-- ------------------------------------------------- ESTOQUE (módulo 5, a espinha)
-- Duas decisões do dono, 22/09, e o modelo inteiro sai delas:
--   1. "chassi e motor: ficha individual com número de série; pneu e peça: quantidade"
--      → dois comportamentos, duas tabelas de saldo: `stock_units` e `stock_levels`.
--      Misturar num modelo só é o erro clássico que trava o sistema depois.
--   2. "dois locais: sede e trailer de corrida" → `stock_locations`, e transferência
--      entre eles é um movimento como qualquer outro, não uma edição de número.
-- Fronteira com o QuickBooks: o painel manda no estoque FÍSICO, o QuickBooks manda no
-- FINANCEIRO. Quantidade controlada dos dois lados diverge, e aí ninguém acredita em
-- nenhum dos dois.
CREATE TABLE IF NOT EXISTS stock_locations (
  id          INTEGER PRIMARY KEY,
  code        TEXT NOT NULL UNIQUE,      -- sede | trailer
  name        TEXT NOT NULL,
  kind        TEXT NOT NULL DEFAULT 'fixo' CHECK (kind IN ('fixo','movel')),
  active      INTEGER NOT NULL DEFAULT 1,
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
INSERT OR IGNORE INTO stock_locations (id, code, name, kind) VALUES
  (1, 'sede',    'Sede',             'fixo'),
  (2, 'trailer', 'Trailer de corrida','movel');

-- O QUE é, não a peça física. Liga no catálogo quando o modelo já existe lá.
CREATE TABLE IF NOT EXISTS stock_items (
  id            INTEGER PRIMARY KEY,
  kind          TEXT NOT NULL CHECK (kind IN ('chassi','motor','pneu','peca')),
  -- `tracking` é derivado de `kind`, mas fica explícito: é ele que o código lê, e um
  -- dia pode existir peça cara com número de série.
  tracking      TEXT NOT NULL CHECK (tracking IN ('serie','quantidade')),
  name          TEXT NOT NULL,
  -- A base das peças é o catálogo da Comet Kart Sales (dono, 22/09), e o SKU é
  -- **referência de compra**, não identidade do item: é por ele que o módulo de compras
  -- (futuro) vai saber o que pedir e onde. Item pode existir sem SKU — peça avulsa,
  -- usado, coisa que veio de outro lugar. Fornecedor fica explícito porque um dia
  -- haverá outro.
  sku           TEXT,
  supplier      TEXT DEFAULT 'comet',
  supplier_url  TEXT,
  part_number   TEXT,                          -- número do fabricante (IAME, OTK…), quando houver
  chassis_id    INTEGER REFERENCES catalog_chassis(id),
  engine_id     INTEGER REFERENCES catalog_engines(id),
  part_id       INTEGER REFERENCES catalog_parts(id),
  unit          TEXT NOT NULL DEFAULT 'un',   -- un, par, jogo, litro
  min_qty       REAL,                          -- estoque mínimo; só vale em 'quantidade'
  notes         TEXT,
  active        INTEGER NOT NULL DEFAULT 1,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS stock_items_kind ON stock_items(kind, active);
CREATE INDEX IF NOT EXISTS stock_items_pn ON stock_items(part_number);
-- Dois itens com o mesmo SKU do mesmo fornecedor são o mesmo item cadastrado duas vezes
-- — e aí a compra pediria em dobro. Item sem SKU não entra no índice.
CREATE UNIQUE INDEX IF NOT EXISTS stock_items_sku
  ON stock_items(supplier, sku) WHERE sku IS NOT NULL;

-- Unidade física com número de série: chassi e motor. Uma linha = uma coisa que existe.
CREATE TABLE IF NOT EXISTS stock_units (
  id           INTEGER PRIMARY KEY,
  item_id      INTEGER NOT NULL REFERENCES stock_items(id),
  serial       TEXT NOT NULL,
  location_id  INTEGER REFERENCES stock_locations(id),
  -- "peça que está com a URACE mas é do cliente" (dono): `client_id` preenchido é peça
  -- de cliente. Ela NUNCA é vendável para outro — a trava está em `estoque.py`.
  client_id    INTEGER REFERENCES clients(id),
  status       TEXT NOT NULL DEFAULT 'disponivel'
               CHECK (status IN ('disponivel','em_uso','em_servico','emprestado','vendido','baixado')),
  acquired_at  TEXT,
  notes        TEXT,
  created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
-- Número de série não repete dentro do mesmo item. Entre itens diferentes pode.
CREATE UNIQUE INDEX IF NOT EXISTS stock_units_serie ON stock_units(item_id, serial);
CREATE INDEX IF NOT EXISTS stock_units_local ON stock_units(location_id, status);
CREATE INDEX IF NOT EXISTS stock_units_cliente ON stock_units(client_id);

-- Saldo de quantidade: pneu e peça de consumo. Uma linha por item × local × dono.
CREATE TABLE IF NOT EXISTS stock_levels (
  id           INTEGER PRIMARY KEY,
  item_id      INTEGER NOT NULL REFERENCES stock_items(id),
  location_id  INTEGER NOT NULL REFERENCES stock_locations(id),
  client_id    INTEGER REFERENCES clients(id),   -- NULL = da URACE
  qty          REAL NOT NULL DEFAULT 0,
  updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
-- COALESCE no índice porque NULL não é igual a NULL em UNIQUE: sem isto, o estoque da
-- URACE criaria uma linha nova a cada movimento e o saldo se espalharia em pedaços.
CREATE UNIQUE INDEX IF NOT EXISTS stock_levels_chave
  ON stock_levels(item_id, location_id, COALESCE(client_id, 0));

-- O razão: toda mudança de saldo passa por aqui, e daqui nada sai. `conferir()` refaz o
-- saldo a partir destes movimentos e acusa divergência — é o que impede o número de
-- virar opinião.
CREATE TABLE IF NOT EXISTS stock_moves (
  id           INTEGER PRIMARY KEY,
  kind         TEXT NOT NULL
               CHECK (kind IN ('entrada','saida','ajuste','transferencia','contagem')),
  item_id      INTEGER NOT NULL REFERENCES stock_items(id),
  unit_id      INTEGER REFERENCES stock_units(id),   -- quando é chassi/motor
  qty          REAL NOT NULL DEFAULT 0,              -- sempre positiva; `kind` diz o sinal
  from_location_id INTEGER REFERENCES stock_locations(id),
  to_location_id   INTEGER REFERENCES stock_locations(id),
  client_id    INTEGER REFERENCES clients(id),       -- dono da peça movida
  reason       TEXT,                                  -- venda, uso em serviço, envio, compra…
  task_id      INTEGER REFERENCES tasks(id),
  invoice_id   INTEGER REFERENCES invoices(id),
  qty_before   REAL,                                  -- saldo antes/depois, para conferência
  qty_after    REAL,
  by_user_id   INTEGER REFERENCES users(id),
  source       TEXT NOT NULL DEFAULT 'painel',        -- painel | ia | sync
  notes        TEXT,
  at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS stock_moves_item ON stock_moves(item_id, at);
CREATE INDEX IF NOT EXISTS stock_moves_unit ON stock_moves(unit_id, at);
CREATE INDEX IF NOT EXISTS stock_moves_cliente ON stock_moves(client_id, at);

-- ------------------------------------------------- catálogo do fornecedor (espelho)
-- O catálogo da Comet é REFERÊNCIA DE COMPRA (dono, 22/09), não o nosso estoque: eles
-- vendem milhares de peças e nós carregamos uma fração. Por isso duas tabelas —
-- `supplier_products` é o que dá para comprar, `stock_items` é o que temos. Um item
-- vira estoque quando passamos a carregá-lo, ligado pelo SKU.
CREATE TABLE IF NOT EXISTS supplier_products (
  id            INTEGER PRIMARY KEY,
  supplier      TEXT NOT NULL DEFAULT 'comet',
  sku           TEXT NOT NULL,
  name          TEXT NOT NULL,
  url           TEXT,
  price         REAL,
  currency      TEXT NOT NULL DEFAULT 'USD',
  brand         TEXT,
  category      TEXT,
  available     INTEGER,
  image_url     TEXT,
  -- O json de origem inteiro. O que hoje não sei mapear não se perde, e amanhã dá para
  -- reprocessar sem incomodar o site deles de novo.
  raw           TEXT,
  first_seen_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  last_seen_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  -- Produto que sumiu do catálogo é MARCADO, nunca apagado: o histórico de compra
  -- continua apontando para ele.
  gone_at       TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS supplier_products_sku ON supplier_products(supplier, sku);
CREATE INDEX IF NOT EXISTS supplier_products_nome ON supplier_products(name);
CREATE INDEX IF NOT EXISTS supplier_products_cat ON supplier_products(supplier, category);
