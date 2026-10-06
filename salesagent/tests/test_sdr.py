#!/usr/bin/env python3
"""SDR (D-2026-09-25): as diretivas que reorganizam o Chase.

Três camadas, todas sem rede:
  1. o pacote salesagent/sdr — classificador, triagem, roteador, estilo,
     funil e executor, com os casos reais do Kommo da URACE;
  2. a ponte nos três níveis (observar, organizar, atender) — o que ela
     escreve no Kommo e o que ela fala com o lead em cada um;
  3. as travas corrigidas junto: G9 pelo id, tags que só somam, erro do
     Kommo que não derruba o turno.

Uso:
    python3 salesagent/tests/test_sdr.py
"""
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SALESAGENT = HERE.parent
_TMP = tempfile.mkdtemp(prefix="urace-sdr-")
os.environ["URACE_DIR"] = _TMP
os.environ.setdefault("SDR_MODO", "observar")
sys.path.insert(0, str(SALESAGENT))
sys.path.insert(0, str(SALESAGENT / "bridge"))

import sdr  # noqa: E402
from sdr import classificador, estilo, executor, funil, regras, roteador, triagem  # noqa: E402

FALHAS = []


def check(rotulo, cond, detalhe=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {rotulo}" + ("" if cond else f"  {detalhe}"))
    if not cond:
        FALHAS.append(rotulo)


# ------------------------------------------------------------------ Kommo
# Estrutura real da conta (25/09, via Command Center): os funis da equipe.
# O SDR trabalha em Urace (página 1) e Comercial (página 2) e não cria nada.
def _st(i, nome, sort, tipo=0):
    return {"id": i, "name": nome, "sort": sort, "type": tipo}


URACE, COMERCIAL, CONTACT_LIST = 9903543, 14512484, 9957459
FIRST_CONTACT, COLD_LEADS, HOT_LEADS = 105276412, 77188783, 78606031
ENTRADA, QUALIFICADO, ATENDIMENTO, PROPOSTA, PERDIDO_NQ = 112100844, 112100848, 112100852, 112113592, 112113604
INTERACTIONS = 76442723

FUNIS_DA_EQUIPE = [
    {"id": URACE, "name": "Urace", "_embedded": {"statuses": [
        _st(76050835, "Incoming leads", 10, 1), _st(FIRST_CONTACT, "First Contact", 10),
        _st(78564259, "Onboarding funnel", 20), _st(90232403, "conversation in progress", 30),
        _st(76052579, "Follow Up 1", 40), _st(COLD_LEADS, "Cold Leads", 70), _st(HOT_LEADS, "Hot Leads", 80),
        _st(77518191, "Closing the sale", 110), _st(76999131, "Suppliers", 170),
        _st(142, "Closed - won", 10000), _st(143, "Closed - lost", 11000)]}},
    {"id": CONTACT_LIST, "name": "Contact list", "_embedded": {"statuses": [
        _st(76442719, "Incoming leads", 10, 1), _st(INTERACTIONS, "Interactions", 40),
        _st(142, "Closed - won", 10000), _st(143, "Closed - lost", 11000)]}},
    {"id": COMERCIAL, "name": "Comercial", "_embedded": {"statuses": [
        _st(112100840, "Incoming leads", 10, 1), _st(ENTRADA, "ENTRADA ", 20), _st(QUALIFICADO, "QUALIFICADO ", 30),
        _st(ATENDIMENTO, "ATENDIMENTO ", 40), _st(112113588, "STAND BY", 50), _st(PROPOSTA, "PROPOSTA ", 60),
        _st(112113596, "FECHAMENTO ", 70), _st(112113600, "FECHAMENTO ", 80),
        _st(PERDIDO_NQ, "PERDIDO / NÃO QUALIFICADO", 90),
        _st(142, "Closed - won", 10000), _st(143, "Closed - lost", 11000)]}},
    {"id": 14316000, "name": "Chase — AI Sales Funnel", "_embedded": {"statuses": [
        _st(110564420, "New Inquiry", 20)]}},
]


class KommoFalso:
    """kommo_client sem rede: guarda leads e registra toda escrita."""

    def __init__(self, funis):
        self.funis = funis
        self.leads = {}
        self.escritas = []

    def lead(self, lead_id, pipeline_id, status_id, **extra):
        self.leads[lead_id] = {"id": lead_id, "pipeline_id": pipeline_id, "status_id": status_id,
                               "closed_at": None, "responsible_user_id": 555,
                               "_embedded": {"tags": []}, **extra}

    # leitura
    def list_pipelines(self):
        return self.funis

    def get_lead(self, lead_id):
        return self.leads[lead_id]

    # escrita
    def move_lead(self, lead_id, pipeline_id, status_id):
        self.escritas.append(("move", lead_id, status_id))
        self.leads[lead_id].update(pipeline_id=pipeline_id, status_id=status_id)

    def add_tags(self, lead_id, tags):
        self.escritas.append(("tags", lead_id, tuple(tags)))
        self.leads.get(lead_id, {"_embedded": {"tags": []}})["_embedded"]["tags"] += [{"name": t} for t in tags]

    def add_note(self, lead_id, texto):
        self.escritas.append(("nota", lead_id, texto))

    def add_task(self, lead_id, texto, prazo, responsavel=None):
        self.escritas.append(("tarefa", lead_id, texto, responsavel))

    def set_stage(self, lead_id, stage_id):
        self.escritas.append(("stage", lead_id, stage_id))

    def run_bot(self, *a):
        return False


def _api(falso):
    return type("Api", (), {"move": staticmethod(falso.move_lead), "add_tags": staticmethod(falso.add_tags),
                            "add_note": staticmethod(falso.add_note), "add_task": staticmethod(falso.add_task)})


def camada_pacote():
    print("\n1. Pacote SDR")

    # Mensagens automáticas vistas no Kommo, marcadas à mão como nao_e_lead.
    for texto, email in [
        ("Your code is 711995", "info@account-d.docusign.net"),
        ("713157 is your code to log in to Kommo", "mfa@kommo.com"),
        ("[Segurança] Sua senha de acesso foi alterada", "changed@rdstation-security.com"),
        ("Zoho Vault - O período de avaliação expirou", "notification@zohostore.com"),
        ("New deals for you", "news@notice.alibaba.com"),
    ]:
        a = classificador.classificar(texto, remetente_email=email)
        check(f"automático: {texto[:34]}", a["automatico"])
    # Cards do Inbox de e-mail do relatório de 25/09: nenhum era lead.
    for texto in ["Seu código para fazer login é 343929",
                  "Seu código de verificação para fazer login no Dialpad",
                  "Alerta de segurança para uracesim3@gmail.com",
                  "[GitHub] A fine-grained personal access token has been added",
                  "Reconnect your Bank of America account",
                  "URace Support, you have 23 new notifications",
                  "New seller message (Alibaba)",
                  "URace Support, você tem 135 novas notificações",
                  "Alguém adicionou este endereço como o próprio e-mail de recuperação"]:
        check(f"relatório 25/09, lixo de e-mail: {texto[:34]}", classificador.classificar(texto)["automatico"])
    for texto in ["Carlos Mendes", "Lead #15712502"]:
        check(f"nome de gente não é lixo: {texto}", not classificador.classificar(texto)["automatico"])
    a = classificador.classificar("Hi, how much is a training day?", "carloscrestana@gmail.com")
    check("e-mail de pessoa real não é automático", not a["automatico"])
    a = classificador.classificar("You are receiving this email because you signed up. Unsubscribe.")
    check("unsubscribe de newsletter não é opt-out", a["automatico"] and not a["opt_out"])

    # Palavra inteira: "hi" não casa com "this", "ok" não casa com "book".
    check("'this is great' não é saudação", not classificador.classificar("this is great")["saudacao_isolada"])
    check("'can I book?' é agenda, não encerramento",
          "agenda" in classificador.classificar("can I book?")["intencoes"])

    entrada = {"existe": True, "zona": regras.ENTRADA}
    casos = [
        ("Oi", entrada, regras.FICA, "First Contact", roteador.RESPONDER),
        ("Quanto custa o 1-Day?", entrada, regras.PROMOVER, "ENTRADA", roteador.RESPONDER),
        ("713157 is your code to log in to Kommo", entrada, regras.FICA, "First Contact", roteador.SILENCIAR),
        ("Nossa empresa oferece trafego pago", entrada, regras.FICA, "First Contact", roteador.SILENCIAR),
        ("Pare de mandar mensagem", entrada, regras.FICA, "PERDIDO", roteador.CONFIRMAR_OPT_OUT),
        ("Lets do it, when can he start?", entrada, regras.PROMOVER, "ATENDIMENTO", roteador.ESCALAR),
        ("He currently races in SKUSA", entrada, regras.PROMOVER, "ATENDIMENTO", roteador.ESCALAR),
        ("Tem desconto para 2 pilotos?", entrada, regras.PROMOVER, "ATENDIMENTO", roteador.ESCALAR),
        ("Obrigado!", entrada, regras.FICA, "First Contact", roteador.RESPONDER),
        ("Quanto custa?", {"existe": True, "zona": regras.COMERCIAL}, regras.ANEXAR, None, roteador.RESPONDER),
    ]
    for texto, card, acao, etapa, rota in casos:
        r = sdr.avaliar(texto, card=card)
        d = r["triagem"]
        check(f"'{texto[:30]}' -> {acao} / {etapa} / {rota}",
              d["acao"] == acao and d["destino"]["etapa"] == etapa and r["roteamento"]["acao"] == rota,
              f"{d['acao']} / {d['destino']} / {r['roteamento']}")
    check("pedido de humano ganha a tag da equipe 'Quer atendimento'",
          "Quer atendimento" in sdr.avaliar("Quero falar com alguem", card=entrada)["triagem"]["tags"])

    check("desconto é fila (média), conversão interrompe (alta)",
          sdr.avaliar("Tem desconto?")["roteamento"]["prioridade"] == "media"
          and sdr.avaliar("lets do it")["roteamento"]["prioridade"] == "alta")

    # Canais com bot da equipe: a ponte não fala; só escalação, sem resposta.
    for canal in regras.CANAIS_COM_BOT_DA_EQUIPE:
        r = sdr.avaliar("How much is a single day?", card=entrada, evento_extra={"canal": canal})
        check(f"{canal}: quem responde é o bot da equipe",
              r["roteamento"] == {"acao": roteador.SILENCIAR, "motivo": "BOT_DA_EQUIPE_NO_CANAL",
                                  "motivo_original": None} and r["triagem"]["entra_no_comercial"], str(r["roteamento"]))
    r = sdr.avaliar("I want to talk to someone", card=entrada, evento_extra={"canal": "instagram"})
    check("instagram: pedido de pessoa fora do menu escala sem resposta",
          r["roteamento"]["acao"] == roteador.ESCALAR and r["roteamento"].get("sem_resposta"), str(r["roteamento"]))
    check("telegram (sem bot da equipe): o robô responde",
          sdr.avaliar("How much?", evento_extra={"canal": "telegram"})["roteamento"]["acao"] == roteador.RESPONDER)
    check("a trilha da Meta cabe na janela de 24 h",
          sum(regras.FOLLOW_UP_MINUTOS_JANELA_24H) < regras.JANELA_MENSAGEM_LIVRE_HORAS * 60)

    em_reserva = {"existe": True, "zona": regras.COMERCIAL, "etapa": funil.chave("QUALIFICADO")}
    r = sdr.avaliar("quero falar com alguem", card=em_reserva)
    check("handoff não tira da reserva quem já está em QUALIFICADO", not r["triagem"]["destino"]["mover"])

    for tipo, etapa in [("reserva_etapa1", "QUALIFICADO"), ("reserva_etapa2", "GANHO"), ("formulario", "ENTRADA")]:
        d = triagem.triar({"tipo": tipo}, classificador.classificar(""), entrada)
        check(f"evento {tipo} -> {etapa}", d["destino"]["etapa"] == etapa, str(d["destino"]))

    limpo, v = estilo.aplicar("Great! 🏁 Come by anytime — we are open. The 1-Day is the best start.")
    check("estilo corta emoji, travessão e frase proibida",
          limpo == "Great! The 1-Day is the best start." and "nunca_dizer:come by" in v, f"{limpo!r} {v}")

    plano = funil.planejar(FUNIS_DA_EQUIPE)
    check("conta atual: Urace e Comercial têm tudo que as regras usam", plano["ok"] and not plano["etapas_duplicadas"],
          str(plano))
    renomeado = [dict(f) for f in FUNIS_DA_EQUIPE]
    renomeado[2] = dict(renomeado[2], _embedded={"statuses": [
        dict(st, name="EM ATENDIMENTO") if st["id"] == ATENDIMENTO else st
        for st in FUNIS_DA_EQUIPE[2]["_embedded"]["statuses"]]})
    check("etapa renomeada vira pendência, nada é criado",
          funil.planejar(renomeado)["etapas_faltando"] == [{"funil": "Comercial", "etapa": "ATENDIMENTO"}])
    check("o SDR não sabe criar funil", not hasattr(funil, "corpo_criacao"))

    m = funil.Mapa(FUNIS_DA_EQUIPE)
    fc, cold, hot = m.localizar(URACE, FIRST_CONTACT), m.localizar(URACE, COLD_LEADS), m.localizar(URACE, HOT_LEADS)
    check("First Contact é Entrada gerenciada; Cold Leads é resgate; Hot Leads é da equipe",
          fc["zona"] == regras.ENTRADA and fc["gerenciada"] and cold["resgate"] and not cold["gerenciada"]
          and not hot["gerenciada"] and not hot["resgate"])
    check("Contact list está fora do SDR; ENTRADA é Comercial",
          not m.localizar(CONTACT_LIST, INTERACTIONS)["do_sdr"]
          and m.localizar(COMERCIAL, ENTRADA)["zona"] == regras.COMERCIAL)
    check("GANHO e PERDIDO são os fechamentos nativos da página certa",
          m.status_id("PERDIDO", regras.ENTRADA) == (URACE, 143) and m.status_id("GANHO", regras.COMERCIAL) == (COMERCIAL, 142))

    # Executor: observar calcula e não escreve; organizar escreve.
    for modo, espera in [(executor.OBSERVAR, 0), (executor.ORGANIZAR, 3)]:
        falso = KommoFalso(FUNIS_DA_EQUIPE)
        falso.lead(1, URACE, COLD_LEADS)
        r = sdr.avaliar("Quanto custa o Academy?", card={"existe": True, "zona": regras.ENTRADA})
        feito = executor.aplicar(_api(falso), falso.leads[1], r["triagem"], m, modo)
        check(f"executor em {modo}: Cold Leads sobe para ENTRADA com DM, escreve {espera}",
              feito["moveu"] == "ENTRADA" and "DM" in feito["tags"] and len(falso.escritas) == espera,
              f"{feito} {falso.escritas}")

    falso = KommoFalso(FUNIS_DA_EQUIPE)
    falso.lead(2, URACE, FIRST_CONTACT)
    r = sdr.avaliar("Quanto custa o Academy?", card={"existe": True, "zona": regras.ENTRADA})
    feito = executor.aplicar(_api(falso), falso.leads[2], r["triagem"], m, executor.ORGANIZAR, segurar_na_entrada=True)
    check("First Contact: o SDR não sobe o card (é a REGRA 2 da equipe), sem nota",
          feito.get("segurado") == "REGRA_2_DA_EQUIPE" and not feito["moveu"] and not feito["nota"]
          and [e[0] for e in falso.escritas] == ["tags"] and "DM" not in feito["tags"], f"{feito} {falso.escritas}")

    falso = KommoFalso(FUNIS_DA_EQUIPE)
    falso.lead(3, COMERCIAL, PROPOSTA)
    r = sdr.avaliar("Quero falar com alguem", card={"existe": True, "zona": regras.COMERCIAL,
                                                     "etapa": funil.chave("PROPOSTA")})
    feito = executor.aplicar(_api(falso), falso.leads[3], r["triagem"], m, executor.ORGANIZAR,
                             roteamento=r["roteamento"])
    check("Comercial: o SDR nunca devolve card para etapa anterior",
          feito.get("nao_voltou") == {"de": "proposta", "para": "ATENDIMENTO"}
          and falso.leads[3]["status_id"] == PROPOSTA and feito["tarefa"], str(feito))

    import scheduler
    agora = int(time.time())
    check("follow-up com o lead calado há 23h30 fica fora da janela da Meta",
          scheduler._fora_da_janela_24h({"last_inbound_at": agora - 23 * 3600 - 1800}, agora))
    check("follow-up com o lead calado há 2h ainda cabe na janela",
          not scheduler._fora_da_janela_24h({"last_inbound_at": agora - 2 * 3600}, agora))


def camada_ponte():
    print("\n2. Ponte nos três níveis")
    import app
    import config
    import directives
    import sdr_ponte
    import state

    def nivel(modo):
        app.SDR_MODO = modo
        sdr_ponte.SDR_MODO = modo
        config.SDR_MODO = modo

    def preparar(agente="Claro! Qual opção descreve melhor o piloto?"):
        falso = KommoFalso(FUNIS_DA_EQUIPE)
        entregues, avisos = [], []
        app.kommo = falso
        sdr_ponte.kommo = falso
        sdr_ponte._forcar_kommo = True
        sdr_ponte._cache["mapa"] = None
        sdr_ponte._vistas.clear()
        sdr_ponte._avisados.clear()
        # Triagem do card síncrona no teste (em produção é thread), com o
        # mesmo guarda-chuva de erro da produção.
        def _triar(lead_id, texto, rota=None):
            try:
                sdr_ponte.triar_lead(lead_id, texto, rota=rota)
            except Exception as exc:
                state.log("error", lead_id, f"sdr (teste): {exc}")
        sdr_ponte.triar_em_segundo_plano = _triar
        app._pending_returns.clear()
        app._salesbot_continue = lambda lead_id, url, tok, texto: entregues.append((lead_id, texto)) or True
        app.notify_human = lambda texto: avisos.append(texto)
        app.run_agent = lambda lead_id, texto, **kw: agente
        app.scheduler.cancel = lambda lead_id, reason="": None
        app.scheduler.start_track = lambda lead_id, track: None
        return falso, entregues, avisos

    def msg(lead_id, texto):
        return {"lead_id": lead_id, "message": texto, "return_url": "https://x/ret", "token": None}

    def evento(*itens, leads=None):
        corpo = {"message": {"add": [
            {"id": i, "text": t, "type": tipo, "element_type": "2", "element_id": str(lead), "origin": origem}
            for i, t, lead, tipo, origem in itens]}}
        if leads:
            corpo["leads"] = {"add": [{"id": str(lid), "name": nome} for lid, nome in leads]}
        return corpo

    # O agendador fala sozinho com o lead (follow-up, resgate): só roda em
    # atender. Em observar e organizar ele nem liga.
    import asyncio
    partidas = []
    start_original = app.scheduler.start
    app.scheduler.start = lambda *a, **k: partidas.append(app.SDR_MODO)
    try:
        for modo in ("observar", "organizar", "atender"):
            nivel(modo)
            asyncio.run(app._start_scheduler())
    finally:
        app.scheduler.start = start_original
    check("agendador só liga em atender (observar e organizar não falam com lead)",
          partidas == ["atender"], str(partidas))

    # --- observar
    nivel("observar")
    falso, entregues, _ = preparar()
    falso.lead(201, URACE, COLD_LEADS)
    app.process_inbound(msg(201, "Quanto custa o 1-Day?"))
    check("observar: a ponte não responde ao lead", entregues == [], str(entregues))
    check("observar: nada é escrito no Kommo", falso.escritas == [], str(falso.escritas))
    feito = sdr_ponte.triar_lead(201, "Quanto custa o 1-Day?")
    check("observar: a decisão fica registrada (e seria subir para ENTRADA)",
          feito["modo"] == "observar" and feito["moveu"] == "ENTRADA", str(feito))

    corpo = evento(("m1", "Your code is 711995", 202, "incoming", "email"))
    falso.lead(202, URACE, FIRST_CONTACT)
    r = sdr_ponte.processar_eventos(corpo)
    check("webhook de conta: código em First Contact ganharia nao_e_lead e fica",
          r and "nao_e_lead" in r[0]["tags"] and not r[0]["moveu"], str(r))
    check("webhook de conta: mesma mensagem duas vezes é tratada uma vez",
          sdr_ponte.processar_eventos(corpo) == [])
    falso.lead(203, URACE, FIRST_CONTACT, name="URace Support, you have 23 new notifications")
    r = sdr_ponte.processar_eventos(evento(leads=[(203, "x")]))
    check("lead criado com nome de lixo: marcaria nao_e_lead, sem escrever",
          r and r[0]["acao"] == "marcar_nao_e_lead" and falso.escritas == [], f"{r} {falso.escritas}")

    # --- organizar
    nivel("organizar")
    falso, entregues, _ = preparar()
    falso.lead(301, URACE, COLD_LEADS)
    falso.lead(302, URACE, HOT_LEADS)
    falso.lead(304, URACE, FIRST_CONTACT, name="Seu código para fazer login é 343929")
    falso.lead(305, URACE, FIRST_CONTACT, name="Carlos Mendes")
    r = sdr_ponte.processar_eventos(evento(
        ("o1", "Hi again, how much for a day?", 301, "incoming", "instagram"),
        ("o2", "Quanto custa?", 302, "incoming", "instagram"),
        ("o3", "resposta da equipe", 301, "outgoing", "instagram"),
        leads=[(304, "x"), (305, "x")]))
    check("organizar: Cold Leads com sinal sobe para ENTRADA, com DM e nota",
          falso.leads[301]["pipeline_id"] == COMERCIAL and falso.leads[301]["status_id"] == ENTRADA
          and any(e[0] == "tags" and e[1] == 301 and "DM" in e[2] for e in falso.escritas)
          and any(e[0] == "nota" and e[1] == 301 for e in falso.escritas), str(falso.escritas))
    check("organizar: Hot Leads é da equipe, não é tocado",
          falso.leads[302]["status_id"] == HOT_LEADS and r[1].get("ignorado") == "ETAPA_DA_EQUIPE", str(r))
    check("organizar: mensagem da equipe (outgoing) é ignorada", len(r) == 4, str(r))
    check("organizar: lead novo de lixo ganha nao_e_lead na hora; lead de gente, nada",
          any(e[0] == "tags" and e[1] == 304 and "nao_e_lead" in e[2] for e in falso.escritas)
          and not any(e[1] == 305 for e in falso.escritas) and r[3].get("ignorado") == "LEAD_DA_EQUIPE", str(r))

    falso.lead(306, URACE, FIRST_CONTACT, created_at=int(time.time()) - 120)
    r = sdr_ponte.processar_eventos(evento(("o4", "How much is a single day?", 306, "incoming", "instagram")))
    check("organizar: card recém-criado em First Contact não sobe pelo SDR (REGRA 2 da equipe)",
          falso.leads[306]["status_id"] == FIRST_CONTACT and r[0].get("segurado") == "REGRA_2_DA_EQUIPE", str(r))

    # Teste ponta a ponta de 28/09: card antigo movido para First Contact
    # ficou 32 min parado; a REGRA 2 só roda para card que nasce ali.
    falso.lead(308, URACE, FIRST_CONTACT, created_at=int(time.time()) - 90 * 86400,
               _embedded={"tags": [{"name": "custom-kart-inquiry"}]})
    r = sdr_ponte.processar_eventos(evento(("o8", "how much is a single day on track?", 308, "incoming", "instagram")))
    check("organizar: card antigo em First Contact com sinal sobe para ENTRADA, com DM e nota",
          falso.leads[308]["pipeline_id"] == COMERCIAL and falso.leads[308]["status_id"] == ENTRADA
          and "DM" in r[0]["tags"] and r[0]["nota"] and not r[0].get("segurado")
          and r[0].get("sem_regra_2") == "CARD_ANTIGO_EM_FIRST_CONTACT", str(r))

    falso.lead(309, URACE, FIRST_CONTACT, created_at=int(time.time()) - 90 * 86400)
    r = sdr_ponte.processar_eventos(evento(("o9", "713157 is your code to log in to Kommo", 309, "incoming", "instagram")))
    check("organizar: código numa DM não põe nao_e_lead (conversa de chat), fica em First Contact",
          not any(e[1] == 309 and "nao_e_lead" in e[2] for e in falso.escritas if e[0] == "tags")
          and r[0].get("nao_marcou") == "nao_e_lead" and falso.leads[309]["status_id"] == FIRST_CONTACT, str(r))

    sdr_ponte.KOMMO_RESPONSAVEL_ID = "777"
    falso.lead(303, COMERCIAL, ENTRADA)
    sdr_ponte.processar_eventos(evento(("o5", "Quero falar com alguem", 303, "incoming", "waba")))
    tarefas = [e for e in falso.escritas if e[0] == "tarefa" and e[1] == 303]
    check("organizar: pedido de humano vai para ATENDIMENTO + tarefa do responsável",
          falso.leads[303]["status_id"] == ATENDIMENTO and tarefas and tarefas[0][3] == "777",
          str(falso.escritas))

    falso.lead(307, CONTACT_LIST, INTERACTIONS)
    r1 = sdr_ponte.processar_eventos(evento(("o6", "Hey, how much is the Academy now?", 307, "incoming", "instagram")))
    r2 = sdr_ponte.processar_eventos(evento(("o7", "Quanto custa?", 307, "incoming", "instagram")))
    check("organizar: contato antigo em Contact list vira aviso (tarefa + nota), sem mover, uma vez",
          r1[0].get("acao") == "avisar_contato_antigo" and falso.leads[307]["pipeline_id"] == CONTACT_LIST
          and len([e for e in falso.escritas if e[0] == "tarefa" and e[1] == 307]) == 1
          and r2[0].get("ignorado") == "AVISO_JA_ENVIADO", f"{r1} {r2}")

    app.process_inbound(msg(303, "oi?"))
    check("organizar: a ponte continua sem responder ao lead", entregues == [])

    # --- atender
    nivel("atender")
    falso, entregues, avisos = preparar()
    falso.lead(401, URACE, FIRST_CONTACT)
    app.process_inbound(msg(401, "713157 is your code to log in to Kommo"))
    conv = state.get_conversation(401)
    check("atender: código não recebe resposta (não é lead)", entregues == [], str(entregues))
    check("atender: e o resgate não vai responder por nós",
          (conv.get("last_outbound_at") or 0) >= (conv.get("last_inbound_at") or 0))

    falso.lead(402, URACE, FIRST_CONTACT)
    app.process_inbound(msg(402, "Please stop messaging me, unsubscribe"))
    check("atender: opt-out recebe uma confirmação e fecha",
          len(entregues) == 1 and state.get_conversation(402)["state"] == "CLOSED", str(entregues))
    check("atender: opt-out vai para perdido com a tag opt_out",
          falso.leads[402]["status_id"] == 143
          and any(e[0] == "tags" and "opt_out" in e[2] for e in falso.escritas), str(falso.escritas))

    entregues.clear()
    falso.lead(403, COMERCIAL, ENTRADA)
    app.process_inbound(msg(403, "Lets do it! When can he start?"))
    check("atender: sinal de conversão escala na hora (alta) e o lead é respondido",
          state.get_conversation(403)["state"] == "WAITING_HUMAN" and len(avisos) == 1 and len(entregues) == 1,
          f"{avisos} {entregues}")
    check("atender: card vai para ATENDIMENTO",
          falso.leads[403]["status_id"] == ATENDIMENTO, str(falso.leads[403]))

    avisos.clear()
    entregues.clear()
    falso.lead(404, COMERCIAL, ENTRADA)
    app.process_inbound(msg(404, "Tem algum desconto?"))
    check("atender: desconto vai para a fila (tarefa), sem interromper no WhatsApp",
          avisos == [] and any(e[0] == "tarefa" and e[1] == 404 for e in falso.escritas)
          and len(entregues) == 1, f"{avisos} {falso.escritas}")

    entregues.clear()
    falso, entregues, _ = preparar(agente="Great 🏁 you can come by anytime. The 1-Day is the best start.")
    falso.lead(405, COMERCIAL, ENTRADA)
    app.process_inbound(msg(405, "How does the 1-Day work?"))
    check("atender: resposta do modelo passa pela guarda de estilo",
          entregues and "🏁" not in entregues[0][1] and "come by" not in entregues[0][1].lower(), str(entregues))

    # Follow-up do agendador: fora da janela de 24 h da Meta não sai
    # mensagem; vira tarefa para uma pessoa e a trilha para.
    sch = app.scheduler
    guardados = (sch.compose_fn, sch.deliver_fn, sch.task_fn, sch.note_fn)
    chamadas = []
    sch.compose_fn = lambda *a: chamadas.append("compor") or "Oi, conseguiu ver?"
    sch.deliver_fn = lambda *a: chamadas.append("entregar") or True
    sch.task_fn = lambda lead_id, texto, prazo: chamadas.append(("tarefa", lead_id))
    sch.note_fn = lambda lead_id, texto: chamadas.append(("nota", lead_id))
    try:
        agora = int(time.time())
        state.get_conversation(501)
        state.get_conversation(502)
        sch._fire_followup({"lead_id": 501, "followup_track": "initial", "followup_attempts": 1,
                            "state": "AI_ACTIVE", "last_inbound_at": agora - 26 * 3600}, agora)
        check("follow-up fora da janela de 24 h vira tarefa, sem mensagem ao lead",
              "compor" not in chamadas and "entregar" not in chamadas and ("tarefa", 501) in chamadas, str(chamadas))
        chamadas.clear()
        sch._fire_followup({"lead_id": 502, "followup_track": "initial", "followup_attempts": 0,
                            "state": "AI_ACTIVE", "last_inbound_at": agora - 2 * 3600}, agora)
        check("follow-up dentro da janela sai normalmente", chamadas == ["compor", "entregar"], str(chamadas))
    finally:
        sch.compose_fn, sch.deliver_fn, sch.task_fn, sch.note_fn = guardados

    print("\n3. Travas corrigidas")
    nivel("observar")
    check("G9: chave closed___won (id 142) é recusada",
          directives.etapa_proibida("closed___won"))
    nivel("atender")
    check("G9: com o SDR ligado, o modelo não muda etapa nenhuma",
          directives.etapa_proibida("follow_up_1"))

    import kommo_client
    enviado = {}

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

    class _Cliente:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def patch(self, url, json=None):
            enviado["json"] = json
            return _Resp()

    kommo_client._client = lambda: _Cliente()
    kommo_client.add_tags(1, ["escalated"])
    check("tags só somam (tags_to_add), nunca apagam as da equipe",
          enviado["json"] == {"tags_to_add": [{"name": "escalated"}]}, str(enviado))

    class _Quebrado(KommoFalso):
        def add_note(self, *a):
            raise RuntimeError("Kommo 500")

    nivel("atender")
    falso, entregues, _ = preparar()
    falso.lead(406, COMERCIAL, ENTRADA)
    app.kommo = _Quebrado(FUNIS_DA_EQUIPE)
    app.process_inbound(msg(406, "I need to talk to a human please"))
    check("erro do Kommo na escalação não deixa o lead sem resposta", len(entregues) == 1, str(entregues))


def main():
    camada_pacote()
    camada_ponte()
    print()
    if FALHAS:
        print(f"FALHOU - {len(FALHAS)} checagem(ns): {FALHAS}")
        return 1
    print("PASSOU - o SDR decide igual nos três níveis, só escreve e só fala quando o nível manda, "
          "e não toca no que é da equipe")
    return 0


if __name__ == "__main__":
    sys.exit(main())
