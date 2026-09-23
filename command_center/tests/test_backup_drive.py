"""Backup semanal para o Drive — provado sem tocar na rede.

Dono, 23/09: *"pode criar uma pasta no drive com o nome Backup urace command center com
o backup semanal"*.

O que estes testes trancam é a ordem das coisas: **nada antigo é apagado antes de a
cópia nova estar lá e conferida**, e upload truncado não conta como backup. Um backup
remoto que apaga o anterior e sobe pela metade é pior que backup nenhum, porque dá a
impressão de existir.
"""
import gzip
import importlib
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from command_center.db import aplicar_schema, conectar, inserir  # noqa: E402

backup_drive = importlib.import_module("adminai.backup_drive")
backup_banco = importlib.import_module("adminai.backup_banco")


class DriveFalso:
    """O Drive inteiro em memória: pastas, arquivos e as falhas que interessam."""

    def __init__(self, falhar_upload=False, truncar=False):
        self.pastas, self.arquivos = {}, {}
        self.falhar_upload, self.truncar = falhar_upload, truncar
        self.apagados, self.seq = [], 0

    def instalar(self, monkeypatch):
        monkeypatch.setattr(backup_drive, "_token", lambda: "tok-de-teste")
        monkeypatch.setattr(backup_drive, "achar_pasta",
                            lambda tok, nome=backup_drive.PASTA: self.pastas.get(nome))
        monkeypatch.setattr(backup_drive, "criar_pasta", self._criar_pasta)
        monkeypatch.setattr(backup_drive, "listar", self._listar)
        monkeypatch.setattr(backup_drive, "enviar", self._enviar)
        monkeypatch.setattr(backup_drive, "apagar", self._apagar)
        return self

    def _criar_pasta(self, tok, nome=backup_drive.PASTA):
        self.seq += 1
        self.pastas[nome] = f"pasta-{self.seq}"
        return self.pastas[nome]

    def _listar(self, tok, pid):
        return [f for f in sorted(self.arquivos.values(), key=lambda x: x["createdTime"], reverse=True)
                if f["parent"] == pid]

    def _enviar(self, tok, caminho, pid):
        if self.falhar_upload:
            raise RuntimeError("Drive: HTTP 500 — deu ruim")
        self.seq += 1
        tam = os.path.getsize(caminho)
        if self.truncar:
            raise RuntimeError(f"upload incompleto: {tam // 2} de {tam} bytes. "
                               "A cópia NÃO conta — nada foi apagado.")
        f = {"id": f"arq-{self.seq}", "name": os.path.basename(caminho), "size": tam,
             "createdTime": f"2026-09-{self.seq:02d}T00:00:00Z", "parent": pid}
        self.arquivos[f["id"]] = f
        return f

    def _apagar(self, tok, fid):
        self.apagados.append(self.arquivos.pop(fid)["name"])


@pytest.fixture()
def banco(tmp_path, monkeypatch):
    caminho = tmp_path / "command-center.sqlite"
    monkeypatch.setenv("CC_DB_PATH", str(caminho))
    con = conectar(); aplicar_schema(con)
    inserir(con, "clients", name="Hank Lai", status="ACTIVE", source="manual")
    con.commit(); con.close()
    return str(caminho)


@pytest.fixture()
def drive(monkeypatch):
    return DriveFalso().instalar(monkeypatch)


def test_sem_aplicar_nao_envia_nada(banco, drive):
    backup_banco.fazer(banco, aplicar=True)
    p = backup_drive.semanal(aplicar=False)
    assert p["aplicado"] is False and not drive.arquivos


def test_cria_a_pasta_com_o_nome_que_o_dono_pediu(banco, drive):
    backup_banco.fazer(banco, aplicar=True)
    backup_drive.semanal(aplicar=True)
    assert "Backup urace command center" in drive.pastas
    assert len(drive.arquivos) == 1


def test_a_pasta_nao_e_criada_duas_vezes(banco, drive):
    backup_banco.fazer(banco, aplicar=True)
    backup_drive.semanal(aplicar=True)
    backup_drive.semanal(aplicar=True)
    assert len(drive.pastas) == 1 and len(drive.arquivos) == 2


def test_sem_copia_local_ele_faz_uma_antes_de_enviar(banco, drive):
    """Backup semanal que depende de o diário ter rodado é backup que falha em silêncio."""
    p = backup_drive.semanal(aplicar=True)
    assert p["aplicado"] and len(drive.arquivos) == 1
    assert os.path.exists(p["arquivo"]), "a cópia local também ficou"


def test_o_que_passa_do_prazo_sai_do_drive(banco, drive):
    backup_banco.fazer(banco, aplicar=True)
    for _ in range(4):
        backup_drive.semanal(aplicar=True, guardar=2)
    assert len(drive.arquivos) == 2
    assert len(drive.apagados) == 2


def test_upload_truncado_nao_apaga_nada(banco, monkeypatch):
    """A trava que importa: se a cópia nova subiu pela metade, as antigas ficam."""
    d = DriveFalso().instalar(monkeypatch)
    backup_banco.fazer(banco, aplicar=True)
    backup_drive.semanal(aplicar=True, guardar=1)
    assert len(d.arquivos) == 1
    d.truncar = True
    with pytest.raises(RuntimeError, match="incompleto"):
        backup_drive.semanal(aplicar=True, guardar=1)
    assert len(d.arquivos) == 1 and d.apagados == [], "a cópia boa continua lá"


def test_falha_de_rede_nao_apaga_nada(banco, monkeypatch):
    d = DriveFalso().instalar(monkeypatch)
    backup_banco.fazer(banco, aplicar=True)
    backup_drive.semanal(aplicar=True, guardar=1)
    d.falhar_upload = True
    with pytest.raises(RuntimeError):
        backup_drive.semanal(aplicar=True, guardar=1)
    assert len(d.arquivos) == 1 and d.apagados == []


def test_copia_quebrada_nao_sobe_para_o_drive(banco, drive, tmp_path):
    """Não adianta guardar longe um arquivo que não abre."""
    ruim = tmp_path / "command-center-quebrada.sqlite"
    ruim.write_bytes(b"isto nao e um banco")
    with pytest.raises(Exception):
        backup_drive.semanal(aplicar=True, caminho=str(ruim))
    assert not drive.arquivos


def test_a_copia_comprimida_e_conferida_antes_de_subir(banco, drive):
    p = backup_banco.fazer(banco, aplicar=True, comprimida=True)
    assert p["destino"].endswith(".gz")
    r = backup_drive.semanal(aplicar=True, caminho=p["destino"])
    assert r["aplicado"] and list(drive.arquivos.values())[0]["name"].endswith(".gz")


def test_o_escopo_pedido_e_o_minimo_que_serve():
    """`drive.file` deixa o app ver só o que ele mesmo criou. `drive` cheio abriria o
    Drive inteiro para ler — e não é preciso para escrever um backup."""
    from adminai import google_auth
    assert "https://www.googleapis.com/auth/drive.file" in google_auth.ESCOPOS
    assert "https://www.googleapis.com/auth/drive" not in google_auth.ESCOPOS


def test_erro_de_permissao_explica_o_que_fazer(monkeypatch):
    """Token velho sem escopo de escrita é o erro mais provável na primeira vez."""
    import urllib.error

    def recusa(*a, **k):
        raise urllib.error.HTTPError("u", 403, "Forbidden", {},
                                     __import__("io").BytesIO(b'{"error":"insufficient scope"}'))
    monkeypatch.setattr(backup_drive.urllib.request, "urlopen", recusa)
    with pytest.raises(RuntimeError) as e:
        backup_drive._pedir("https://x", "tok")
    assert "google_auth.py" in str(e.value) and "ESCRITA" in str(e.value)
