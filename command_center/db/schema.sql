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
  ('gmail','DISCONNECTED'), ('quickbooks','DISCONNECTED');

-- A política inicial vem do cérebro (PARAMETROS + decisões de 04/09).
INSERT OR IGNORE INTO action_policies (action, policy, note) VALUES
  ('asana_buscar','SAFE','leitura'),
  ('asana_tarefa','SAFE','leitura'),
  ('asana_criar_tarefa','SAFE','criar tarefa: autorizado pelo dono (31/08)'),
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
