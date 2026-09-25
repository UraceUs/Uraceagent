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
# Estrutura real da conta (25/09, via Command Center), mais o Novo funil que
# o setup cria. Os funis da equipe estão aqui para provar que ninguém mexe
# neles.
def _st(i, nome, sort, tipo=0):
    return {"id": i, "name": nome, "sort": sort, "type": tipo}


FUNIS_DA_EQUIPE = [
    {"id": 9903543, "name": "Urace", "_embedded": {"statuses": [
        _st(76050835, "Incoming leads", 10, 1), _st(105276412, "First Contact", 10),
        _st(77188783, "Cold Leads", 70), _st(78606031, "Hot Leads", 80),
        _st(142, "Closed won", 10000), _st(143, "Lost sale", 11000)]}},
    {"id": 14512484, "name": "Comercial", "_embedded": {"statuses": [
        _st(112100844, "ENTRADA ", 20), _st(112100852, "ATENDIMENTO ", 40),
        _st(142, "Closed - won", 10000), _st(143, "Closed - lost", 11000)]}},
    {"id": 14316000, "name": "Chase — AI Sales Funnel", "_embedded": {"statuses": [
        _st(110564420, "New Inquiry", 20)]}},
]
NOVO_ID = 99000001
NOVO_FUNIL = {"id": NOVO_ID, "name": "Novo funil", "_embedded": {"statuses": (
    [_st(99100000 + i, nome, 20 + i * 10) for i, nome in enumerate(regras.ORDEM_ETAPAS)]
    + [_st(142, "Closed - won", 10000), _st(143, "Closed - lost", 11000)])}}
ETAPA = {nome: 99100000 + i for i, nome in enumerate(regras.ORDEM_ETAPAS)}


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
        ("Oi", entrada, regras.FICA, "Aguardando contexto", roteador.RESPONDER),
        ("Quanto custa o 1-Day?", entrada, regras.PROMOVER, "Em qualificação (robô)", roteador.RESPONDER),
        ("713157 is your code to log in to Kommo", entrada, regras.FICA,
         "Automáticos (e-mails e códigos)", roteador.SILENCIAR),
        ("Nossa empresa oferece trafego pago", entrada, regras.FICA,
         "Ruído (spam e fornecedores)", roteador.SILENCIAR),
        ("Pare de mandar mensagem", entrada, regras.FICA, "PERDIDO", roteador.CONFIRMAR_OPT_OUT),
        ("Lets do it, when can he start?", entrada, regras.PROMOVER, "Atendimento humano", roteador.ESCALAR),
        ("He currently races in SKUSA", entrada, regras.PROMOVER, "Atendimento humano", roteador.ESCALAR),
        ("Tem desconto para 2 pilotos?", entrada, regras.PROMOVER, "Atendimento humano", roteador.ESCALAR),
        ("Obrigado!", entrada, regras.FICA, "Sem sinal comercial", roteador.RESPONDER),
        ("Quanto custa?", {"existe": True, "zona": regras.COMERCIAL}, regras.ANEXAR, None, roteador.RESPONDER),
    ]
    for texto, card, acao, etapa, rota in casos:
        r = sdr.avaliar(texto, card=card)
        d = r["triagem"]
        check(f"'{texto[:30]}' -> {acao} / {etapa} / {rota}",
              d["acao"] == acao and d["destino"]["etapa"] == etapa and r["roteamento"]["acao"] == rota,
              f"{d['acao']} / {d['destino']} / {r['roteamento']}")

    check("desconto é fila (média), conversão interrompe (alta)",
          sdr.avaliar("Tem desconto?")["roteamento"]["prioridade"] == "media"
          and sdr.avaliar("lets do it")["roteamento"]["prioridade"] == "alta")

    em_reserva = {"existe": True, "zona": regras.COMERCIAL, "etapa": funil.chave("Reserva Etapa 1 (Pit ID)")}
    r = sdr.avaliar("quero falar com alguem", card=em_reserva)
    check("handoff não tira da reserva quem já está na Etapa 1", not r["triagem"]["destino"]["mover"])

    for tipo, etapa in [("reserva_etapa1", "Reserva Etapa 1 (Pit ID)"), ("reserva_etapa2", "GANHO"),
                        ("formulario", "Lead novo")]:
        d = triagem.triar({"tipo": tipo}, classificador.classificar(""), entrada)
        check(f"evento {tipo} -> {etapa}", d["destino"]["etapa"] == etapa, str(d["destino"]))

    limpo, v = estilo.aplicar("Great! 🏁 Come by anytime — we are open. The 1-Day is the best start.")
    check("estilo corta emoji, travessão e frase proibida",
          limpo == "Great! The 1-Day is the best start." and "nunca_dizer:come by" in v, f"{limpo!r} {v}")

    plano = funil.planejar(FUNIS_DA_EQUIPE)
    check("conta atual: falta só o Novo funil, com as 10 etapas",
          plano["criar_funil"] and plano["etapas"] == regras.ORDEM_ETAPAS)
    corpo = funil.corpo_criacao()[0]
    check("Novo funil nasce sem Incoming leads e fora do principal",
          corpo["is_unsorted_on"] is False and corpo["is_main"] is False)
    faltando = dict(NOVO_FUNIL, _embedded={"statuses": NOVO_FUNIL["_embedded"]["statuses"][1:]})
    check("etapa apagada à mão aparece como pendência",
          funil.planejar(FUNIS_DA_EQUIPE + [faltando])["etapas_faltando"] == ["Triagem"])

    m = funil.Mapa(FUNIS_DA_EQUIPE + [NOVO_FUNIL])
    check("card da equipe está fora do SDR", not m.localizar(9903543, 105276412)["do_sdr"])
    check("Triagem é zona Entrada; Atendimento humano é Comercial",
          m.localizar(NOVO_ID, ETAPA["Triagem"])["zona"] == regras.ENTRADA
          and m.localizar(NOVO_ID, ETAPA["Atendimento humano"])["zona"] == regras.COMERCIAL)
    check("GANHO e PERDIDO são os fechamentos nativos",
          m.status_id("GANHO") == 142 and m.status_id("PERDIDO") == 143)

    # Executor: observar calcula e não escreve; organizar escreve.
    for modo, espera in [(executor.OBSERVAR, 0), (executor.ORGANIZAR, 3)]:
        falso = KommoFalso(FUNIS_DA_EQUIPE + [NOVO_FUNIL])
        falso.lead(1, NOVO_ID, ETAPA["Triagem"])
        api = type("Api", (), {"move": staticmethod(falso.move_lead), "add_tags": staticmethod(falso.add_tags),
                               "add_note": staticmethod(falso.add_note), "add_task": staticmethod(falso.add_task)})
        r = sdr.avaliar("Quanto custa o Academy?", card={"existe": True, "zona": regras.ENTRADA})
        feito = executor.aplicar(api, falso.leads[1], r["triagem"], m, modo)
        check(f"executor em {modo}: decide igual, escreve {espera}",
              feito["moveu"] == "Em qualificação (robô)" and len(falso.escritas) == espera,
              f"{feito} {falso.escritas}")


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
        falso = KommoFalso(FUNIS_DA_EQUIPE + [NOVO_FUNIL])
        entregues, avisos = [], []
        app.kommo = falso
        sdr_ponte.kommo = falso
        sdr_ponte._forcar_kommo = True
        sdr_ponte._cache["mapa"] = None
        sdr_ponte._vistas.clear()
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

    # --- observar
    nivel("observar")
    falso, entregues, _ = preparar()
    falso.lead(201, NOVO_ID, ETAPA["Triagem"])
    app.process_inbound(msg(201, "Quanto custa o 1-Day?"))
    check("observar: a ponte não responde ao lead", entregues == [], str(entregues))
    check("observar: nada é escrito no Kommo", falso.escritas == [], str(falso.escritas))
    feito = sdr_ponte.triar_lead(201, "Quanto custa o 1-Day?")
    check("observar: a decisão fica registrada (e seria mover para venda)",
          feito["modo"] == "observar" and feito["moveu"] == "Em qualificação (robô)", str(feito))

    corpo = {"message": {"add": {"0": {"id": "m1", "text": "Your code is 711995", "type": "incoming",
                                       "element_type": "2", "element_id": "202", "origin": "email"}}}}
    falso.lead(202, NOVO_ID, ETAPA["Triagem"])
    r = sdr_ponte.processar_eventos(corpo)
    check("webhook de conta: código cairia em Automáticos",
          r and r[0]["moveu"] == "Automáticos (e-mails e códigos)", str(r))
    check("webhook de conta: mesma mensagem duas vezes é tratada uma vez",
          sdr_ponte.processar_eventos(corpo) == [])

    # --- organizar
    nivel("organizar")
    falso, entregues, _ = preparar()
    falso.lead(301, NOVO_ID, ETAPA["Aguardando contexto"])
    falso.lead(302, 9903543, 105276412)  # card do funil Urace, da equipe
    corpo = {"message": {"add": [
        {"id": "o1", "text": "Quanto custa o Academy?", "type": "incoming", "element_type": "2", "element_id": "301"},
        {"id": "o2", "text": "Quanto custa?", "type": "incoming", "element_type": "2", "element_id": "302"},
        {"id": "o3", "text": "resposta da equipe", "type": "outgoing", "element_type": "2", "element_id": "301"},
    ]}}
    r = sdr_ponte.processar_eventos(corpo)
    check("organizar: card desce para venda com nota", falso.leads[301]["status_id"] == ETAPA["Em qualificação (robô)"]
          and any(e[0] == "nota" for e in falso.escritas), str(falso.escritas))
    check("organizar: card de funil da equipe não é tocado",
          falso.leads[302]["status_id"] == 105276412 and r[1].get("ignorado") == "FORA_DO_NOVO_FUNIL", str(r))
    check("organizar: mensagem da equipe (outgoing) é ignorada", len(r) == 2)

    falso.lead(303, NOVO_ID, ETAPA["Triagem"])
    sdr_ponte.KOMMO_RESPONSAVEL_ID = "777"
    sdr_ponte.processar_eventos({"message": {"add": [{"id": "o4", "text": "Quero falar com alguem",
                                                      "type": "incoming", "element_type": "2", "element_id": "303"}]}})
    tarefas = [e for e in falso.escritas if e[0] == "tarefa" and e[1] == 303]
    check("organizar: pedido de humano vira Atendimento humano + tarefa do responsável",
          falso.leads[303]["status_id"] == ETAPA["Atendimento humano"] and tarefas and tarefas[0][3] == "777",
          str(falso.escritas))
    app.process_inbound(msg(303, "oi?"))
    check("organizar: a ponte continua sem responder ao lead", entregues == [])

    # --- atender
    nivel("atender")
    falso, entregues, avisos = preparar()
    falso.lead(401, NOVO_ID, ETAPA["Triagem"])
    app.process_inbound(msg(401, "713157 is your code to log in to Kommo"))
    conv = state.get_conversation(401)
    check("atender: código não recebe resposta (não é lead)", entregues == [], str(entregues))
    check("atender: e o resgate não vai responder por nós",
          (conv.get("last_outbound_at") or 0) >= (conv.get("last_inbound_at") or 0))

    falso.lead(402, NOVO_ID, ETAPA["Aguardando contexto"])
    app.process_inbound(msg(402, "Please stop messaging me, unsubscribe"))
    check("atender: opt-out recebe uma confirmação e fecha",
          len(entregues) == 1 and state.get_conversation(402)["state"] == "CLOSED", str(entregues))
    check("atender: opt-out vai para Perdido com a tag opt_out",
          falso.leads[402]["status_id"] == 143
          and any(e[0] == "tags" and "opt_out" in e[2] for e in falso.escritas), str(falso.escritas))

    entregues.clear()
    falso.lead(403, NOVO_ID, ETAPA["Em qualificação (robô)"])
    app.process_inbound(msg(403, "Lets do it! When can he start?"))
    check("atender: sinal de conversão escala na hora (alta) e o lead é respondido",
          state.get_conversation(403)["state"] == "WAITING_HUMAN" and len(avisos) == 1 and len(entregues) == 1,
          f"{avisos} {entregues}")
    check("atender: card vai para Atendimento humano",
          falso.leads[403]["status_id"] == ETAPA["Atendimento humano"], str(falso.leads[403]))

    avisos.clear()
    entregues.clear()
    falso.lead(404, NOVO_ID, ETAPA["Em qualificação (robô)"])
    app.process_inbound(msg(404, "Tem algum desconto?"))
    check("atender: desconto vai para a fila (tarefa), sem interromper no WhatsApp",
          avisos == [] and any(e[0] == "tarefa" and e[1] == 404 for e in falso.escritas)
          and len(entregues) == 1, f"{avisos} {falso.escritas}")

    entregues.clear()
    falso, entregues, _ = preparar(agente="Great 🏁 you can come by anytime. The 1-Day is the best start.")
    falso.lead(405, NOVO_ID, ETAPA["Triagem"])
    app.process_inbound(msg(405, "How does the 1-Day work?"))
    check("atender: resposta do modelo passa pela guarda de estilo",
          entregues and "🏁" not in entregues[0][1] and "come by" not in entregues[0][1].lower(), str(entregues))

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
    falso.lead(406, NOVO_ID, ETAPA["Triagem"])
    app.kommo = _Quebrado(FUNIS_DA_EQUIPE + [NOVO_FUNIL])
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
