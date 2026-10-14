#!/usr/bin/env python3
"""Nível atender (13/10): a ponte responde TODA mensagem que chega pelo webhook de conta, e a
equipe pode pausar a IA numa conversa pelo Command Center.

Dono, 13/10: "precisa ser em todas as msg e ter a possibilidade de desativar pelo command center
… respostas da ia em uma conversa específica".

Contexto do teste ao vivo de 13/10: em atender o /kommo/eventos só confirmava o recebimento e
esperava o Salesbot chamar o /kommo/hook — mas o Salesbot #9 estava sem gatilho, e o menor
intervalo que o Kommo aceita lá é 5 min. Resultado: quatro DMs, nenhuma resposta.

Sem rede: Kommo, agente e Salesbot são stubs.

Uso:
    python3 salesagent/tests/test_sdr_atender_eventos.py
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SALESAGENT = HERE.parent
_TMP = tempfile.mkdtemp(prefix="urace-sdr-atender-")
os.environ["URACE_DIR"] = _TMP
os.environ["SDR_MODO"] = "atender"
sys.path.insert(0, str(SALESAGENT))
sys.path.insert(0, str(SALESAGENT / "bridge"))

FALHAS = []


def check(rotulo, cond, detalhe=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {rotulo}" + ("" if cond else f"  {detalhe}"))
    if not cond:
        FALHAS.append(rotulo)


class _Kommo:
    def __init__(self):
        self.bots, self.notas, self.leads = [], [], {}

    def run_bot(self, bot_id, lead_id):
        self.bots.append((int(bot_id), int(lead_id)))
        return True

    def add_note(self, lead_id, texto):
        self.notas.append((lead_id, texto))

    def get_lead(self, lead_id):
        return self.leads[int(lead_id)]


class _Mapa:
    """Urace: 10 = First Contact (gerenciada), 11 = Hot Leads (equipe). Comercial: 20 = ENTRADA,
    21 = ATENDIMENTO. 142/143 = fechado. Outro funil (9) = fora do SDR."""

    def localizar(self, pipeline_id, status_id):
        sid = int(status_id or 0)
        fechado = sid in (142, 143)
        if pipeline_id == 1:
            return {"do_sdr": True, "zona": "Entrada", "fechado": fechado, "incoming": False,
                    "gerenciada": sid == 10, "resgate": False, "etapa": {10: "First Contact", 11: "Hot Leads"}.get(sid)}
        if pipeline_id == 2:
            return {"do_sdr": True, "zona": "Comercial", "fechado": fechado, "incoming": False,
                    "gerenciada": sid in (20, 21), "resgate": False, "etapa": {20: "ENTRADA   ", 21: "ATENDIMENTO"}.get(sid)}
        return {"do_sdr": False, "zona": None, "fechado": fechado, "incoming": False,
                "gerenciada": False, "resgate": False, "etapa": None}


def _lead(lid, pipeline, status, tags=()):
    return {"id": lid, "pipeline_id": pipeline, "status_id": status, "created_at": int(time.time()) - 86400,
            "_embedded": {"tags": [{"name": t} for t in tags]}}


def _evento(msg_id, lead_id, texto):
    return {"message": {"add": [{"id": msg_id, "type": "incoming", "text": texto, "element_type": "2",
                                 "element_id": str(lead_id), "origin": "instagram"}]}}


def rodar() -> list[str]:
    FALHAS.clear()
    import app
    import pausas
    import scheduler
    import sdr_ponte
    import state
    import textproc

    (Path(pausas.URACE_DIR) / pausas.ARQUIVO).unlink(missing_ok=True)
    k = _Kommo()
    app.kommo = k
    sdr_ponte.kommo = k
    sdr_ponte.mapa = lambda forcar=False: _Mapa()
    triados = []
    sdr_ponte.triar_em_segundo_plano = lambda lead_id, texto, rota=None: triados.append((lead_id, texto))
    app.FOLLOWUP_BOT_ID = "162247"
    resposta = "Hi! Chase here from URACE. How old is the driver?"
    app._call_agent = lambda lead_id, msg: (resposta, textproc.extract_directives(resposta))
    app.notify_human = lambda texto: None
    continuados = []
    app._salesbot_continue = lambda lead_id, url, tok, texto: continuados.append((lead_id, texto)) or True
    app.scheduler.cancel = lambda lead_id, reason="": None
    app.scheduler.start_track = lambda lead_id, track: None

    k.leads.update({
        101: _lead(101, 1, 10, ["teste-sdr"]),   # Urace > First Contact
        102: _lead(102, 1, 11),                  # Urace > Hot Leads (equipe)
        103: _lead(103, 2, 20),                  # Comercial > ENTRADA
        104: _lead(104, 2, 21),                  # Comercial > ATENDIMENTO (pessoa)
        105: _lead(105, 9, 1),                   # outro funil
        106: _lead(106, 1, 143),                 # Urace fechado
        107: _lead(107, 1, 10),                  # First Contact, sem a tag de teste
    })

    print("1. Escopo: onde o robô responde")
    for lid, esperado in ((101, (True, "OK")), (102, (False, "ETAPA_DA_EQUIPE")), (103, (True, "OK")),
                          (104, (False, "ETAPA_DA_EQUIPE")), (105, (False, "FUNIL_FORA_DO_SDR")),
                          (106, (False, "CARD_FECHADO"))):
        check(f"lead {lid} -> {esperado}", sdr_ponte.pode_responder(lid) == esperado, sdr_ponte.pode_responder(lid))
    sdr_ponte.SDR_ATENDER_SO_TAG = "teste-sdr"
    check("fase de teste: First Contact sem a tag não recebe", sdr_ponte.pode_responder(107) == (False, "SEM_TAG_DE_TESTE"))
    check("fase de teste: o card com a tag recebe", sdr_ponte.pode_responder(101) == (True, "OK"))

    print("\n2. Toda mensagem do webhook de conta é respondida, sem gatilho de Salesbot")
    r = app.responder_eventos(_evento("m1", 101, "quanto custa pra criança de 8 anos?"), espera=0)
    check("respondida", r == [{"lead_id": 101, "resposta": "RESPONDIDA"}], r)
    check("a ponte disparou o bot de entrega (bots/run) no lead", k.bots == [(162247, 101)], k.bots)
    pendente = state.get_conversation(101).get("pending_followup_text") or ""
    check("o texto ficou pendente para o bot buscar", "How old is the driver?" in pendente, pendente)
    check("nada virou nota (a resposta não se perdeu)", not k.notas, k.notas)
    app.process_inbound({"lead_id": 101, "message": "", "return_url": "https://kommo/continue/1"})
    check("o bot buscou o texto e ele foi entregue no chat", continuados and "How old" in continuados[-1][1], continuados)
    check("o card também foi organizado", (101, "quanto custa pra criança de 8 anos?") in triados, triados)
    r = app.responder_eventos(_evento("m2", 101, "quero começar, como faço?"), espera=0)
    check("a segunda mensagem também é respondida (sem intervalo de 5 min)",
          r == [{"lead_id": 101, "resposta": "RESPONDIDA"}] and len(k.bots) == 2, (r, k.bots))
    check("o mesmo evento repetido pelo Kommo não responde duas vezes",
          app.responder_eventos(_evento("m2", 101, "quero começar, como faço?"), espera=0) == [])

    print("\n2b. Rajada: \"Oi\" + \"Quanto custa?\" seguidos viram UMA resposta (14/10)")
    recebidos = []
    app._call_agent = lambda lead_id, msg: (recebidos.append(msg) or resposta,
                                            textproc.extract_directives(resposta))
    bots_antes = len(k.bots)
    rajada = {"message": {"add": [
        {"id": "r1", "type": "incoming", "text": "Oi", "element_type": "2",
         "element_id": "101", "origin": "instagram"},
        {"id": "r2", "type": "incoming", "text": "Quanto custa?", "element_type": "2",
         "element_id": "101", "origin": "instagram"}]}}
    r = app.responder_eventos(rajada, espera=0)
    check("no mesmo payload: a primeira junta com a seguinte, a última responde",
          r == [{"lead_id": 101, "resposta": "JUNTADA_COM_A_SEGUINTE"},
                {"lead_id": 101, "resposta": "RESPONDIDA"}], r)
    check("uma entrega só", len(k.bots) == bots_antes + 1, k.bots)
    check("o agente recebeu as duas mensagens juntas",
          recebidos and "Oi" in recebidos[-1] and "Quanto custa?" in recebidos[-1], recebidos[-1:])
    import threading
    resultados = []
    t1 = threading.Thread(target=lambda: resultados.extend(
        app.responder_eventos(_evento("r3", 101, "Oi de novo"), espera=0.6)))
    t1.start()
    time.sleep(0.2)
    resultados.extend(app.responder_eventos(_evento("r4", 101, "Qual o valor?"), espera=0.6))
    t1.join()
    check("em webhooks separados (6 s de diferença na vida real): também uma resposta só",
          sorted(x["resposta"] for x in resultados) == ["JUNTADA_COM_A_SEGUINTE", "RESPONDIDA"]
          and len(k.bots) == bots_antes + 2, (resultados, k.bots))
    app._call_agent = lambda lead_id, msg: (resposta, textproc.extract_directives(resposta))

    print("\n2c. Mensagens curtas: um bloco vira balões separados, entregues em fila (14/10)")
    bloco = ("Oi, aqui é o Chase da URACE. É um dia inteiro na pista num kart de corrida de verdade, "
             "com o coach do seu lado o tempo todo: kart, equipamento de segurança, briefing e "
             "coaching inclusos. Na categoria 4 tempos fica $719 o dia, na 2 tempos $819. A taxa "
             "da pista é separada, paga direto pro Orlando Kart Center. Quantos anos tem o piloto?")
    msgs = app.dividir_em_mensagens(bloco)
    check("o bloco do print vira 2 a 4 mensagens curtas",
          2 <= len(msgs) <= app.MENSAGENS_MAX and all(len(m) <= app.MENSAGEM_MAX for m in msgs[:-1])
          and " ".join(msgs) == bloco, msgs)
    linhas = "Oi! Aqui é o Chase, da URACE.\nUm dia inteiro na pista: $719.\nÉ pra você ou pra outra pessoa?"
    check("cada linha do modelo é uma mensagem", app.dividir_em_mensagens(linhas) == linhas.split("\n"),
          app.dividir_em_mensagens(linhas))
    modo_antes, intervalo_antes = app.SALESBOT_DISPLAY, app.INTERVALO_ENTRE_MENSAGENS_S
    app.SALESBOT_DISPLAY, app.INTERVALO_ENTRE_MENSAGENS_S = "json_reply", 0.05
    spc_antes, app.SEGUNDOS_POR_CARACTERE = app.SEGUNDOS_POR_CARACTERE, 0
    bots_antes, cont_antes = len(k.bots), len(continuados)
    resposta = linhas
    app._call_agent = lambda lead_id, msg: (resposta, textproc.extract_directives(resposta))
    app.responder_eventos(_evento("q1", 101, "quanto custa?"), espera=0)
    for _ in range(3):  # o bot de entrega busca uma mensagem por disparo
        app.process_inbound({"lead_id": 101, "message": "", "return_url": "https://kommo/continue/q"})
        time.sleep(0.3)
    entregues_q = [t for _lid, t in continuados[cont_antes:]]
    check("três balões, na ordem, um por disparo do bot",
          entregues_q == linhas.split("\n") and len(k.bots) == bots_antes + 3, (entregues_q, k.bots))
    check("a fila terminou vazia", not state.get_conversation(101).get("pending_followup_text"))
    app.SALESBOT_DISPLAY, app.INTERVALO_ENTRE_MENSAGENS_S = modo_antes, intervalo_antes
    app.SEGUNDOS_POR_CARACTERE = spc_antes
    resposta = "Hi! Chase here from URACE. How old is the driver?"
    app._call_agent = lambda lead_id, msg: (resposta, textproc.extract_directives(resposta))

    print("\n2d. Testar o robô pelo painel: mesma guarda, nada no Kommo (14/10)")
    sessoes = []
    resp_teste = ("Oi! Aqui é o Chase, da URACE.\nVeja tudo aqui: https://urace.us/urace-academy/\n"
                  "É pra você ou pra outra pessoa?\n[[crm op=tags tags=\"x\"]]")
    app._call_agent = lambda lead_id, msg, session_key=None: (
        sessoes.append(session_key) or resp_teste, textproc.extract_directives(resp_teste))
    escritas_antes, bots_antes = (len(k.notas), len(k.bots))
    t = app.turno_de_teste("cc-teste01", "Oi, quanto custa?", "Eduardo")
    check("roda numa sessão de teste própria, nunca na de um lead", sessoes == ["playground-cc-teste01"], sessoes)
    check("primeira resposta do teste também sai sem link (mesma guarda)",
          all("http" not in m for m in t["mensagens"]) and "link_na_primeira_resposta" in t["cortes"], t)
    check("a diretiva aparece, mas não é executada nem vai ao lead",
          t["diretivas"] and not any("[[" in m for m in t["mensagens"]), t)
    check("balões separados", t["mensagens"] == ["Oi! Aqui é o Chase, da URACE.", "É pra você ou pra outra pessoa?"],
          t["mensagens"])
    t2 = app.turno_de_teste("cc-teste01", "8 anos", "Eduardo")
    check("da segunda em diante o link passa", any("urace-academy" in m for m in t2["mensagens"]), t2)
    check("nada escrito no Kommo nem disparado", (len(k.notas), len(k.bots)) == (escritas_antes, bots_antes),
          (k.notas, k.bots))
    t3 = app.turno_de_teste("cc-teste01", "Faria se fosse mais barato")
    check("objeção de preço no teste mostra a oferta de call da ponte",
          any("calendar.app.google" in m for m in t3["mensagens"]) and "Objeção" in t3["nota"], t3)
    t4 = app.turno_de_teste("cc-teste02", "Faria se fosse mais barato")
    check("objeção logo na 1ª mensagem: sai sem link e sem a chamada pendurada",
          t4["mensagens"] and all("http" not in m and not m.rstrip().endswith(":") for m in t4["mensagens"]), t4)
    try:
        app.turno_de_teste("../x", "oi")
        check("sessão inválida é recusada", False)
    except Exception as exc:
        check("sessão inválida é recusada", getattr(exc, "status_code", 0) == 400, exc)
    app._call_agent = lambda lead_id, msg, session_key=None: (resposta, textproc.extract_directives(resposta))

    print("\n2e. \"Agora não\": respeita, sem follow-up, com tarefa para uma pessoa (14/10)")
    tarefas, tags_postas = [], []
    k.add_task = lambda lead_id, texto, ate, responsible_user_id=None: tarefas.append((lead_id, texto, ate))
    app.kommo_tags_seguras = lambda lead_id, tags: tags_postas.append((lead_id, tuple(tags))) or True
    cancelados = []
    app.scheduler.cancel = lambda lead_id, reason="": cancelados.append((lead_id, reason))
    iniciados = []
    app.scheduler.start_track = lambda lead_id, track: iniciados.append((lead_id, track))
    bots_antes = len(k.bots)
    r = app.responder_eventos(_evento("a1", 101, "Agora não, obrigado"), espera=0)
    check("responde, agradece e deixa a porta aberta", r == [{"lead_id": 101, "resposta": "RESPONDIDA"}]
          and len(k.bots) == bots_antes + 1 and "Sem problema" in (state.get_conversation(101).get("pending_followup_text") or ""),
          (r, state.get_conversation(101).get("pending_followup_text")))
    check("não começa trilha de follow-up e cancela a que existia", iniciados == [] and (101, "lead pediu para falar depois") in cancelados,
          (iniciados, cancelados))
    check("marca o card e cria a tarefa para uma pessoa retomar em 7 dias",
          (101, ("sdr:agora-nao",)) in tags_postas and len(tarefas) == 1
          and 6 * 86400 < tarefas[0][2] - int(time.time()) <= 7 * 86400, (tags_postas, tarefas))
    check("o card não é fechado", state.get_conversation(101)["state"] != "CLOSED")
    t5 = app.turno_de_teste("cc-teste03", "Not now, thanks")
    check("no teste do painel aparece a nota e a resposta em inglês",
          t5["rota"] == "adiar" and any("No problem" in m for m in t5["mensagens"]) and "adiou" in t5["nota"], t5)

    print("\n3. Fora do escopo: só organiza")
    sdr_ponte.SDR_ATENDER_SO_TAG = ""
    antes = len(k.bots)
    r = app.responder_eventos(_evento("m3", 104, "oi, tudo certo pra sexta?"), espera=0)
    check("lead com a pessoa (ATENDIMENTO) não recebe resposta da ponte",
          r == [{"lead_id": 104, "resposta": "ETAPA_DA_EQUIPE"}] and len(k.bots) == antes, (r, k.bots))
    check("mas o card é organizado", (104, "oi, tudo certo pra sexta?") in triados)

    print("\n4. Se o Salesbot do Kommo já tratou a mensagem, a ponte não responde de novo")
    state.update_conversation(103, last_inbound_at=int(time.time()), last_inbound_text="tem aula sábado?")
    r = app.responder_eventos(_evento("m4", 103, "tem aula sábado?"), espera=0)
    check("JA_TRATADA_PELO_SALESBOT", r == [{"lead_id": 103, "resposta": "JA_TRATADA_PELO_SALESBOT"}], r)

    print("\n5. IA pausada numa conversa pelo Command Center")
    # o URACE_DIR que vale é o do config já importado (no pytest, outro teste pode ter importado antes)
    arquivo = Path(pausas.URACE_DIR) / pausas.ARQUIVO
    arquivo.write_text(json.dumps({"101": {"por": "Lucas", "em": "2026-10-13T11:00:00-04:00"}}), encoding="utf-8")
    antes = len(k.bots)
    r = app.responder_eventos(_evento("m5", 101, "e o preço do academy?"), espera=0)
    check("a ponte não responde", len(k.bots) == antes, k.bots)
    with state.db() as conn:
        g = conn.execute("SELECT detail FROM audit WHERE kind='gate' AND lead_id=101 ORDER BY id DESC LIMIT 1").fetchone()
    check("e registra o motivo", g and "IA pausada" in g[0], g)
    check("o card continua sendo organizado", (101, "e o preço do academy?") in triados)
    check("a entrega espontânea (follow-up/resgate) também para", app.deliver_followup(101, "oi?") is False)
    check("a outra conversa segue normal", app.responder_eventos(_evento("m6", 103, "qual o horário?"), espera=0)
          == [{"lead_id": 103, "resposta": "RESPONDIDA"}])
    agora = int(time.time())
    state.update_conversation(101, last_inbound_at=agora - 3600, last_outbound_at=agora - 7200, state="AI_ACTIVE")
    resgatados = []
    scheduler.rescue_fn = lambda conv: resgatados.append(conv["lead_id"]) or True
    scheduler.tick(agora)
    check("o agendador não resgata a conversa pausada", 101 not in resgatados, resgatados)
    arquivo.write_text("{ quebrado", encoding="utf-8")
    check("arquivo ilegível = nenhuma pausa (a ponte segue respondendo)", pausas.ia_pausada(101) is False)
    arquivo.unlink()
    check("sem o arquivo, nenhuma pausa", pausas.pausadas() == {})
    return list(FALHAS)


def test_sdr_atender_eventos():
    assert rodar() == []


def main(argv=None) -> int:
    f = rodar()
    print("\nRESULTADO:", "PASSOU" if not f else f"FALHOU ({len(f)}): " + "; ".join(f))
    return 1 if f else 0


if __name__ == "__main__":
    sys.exit(main())
