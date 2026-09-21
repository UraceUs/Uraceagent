"""A assinatura "by Urace Ai agent" em tudo que o painel escreve fora dele.

Dono, 21/09, depois de descobrir tarefa de agente no Asana dele sem saber de quem era:
*"tudo que for feito pelo command center de agora em diante tem que ter a assinatura by
Urace Ai agent"*.

Sem rede: o `_req` de cada MCP é trocado por um espião que guarda o que sairia. O que se
prova são as duas metades da regra — **o que é assinado** (tarefa, comentário, anotação:
coisa interna, que alguém da equipe lê e precisa saber de onde veio) e **o que NÃO é**
(mensagem no chat do cliente, que é o texto que uma pessoa digitou).
"""
import os
import sys

import pytest

os.environ["URACE_ENV"] = "/nao/existe"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "adminai", "mcp"))

import asana_mcp as A  # noqa: E402
import kommo_mcp as K  # noqa: E402
from mcp_stdio import ASSINATURA, assinar  # noqa: E402

TAREFA = {"gid": "1", "name": "Serviço do Pedro", "notes": "",
          "memberships": [{"project": {"gid": A.PROJETO_URACE, "name": "U-RACE"},
                           "section": {"gid": "9", "name": "QUA"}}]}


class Espiao:
    """Guarda cada escrita. Devolve o mínimo que cada chamada espera."""

    def __init__(self):
        self.escritas = []

    tarefa_do_modelo = ""

    def __call__(self, caminho, metodo="GET", corpo=None, **kw):
        if metodo != "GET":
            self.escritas.append((caminho, corpo))
        if "instantiateTask" in caminho:
            return {"data": {"gid": "job-1", "new_task": {"gid": "nova-1"}}}
        if caminho.startswith("/tasks/nova-1?opt_fields=notes"):
            return {"data": {"notes": self.tarefa_do_modelo}}
        if caminho.startswith("/tasks/") and "/stories" in caminho:
            return {"data": {"gid": "story-1"}}
        if caminho.startswith("/tasks") and metodo == "POST":
            return {"data": {"gid": "nova-1", "permalink_url": "http://x"}}
        if "/notes" in caminho:
            return {"_embedded": {"notes": [{"id": 7}]}}
        return {"data": {}}

    def corpo(self, contem):
        return [c for cam, c in self.escritas if contem in cam]


@pytest.fixture()
def asana(monkeypatch):
    e = Espiao()
    monkeypatch.setattr(A, "_req", e)
    monkeypatch.setattr(A, "_ler_tarefa", lambda gid, *a, **k: dict(TAREFA, gid=gid))
    monkeypatch.setenv("APLICAR", "1")
    monkeypatch.setenv("ASANA_TOKEN", "x")
    return e


# ------------------------------------------------------------------ o carimbo
def test_assinar_e_idempotente_e_nunca_perde_o_texto():
    assert assinar("oi") == "oi\n\n" + ASSINATURA
    assert assinar(assinar("oi")) == assinar("oi")          # editar três vezes não carimba três
    assert assinar("") == ASSINATURA and assinar(None) == ASSINATURA
    ja = "BY URACE AI AGENT já estava aqui"
    assert assinar(ja) == ja                                # reconhece a marca em qualquer caixa
    assert "combinado com o cliente" in assinar("combinado com o cliente")


# ------------------------------------------------------------------ Asana
def test_tarefa_nova_nasce_assinada_mesmo_sem_descricao(asana):
    A.asana_criar_tarefa(A.PROJETO_URACE, "Trocar pneu do kart 12")
    corpo = asana.corpo("/tasks")[0]
    assert corpo["notes"] == ASSINATURA


def test_tarefa_com_descricao_mantem_a_descricao_e_ganha_a_marca(asana):
    A.asana_criar_tarefa(A.PROJETO_URACE, "Serviço", notas="Levar pneu novo")
    corpo = asana.corpo("/tasks")[0]
    assert corpo["notes"].startswith("Levar pneu novo") and corpo["notes"].endswith(ASSINATURA)


def test_comentario_do_agente_e_o_do_painel_sao_assinados(asana):
    A.asana_comentar("1", "waiver pendente")
    A.comentar_humano("1", "corrida confirmada")
    for _, corpo in asana.escritas:
        assert corpo["text"].endswith(ASSINATURA)


def test_link_da_invoice_deixa_a_tarefa_assinada(asana):
    A.preencher_invoice_na_tarefa("1", "http://invoice", valor=500)
    corpo = asana.corpo("/tasks/1")[0]
    assert "Invoice link: http://invoice" in corpo["notes"] and corpo["notes"].endswith(ASSINATURA)


def test_servico_pelo_modelo_e_assinado_sem_apagar_o_texto_do_modelo(asana, monkeypatch):
    """É assim que serviço e corrida nascem, e quase sempre SEM descrição própria: o texto
    vem do modelo. Escrever só o carimbo apagaria o checklist do modelo — então lê o que
    veio e acrescenta ao fim."""
    monkeypatch.setattr(A, "_req", asana)
    asana.tarefa_do_modelo = "Checklist do serviço:\n- conferir pneus"
    A._instanciar_modelo("modelo-1", "Serviço do Pedro")
    ajuste = [c for cam, c in asana.escritas if cam.startswith("/tasks/") and c and "notes" in c][-1]
    assert "conferir pneus" in ajuste["notes"] and ajuste["notes"].endswith(ASSINATURA)

    # e com descrição própria, a descrição manda
    asana.escritas.clear()
    A._instanciar_modelo("modelo-1", "Outro", notas="observação do dono")
    ajuste = [c for cam, c in asana.escritas if cam.startswith("/tasks/") and c and "notes" in c][-1]
    assert ajuste["notes"] == "observação do dono\n\n" + ASSINATURA


# ------------------------------------------------------------------ Kommo
def test_anotacao_no_lead_e_assinada(monkeypatch):
    e = Espiao()
    monkeypatch.setattr(K, "_req", e)
    monkeypatch.setenv("APLICAR", "1")
    K.nota_humana("5001", "cliente pediu para ligar amanhã")
    assert e.corpo("/notes")[0][0]["params"]["text"].endswith(ASSINATURA)


def test_a_resposta_no_chat_do_cliente_nao_leva_assinatura(monkeypatch):
    """A linha que não se cruza: no chat quem fala é a pessoa que digitou. Carimbar
    "Ai agent" ali mudaria o que o cliente entende da conversa — e isso é decisão de
    negócio, não de código."""
    saiu = {}
    monkeypatch.setattr(K, "_req", lambda c, m="GET", b=None, **k: saiu.update(corpo=b) or {"data": {}})
    monkeypatch.setenv("APLICAR", "1")
    monkeypatch.setenv("KOMMO_TOKEN", "x")
    monkeypatch.setenv("KOMMO_DOMAIN", "urace.kommo.com")
    ok, _ = K.continuar_bot_humano("https://urace.kommo.com/api/v4/salesbot/1/continue/abc",
                                   "Oi Charles, temos vaga sábado!")
    assert ASSINATURA not in str(saiu.get("corpo"))
