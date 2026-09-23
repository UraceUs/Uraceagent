"""Acesso ao banco do Command Center. SQLite, sem ORM.

Uma conexão por requisição (FastAPI injeta via `get_db`), `Row` como
dict, `foreign_keys` ligado. O esquema é aplicado em toda subida — cada
bloco de schema.sql é idempotente.

O arquivo do banco fica FORA do repositório, em ~/.urace/ por padrão,
ao lado dos outros segredos (permissão 600).
"""
import json
import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(AQUI, "schema.sql")
URACE_DIR = os.environ.get("URACE_DIR", os.path.expanduser("~/.urace"))
def db_path():
    """Lido a cada chamada: testes e serviços trocam pelo ambiente."""
    return os.environ.get("CC_DB_PATH", os.path.join(
        os.environ.get("URACE_DIR", os.path.expanduser("~/.urace")), "command-center.sqlite"))


def agora():
    """ISO-8601 em UTC com milissegundos — o mesmo formato do schema."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
        f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"


def conectar(caminho=None):
    caminho = caminho or db_path()
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    novo = not os.path.exists(caminho)
    # check_same_thread=False: o FastAPI abre a dependência num thread do pool
    # e roda o endpoint em outro. A conexão é de UMA requisição, nunca é
    # compartilhada entre duas ao mesmo tempo, então é seguro.
    con = sqlite3.connect(caminho, timeout=10, isolation_level=None,  # autocommit
                          check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 10000")
    # Em TESTE, o banco é descartável: gravar com segurança de queda de energia não
    # protege nada e custa caro. Medido na VPS em 21/09: cada fixture levava ~2 s só
    # criando a schema (o disco é volume de rede, e cada CREATE TABLE sincroniza), o que
    # colocava 170 s no deploy e fazia o terminal do dono cair antes do fim.
    #
    # Em produção NADA muda — e a trava é a mesma do custo da senha: isto só vale com o
    # pytest carregado no processo. Não há variável de ambiente que desligue a durabilidade
    # do banco de verdade, nem por engano nem de propósito.
    # Só `synchronous`: trocar `journal_mode` pede lock exclusivo e falha quando outra
    # conexão está com o banco aberto — um teste pegou isso na hora (21/09). O ganho está
    # no fsync mesmo; o journal em memória acrescentava pouco e trazia essa fragilidade.
    if "pytest" in sys.modules:
        con.execute("PRAGMA synchronous = OFF")
    if novo:
        try:
            os.chmod(caminho, 0o600)
        except OSError:
            pass
    return con


# Colunas acrescentadas depois do primeiro deploy: CREATE TABLE IF NOT EXISTS
# não as adiciona em banco existente; cada linha aqui é idempotente.
MIGRACOES = [
    ("tasks", "fields", "TEXT"),          # campos personalizados do Asana (json)
    ("tasks", "section_gid", "TEXT"),
    ("emails", "snippet", "TEXT"),
    ("emails", "is_inbox", "INTEGER NOT NULL DEFAULT 1"),
    ("emails", "messages", "INTEGER"),
    ("emails", "suggested_label", "TEXT"),   # sugestão da IA/regras: para onde mover
    ("emails", "suggested_reason", "TEXT"),
    ("emails", "suggested_by", "TEXT"),      # rules | ia | label (já tinha marcador)
    ("emails", "suggested_at", "TEXT"),
    ("emails", "triaged_at", "TEXT"),        # triagem automática da IA (manhã/tarde/noite)
    ("emails", "triage_reason", "TEXT"),
    ("emails", "needs_human", "INTEGER NOT NULL DEFAULT 0"),  # movido pela IA, mas pede resposta humana
    ("automation_rules", "schedule", "TEXT"),      # json: ["07:00","13:00","21:00"] hora local (Orlando)
    ("automation_rules", "last_run_at", "TEXT"),   # chave do último horário rodado: "2026-09-09 07:00"
    ("automation_rules", "last_result", "TEXT"),
    ("races", "task_id", "INTEGER"),
    ("clients", "email_alt", "TEXT"),
    ("ai_commands", "prompt", "TEXT"),              # o que foi ao agente (texto do dono + contexto); `text` é só o que o dono escreveu              # segundo e-mail da descrição (o principal fica limpo)               # tarefa da coluna RACES (calendário = o que está no Asana)
    ("gmail_labels", "mailboxes", "TEXT"),         # json: em que caixas o marcador existe, ex. ["urace","support"]
    ("gmail_labels", "origin", "TEXT"),            # caixa | ia (marcador que a IA propôs, ainda não existe no Gmail)
    ("gmail_labels", "proposed_reason", "TEXT"),   # o e-mail que motivou a proposta
    ("waivers", "hidden", "INTEGER NOT NULL DEFAULT 0"),   # lixeira do painel (restaurável)
    ("waivers", "minor_name", "TEXT"),                     # nome do menor (parental), do form data
    ("waivers", "link_reason", "TEXT"),                    # por que está ligada a este cliente
    ("waivers", "link_by", "TEXT"),                        # sync | human
    ("clients", "status_locked", "INTEGER NOT NULL DEFAULT 0"),  # status mudado à mão não é recalculado
    ("clients", "last_service_at", "TEXT"),
    ("clients", "scanned_at", "TEXT"),                     # última varredura Gmail/DocuSign deste cliente
    ("emails", "handled_by", "TEXT"),                      # user:<id> | auto
    ("emails", "handled_reason", "TEXT"),
    ("clients", "monthly_plan", "TEXT"),                  # ex.: "Academy 4 stroke" — gera a invoice do dia 1
    ("clients", "monthly_note", "TEXT"),                  # ajustes do plano (extra, desconto de contrato)
    ("clients", "plan_type", "TEXT"),                     # monthly | daily
    ("clients", "pro_driver", "INTEGER NOT NULL DEFAULT 0"),  # estrela: pronto para competir
    ("clients", "chassis_id", "INTEGER"),
    ("clients", "engine_id", "INTEGER"),
    ("clients", "equipment_notes", "TEXT"),
    ("invoices", "memo", "TEXT"),                         # ex.: "Urace Academy Training Program + Tuner [August, 2026]"
    ("invoices", "customer_email", "TEXT"),
    ("invoices", "customer_ref", "TEXT"),                 # id do cliente no QBO (a IA usa direto na próxima invoice)
    ("waivers", "pdf_path", "TEXT"),                      # PDF assinado guardado em ~/.urace/waivers (card e anexo usam)
    ("waivers", "subject", "TEXT"),                       # assunto do envelope: é o que identifica um documento interno
    ("waivers", "internal", "INTEGER NOT NULL DEFAULT 0"), # 1 = documento da empresa (support@ assina); não é waiver de cliente
    ("tasks", "waiver_id", "INTEGER"),                    # waiver que já foi anexada nesta tarefa (não anexa duas vezes)
    ("crm_messages", "status", "TEXT"),                   # saída: queued | sent | failed (entrada fica NULL)
    ("crm_messages", "error", "TEXT"),
    ("crm_leads", "return_url", "TEXT"),                  # continuação do Salesbot em aberto (efêmera)
    ("crm_leads", "return_token", "TEXT"),
    ("crm_leads", "return_at", "TEXT"),
    ("crm_leads", "last_hook_at", "TEXT"),                # última vez que o bot falou com o painel por este lead
    ("crm_leads", "link_by", "TEXT"),
    ("crm_leads", "detail", "TEXT"),                      # retrato completo do lead no Kommo (json de kommo_lead_completo)
    ("crm_leads", "detail_at", "TEXT"),
    ("crm_leads", "starred", "INTEGER"),                   # conversa favorita (estrela na lista do chat)
    ("crm_messages", "starred", "INTEGER"),                # mensagem favorita dentro da conversa
    ("crm_leads", "contact_avatar", "TEXT"),               # foto do perfil que o Kommo manda no webhook (author.avatar_url)
    ("crm_leads", "profiles", "TEXT"),                     # json {instagram: "@usuario", facebook: "url"} informado no painel                     # human = vínculo com o cliente feito à mão (a sincronia não mexe)
    # 21/09: entregar uma vez e torcer não é entregar. A fila agora insiste sozinha e a
    # entrega só é dada por certa quando o próprio Kommo devolve a mensagem.
    ("crm_messages", "tentativas", "INTEGER NOT NULL DEFAULT 0"),
    ("crm_messages", "ultima_tentativa", "TEXT"),
    ("crm_messages", "confirmado_em", "TEXT"),             # o Kommo devolveu esta mensagem: chegou mesmo
    ("api_keys", "read_only", "INTEGER NOT NULL DEFAULT 1"),   # chave que lê e não mexe (padrão)
    # 21/09, o dono explicando a intenção do chat interno: falar com uma pessoa em um
    # clique, montar grupo com nome e foto, e poder silenciar os dois.
    ("team_channels", "icon", "TEXT"),        # emoji do grupo (o barato: não precisa de upload)
    ("team_channels", "image_path", "TEXT"),  # foto do grupo, guardada fora do repositório
    # conversa direta entre duas pessoas: "menor-maior" dos ids. O UNIQUE é o que impede
    # duas conversas paralelas entre as mesmas pessoas — cada uma com metade do histórico.
    ("team_channels", "dm_key", "TEXT"),
    # 22/09 — dono: "pode só separar". Card que é corrida/tarefa não é apagado: sai da
    # lista de clientes com kind='separado', e continua consultável.
    ("clients", "kind", "TEXT NOT NULL DEFAULT 'cliente'"),
    # 22/09 — dono: "o princípio para cruzar e confirmar é usar o nome do responsável e
    # informações de contato" — e "aplique como base de agora para frente". A sincronia
    # já lia isso da descrição da tarefa e jogava fora; agora fica na tarefa, para a
    # atribuição decidir por contato antes de olhar o título.
    ("tasks", "resp_name", "TEXT"),
    ("tasks", "resp_email", "TEXT"),
    ("tasks", "resp_phone", "TEXT"),
    ("tasks", "desc_read_at", "TEXT"),
    # 22/09 — o dono CONFIRMOU de quem é o serviço. A varredura nunca mexe nisso de novo:
    # "está certo hoje" não basta, porque um homônimo novo no cadastro faria o serviço sair.
    ("tasks", "client_by", "TEXT"),        # sync | human
    ("tasks", "client_at", "TEXT"),   # quando a descrição foi lida — mesmo que não tivesse contato nenhum
    # Foto da peça, tirada pelo mecânico no celular (dono, 23/09). Só o nome do arquivo:
    # a imagem mora em ~/.urace/estoque, fora do banco e fora do repositório.
    ("stock_items", "image_path", "TEXT"),
]
INDICES_EXTRA = [
    "CREATE UNIQUE INDEX IF NOT EXISTS team_channels_dm ON team_channels(dm_key) WHERE dm_key IS NOT NULL",
]


def aplicar_schema(con):
    with open(SCHEMA, encoding="utf-8") as f:
        con.executescript(f.read())
    for tabela, coluna, tipo in MIGRACOES:
        existentes = {r[1] for r in con.execute(f"PRAGMA table_info({tabela})")}
        if coluna not in existentes:
            con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
    for sql in INDICES_EXTRA:        # índices de colunas que só existem depois da migração
        con.execute(sql)
    _migrar_papeis(con)              # o papel CLOSER foi desfeito: quem tiver vira OPERATOR
    _semear_marcadores(con)          # depois das migrações: a semente escreve `mailboxes`
    for sql in POS_MIGRACAO:
        con.execute(sql)


def _migrar_papeis(con):
    """O papel CLOSER existiu por algumas horas em 17/09 e foi desfeito na mesma tarde
    ("vendas e operador devem ser a mesma coisa, com os acessos de operador"). Quem tiver
    ficado com ele vira OPERATOR — o CHECK antigo do banco aceita os dois, então não é
    preciso recriar a tabela."""
    con.execute("UPDATE users SET role='OPERATOR' WHERE role='CLOSER'")


def _semear_marcadores(con):
    """Manual dos marcadores do Gmail. O dono confirmou os 145 em 11/09 (marcador por
    marcador): a semente traz esse estado para quem ainda está `pendente`. Nunca
    desfaz o que ele mudar depois no painel — só promove pendente → confirmado."""
    from command_center.providers.taxonomia_gmail import MANUAL, MANUAL_SUPPORT, CONFIRMADO_POR
    livros = (("urace", MANUAL), ("support", MANUAL_SUPPORT))
    for caixa, nome, familia, o_que, threads, estado in (
            (c, *linha) for c, livro in livros for linha in livro):
        con.execute("""INSERT INTO gmail_labels (name, family, what, threads, status, mailboxes, confirmed_by, confirmed_at)
                       VALUES (?,?,?,?,?,?,
                               CASE WHEN ?='confirmado' THEN ? END,
                               CASE WHEN ?='confirmado' THEN strftime('%Y-%m-%dT%H:%M:%fZ','now') END)
                       ON CONFLICT(name) DO UPDATE SET
                         family=excluded.family,
                         mailboxes=COALESCE(gmail_labels.mailboxes, excluded.mailboxes),
                         what=CASE WHEN gmail_labels.status='pendente' THEN excluded.what ELSE gmail_labels.what END,
                         threads=COALESCE(gmail_labels.threads, excluded.threads),
                         status=CASE WHEN gmail_labels.status='pendente' THEN excluded.status ELSE gmail_labels.status END,
                         confirmed_by=CASE WHEN gmail_labels.status='pendente' AND excluded.status='confirmado'
                                           THEN ? ELSE gmail_labels.confirmed_by END,
                         confirmed_at=CASE WHEN gmail_labels.status='pendente' AND excluded.status='confirmado'
                                           THEN strftime('%Y-%m-%dT%H:%M:%fZ','now') ELSE gmail_labels.confirmed_at END""",
                    (nome, familia, o_que, threads, estado, json.dumps([caixa]),
                     estado, CONFIRMADO_POR, estado, CONFIRMADO_POR))


# Sementes que dependem de coluna criada por migração (rodam depois dela).
# Horários em hora local de Orlando; quem lê é command_center/api/agenda.py.
# --------------------------------------------------------- portão do APLICAR, revisado
# O dono respondeu as 42 ações uma a uma em 21/09 (página editável). Cada linha abaixo só
# troca a política SE ela ainda for a que estava valendo — o que ele mudar depois no painel
# fica. Isso é o que torna a revisão idempotente e não atropela decisão posterior.
#
# 22/09, segunda rodada: perguntei as seis que tinha segurado e ele respondeu uma a uma.
#   · apagar_cliente e qbo_apagar: MANTER em "nunca" — ele confirmou o que eu tinha
#     segurado. Cliente e contabilidade não se apagam, ponto.
#   · apagar_qualquer_coisa: ele ABRIU para aprovação. É a regra guarda-chuva — e abrir só
#     faz sentido se ela de fato guardar alguma coisa, o que até ontem não acontecia (ver
#     `piso_de_apagar` em api/ia.py).
#   · docusign_send_reminder e gmail_rotular: ele escolheu a REGRA, não só o portão. A
#     política abre, e a condição virou trava no servidor — é lá que ela protege.
#   · venda_tarefa: era toque errado mesmo. Continua fazendo sozinha.
REVISAO_21_09 = [
    # afrouxaram (decisão dele)
    ("docusign_enviar_waiver", "REQUIRES_APPROVAL", "SAFE"),
    ("docusign_reenviar_waiver", "REQUIRES_APPROVAL", "SAFE"),
    ("docusign_anular_envelope", "REQUIRES_APPROVAL", "REQUIRES_CONFIRMATION"),
    ("venda_enviar_waiver", "REQUIRES_CONFIRMATION", "SAFE"),
    ("venda_enviar_invoice", "REQUIRES_APPROVAL", "REQUIRES_CONFIRMATION"),
    ("qbo_criar_invoice", "REQUIRES_CONFIRMATION", "SAFE"),
    ("qbo_enviar_invoice", "REQUIRES_APPROVAL", "REQUIRES_CONFIRMATION"),
    ("gmail_enviar", "BLOCKED", "REQUIRES_APPROVAL"),
    # apertou (decisão dele)
    ("venda_mover_etapa", "SAFE", "REQUIRES_CONFIRMATION"),
    # 22/09, com a regra escrita no servidor junto (sem a trava, isto seria perigoso)
    ("apagar_qualquer_coisa", "BLOCKED", "REQUIRES_APPROVAL"),
    ("gmail_rotular", "REQUIRES_CONFIRMATION", "SAFE"),
    ("docusign_send_reminder", "BLOCKED", "SAFE"),
]

POS_MIGRACAO = [
    # 16/09: o dono ditou a regra Docusign x Waivers depois de já ter confirmado os dois.
    # Troca o texto só se ainda for o que eu escrevi em 14/09 — o que ele editar fica.
    """UPDATE gmail_labels SET what='TODO e-mail do DocuSign, sem exceção (regra do dono, 16/09): enviado, visualizado, concluído, anulado, aviso da conta. Se for waiver enviada ou assinada, leva TAMBÉM o marcador ''Waivers''.'
       WHERE name='Softwares|Apps/Docusign' AND what LIKE 'DocuSign, TODO o tráfego de envelope%'""",
    """UPDATE gmail_labels SET what='WAIVER do DocuSign ENVIADA ao cliente ou RECEBIDA ASSINADA (regra do dono, 16/09). Vai SEMPRE junto com ''Softwares|Apps/Docusign'', nunca sozinho. Aviso de ''visualizou'' e ''anulada'' NÃO entra aqui. Ao marcar, a IA identifica de quem é, guarda o PDF no card do cliente e fecha a subtarefa da waiver nas tarefas dele.'
       WHERE name='Waivers' AND what LIKE 'WAIVER de responsabilidade no DocuSign: enviada, vista%'""",
    # o manual nasceu lendo só a urace@ (11/09). Quem não tem caixa é de lá.
    """UPDATE gmail_labels SET mailboxes='["urace"]' WHERE mailboxes IS NULL OR mailboxes=''""",
    """INSERT OR IGNORE INTO automation_rules (name, enabled, trigger, conditions, actions) VALUES
       ('gmail_triagem', 1, '{"schedule":true}', NULL,
        '{"ia":"ler cada e-mail da inbox, aplicar os marcadores e mover para o marcador principal"}')""",
    """INSERT OR IGNORE INTO automation_rules (name, enabled, trigger, conditions, actions) VALUES
       ('sondagem_integracoes', 1, '{"schedule":true}', NULL,
        '{"sistema":"sondar cada integração com uma chamada real; fora do horário, só se uma falhar"}')""",
    """UPDATE automation_rules SET schedule='["07:00","13:00","21:00"]' WHERE name='gmail_triagem' AND schedule IS NULL""",
    """UPDATE automation_rules SET schedule='["07:00","22:00"]' WHERE name='sondagem_integracoes' AND schedule IS NULL""",
    """INSERT OR IGNORE INTO automation_rules (name, enabled, trigger, conditions, actions) VALUES
       ('lembrete_invoice', 1, '{"schedule":true}', NULL,
        '{"sistema":"mandar o lembrete (reenvio da invoice pelo QuickBooks) de cada invoice em aberto com lembrete ligado e dia chegado"}')""",
    """UPDATE automation_rules SET schedule='["09:00"]' WHERE name='lembrete_invoice' AND schedule IS NULL""",
    """INSERT OR IGNORE INTO automation_rules (name, enabled, trigger, conditions, actions) VALUES
       ('varredura_clientes', 1, '{"schedule":true}', NULL,
        '{"sistema":"varrer o Gmail (as duas caixas) e o DocuSign de cada cliente ativo e ligar o que achar ao card"}')""",
    """UPDATE automation_rules SET schedule='["06:00"]' WHERE name='varredura_clientes' AND schedule IS NULL""",
    """INSERT OR IGNORE INTO automation_rules (name, enabled, trigger, conditions, actions) VALUES
       ('ratecard_semanal', 1, '{"schedule":true}', NULL,
        '{"sistema":"ler a URACE RATE CARD 2026 no Drive e aplicar os preços no QuickBooks, pelo mapa revisado"}')""",
    """UPDATE automation_rules SET schedule='["07:30"]' WHERE name='ratecard_semanal' AND schedule IS NULL""",
    # dono, 21/09: "preciso garantir que todas cheguem". Confere o chat contra o Kommo todo dia.
    """INSERT OR IGNORE INTO automation_rules (name, enabled, trigger, conditions, actions) VALUES
       ('conferir_chat', 1, '{"schedule":true}', NULL,
        '{"sistema":"conferir a conversa de cada lead no Kommo contra a do painel e avisar o que o painel nao recebeu"}')""",
    """UPDATE automation_rules SET schedule='["08:10"]' WHERE name='conferir_chat' AND schedule IS NULL""",
    """INSERT OR IGNORE INTO action_policies (action, policy, note) VALUES
       ('docusign_reenviar_waiver','REQUIRES_APPROVAL','reenvia/corrige e-mail do signatário: sai da empresa (dono, 17/09)'),
       ('docusign_anular_envelope','REQUIRES_APPROVAL','anula envelope em aberto; assinado nunca (dono, 17/09)'),
       ('docusign_renomear_modelo','REQUIRES_CONFIRMATION','só o nome do modelo (dono, 17/09)'),
       ('docusign_substituir_documento_modelo','REQUIRES_APPROVAL','troca o PDF do modelo com cópia do antigo (dono, 17/09)'),
       ('asana_criar_corrida','SAFE','corrida pelo modelo New Race, na coluna RACES (dono, 17/09)'),
       ('qbo_lembrete_invoice','SAFE','lembrete de invoice: o gerente escolhe quais, o disparo é da IA (dono, 17/09)'),
       ('venda_registrar_ligacao','SAFE','registro do closer na oportunidade, ditado ou digitado (dono, 17/09)'),
       ('venda_agendar_retorno','SAFE','retorno na agenda de vendas; nada sai para o cliente (dono, 17/09)'),
       ('venda_anotar','SAFE','anotação interna na oportunidade (dono, 17/09)'),
       ('venda_mover_etapa','SAFE','move a oportunidade no quadro de vendas (dono, 17/09)'),
       ('venda_tarefa','SAFE','tarefa/lembrete do fechamento: painel ou Asana (dono, 17/09)'),
       ('venda_enviar_waiver','REQUIRES_CONFIRMATION','waiver do serviço combinado, pelo modelo do DocuSign (dono, 17/09)'),
       ('venda_enviar_invoice','REQUIRES_APPROVAL','invoice fora da tabela de preços só com o dono (dono, 17/09)'),
       ('venda_fechar','REQUIRES_CONFIRMATION','fecha a venda e dispara cliente, QuickBooks, waiver, Asana e Kommo (dono, 17/09)'),
       ('painel_unir_clientes','SAFE','só com mesmo e-mail, telefone ou responsável; fora disso a ação recusa (dono, 17/09)'),
       ('painel_varrer_cliente','SAFE','Gmail + DocuSign do cliente: só leitura e espelho (dono, 17/09)'),
       ('painel_waiver_lixeira','REQUIRES_CONFIRMATION','tira do painel; em aberto anula no DocuSign (dono, 17/09)'),
       ('dialpad_ligar','REQUIRES_CONFIRMATION','discar pelo Dialpad: só a pedido de uma pessoa, nunca por conta da IA (dono, 18/09)'),
       ('qbo_atualizar_preco','SAFE','preço do catálogo vindo da Rate Card do Drive: o dono dispensou aprovação quando o valor é o dela (18/09); peça nunca muda')""",
    """INSERT OR IGNORE INTO automation_rules (name, enabled, trigger, conditions, actions) VALUES
       ('waiver_na_tarefa', 1, '{"event":"task.created","por":"sistema"}', NULL,
        '{"sistema":"anexar a waiver assinada do piloto na tarefa do Asana e guardar o PDF no card do cliente"}')""",
    # Por último, de propósito: os UPDATE abaixo só encontram a linha depois dos
    # INSERT OR IGNORE acima. Tentei colocá-los no topo e, em banco novo, metade não
    # pegou — a linha ainda não existia.
    *[f"""UPDATE action_policies SET policy='{depois}',
             note=COALESCE(note,'') || ' · revisto pelo dono em 21/09 ({antes} -> {depois})'
           WHERE action='{acao}' AND policy='{antes}'"""
      for acao, antes, depois in REVISAO_21_09],
]


@contextmanager
def transacao(con):
    """BEGIN/COMMIT explícitos; rollback em exceção."""
    con.execute("BEGIN")
    try:
        yield con
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


# ------------------------------------------------------------ helpers
def um(con, sql, params=()):
    r = con.execute(sql, params).fetchone()
    return dict(r) if r else None


def todos(con, sql, params=()):
    return [dict(r) for r in con.execute(sql, params).fetchall()]


def inserir(con, tabela, **campos):
    cols = ", ".join(campos)
    marks = ", ".join("?" for _ in campos)
    cur = con.execute(f"INSERT INTO {tabela} ({cols}) VALUES ({marks})",
                      tuple(campos.values()))
    return cur.lastrowid


def atualizar(con, tabela, id_, **campos):
    sets = ", ".join(f"{k} = ?" for k in campos)
    con.execute(f"UPDATE {tabela} SET {sets} WHERE id = ?",
                (*campos.values(), id_))


def auditar(con, event, actor, user_id=None, entity_type=None, entity_id=None,
            detail=None, ip=None):
    """Grava no audit_logs. `detail` vira JSON; nunca passe segredo aqui."""
    inserir(con, "audit_logs", event=event, actor=actor, user_id=user_id,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            detail=json.dumps(detail, ensure_ascii=False) if detail is not None else None,
            ip=ip)


# ------------------------------------------------------------ FastAPI
def get_db():
    con = conectar()
    try:
        yield con
    finally:
        con.close()
