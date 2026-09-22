"""As travas que nasceram das decisões do dono de 22/09.

Abrir uma política é uma frase; a condição que veio junto com ela é código. Cada
teste aqui guarda uma dessas condições:

  - `apagar_qualquer_coisa` virou REQUIRES_APPROVAL e voltou a ser guarda-chuva:
    ação nova com "apagar" no nome não passa por baixo dela;
  - `gmail_rotular` virou SAFE, mas arquivar só com marcador CONFIRMADO no painel;
  - `docusign_send_reminder` virou SAFE, mas só com serviço marcado, a 3 e a 1 dia,
    no máximo 2 por envelope.
"""
import datetime as dt
import importlib.util
import os
import sys
import tempfile

import pytest

from command_center.api import ia
from command_center.db import aplicar_schema, conectar

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "adminai", "mcp"))
import docusign_mcp  # noqa: E402
import gmail_mcp  # noqa: E402


@pytest.fixture()
def con():
    """Banco próprio por teste, e a variável DEVOLVIDA no fim.

    Os MCP não recebem conexão: eles abrem o banco sozinhos, por `CC_DB_PATH` — é
    justamente isso que estes testes precisam exercitar. Deixar a variável apontando
    para o banco de um teste que já acabou derruba o módulo seguinte."""
    antes = os.environ.get("CC_DB_PATH")
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="cc-travas-"), "cc.sqlite")
    c = conectar(); aplicar_schema(c)
    try:
        yield c
    finally:
        c.close()
        if antes is None:
            os.environ.pop("CC_DB_PATH", None)
        else:
            os.environ["CC_DB_PATH"] = antes


# ------------------------------------------------- guarda-chuva do apagar
def test_acao_nova_de_apagar_herda_o_piso_do_guarda_chuva(con):
    """O buraco de 22/09: `asana_apagar_tarefa` não tinha política própria, caía no
    padrão (pergunta antes) e passava por baixo do guarda-chuva que dizia que a IA
    nunca apaga. Agora o piso vale para qualquer nome de apagar."""
    con.execute("DELETE FROM action_policies WHERE action='asana_apagar_tarefa'")
    con.commit()
    assert ia._politica(con, "asana_apagar_tarefa") == "REQUIRES_APPROVAL"
    for nome in ("qbo_deletar_pagamento", "excluir_cliente", "remover_anexo", "destruir_backup"):
        assert ia._politica(con, nome) == "REQUIRES_APPROVAL", nome


def test_o_piso_nao_rebaixa_quem_ja_e_mais_severo(con):
    """`apagar_cliente` continua BLOCKED: o guarda-chuva é chão, não teto."""
    assert ia._politica(con, "apagar_cliente") == "BLOCKED"
    assert ia._politica(con, "qbo_apagar") == "BLOCKED"


def test_acao_sem_apagar_no_nome_nao_e_tocada(con):
    assert ia.piso_de_apagar(con, "asana_criar_tarefa") is None
    assert ia._politica(con, "asana_criar_tarefa") == "SAFE"
    assert ia._politica(con, "gmail_rotular") == "SAFE"


# ------------------------------------------------- arquivar no Gmail
def _marcador(con, nome, status="confirmado", caixas='["urace"]'):
    con.execute("INSERT INTO gmail_labels (name, status, in_gmail, mailboxes) VALUES (?,?,1,?) "
                "ON CONFLICT(name) DO UPDATE SET status=excluded.status, mailboxes=excluded.mailboxes",
                (nome, status, caixas))
    con.commit()


def test_arquiva_com_marcador_confirmado_no_painel(con):
    _marcador(con, "Finances/Receipt")
    pode, por = gmail_mcp._pode_arquivar("urace", ["Finances/Receipt"])
    assert pode and por == "Finances/Receipt"


def test_nao_arquiva_com_marcador_que_a_ia_inventou(con):
    _marcador(con, "Finances/Receipt")
    pode, _ = gmail_mcp._pode_arquivar("urace", ["Coisas/Que/Eu/Inventei"])
    assert not pode, "marcador fora do manual não tira e-mail da inbox"


def test_nao_arquiva_com_marcador_so_pendente(con):
    _marcador(con, "Talvez", status="pendente")
    assert gmail_mcp._pode_arquivar("urace", ["Talvez"])[0] is False


def test_marcador_confirmado_na_outra_caixa_nao_vale(con):
    _marcador(con, "Support/Only", caixas='["support"]')
    assert gmail_mcp._pode_arquivar("urace", ["Support/Only"])[0] is False
    assert gmail_mcp._pode_arquivar("support", ["Support/Only"])[0] is True


def test_wnews_continua_arquivando_sem_banco(con, monkeypatch):
    """Sem o manual, a regra volta a ser a estreita: só propaganda sai da inbox."""
    monkeypatch.setattr(gmail_mcp, "_confirmados_no_painel", lambda conta: None)
    assert gmail_mcp._pode_arquivar("urace", ["wNews/George | Atendente"])[0] is True
    assert gmail_mcp._pode_arquivar("urace", ["Finances/Receipt"])[0] is False


# ------------------------------------------------- lembrete de waiver
def _cliente_com_servico(con, email, daqui_a_dias, nome="Cliente"):
    cur = con.execute("INSERT INTO clients (name, email) VALUES (?,?)", (nome, email))
    cid = cur.lastrowid
    quando = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=daqui_a_dias)).replace(hour=15)
    con.execute("INSERT INTO calendar_events (client_id, title, starts_at) VALUES (?,?,?)",
                (cid, "Track day", quando.isoformat()))
    con.commit()
    return cid


def test_lembra_tres_dias_antes(con):
    _cliente_com_servico(con, "pai@exemplo.com", 3)
    d = docusign_mcp.avaliar_lembrete(con, "ENV-1", "pai@exemplo.com")
    assert d["pode"] and d["dias"] == 3


def test_lembra_um_dia_antes(con):
    _cliente_com_servico(con, "pai@exemplo.com", 1)
    assert docusign_mcp.avaliar_lembrete(con, "ENV-1", "pai@exemplo.com")["dias"] == 1


@pytest.mark.parametrize("dias", [0, 2, 4, 10])
def test_nao_lembra_fora_das_duas_janelas(con, dias):
    _cliente_com_servico(con, "pai@exemplo.com", dias)
    d = docusign_mcp.avaliar_lembrete(con, "ENV-1", "pai@exemplo.com")
    assert not d["pode"], f"{dias} dias não é janela de lembrete"


def test_sem_servico_marcado_nao_lembra(con):
    con.execute("INSERT INTO clients (name, email) VALUES ('Sem agenda','pai@exemplo.com')")
    con.commit()
    d = docusign_mcp.avaliar_lembrete(con, "ENV-1", "pai@exemplo.com")
    assert not d["pode"] and "serviço marcado" in d["motivo"]


def test_servico_no_passado_nao_conta(con):
    _cliente_com_servico(con, "pai@exemplo.com", -3)
    assert docusign_mcp.avaliar_lembrete(con, "ENV-1", "pai@exemplo.com")["pode"] is False


def test_quem_nao_e_cliente_do_painel_nao_lembra(con):
    d = docusign_mcp.avaliar_lembrete(con, "ENV-1", "estranho@exemplo.com")
    assert not d["pode"] and "não é cliente" in d["motivo"]


def test_a_waiver_tambem_liga_o_email_ao_cliente(con):
    """O e-mail do signatário nem sempre é o do cadastro: quem assina pode ser o
    responsável. A waiver já guarda esse vínculo."""
    cid = _cliente_com_servico(con, "mae@exemplo.com", 3)
    con.execute("INSERT INTO waivers (client_id, signer_email, status) VALUES (?,?, 'sent')",
                (cid, "pai@exemplo.com"))
    con.commit()
    assert docusign_mcp.avaliar_lembrete(con, "ENV-1", "pai@exemplo.com")["pode"] is True


def test_no_maximo_dois_lembretes_por_envelope(con):
    _cliente_com_servico(con, "pai@exemplo.com", 3)
    d = docusign_mcp.avaliar_lembrete(con, "ENV-1", "pai@exemplo.com")
    docusign_mcp.registrar_lembrete(con, "ENV-1", "pai@exemplo.com", d["dias"], d["servico_em"])
    docusign_mcp.registrar_lembrete(con, "ENV-1", "pai@exemplo.com", 1, d["servico_em"])
    d3 = docusign_mcp.avaliar_lembrete(con, "ENV-1", "pai@exemplo.com")
    assert not d3["pode"] and "autorizou 2" in d3["motivo"]


def test_a_mesma_janela_nao_vale_por_dois(con):
    """Chamar duas vezes no mesmo dia não gasta as duas autorizações — e também
    não manda dois e-mails iguais para o cliente."""
    _cliente_com_servico(con, "pai@exemplo.com", 3)
    d = docusign_mcp.avaliar_lembrete(con, "ENV-1", "pai@exemplo.com")
    docusign_mcp.registrar_lembrete(con, "ENV-1", "pai@exemplo.com", d["dias"], d["servico_em"])
    de_novo = docusign_mcp.avaliar_lembrete(con, "ENV-1", "pai@exemplo.com")
    assert not de_novo["pode"] and "já foi" in de_novo["motivo"]


def test_o_limite_e_por_envelope(con):
    _cliente_com_servico(con, "pai@exemplo.com", 3)
    docusign_mcp.registrar_lembrete(con, "ENV-1", "pai@exemplo.com", 3, "x")
    docusign_mcp.registrar_lembrete(con, "ENV-1", "pai@exemplo.com", 1, "x")
    assert docusign_mcp.avaliar_lembrete(con, "ENV-2", "pai@exemplo.com")["pode"] is True


def test_envelope_sem_email_nao_lembra(con):
    assert docusign_mcp.avaliar_lembrete(con, "ENV-1", "")["pode"] is False


def test_o_dia_e_o_de_orlando_nao_24h_corridas(con):
    """Serviço às 9h da manhã, visto às 22h da véspera: é "amanhã", 1 dia — não 0."""
    from zoneinfo import ZoneInfo
    casa = ZoneInfo(docusign_mcp.FUSO_CASA)
    servico = dt.datetime(2026, 10, 10, 9, 0, tzinfo=casa)
    vespera = dt.datetime(2026, 10, 9, 22, 0, tzinfo=casa)
    cur = con.execute("INSERT INTO clients (name, email) VALUES ('X','pai@exemplo.com')")
    con.execute("INSERT INTO calendar_events (client_id, title, starts_at) VALUES (?,?,?)",
                (cur.lastrowid, "Track day", servico.astimezone(dt.timezone.utc).isoformat()))
    con.commit()
    d = docusign_mcp.avaliar_lembrete(con, "ENV-1", "pai@exemplo.com", agora=vespera)
    assert d["pode"] and d["dias"] == 1
