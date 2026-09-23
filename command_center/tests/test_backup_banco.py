"""Backup e auditoria do banco.

Dono, 23/09: *"preciso garantir que temos hoje um banco de dados estruturado e seguro
para todos os dados de clientes, financeiro, estoque e todos os outros dados"*. A
auditoria achou o buraco: **não havia backup nenhum**.

O pior tipo de backup é o que parece existir e não abre. Por isso toda cópia é aberta e
conferida antes de contar, e a limpeza das velhas só roda depois disso.
"""
import gzip
import importlib
import os
import sqlite3
import sys
import time

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from command_center.db import aplicar_schema, conectar, inserir, um  # noqa: E402

backup_banco = importlib.import_module("adminai.backup_banco")
auditar_banco = importlib.import_module("adminai.auditar_banco")


@pytest.fixture()
def banco(tmp_path, monkeypatch):
    caminho = tmp_path / "command-center.sqlite"
    monkeypatch.setenv("CC_DB_PATH", str(caminho))
    con = conectar(); aplicar_schema(con)
    inserir(con, "clients", name="Hank Lai", status="ACTIVE", source="manual")
    inserir(con, "clients", name="Alexander Savage", status="ACTIVE", source="manual")
    con.commit(); con.close()
    return str(caminho)


# ------------------------------------------------------------------ backup
def test_sem_aplicar_nao_cria_nada(banco):
    p = backup_banco.fazer(banco, aplicar=False)
    assert p["aplicado"] is False
    assert not os.path.exists(p["destino"])


def test_a_copia_e_conferida_antes_de_contar(banco):
    """Backup que não abre não é backup — e a descoberta não pode ser no dia do incêndio."""
    p = backup_banco.fazer(banco, aplicar=True)
    assert p["aplicado"] and p["conferido"]["clientes"] == 2
    assert p["conferido"]["tabelas"] > 10
    assert os.path.exists(p["destino"])


def test_a_copia_abre_e_tem_os_dados(banco):
    p = backup_banco.fazer(banco, aplicar=True, comprimida=False)
    con = sqlite3.connect(p["destino"])
    nomes = {r[0] for r in con.execute("SELECT name FROM clients")}
    con.close()
    assert nomes == {"Hank Lai", "Alexander Savage"}


def test_a_copia_nao_fica_legivel_para_a_maquina_toda(banco):
    """O backup tem exatamente os mesmos dados do banco: e-mail, telefone, valor."""
    p = backup_banco.fazer(banco, aplicar=True)
    import stat
    assert stat.S_IMODE(os.stat(p["destino"]).st_mode) & 0o077 == 0
    assert stat.S_IMODE(os.stat(p["pasta"]).st_mode) & 0o077 == 0


def test_comprime_e_continua_abrindo(banco):
    p = backup_banco.fazer(banco, aplicar=True, comprimida=True)
    assert p["destino"].endswith(".gz")
    with gzip.open(p["destino"], "rb") as f:
        assert f.read(16).startswith(b"SQLite format 3")


def test_copia_velha_e_apagada_so_depois_de_a_nova_existir(banco):
    """A ordem importa: limpar antes de copiar é como ficar sem backup nenhum se a
    cópia falhar no meio."""
    pasta = backup_banco.pasta_backups(banco)
    velha = os.path.join(pasta, "command-center-20200101-000000.sqlite")
    open(velha, "wb").write(b"SQLite format 3\x00" + b"\x00" * 100)
    os.utime(velha, (time.time() - 40 * 86400,) * 2)
    p = backup_banco.fazer(banco, aplicar=True, guardar=14)
    assert velha in p["apagadas"] and not os.path.exists(velha)
    assert os.path.exists(p["destino"]), "a nova ficou"


def test_copia_recente_nao_e_apagada(banco):
    pasta = backup_banco.pasta_backups(banco)
    ontem = os.path.join(pasta, "command-center-20260922-030000.sqlite")
    open(ontem, "wb").write(b"SQLite format 3\x00")
    os.utime(ontem, (time.time() - 86400,) * 2)
    p = backup_banco.fazer(banco, aplicar=True, guardar=14)
    assert p["apagadas"] == [] and os.path.exists(ontem)


def test_copia_quebrada_nao_passa_na_conferencia(tmp_path):
    ruim = tmp_path / "quebrada.sqlite"
    ruim.write_bytes(b"isto nao e um banco")
    with pytest.raises(Exception):
        backup_banco.verificar(str(ruim))


# ---------------------------------------------------------------- restaurar
def test_restaurar_guarda_o_banco_atual_antes(banco):
    """Restaurar por engano não pode ser caminho sem volta."""
    p = backup_banco.fazer(banco, aplicar=True, comprimida=False)
    con = conectar(); inserir(con, "clients", name="Cliente novo", status="ACTIVE", source="manual")
    con.commit(); con.close()
    r = backup_banco.restaurar(p["destino"], banco, aplicar=True)
    assert r["aplicado"] and os.path.exists(r["atual_guardado_em"])
    con = sqlite3.connect(r["atual_guardado_em"])
    assert con.execute("SELECT COUNT(*) FROM clients").fetchone()[0] == 3, "o de antes tem os 3"
    con.close()
    con = conectar()
    assert um(con, "SELECT COUNT(*) n FROM clients")["n"] == 2, "o restaurado tem os 2"
    con.close()


def test_restaurar_sem_aplicar_nao_toca_no_banco(banco):
    p = backup_banco.fazer(banco, aplicar=True, comprimida=False)
    con = conectar(); inserir(con, "clients", name="Depois", status="ACTIVE", source="manual")
    con.commit(); con.close()
    r = backup_banco.restaurar(p["destino"], banco, aplicar=False)
    assert r["aplicado"] is False
    con = conectar()
    assert um(con, "SELECT COUNT(*) n FROM clients")["n"] == 3, "nada mudou"
    con.close()


def test_restaurar_copia_comprimida(banco):
    p = backup_banco.fazer(banco, aplicar=True, comprimida=True)
    r = backup_banco.restaurar(p["destino"], banco, aplicar=True)
    assert r["aplicado"]
    con = conectar()
    assert um(con, "SELECT COUNT(*) n FROM clients")["n"] == 2
    con.close()


# ---------------------------------------------------------------- auditoria
def test_a_auditoria_acusa_a_falta_de_backup(banco):
    con = conectar()
    try:
        a = auditar_banco.backup(banco)
    finally:
        con.close()
    assert a["estado"] == auditar_banco.GRAVE and "não existe" in a["detalhe"]
    assert "backup_banco.py" in a["acao"]


def test_depois_do_backup_a_auditoria_fica_ok(banco):
    backup_banco.fazer(banco, aplicar=True)
    assert auditar_banco.backup(banco)["estado"] == auditar_banco.OK


def test_backup_velho_demais_e_grave(banco):
    p = backup_banco.fazer(banco, aplicar=True)
    os.utime(p["destino"], (time.time() - 5 * 86400,) * 2)
    a = auditar_banco.backup(banco)
    assert a["estado"] == auditar_banco.GRAVE and "dia(s)" in a["detalhe"]


def test_a_auditoria_ve_banco_integro_e_sem_orfaos(banco):
    con = conectar()
    try:
        assert auditar_banco.integridade(con)["estado"] == auditar_banco.OK
        assert auditar_banco.chaves_estrangeiras(con)["estado"] == auditar_banco.OK
        assert auditar_banco.auditoria_imutavel(con)["estado"] == auditar_banco.OK
    finally:
        con.close()


def test_a_auditoria_acusa_arquivo_legivel_por_todos(banco):
    os.chmod(banco, 0o644)
    a = auditar_banco.permissoes(banco)
    assert a["estado"] == auditar_banco.GRAVE and "chmod 600" in a["acao"]


def test_a_auditoria_acusa_orfao_de_verdade(banco):
    """Serviço apontando para cliente que não existe — o dado apontando para o vazio."""
    con = conectar()
    con.execute("PRAGMA foreign_keys = OFF")          # só assim dá para criar o órfão
    inserir(con, "tasks", client_id=9999, title="Serviço órfão", project="U-RACE", status="open")
    con.commit()
    a = auditar_banco.chaves_estrangeiras(con)
    con.close()
    assert a["estado"] == auditar_banco.GRAVE and "tasks" in a["detalhe"]


def test_a_auditoria_confere_que_senha_nao_e_reversivel(banco):
    from command_center.api import auth
    con = conectar()
    auth.criar_usuario(con, "a@urace.us", "A", "ADMIN", "senha-forte-123")
    con.commit()
    a = auditar_banco.segredo_no_banco(con)
    con.close()
    assert a["estado"] == auditar_banco.OK and "scrypt" in a["detalhe"]


def test_a_auditoria_grita_se_nao_ha_admin(banco):
    con = conectar()
    a = auditar_banco.acessos(con)
    con.close()
    assert a["estado"] == auditar_banco.GRAVE and "ADMIN" in a["detalhe"]


def test_a_auditoria_conta_o_que_existe_por_area(banco):
    con = conectar()
    d = auditar_banco.dados_por_dominio(con)
    con.close()
    areas = {x["dominio"] for x in d}
    assert areas >= {"clientes", "financeiro", "estoque", "segurança"}
    assert all(not x["faltando"] for x in d), "nenhuma tabela do desenho está faltando"
    clientes = [x for x in d if x["dominio"] == "clientes"][0]
    assert "clients=2" in clientes["contagem"]
