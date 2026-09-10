"""Ambiente de teste do Command Center: um retrato da operação real, sem tocar em sistema nenhum.

Cobre: pilotos (mensal, diária, Pro, VIP, menor, duplicado), serviços em várias
colunas, waivers (assinada, aberta, devolvida, a expirar), e-mails (inbox, triado,
pede humano), invoices (paga, aberta, vencida), corridas com convites, catálogo de
equipamento, itens do QBO, conversa da IA com ações em todos os estados.
"""
import os
import sys
from datetime import date, timedelta

SC = os.path.dirname(os.path.abspath(__file__))
os.environ["URACE_ENV"] = "/nao/existe"
os.environ.setdefault("CC_DB_PATH", os.path.join(SC, "e2e_full.sqlite"))   # o README manda o caminho por CC_DB_PATH
sys.path.insert(0, "/home/user/Uraceagent")

from command_center.api import auth                                    # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir        # noqa: E402

HOJE = date.today()
d = lambda n: (HOJE + timedelta(days=n)).isoformat()                    # noqa: E731

con = conectar()
aplicar_schema(con)

# ---------------------------------------------------------------- usuários
auth.criar_usuario(con, "italo@urace.us", "Italo Silveira", "ADMIN", "senha-de-teste-123")
auth.criar_usuario(con, "eduardo@urace.us", "Eduardo Resende", "MANAGER", "senha-de-teste-123")
auth.criar_usuario(con, "op@urace.us", "Operador Pista", "OPERATOR", "senha-de-teste-123")
auth.criar_usuario(con, "leitor@urace.us", "Leitor", "VIEWER", "senha-de-teste-123")

# ---------------------------------------------------------------- clientes
brian = inserir(con, "clients", name="Pablo Santiago", email="pablosantiago@outlook.com", email_alt="bryanlsantiago@outlook.com",
                phone="305-609-7845", pilot_name="Bryan Santiago", pilot_dob="2011-03-14", vip=0, status="ACTIVE",
                source="asana", plan_type="monthly", pro_driver=1, monthly_plan="Academy 2 stroke")
david = inserir(con, "clients", name="Nicolas Pera", email="peranicolas2106@gmail.com", phone="305-906-2542",
                pilot_name="David Pera", pilot_dob="2014-05-02", vip=0, status="ACTIVE", source="asana", plan_type="daily")
renato = inserir(con, "clients", name="Rafael Pionti", email="rafael@spmesportes.com.br", phone="+55 11 93005-8900",
                 pilot_name="Renato Frota Pionti", pilot_dob="2012-01-03", vip=1, status="ACTIVE", source="asana")
alex = inserir(con, "clients", name="Alex Alonso", email="alonso@example.com", pilot_name="Alex Alonso",
               vip=0, status="ACTIVE", source="asana")
alexb = inserir(con, "clients", name="Alex Alonzo", email=None, pilot_name="Alex Alonzo", vip=0, status="INACTIVE", source="asana")
theo = inserir(con, "clients", name="Carla Mendes", email="carla@example.com", phone="407-555-0199",
               pilot_name="Théo Mendes", pilot_dob="2009-08-20", vip=0, status="INACTIVE", source="asana", plan_type="daily")

# ---------------------------------------------------------------- serviços (Asana)
def tarefa(cid, titulo, secao, status, quando, feitas=None, total=12, gid=None):
    t = inserir(con, "tasks", client_id=cid, title=titulo, project="U-RACE", section=secao,
                section_gid="1205141832260879" if secao == "SUNDAY" else None, status=status, due_on=quando,
                subtasks_total=total, subtasks_done=feitas if feitas is not None else (total if status == "completed" else 3),
                assignee="Luis Barros")
    if gid:
        inserir(con, "entity_links", entity_type="task", entity_id=t, system="asana", external_id=gid,
                deep_link=f"https://app.asana.com/0/1205450093098920/{gid}/f")
    return t

t_david = tarefa(david, "David Pera_Urace Daily_Using Own Kart [1/1]", "SUNDAY", "open", d(3), 0, 12, "1218352906747605")
tarefa(brian, "Bryan Santiago_Academy_2 stroke [3/4]", "SATURDAY", "open", d(2), 4, 12, "8880001")
tarefa(brian, "Bryan Santiago_Academy_2 stroke [2/4]", "Finished Services", "completed", d(-14), 12, 12, "8880002")
tarefa(brian, "Bryan Santiago_Academy_2 stroke [1/4]", "Finished Services", "completed", d(-28), 12, 12, "8880003")
t_vencida = tarefa(theo, "Théo Mendes_Urace Daily_2 stroke [1/1]", "SATURDAY", "open", d(-5), 9, 12, "8880004")
tarefa(renato, "Renato Frota Pionti_Professional Coaching_2T [1/1]", "SATURDAY", "open", d(1), 2, 12, "8880005")
corrida_task = tarefa(None, "ROK Cup USA Round 5 [Orlando / OKC]", "RACES", "open", d(9), 0, 8, "8880006")
tarefa(None, "SKUSA Winter Series RD1 [Homestead]", "RACES", "open", d(24), 0, 8, "8880007")

# ---------------------------------------------------------------- waivers (DocuSign)
def waiver(cid, nome, email, status, enviada, assinada=None, expira=None, env=None):
    w = inserir(con, "waivers", client_id=cid, signer_name=nome, signer_email=email, template="parental",
                status=status, sent_at=enviada, completed_at=assinada, expires_at=expira)
    if env:
        inserir(con, "entity_links", entity_type="waiver", entity_id=w, system="docusign", external_id=env,
                deep_link=f"https://app.docusign.com/documents/details/{env}")
    return w

waiver(david, "Nicolas Pera", "peranicolas2106@gmail.com", "completed", d(-25), d(-24), d(340), "env-david")
waiver(brian, "Pablo Santiago", "pablosantiago@outlook.com", "completed", d(-60), d(-59), d(305), "env-brian")
waiver(theo, "Carla Mendes", "carla@example.com", "delivered", d(-9), None, d(12), "env-theo")
waiver(None, "Matthew Hubbard", "misterhubbbard@gmail.com", "autoresponded", d(-106), None, d(14), "env-matt")

# ---------------------------------------------------------------- e-mails (Gmail)
def email(cid, caixa, assunto, de, quando, **kw):
    e = inserir(con, "emails", client_id=cid, mailbox=caixa, subject=assunto, sender=de, last_at=quando, **kw)
    inserir(con, "entity_links", entity_type="email", entity_id=e, system="gmail", external_id=f"th{e}",
            deep_link=f"https://mail.google.com/mail/u/0/#all/th{e}")
    return e

email(renato, "urace", "Posso trocar o dia do treino?", "Rafael Pionti <rafael@spmesportes.com.br>", d(-1) + "T11:00:00",
      handled=0, is_inbox=1, labels='["INBOX","Kart Racing School | Client talks"]', snippet="Consigo levar o Renato no domingo em vez de sábado?")
email(None, "urace", "Your Amazon.com order #113-55", "auto-confirm@amazon.com", d(-1) + "T09:12:00",
      handled=1, handled_by="ia", handled_reason="triagem: Finances/Receipts + Amazon", is_inbox=0,
      labels='["Finances/Receipts","Amazon"]', snippet="Shipped: Tillotson carburetor kit", triaged_at=d(-1) + "T13:00:00")
email(brian, "support", "Karting opportunities", "Luke Justice <luke@example.com>", d(-11) + "T15:40:00",
      handled=0, is_inbox=0, needs_human=1, labels='["Kart Racing School | Client talks"]',
      suggested_label="Kart Racing School | Client talks", suggested_by="ia", triage_reason="pergunta de cliente",
      triaged_at=d(-11) + "T21:00:00", snippet="Would love to talk about coaching for my son.")
email(None, "urace", "ROK Cup entry list is out", "ROK Cup USA <info@rokcupusa.com>", d(0) + "T08:00:00",
      handled=0, is_inbox=1, labels='["INBOX"]', snippet="Entry list for the September round")

# ---------------------------------------------------------------- invoices (QuickBooks)
def invoice(cid, num, valor, saldo, status, emitida, vence, memo, email_cob, ref=None):
    i = inserir(con, "invoices", client_id=cid, doc_number=num, amount=valor, balance=saldo, status=status,
                issued_on=emitida, due_on=vence, memo=memo, customer_email=email_cob, customer_ref=ref)
    inserir(con, "entity_links", entity_type="invoice", entity_id=i, system="quickbooks", external_id=num,
            deep_link=f"https://qbo.intuit.com/app/invoice?txnId={num}")
    return i

invoice(david, "1031", 500, 0, "paid", d(-24), d(-22), "Urace Daily | Using Own Kart | David Pera", "peranicolas2106@gmail.com", "696")
invoice(brian, "1044", 3156.90, 3156.90, "open", d(-9), d(6), "Urace Academy Training Program [September, 2026]", "pablosantiago@outlook.com", "412")
invoice(theo, "1077", 819, 819, "overdue", d(-71), d(-45), "Urace Daily 2 stroke - Théo Mendes [July, 2026]", "carla@example.com", "530")

# ---------------------------------------------------------------- catálogo do QuickBooks
con.execute("""INSERT OR REPLACE INTO qbo_items (id, name, full_name, price, type, active) VALUES
  ('31','Arrive and Drive daily','Arrive and Drive daily',500,'Service',1),
  ('32','Urace Daily','Urace Daily',500,'Service',1),
  ('33','Urace Academy Training Program','Urace Academy Training Program',2756.90,'Service',1),
  ('34','Race Support','Race Support',1200,'Service',1),
  ('35','Security deposit','Security deposit',400,'Service',1)""")

# ---------------------------------------------------------------- corridas e convites
from command_center.providers import sync as sy                        # noqa: E402
sy.sincronizar_corridas(con)
rok = con.execute("SELECT id FROM races WHERE task_id=?", (corrida_task,)).fetchone()[0]
con.execute("UPDATE races SET track='Orlando Kart Center', city='Orlando, FL', series='ROK' WHERE id=?", (rok,))
inserir(con, "race_invites", race_id=rok, client_id=brian, invited_by=1, status="confirmed",
        estimate_text="| Item | Qtd | Unit | Total |\n| Inscrição ROK | 1 | $450 | $450 |\n| Race support | 1 | $1,200 | $1,200 |\n\n**Total: $1.650**")

# ---------------------------------------------------------------- equipamento do Pro
ch = con.execute("SELECT id FROM catalog_chassis LIMIT 1").fetchone()[0]
en = con.execute("SELECT id FROM catalog_engines LIMIT 1").fetchone()[0]
con.execute("UPDATE clients SET chassis_id=?, engine_id=?, equipment_notes='Chassi nº 4471; pneus MG Yellow' WHERE id=?", (ch, en, brian))

# ---------------------------------------------------------------- integrações
for s, st in (("asana", "CONNECTED"), ("docusign", "CONNECTED"), ("gmail", "CONNECTED"), ("quickbooks", "CONNECTED")):
    con.execute("UPDATE integrations SET status=?, last_success_at=?, last_attempt_at=? WHERE system=?",
                (st, d(0) + "T07:00:00Z", d(0) + "T07:00:00Z", s))
con.execute("UPDATE integrations SET status='ERROR', last_error='HTTP 401 em GET /v2.1/accounts: token expirado', error_count=3 WHERE system='docusign'")
for s, ok, msg in (("asana", 1, "412 tarefas em 11 colunas, 6 clientes novos"), ("gmail", 1, "38 threads"),
                   ("quickbooks", 1, "490 invoices, 353 ligadas a cliente, 61 itens"), ("docusign", 0, "token expirado")):
    inserir(con, "sync_logs", system=s, started_at=d(0) + "T07:00:00Z", finished_at=d(0) + "T07:02:00Z", ok=ok, items=1, message=msg)

# ---------------------------------------------------------------- conversa da IA com ações em todos os estados
c1 = inserir(con, "ai_commands", user_id=1, text="Filho do Nicolas Pera - David Pera. Coloca na agenda pro domingo. Mesmo esquema da última vez.",
             prompt="(contexto do painel)", session_key="agent:urace-admin:web-1", status="DONE",
             created_at=d(0) + "T11:20:00Z", finished_at=d(0) + "T11:23:00Z",
             output="Achei o histórico: David Pera, Using Own Kart, prática no OKC, invoice de $500 (Nicolas pagando).\n\nCriei a tarefa na coluna SUNDAY e montei a invoice de $500 no nome do Nicolas para você aprovar.")
inserir(con, "ai_actions", command_id=c1, action="asana_criar_do_modelo", system="asana", policy="SAFE", status="DONE",
        payload='{"alvo":"David Pera","args":{"nome":"David Pera_Urace Daily_Using Own Kart [1/1]","campos":{"Race":"Practice OKC"}}}',
        result='{"aplicado": true, "gid": "1218352906747605", "nome": "David Pera_Urace Daily_Using Own Kart [1/1]", "link": "https://app.asana.com/0/1205450093098920/1218352906747605/f"}',
        reason="proposta pelo agente", finished_at=d(0) + "T11:23:00Z")
a_inv = inserir(con, "ai_actions", command_id=c1, action="qbo_criar_e_enviar_invoice", system="qbo", policy="REQUIRES_APPROVAL",
                status="PROPOSED", reason="proposta pelo agente",
                payload='{"alvo":"Nicolas Pera","args":{"cliente_id":"696","email":"peranicolas2106@gmail.com","data_servico":"%s","vence_em":"%s","memo":"Urace Daily | Using Own Kart | David Pera | Service date: %s","nota_privada":"Urace Daily | Using Own Kart | David Pera","linhas":[{"item_id":"32","quantidade":1,"unitario":500,"descricao":"Urace Daily - Using Own Kart - David Pera"}]}}'
                % (d(3), d(1), d(3)))
inserir(con, "approvals", action_id=a_inv)
a_ruim = inserir(con, "ai_actions", command_id=c1, action="qbo_criar_e_enviar_invoice", system="qbo", policy="REQUIRES_APPROVAL",
                 status="PROPOSED", reason="incompleta: linha sem item do QuickBooks",
                 payload='{"alvo":"Carla Mendes","problemas":["linha sem item do QuickBooks"],"args":{"cliente_id":"530","email":"carla@example.com","linhas":[{"item_id":null,"quantidade":1,"unitario":819,"descricao":"Urace Daily - 2 stroke - Théo Mendes"}]}}')
inserir(con, "approvals", action_id=a_ruim)
inserir(con, "ai_commands", user_id=1, text="pode continuar com a invoice", prompt="(contexto)", session_key="agent:urace-admin:web-1",
        status="DONE", created_at=d(0) + "T11:40:00Z", finished_at=d(0) + "T11:41:00Z",
        output="A invoice de $500 já está pronta esperando sua aprovação. Waiver do David válida até " + d(340) + ".")
inserir(con, "ai_commands", user_id=2, text="quantos serviços o Bryan tem esse mês?", prompt="(contexto)", session_key="agent:urace-admin:web-2",
        status="DONE", created_at=d(0) + "T10:00:00Z", finished_at=d(0) + "T10:01:00Z", output="Três: dois concluídos e um no sábado.")
inserir(con, "ai_commands", user_id=1, text="EVENTO AUTOMÁTICO: task.overdue — Théo Mendes_Urace Daily_2 stroke [1/1]",
        prompt="(evento)", session_key="agent:urace-admin:eventos", status="DONE",
        created_at=d(-1) + "T07:05:00Z", finished_at=d(-1) + "T07:07:00Z",
        output="Conferi a tarefa: sem comentário de conclusão e as subtarefas de pagamento estão abertas. Não movi.")
inserir(con, "ai_events", kind="task.overdue", entity_type="task", entity_id=t_vencida, client_id=theo,
        summary="Théo Mendes_Urace Daily_2 stroke [1/1] ainda aberta", status="FAILED")

# ------------------------------------------------------------------ CRM (Kommo)
# Funil comercial com lead do Instagram esperando resposta, lead já ligado a cliente
# e lead de WhatsApp em outra etapa. Espelho: nada aqui fala com o Kommo.
con.execute("UPDATE integrations SET status='CONNECTED', last_success_at=? WHERE system='kommo'", (d(0) + "T07:02:00Z",))
lead1 = inserir(con, "crm_leads", external_id="5001", name="Maria Souza — aula experimental",
                pipeline_id="9903543", pipeline_name="Sales funnel", stage_id="76050835",
                stage_name="Leads de entrada", stage_order=1, price=500, source="Instagram",
                tags='["instagram","experimental"]', contact_name="Maria Souza", contact_email="maria@example.com",
                contact_phone="+1 407 555 0101", link="https://urace.kommo.com/leads/detail/5001",
                created_at_src=d(-2) + "T18:00:00Z", updated_at_src=d(0) + "T09:10:00Z",
                last_message_at=d(0) + "T09:10:00Z", needs_reply=1)
inserir(con, "crm_messages", lead_id=lead1, external_id="m1", direction="entrada", author="Maria Souza",
        text="Oi! Vi o vídeo do kart. Quanto custa a aula experimental para o meu filho de 9 anos?",
        at=d(0) + "T09:10:00Z", source="kommo")
lead2 = inserir(con, "crm_leads", external_id="5002", name="Carla Mendes — mensalidade 2 stroke",
                client_id=theo, pipeline_id="9903543", pipeline_name="Sales funnel", stage_id="105276412",
                stage_name="First Contact", stage_order=2, price=3156.9, source="WhatsApp",
                tags='["mensalidade"]', contact_name="Carla Mendes", contact_email="carla@example.com",
                contact_phone="407-555-0199", link="https://urace.kommo.com/leads/detail/5002",
                created_at_src=d(-9) + "T12:00:00Z", updated_at_src=d(-1) + "T16:00:00Z",
                last_message_at=d(-1) + "T16:00:00Z", needs_reply=0)
inserir(con, "crm_messages", lead_id=lead2, external_id="m2", direction="entrada", author="Carla Mendes",
        text="Fechado, pode mandar a invoice da mensalidade.", at=d(-1) + "T15:40:00Z", source="kommo")
inserir(con, "crm_messages", lead_id=lead2, external_id=None, direction="saida", author="Italo Silveira",
        text="Perfeito, Carla! Mando ainda hoje.", at=d(-1) + "T16:00:00Z", source="painel")

# aprendizado do dono e fonte de contexto já vêm do schema
con.commit()
n = lambda t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]                       # noqa: E731
print(f"clientes={n('clients')} tarefas={n('tasks')} waivers={n('waivers')} emails={n('emails')} "
      f"invoices={n('invoices')} corridas={n('races')} acoes={n('ai_actions')} comandos={n('ai_commands')} "
      f"itens_qbo={n('qbo_items')} leads={n('crm_leads')}")
con.close()
