"""#299 (dono, 16/10): *"eu preciso que dados de clientes como e-mails, nomes, informações de contatos, sejam
armazenados em um banco de dados … conectado à VPS"*. Decisão: **SQLite + backup diário**.

O que estes testes trancam:
- a cópia que vai para o Drive sai **cifrada** (o nome do cliente não aparece no arquivo), abre só com a chave
  certa e um byte trocado não vira um banco errado;
- o histórico: 30 dias de cópias diárias e, antes disso, a primeira de cada mês por 12 meses (no disco e no Drive);
- cada rodada grava o resultado, e **Sistemas** avisa quando o backup do dia falhou ou faltou;
- **a restauração de verdade**: baixar do Drive, decifrar, conferir e pôr no lugar devolve os clientes;
- o deploy cria a chave uma vez (sem mostrar) e liga os dois timers diários.
"""
import importlib
import json
import os
import sys
import time

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from command_center.db import aplicar_schema, conectar, inserir, um  # noqa: E402
from command_center.tests.test_backup_drive import DriveFalso  # noqa: E402

backup_banco = importlib.import_module("adminai.backup_banco")
backup_drive = importlib.import_module("adminai.backup_drive")
cifra = importlib.import_module("adminai.cifra_backup")
NOME = "Quinn Fictício"                              # nome inventado: tem de sumir dentro do arquivo cifrado


class DriveComBytes(DriveFalso):
    """O Drive falso guardando o conteúdo (para baixar de volta) e a data de criação de hoje."""

    def instalar(self, monkeypatch):
        super().instalar(monkeypatch)
        self.conteudo = {}
        monkeypatch.setattr(backup_drive, "baixar_bytes", lambda tok, fid: self.conteudo[fid])
        return self

    def _enviar(self, tok, caminho, pid):
        f = super()._enviar(tok, caminho, pid)
        f["createdTime"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.conteudo[f["id"]] = open(caminho, "rb").read()
        return f


@pytest.fixture()
def banco(tmp_path, monkeypatch):
    caminho = tmp_path / "command-center.sqlite"
    monkeypatch.setenv("CC_DB_PATH", str(caminho))
    monkeypatch.setenv("CC_BACKUP_CHAVE", cifra.nova_chave())
    con = conectar(); aplicar_schema(con)
    inserir(con, "clients", name=NOME, email="quinn@example.com", status="ACTIVE", source="manual")
    con.commit(); con.close()
    return str(caminho)


@pytest.fixture()
def drive(monkeypatch):
    return DriveComBytes().instalar(monkeypatch)


# ------------------------------------------------------------------ a cifra
def test_a_copia_do_drive_sai_cifrada_e_so_abre_com_a_chave(banco, drive, tmp_path, monkeypatch):
    backup_banco.fazer(banco, aplicar=True, comprimida=False)
    p = backup_drive.diario(aplicar=True)
    enviado = drive.conteudo[p["enviado"]["id"]]
    assert enviado.startswith(cifra.MAGICA) and p["enviado"]["name"].endswith(".sqlite.enc")
    assert NOME.encode() not in enviado and b"quinn@example.com" not in enviado, "nada do cliente em claro"
    assert b"SQLite format" not in enviado
    assert not [n for n in os.listdir(backup_banco.pasta_backups(banco)) if n.endswith(".enc")], "o .enc não fica no disco"
    # chave errada não abre e diz qual era
    arq = tmp_path / "x.enc"
    arq.write_bytes(enviado)
    certa = cifra.impressao()
    monkeypatch.setenv("CC_BACKUP_CHAVE", cifra.nova_chave())
    with pytest.raises(cifra.ChaveErrada, match=certa):
        cifra.decifrar(str(arq), str(tmp_path / "x.sqlite"))


def test_um_byte_trocado_nao_vira_banco_errado(banco, tmp_path):
    p = backup_banco.fazer(banco, aplicar=True)
    enc = cifra.cifrar(p["destino"], str(tmp_path / "c.enc"))
    bruto = bytearray(open(enc, "rb").read())
    bruto[-5] ^= 0x01
    open(enc, "wb").write(bytes(bruto))
    with pytest.raises(cifra.ChaveErrada, match="alterado"):
        cifra.decifrar(enc, str(tmp_path / "c.sqlite"))


def test_sem_chave_nada_sobe(banco, drive, monkeypatch):
    monkeypatch.delenv("CC_BACKUP_CHAVE")
    backup_banco.fazer(banco, aplicar=True)
    with pytest.raises(cifra.ChaveAusente, match="deploy"):
        backup_drive.diario(aplicar=True)
    assert not drive.arquivos


# ------------------------------------------------------------------ o histórico
def test_historico_30_dias_e_a_primeira_de_cada_mes_por_12_meses():
    agora = time.mktime((2026, 10, 16, 12, 0, 0, 0, 0, 0))
    dia = 86400
    itens = [(f"d{n}", agora - n * dia) for n in range(0, 500)]          # uma cópia por dia, 500 dias
    sai = set(backup_banco.apagar_do_historico(itens, agora_ts=agora))
    fica = [c for c, _ in itens if c not in sai]
    assert all(f"d{n}" in fica for n in range(0, 31)), "os últimos 30 dias ficam"
    antigas = [c for c in fica if int(c[1:]) > 30]
    assert 11 <= len(antigas) <= 12, (len(antigas), antigas)            # uma por mês, até 12 meses para trás
    assert "d499" in sai and "d400" in sai, "passou de 12 meses: sai"


def test_o_historico_do_drive_e_o_mesmo(banco, drive):
    backup_banco.fazer(banco, aplicar=True)
    backup_drive.diario(aplicar=True)
    pid = drive.pastas[(drive.pastas[(None, "Command Center")], "Backup do banco")]
    velhos = {"v-ano": "2025-01-10T04:00:00Z", "v-mes-1": "2026-08-01T04:00:00Z", "v-mes-2": "2026-08-15T04:00:00Z"}
    for fid, quando in velhos.items():
        drive.arquivos[fid] = {"id": fid, "name": f"command-center-{fid}.sqlite.gz.enc", "size": 1, "createdTime": quando, "parent": pid}
    backup_drive.diario(aplicar=True)
    nomes = {f["id"] for f in drive.arquivos.values()}
    assert "v-mes-1" in nomes, "a primeira de agosto fica"
    assert "v-mes-2" not in nomes and "v-ano" not in nomes


# ------------------------------------------------------------------ o painel avisa
def test_sistemas_avisa_quando_o_backup_falha_ou_falta(banco, drive):
    from command_center.providers import backup_saude
    st, det = backup_saude.estado()
    assert st == "ERROR" and "nenhum backup" in det["motivo"]
    backup_banco.gravar_estado("local", False, erro="disco cheio")
    st, det = backup_saude.estado()
    assert st == "ERROR" and "disco cheio" in det["motivo"]
    p = backup_banco.fazer(banco, aplicar=True)
    backup_banco.gravar_estado("local", True, arquivo=os.path.basename(p["destino"]), tamanho=1, clientes=1)
    st, det = backup_saude.estado()
    assert st == "DEGRADED" and "Drive" in det["motivo"], "só a cópia de fora faltando: amarelo"
    backup_banco.gravar_estado("drive", True, arquivo="x.enc", tamanho=1, clientes=1, chave=cifra.impressao())
    assert backup_saude.estado()[0] == "CONNECTED"
    # no dia seguinte sem rodar: vermelho de novo
    st, det = backup_saude.estado(agora=time.time() + 30 * 3600)
    assert st == "ERROR" and "não rodou" in det["motivo"]
    assert NOME not in json.dumps(det), "nada do cliente no detalhe"


def test_o_script_grava_o_resultado_que_o_painel_le(banco, drive, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["backup_banco.py", "--aplicar"])
    assert backup_banco.main() == 0
    assert backup_banco.ler_estado("local")["ok"] is True
    monkeypatch.setattr(sys, "argv", ["backup_drive.py", "--aplicar"])
    assert backup_drive.main() == 0
    e = backup_banco.ler_estado("drive")
    assert e["ok"] and e["chave"] == cifra.impressao() and e["arquivo"].endswith(".enc")
    drive.falhar_upload = True
    assert backup_drive.main() == 1
    assert backup_banco.ler_estado("drive")["ok"] is False


def test_a_sondagem_poe_o_backup_na_tela_sistemas(banco):
    from command_center.api import agenda
    p = backup_banco.fazer(banco, aplicar=True)
    backup_banco.gravar_estado("local", True, arquivo=os.path.basename(p["destino"]), tamanho=1, clientes=1)
    con = conectar()
    agenda.sondar(con, ["backup"])
    i = um(con, "SELECT * FROM integrations WHERE system='backup'")
    con.close()
    assert i and i["status"] == "DEGRADED" and "Drive" in (i["last_error"] or i["detail"])


# ------------------------------------------------------------------ restaurar de verdade
def test_restaurar_do_drive_devolve_os_clientes(banco, drive):
    """O passo a passo do playbook: baixar do Drive, decifrar, conferir e pôr no lugar."""
    backup_banco.fazer(banco, aplicar=True)
    p = backup_drive.diario(aplicar=True)
    con = conectar()                                     # o desastre: o cliente some do banco
    con.execute("DELETE FROM clients")
    con.commit(); con.close()
    b = backup_drive.baixar(p["enviado"]["name"])
    assert b["conferido"]["clientes"] == 1 and not b["arquivo"].endswith(".enc")
    r = backup_banco.restaurar(b["arquivo"], banco, aplicar=True)
    assert r["aplicado"] and os.path.exists(r["atual_guardado_em"]), "o banco de antes foi guardado"
    con = conectar()
    assert um(con, "SELECT name FROM clients")["name"] == NOME
    con.close()


# ------------------------------------------------------------------ o deploy
def test_o_deploy_cria_a_chave_uma_vez_e_liga_os_timers_diarios():
    sh = open(os.path.join(RAIZ, "adminai", "deploy", "command_center", "servir_command_center.sh"), encoding="utf-8").read()
    assert "if ! grep -q '^CC_BACKUP_CHAVE=" in sh, "só cria quando não existe"
    assert "enable --now urace-backup.timer urace-backup-drive.timer" in sh
    timer = open(os.path.join(RAIZ, "adminai", "deploy", "urace-backup-drive.timer"), encoding="utf-8").read()
    assert "OnCalendar=*-*-* 04:00:00" in timer, "todo dia, depois do local das 03:15"
