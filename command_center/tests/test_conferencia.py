"""Conferência do chat: dizer QUAIS mensagens não foram e quais não chegaram.

Pergunta do dono em 21/09. Sem rede: o Kommo é uma lista montada aqui. O que se prova é
o casamento — mesma direção, ±3 min, texto como desempate — e as duas sobras.
"""
import os
import tempfile

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from command_center.db import agora, aplicar_schema, conectar, inserir  # noqa: E402
from command_center.providers import conferencia  # noqa: E402


@pytest.fixture()
def con():
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "cc.sqlite")
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


def em(minutos):
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(minutes=minutos)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _lead(con, ext="7001"):
    lid = inserir(con, "crm_leads", external_id=ext, name="Maria", source="Instagram",
                  last_message_at=agora(), synced_at=agora())
    con.commit()
    return {"id": lid, "external_id": ext, "name": "Maria", "source": "Instagram", "link": None}


def test_diz_qual_resposta_nao_foi_e_qual_mensagem_nao_chegou(con):
    l = _lead(con)
    # o painel guardou: uma resposta que o Kommo tem, outra que o Kommo NÃO tem
    inserir(con, "crm_messages", lead_id=l["id"], external_id=None, direction="saida", status="sent",
            author="Italo", text="Chegou essa", at=em(30), source="painel")
    inserir(con, "crm_messages", lead_id=l["id"], external_id=None, direction="saida", status="sent",
            author="Italo", text="Essa sumiu", at=em(20), source="painel")
    inserir(con, "crm_messages", lead_id=l["id"], external_id="msg:1", direction="entrada",
            author="cliente", text="Oi", at=em(40), source="Instagram")
    con.commit()
    # o Kommo tem: a primeira resposta, o "Oi" e uma mensagem do cliente que o painel perdeu
    kommo = [
        {"id": "n1", "direcao": "entrada", "texto": "Oi", "em": em(40)},
        {"id": "n2", "direcao": "saida", "texto": "Chegou essa", "em": em(30)},
        {"id": "n3", "direcao": "entrada", "texto": "Consegue domingo?", "em": em(10)},
    ]
    r = conferencia.conferir_lead(con, l, ler=lambda _e: kommo)
    assert [m["text"] for m in r["nao_foi"]] == ["Essa sumiu"]
    assert [k["texto"] for k in r["nao_chegou"]] == ["Consegue domingo?"]
    assert r["confere"] == 2 and r["erro"] is None


def test_o_que_o_painel_ja_sabe_que_nao_saiu_nao_vira_acusacao_nova(con):
    """Mensagem na fila ou falhada já aparece marcada na conversa: ela é listada como
    pendente, não como 'não foi' — senão o mesmo problema seria contado duas vezes."""
    l = _lead(con, "7002")
    inserir(con, "crm_messages", lead_id=l["id"], external_id=None, direction="saida", status="failed",
            author="Italo", text="Travou", at=em(5), source="painel")
    con.commit()
    r = conferencia.conferir_lead(con, l, ler=lambda _e: [])
    assert not r["nao_foi"] and [m["text"] for m in r["pendentes"]] == ["Travou"]


def test_sem_texto_dos_dois_lados_o_tempo_basta(con):
    """A API de notas do Kommo nem sempre traz o texto da mensagem de chat. Sem texto, o
    casamento é por direção e tempo — e a conferência conta quantas ficaram assim."""
    l = _lead(con, "7003")
    inserir(con, "crm_messages", lead_id=l["id"], external_id="ev:9", direction="entrada",
            author="cliente", text=None, at=em(15), source="kommo-evento")
    con.commit()
    r = conferencia.conferir_lead(con, l, ler=lambda _e: [{"id": "n9", "direcao": "entrada", "texto": "", "em": em(15)}])
    assert r["confere"] == 1 and not r["nao_chegou"] and r["sem_texto_kommo"] == 1


def test_texto_diferente_no_mesmo_minuto_sao_duas_mensagens(con):
    """Duas mensagens seguidas não podem casar uma com a outra só porque são do mesmo minuto."""
    l = _lead(con, "7004")
    inserir(con, "crm_messages", lead_id=l["id"], external_id=None, direction="saida", status="sent",
            author="Italo", text="primeira", at=em(9), source="painel")
    con.commit()
    r = conferencia.conferir_lead(con, l, ler=lambda _e: [{"id": "n1", "direcao": "saida", "texto": "segunda", "em": em(9)}])
    assert [m["text"] for m in r["nao_foi"]] == ["primeira"]


def test_kommo_fora_do_ar_nao_vira_acusacao(con):
    """Se não deu para ler o Kommo, a conferência diz isso — não sai dizendo que sumiu."""
    l = _lead(con, "7005")
    inserir(con, "crm_messages", lead_id=l["id"], external_id=None, direction="saida", status="sent",
            author="Italo", text="oi", at=em(3), source="painel")
    con.commit()

    def explode(_e):
        raise RuntimeError("Kommo: HTTP 502")
    r = conferencia.conferir_lead(con, l, ler=explode)
    assert r["erro"].startswith("Kommo: HTTP 502") and not r["nao_foi"] and not r["nao_chegou"]


def test_conferencia_inteira_soma_os_leads_da_janela(con):
    a, b = _lead(con, "7006"), _lead(con, "7007")
    inserir(con, "crm_messages", lead_id=a["id"], external_id=None, direction="saida", status="sent",
            author="Italo", text="sumiu A", at=em(12), source="painel")
    inserir(con, "crm_messages", lead_id=b["id"], external_id=None, direction="saida", status="sent",
            author="Italo", text="sumiu B", at=em(11), source="painel")
    con.commit()
    # o Kommo mostra resposta nossa nos dois: aí a ausência conta
    visivel = [{"id": "n0", "direcao": "saida", "texto": "outra", "em": em(300)}]
    r = conferencia.conferir(con, dias=7, ler=lambda _e: visivel, eventos={})
    assert r["nao_foi"] == 2 and r["nao_chegou"] == 0 and r["erros"] == 0
    assert len(r["leads"]) == 2


# ------------------------------------------- a trava: não acusar sem enxergar (21/09, tarde)
def test_conversa_vazia_no_kommo_nao_acusa_ninguem(con):
    """O defeito da primeira versão: o Kommo devolveu ZERO linha e ela apontou quatro
    respostas como "não foi". Lista vazia não é prova de nada."""
    l = _lead(con, "7008")
    inserir(con, "crm_messages", lead_id=l["id"], external_id=None, direction="saida", status="sent",
            author="Italo", text="hey", at=em(25), source="painel")
    con.commit()
    r = conferencia.conferir_lead(con, l, ler=lambda _e: [], eventos=[])
    assert r["nao_foi"] == [] and r["sem_dados"] is True
    assert [m["text"] for m in r["cego_saida"]] == ["hey"]


def test_kommo_que_so_mostra_entrada_nao_julga_a_saida(con):
    """Se a conta registra o que o cliente manda mas não o que nós respondemos, a saída
    inteira é ponto cego — e ponto cego se chama 'não dá para dizer'."""
    l = _lead(con, "7009")
    inserir(con, "crm_messages", lead_id=l["id"], external_id=None, direction="saida", status="sent",
            author="Italo", text="respondi", at=em(20), source="painel")
    inserir(con, "crm_messages", lead_id=l["id"], external_id="msg:5", direction="entrada",
            author="cliente", text="oi", at=em(22), source="Instagram")
    con.commit()
    r = conferencia.conferir_lead(con, l, ler=lambda _e: [{"id": "n1", "direcao": "entrada", "texto": "oi", "em": em(22)}])
    assert r["nao_foi"] == [] and [m["text"] for m in r["cego_saida"]] == ["respondi"]
    assert r["sem_dados"] is False and r["confere"] == 1


def test_evento_de_conversa_serve_de_segunda_fonte(con):
    """A conta registra a conversa como evento (sem texto) mesmo quando a nota não existe.
    Com o evento, a saída volta a ser conferível — e o que casa, casa."""
    l = _lead(con, "7010")
    inserir(con, "crm_messages", lead_id=l["id"], external_id=None, direction="saida", status="sent",
            author="Italo", text="chegou", at=em(18), source="painel")
    inserir(con, "crm_messages", lead_id=l["id"], external_id=None, direction="saida", status="sent",
            author="Italo", text="essa não", at=em(8), source="painel")
    con.commit()
    eventos = [{"id": "e1", "direcao": "saida", "texto": "", "em": em(18), "fonte": "evento"}]
    r = conferencia.conferir_lead(con, l, ler=lambda _e: [], eventos=eventos)
    assert r["confere"] == 1 and [m["text"] for m in r["nao_foi"]] == ["essa não"]
    assert not r["cego_saida"] and r["sem_dados"] is False


def test_nota_e_evento_da_mesma_mensagem_nao_viram_duas(con):
    """As duas fontes descrevem a mesma mensagem: contar as duas inventaria conversa."""
    l = _lead(con, "7011")
    inserir(con, "crm_messages", lead_id=l["id"], external_id=None, direction="saida", status="sent",
            author="Italo", text="oi", at=em(10), source="painel")
    con.commit()
    r = conferencia.conferir_lead(
        con, l, ler=lambda _e: [{"id": "n1", "direcao": "saida", "texto": "oi", "em": em(10)}],
        eventos=[{"id": "e1", "direcao": "saida", "texto": "", "em": em(10), "fonte": "evento"}])
    assert r["confere"] == 1 and not r["nao_foi"] and not r["nao_chegou"]


def test_duas_respostas_no_mesmo_minuto_nao_viram_uma_perdida(con):
    """O caso real do lead do Charles (18/09, 11:24): o painel mandou "Hey Charles" e
    "how are you?" no mesmo minuto, o Kommo mostrou as DUAS com ✓Delivered e registrou UM
    evento de conversa. Casando um-para-um, a segunda virava acusação falsa."""
    l = _lead(con, "7012")
    inserir(con, "crm_messages", lead_id=l["id"], external_id=None, direction="saida", status="sent",
            author="Italo", text="Hey Charles", at=em(60), source="painel")
    inserir(con, "crm_messages", lead_id=l["id"], external_id=None, direction="saida", status="sent",
            author="Italo", text="how are you?", at=em(60), source="painel")
    con.commit()
    um_evento = [{"id": "e1", "direcao": "saida", "texto": "", "em": em(60), "fonte": "evento"}]
    r = conferencia.conferir_lead(con, l, ler=lambda _e: [], eventos=um_evento)
    # uma casou no par, a outra ficou coberta pelo mesmo evento: as duas explicadas, zero acusação
    assert r["nao_foi"] == [] and r["confere"] == 2 and r["por_evento"] == 1


def test_resposta_longe_do_evento_continua_sendo_acusada(con):
    """A cobertura é só dentro da janela: resposta de outra hora, sem nenhum sinal do
    Kommo perto dela, continua aparecendo — senão a conferência não serviria para nada."""
    l = _lead(con, "7013")
    inserir(con, "crm_messages", lead_id=l["id"], external_id=None, direction="saida", status="sent",
            author="Italo", text="perto", at=em(60), source="painel")
    inserir(con, "crm_messages", lead_id=l["id"], external_id=None, direction="saida", status="sent",
            author="Italo", text="longe", at=em(5), source="painel")
    con.commit()
    r = conferencia.conferir_lead(con, l, ler=lambda _e: [],
                                  eventos=[{"id": "e1", "direcao": "saida", "texto": "", "em": em(60), "fonte": "evento"}])
    assert [m["text"] for m in r["nao_foi"]] == ["longe"] and r["por_evento"] == 0 and r["confere"] == 1
