#!/usr/bin/env python3
"""Rodada final do robô SDR (14/10): o que a revisão de vendas e de engenharia mudou.

- quem decide ("quero fechar"), quem já corre e quem acha caro recebe a oferta de call, não a espera;
- o nome do lead só entra na mensagem se parecer nome de gente;
- ninguém recebe follow-up de madrugada, e o toque nunca é perdido por isso;
- nomes do time não chegam ao modelo;
- o robô registra o que o Kommo diz sobre mensagens que saíram.

Os testes que importam a ponte inteira (config, estado, agendador) rodam em processo à parte, com banco
temporário: importar config cedo demais trava o URACE_DIR dos outros testes.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SALESAGENT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SALESAGENT / "bridge"))
sys.path.insert(0, str(SALESAGENT))

import holding  # noqa: E402
import textproc  # noqa: E402
from sdr import evento  # noqa: E402

LINK = "https://calendar.app.google/KBbHhXjoRMS6sbHv8"


# ------------------------------------------------------------------ ofertas de call
@pytest.mark.parametrize("motivo", ["objecao", "decisao", "competidor"])
@pytest.mark.parametrize("texto,idioma", [("Quero fechar", "pt"), ("how much is it", "en"), ("hola, cuánto cuesta", "es")])
def test_oferta_de_call_por_motivo(motivo, texto, idioma):
    msg = holding.call_offer(texto, LINK, contact_name="Eduardo F F", motivo=motivo)
    linhas = msg.split("\n")
    assert linhas[-1] == LINK, "o link fica sozinho na última linha"
    assert 3 <= len(linhas) <= 4, "poucos balões curtos"
    assert all(len(l) <= 110 for l in linhas[:-1]), linhas
    assert "Lucas" not in msg and "Italo" not in msg
    assert msg.count("?") <= 1
    assert "Eduardo" in msg
    esperado = {"pt": "nosso time", "en": "our team", "es": "nuestro equipo"}[idioma]
    assert esperado in msg


def test_oferta_de_decisao_nao_promete_data_nem_desconto():
    msg = holding.call_offer("Quero fechar", LINK, motivo="decisao").lower()
    for proibido in ("reservad", "confirmad", "desconto", "% off", "garant"):
        assert proibido not in msg


def test_motivos_do_roteador_que_viram_call():
    assert holding.MOTIVO_DA_CALL == {"NEGOCIACAO": "objecao", "SINAL_CONVERSAO": "decisao",
                                      "PILOTO_COMPETIDOR": "competidor"}
    # pedir uma pessoa e assunto sensível continuam na frase de passagem, nunca na oferta de call
    assert "PEDIDO_HUMANO" not in holding.MOTIVO_DA_CALL and "TEMA_SENSIVEL" not in holding.MOTIVO_DA_CALL


@pytest.mark.parametrize("nome,esperado", [
    ("Eduardo F F Resende", " Eduardo"),
    ("055⚡ · Eduardo F F Resende", " Eduardo"),       # o prefixo de score do Kommo não é nome
    ("@urace_fan23", ""), ("urace_fan23", ""), ("12345", ""), ("", ""), (None, ""),
    ("João", " João"), ("Ana-Clara", ""),
])
def test_primeiro_nome_so_se_parece_nome_de_gente(nome, esperado):
    assert holding._primeiro_nome(nome) == esperado


# ------------------------------------------------------------------ nomes do time não chegam ao modelo
def test_nomes_do_time_saem_do_contexto_do_modelo():
    assert textproc.sem_nomes_do_time("Passe para o Lucas ou para o Italo.") == "Passe para o a equipe ou para o a equipe."
    assert textproc.sem_nomes_do_time("Lúcas confirmou") == "a equipe confirmou"
    assert textproc.sem_nomes_do_time("") == "" and textproc.sem_nomes_do_time(None) == ""
    assert textproc.sem_nomes_do_time("Lucasfilm") == "Lucasfilm", "só a palavra inteira"


# ------------------------------------------------------------------ mensagens que saíram
def test_mensagens_enviadas_so_as_que_nao_sao_do_lead():
    payload = {"message": {"add": [
        {"id": "1", "type": "incoming", "text": "Oi", "element_type": "2", "element_id": "5"},
        {"id": "2", "type": "outgoing", "text": "Oi! Aqui é o Chase, da URACE. Um dia inteiro na pista",
         "element_type": "2", "element_id": "5", "origin": "instagram",
         "author": {"id": "77", "type": "internal", "name": "Fulano"}},
    ]}}
    assert [m["id"] for m in evento.mensagens_recebidas(payload)] == ["1"]
    saiu = evento.mensagens_enviadas(payload)
    assert len(saiu) == 1 and saiu[0]["lead_id"] == 5 and saiu[0]["tipo"] == "outgoing"
    assert saiu[0]["autor_tipo"] == "internal" and saiu[0]["autor_id"] == "77"
    assert len(saiu[0]["inicio"]) <= 40, "nunca o texto inteiro"
    assert evento.mensagens_enviadas({}) == [] and evento.mensagens_enviadas(None) == []


# ------------------------------------------------------------------ horário de silêncio (processo à parte)
CODIGO_SILENCIO = r"""
import sys, time
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, %(bridge)r); sys.path.insert(0, %(raiz)r)
import scheduler as sch
ET = ZoneInfo("America/New_York")
def ts(dia, h, m=0):
    return int(datetime(2026, 10, dia, h, m, tzinfo=ET).timestamp())
def hora(t):
    d = datetime.fromtimestamp(t, tz=ET); return (d.day, d.hour, d.minute)

# dentro do horário: não mexe
assert sch.horario_de_envio(ts(20, 14), ts(20, 12, 30), ts(20, 12, 30)) == ts(20, 14)
# lead escreveu à 1h, o toque venceria às 2h30: vai para as 9h do mesmo dia (cabe na janela de 24 h)
assert hora(sch.horario_de_envio(ts(20, 2, 30), ts(20, 1), ts(20, 1))) == (20, 9, 0)
# venceria às 22h: vai para as 9h do dia seguinte
assert hora(sch.horario_de_envio(ts(20, 22), ts(20, 20, 30), ts(20, 20, 30))) == (21, 9, 0)
# 2º toque (23 h depois): o lead escreveu às 6h; venceria às 21h30 e as 9h seguintes já passam da janela
# (06h + 24h - 30 min = 05h30 do dia seguinte): sai no último horário da noite, 20h30, e não é perdido
assert hora(sch.horario_de_envio(ts(20, 21, 30), ts(20, 6), ts(20, 20))) == (20, 20, 30)
# se o agendador só olha depois das 20h30, não dá para sair mais cedo: sai quando venceu
assert sch.horario_de_envio(ts(20, 21, 30), ts(20, 6), ts(20, 21)) == ts(20, 21, 30)
# madrugada que cruza a janela: sai na noite anterior (20h30), se ainda dá tempo
assert hora(sch.horario_de_envio(ts(21, 3), ts(20, 4, 30), ts(20, 19))) == (20, 20, 30)
# desligado (testes que usam o relógio real)
sch.SILENCIO_LIGADO = False
assert sch.horario_de_envio(ts(20, 2, 30), ts(20, 1), ts(20, 1)) == ts(20, 2, 30)
print("ok")
"""


def _processo(codigo):
    env = dict(os.environ, URACE_DIR=tempfile.mkdtemp(prefix="urace-final-"), SDR_MODO="atender")
    r = subprocess.run([sys.executable, "-c", codigo], env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and r.stdout.strip().endswith("ok"), (r.stdout[-1500:], r.stderr[-2500:])


def test_horario_de_silencio_dos_follow_ups():
    _processo(CODIGO_SILENCIO % {"bridge": str(SALESAGENT / "bridge"), "raiz": str(SALESAGENT)})


CODIGO_DISPARO = r"""
import sys, time
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, %(bridge)r); sys.path.insert(0, %(raiz)r)
import scheduler as sch, state
ET = ZoneInfo("America/New_York")
def ts(h, m=0):
    return int(datetime(2026, 10, 20, h, m, tzinfo=ET).timestamp())
chamadas = []
sch.compose_fn = lambda *a: chamadas.append("compor") or "Oi"
sch.deliver_fn = lambda *a: chamadas.append("entregar") or True
sch.task_fn = lambda *a: chamadas.append("tarefa"); sch.note_fn = lambda *a: chamadas.append("nota")
state.get_conversation(901)
# 2h30 da manhã: o toque vence, mas não sai; fica marcado para as 9h
conv = {"lead_id": 901, "followup_track": "initial", "followup_attempts": 0, "state": "AI_ACTIVE", "last_inbound_at": ts(1)}
state.update_conversation(901, followup_track="initial", state="AI_ACTIVE", next_followup_at=ts(2, 30))
sch._fire_followup(conv, ts(2, 30))
assert chamadas == [], chamadas
assert state.get_conversation(901)["next_followup_at"] == ts(9), state.get_conversation(901)["next_followup_at"]
# às 9h sai normalmente
sch._fire_followup(dict(conv), ts(9))
assert chamadas == ["compor", "entregar"], chamadas
print("ok")
"""


def test_toque_de_madrugada_espera_as_9h_e_depois_sai():
    _processo(CODIGO_DISPARO % {"bridge": str(SALESAGENT / "bridge"), "raiz": str(SALESAGENT)})


# ------------------------------------------------------------------ persona e a finalização
def test_persona_sem_contradicao_conhecida():
    texto = (SALESAGENT / "instructions" / "urace-sales-agent.md").read_text(encoding="utf-8")
    assert "The finish line" in texto and 'reason="qualified: ready for' in texto
    assert "1h30 follow-up is the one" in texto, "a exceção do link no follow-up está nos dois lugares"
    assert "op=stage" not in texto.replace("you never use `[[crm op=stage]]`", ""), "o modelo não move etapa"
    assert "due=+3d" not in texto and "due=+7d" not in texto, "follow-up fora da janela da Meta"
    assert "a link or a video" not in texto, "o 2º toque é check-in sem link"


def test_preflight_e_roteiro_existem():
    assert (SALESAGENT / "tools" / "sdr_preflight.py").exists()
    roteiro = (SALESAGENT / "docs" / "liberar-robo-sdr.md").read_text(encoding="utf-8")
    for trecho in ("SDR_ATENDER_SO_TAG", "Pausar IA", "ATENDIMENTO", "Voltar atrás", "sdr_preflight.py"):
        assert trecho in roteiro, trecho


def test_preflight_roda_sem_rede_e_sem_vazar_segredo():
    env = dict(os.environ, URACE_DIR=tempfile.mkdtemp(prefix="urace-pre-"))
    # uma chave e um token de mentira no bridge.env: o script não pode imprimir nenhum dos dois
    Path(env["URACE_DIR"], "bridge.env").write_text("AGENT_API_KEY=chave-secreta-xyz\nSDR_MODO=atender\n")
    Path(env["URACE_DIR"], "kommo.env").write_text("KOMMO_TOKEN=token-secreto-abc\n")
    r = subprocess.run([sys.executable, str(SALESAGENT / "tools" / "sdr_preflight.py"), "--sem-rede"],
                       env=env, capture_output=True, text=True, timeout=60)
    saida = r.stdout + r.stderr
    assert "chave-secreta-xyz" not in saida and "token-secreto-abc" not in saida
    assert "Resultado:" in r.stdout, saida[-1500:]
    assert r.returncode in (0, 1)


# ------------------------------------------------------------------ RAG (busca no cofre `brain/`)
BRAIN = SALESAGENT.parent / "brain"


def test_indice_nao_traz_regra_velha_do_chase():
    """O cofre do tempo do Chase tinha o menu A/B/C/D, "preço só depois da classificação", follow-up
    +2h/+24h/+3d e o script "Italo handles program terms". Isso contradiz o playbook de 13/10 e, vindo no
    bloco [SYSTEM] do turno, ganharia da persona. Esses documentos ficam fora do índice."""
    sys.path.insert(0, str(BRAIN))
    import indexer
    db = Path(tempfile.mkdtemp(prefix="urace-rag-")) / "i.db"
    indexer.index_vault(BRAIN, db)
    import sqlite3
    caminhos = [r[0] for r in sqlite3.connect(db).execute("SELECT path FROM docs")]
    for velho in ("Objecoes", "Follow-ups", "Qualificacao", "Leads pedem preco"):
        assert not any(velho in c for c in caminhos), (velho, caminhos)
    assert any("Politicas Comerciais" in c for c in caminhos), "o que ainda vale continua"
    texto = " ".join(Path(BRAIN, c).read_text(encoding="utf-8") for c in caminhos)
    assert "Italo handles program terms" not in texto
    assert "menu fixo A/B/C/D" not in texto


def test_aviso_de_pouca_informacao_nao_manda_confirmar_o_que_a_persona_ja_sabe():
    import confidence
    for nivel in (confidence.NONE, confidence.LOW):
        nota = confidence.system_note({"level": nivel, "reason": "x"})
        assert "tabela de preços, dias e horários, endereço" in nota and "nas suas instruções" in nota, nivel


# ------------------------------------------------------------------ teste do comercial, 16/10
@pytest.mark.parametrize("texto,idioma", [
    ("E caro, faz por 2000 que fecho hoje?", "pt"), ("É caro, faz por 2000 que fecho hoje?", "pt"),
    ("Tem desconto?", "pt"), ("Esta muito caro", "pt"), ("es muy caro, hay descuento?", "es"),
    ("is it expensive?", "en"), ("can i bring my own kart?", "en"),
])
def test_idioma_da_objecao_curta(texto, idioma):
    assert holding.detect_language(texto) == idioma


def test_contraproposta_vira_call_no_idioma_do_lead():
    import sdr
    texto = "E caro, faz por 2000 que fecho hoje?"
    assert sdr.avaliar(texto)["roteamento"]["motivo"] == "NEGOCIACAO"
    msg = holding.call_offer(texto, LINK, motivo="objecao")
    assert "nosso time" in msg and "our team" not in msg


def test_academy_sem_preco_solto_e_com_minimo_de_6_meses():
    texto = (SALESAGENT / "instructions" / "urace-sales-agent.md").read_text(encoding="utf-8")
    for numero in ("2,756", "3,156", "$1,800", "$1,200"):
        assert numero not in texto, numero
    assert "6-month minimum" in texto and "never quote an Academy" in texto
    assert "4 sessions a month, no contract" not in texto
    from sdr import estilo
    limpo, v = estilo.aplicar("O Academy é mensal, 4 sessões por mês: $2.756,90 (4 tempos) ou $3.156,90 "
                              "(2 tempos). Qual a idade dele?")
    assert limpo == "Qual a idade dele?" and any("2.756" in x for x in v)


def test_video_para_quem_compara():
    texto = (SALESAGENT / "instructions" / "urace-sales-agent.md").read_text(encoding="utf-8")
    assert "Comparing us with indoor karting" in texto and "**send the video**" in texto


@pytest.mark.parametrize("texto,negocia", [
    ("E caro, faz por 2000 que fecho hoje?", True), ("Would you do it for 600?", True),
    ("fecha por $1500?", True), ("lo haces por 500?", True), ("É caro", True),
    ("O que o coach faz por ele?", False), ("Can you do Saturdays?", False),
    ("I want to do it for my son birthday", False),
])
def test_contraproposta_so_com_numero(texto, negocia):
    import sdr
    assert (sdr.avaliar(texto)["roteamento"].get("motivo") == "NEGOCIACAO") is negocia
