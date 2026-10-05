"""O token do Google que o VPS usa fora do Gmail (#88).

O backup semanal para o Drive e a leitura da Rate Card chamavam
`google_auth.access_token()`, uma função que **não existia**. Os testes deles
trocavam o token por um falso, então ninguém viu: no VPS os dois quebravam antes de
falar com o Google. Aqui é o caminho de verdade: o arquivo do token no disco, a
troca do refresh token, e as mensagens quando falta o token ou ele foi revogado.
"""
import io
import json
import urllib.error
import urllib.parse

import pytest

from adminai import backup_drive, google_auth


class Resposta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture()
def token(tmp_path, monkeypatch):
    p = tmp_path / "google-token.json"
    p.write_text(json.dumps({"client_id": "cid", "client_secret": "segredo", "refresh_token": "rt-1",
                             "email": "urace@urace.us", "scopes": google_auth.ESCOPOS}))
    monkeypatch.setenv("GOOGLE_TOKEN_JSON", str(p))
    google_auth._cache.clear()
    return p


def test_troca_o_refresh_token_e_guarda_ate_vencer(token, monkeypatch):
    pedidos = []

    def urlopen(req, timeout=None):
        pedidos.append((req.full_url, urllib.parse.parse_qs(req.data.decode())))
        return Resposta(json.dumps({"access_token": "at-123", "expires_in": 3600}).encode())
    monkeypatch.setattr(google_auth.urllib.request, "urlopen", urlopen)
    assert google_auth.access_token() == "at-123"
    assert google_auth.access_token() == "at-123", "segunda chamada usa o que já tem"
    assert len(pedidos) == 1
    url, corpo = pedidos[0]
    assert url == "https://oauth2.googleapis.com/token"
    assert corpo["grant_type"] == ["refresh_token"] and corpo["refresh_token"] == ["rt-1"]


def test_o_backup_do_drive_usa_o_token_de_verdade(token, monkeypatch):
    monkeypatch.setattr(google_auth.urllib.request, "urlopen",
                        lambda req, timeout=None: Resposta(b'{"access_token": "at-drive", "expires_in": 3600}'))
    assert backup_drive._token() == "at-drive"


def test_sem_token_diz_o_que_rodar(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_TOKEN_JSON", str(tmp_path / "nao-existe.json"))
    google_auth._cache.clear()
    with pytest.raises(RuntimeError) as e:
        google_auth.access_token()
    assert "google_auth.py" in str(e.value)


def test_token_revogado_diz_o_que_rodar(token, monkeypatch):
    def recusa(req, timeout=None):
        raise urllib.error.HTTPError("u", 400, "Bad Request", {}, io.BytesIO(b'{"error": "invalid_grant"}'))
    monkeypatch.setattr(google_auth.urllib.request, "urlopen", recusa)
    with pytest.raises(RuntimeError) as e:
        google_auth.access_token()
    assert "revogado" in str(e.value) and "google_auth.py" in str(e.value)
    assert "segredo" not in str(e.value) and "rt-1" not in str(e.value), "segredo nunca na mensagem"
