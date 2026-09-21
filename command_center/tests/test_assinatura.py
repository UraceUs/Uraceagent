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
from mcp_stdio import AGENTE, ASSINATURA, assinar, rastro  # noqa: E402

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
def test_tarefa_nova_nasce_dizendo_quem_criou_e_quando(asana):
    """21/09, segunda volta do dono: não basta assinar — a descrição diz que foi criada
    pelo agente, com dia e hora."""
    A.asana_criar_tarefa(A.PROJETO_URACE, "Trocar pneu do kart 12")
    notas = asana.corpo("/tasks")[0]["notes"]
    assert notas.startswith("Tarefa criada em ") and notas.endswith(AGENTE)
    assert "/2026 " in notas and ("EDT" in notas or "EST" in notas)


def test_tarefa_com_descricao_mantem_a_descricao_e_ganha_a_marca(asana):
    A.asana_criar_tarefa(A.PROJETO_URACE, "Serviço", notas="Levar pneu novo")
    notas = asana.corpo("/tasks")[0]["notes"]
    assert notas.startswith("Levar pneu novo") and notas.endswith(AGENTE)


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
    assert "conferir pneus" in ajuste["notes"] and ajuste["notes"].endswith(AGENTE)

    # e com descrição própria, a descrição manda
    asana.escritas.clear()
    A._instanciar_modelo("modelo-1", "Outro", notas="observação do dono")
    ajuste = [c for cam, c in asana.escritas if cam.startswith("/tasks/") and c and "notes" in c][-1]
    assert ajuste["notes"].startswith("observação do dono") and ajuste["notes"].endswith(AGENTE)


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


# ------------------------------------------------- o rastro do que aconteceu FORA do Asana
def test_mover_tarefa_deixa_comentario_com_a_hora(asana, monkeypatch):
    """*"moveu uma tarefa, coloca um comentário dizendo que foi movido tal dia, tal hora,
    pelo agente de IA"* — dono, 21/09."""
    monkeypatch.setattr(A, "asana_secoes", lambda pg: [{"gid": "77", "nome": "Finished Services"}])
    A.asana_mover_para_secao("1", "77")
    comentarios = [c["text"] for cam, c in asana.escritas if "/stories" in cam]
    assert len(comentarios) == 1
    assert comentarios[0].startswith("Movida de [") and "para [Finished Services]" in comentarios[0]
    assert comentarios[0].endswith(AGENTE) and "/2026 " in comentarios[0]


def test_comentario_falhando_nao_desfaz_a_mudanca(asana, monkeypatch):
    """O rastro sai DEPOIS da ação. Se o comentário falhar, a tarefa continua movida — e o
    chamador não pode receber um erro por causa disso."""
    monkeypatch.setattr(A, "asana_secoes", lambda pg: [{"gid": "77", "nome": "QUA"}])
    real = asana.__call__

    def quebra(caminho, metodo="GET", corpo=None, **kw):
        if "/stories" in caminho:
            raise RuntimeError("Asana fora do ar")
        return real(caminho, metodo, corpo, **kw)
    monkeypatch.setattr(A, "_req", quebra)
    r = A.asana_mover_para_secao("1", "77")
    assert r["aplicado"] is True


def test_a_porta_do_rastro_recusa_projeto_protegido(asana, monkeypatch):
    """ADM URACE é só leitura (regra do dono): nem o registro do agente escreve lá."""
    protegida = dict(TAREFA, memberships=[{"project": {"gid": A.PROJETO_ADM, "name": "ADM URACE"},
                                           "section": {"gid": "1", "name": "x"}}])
    monkeypatch.setattr(A, "_ler_tarefa", lambda gid, *a, **k: protegida)
    with pytest.raises(A.ErroFerramenta):
        A.comentar_rastro("1", "Invoice enviada")


def test_rastro_de_invoice_e_de_waiver_dizem_o_que_saiu(asana):
    A.comentar_rastro("1", "Invoice 1234 enviada para pedro@exemplo.com")
    A.comentar_rastro("1", "Waiver enviada para Pedro Souza (modelo parental)")
    textos = [c["text"] for cam, c in asana.escritas if "/stories" in cam]
    assert all(t.endswith(AGENTE) and " em " in t for t in textos)
    assert "Invoice 1234 enviada" in textos[0] and "Waiver enviada" in textos[1]
