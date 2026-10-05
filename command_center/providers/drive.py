"""Google Drive pelo token do VPS (urace@), com o escopo mínimo `drive.file`: o sistema só
enxerga e mexe no que ele mesmo criou — a pasta "Command Center" e o que está dentro.

Usado pela Biblioteca (#88). Nada aqui apaga arquivo: um documento que mudou SUBSTITUI o
conteúdo do mesmo arquivo, e o Drive guarda a versão anterior no histórico dele.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
PASTA_MIME = "application/vnd.google-apps.folder"


def token():
    from adminai import google_auth
    return google_auth.access_token()


def _pedir(url, tok, metodo="GET", corpo=None, tipo="application/json"):
    dados = corpo if isinstance(corpo, bytes) else (json.dumps(corpo).encode() if corpo is not None else None)
    req = urllib.request.Request(url, data=dados, method=metodo)
    req.add_header("Authorization", f"Bearer {tok}")
    if dados is not None:
        req.add_header("Content-Type", tipo)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            b = r.read()
            return json.loads(b) if b else {}
    except urllib.error.HTTPError as e:
        detalhe = e.read()[:300].decode(errors="replace")
        if e.code in (401, 403) and "insufficient" in detalhe.lower():
            raise RuntimeError("o token do Google no VPS não tem permissão de escrita no Drive: "
                               "rode python3 adminai/google_auth.py --conta urace")
        raise RuntimeError(f"Drive: HTTP {e.code} — {detalhe}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Drive: sem conexão — {e.reason}")


def _q(texto):
    return texto.replace("\\", "\\\\").replace("'", "\\'")


def pasta(tok, nome, pai=None):
    """A pasta `nome` dentro de `pai` (ou na raiz do Drive); cria se não existe."""
    q = f"name = '{_q(nome)}' and mimeType = '{PASTA_MIME}' and trashed = false"
    q += f" and '{pai}' in parents" if pai else " and 'root' in parents"
    achadas = _pedir(f"{API}/files?q={urllib.parse.quote(q)}&fields=files(id,name)", tok).get("files", [])
    if achadas:
        return achadas[0]["id"]
    corpo = {"name": nome, "mimeType": PASTA_MIME}
    if pai:
        corpo["parents"] = [pai]
    return _pedir(f"{API}/files?fields=id", tok, "POST", corpo)["id"]


def enviar(tok, nome, dados, pai, file_id=None, tipo="application/pdf"):
    """Cria o arquivo, ou substitui o conteúdo de `file_id`. Confere o tamanho: upload pela
    metade não conta. Devolve o id do arquivo."""
    limite = "===============urace-biblioteca=="
    meta = {"name": nome} if file_id else {"name": nome, "parents": [pai]}
    corpo = (f"--{limite}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}"
             f"\r\n--{limite}\r\nContent-Type: {tipo}\r\n\r\n").encode() + dados + f"\r\n--{limite}--\r\n".encode()
    url = (f"{UPLOAD}/{file_id}?uploadType=multipart&fields=id,size" if file_id
           else f"{UPLOAD}?uploadType=multipart&fields=id,size")
    r = _pedir(url, tok, "PATCH" if file_id else "POST", corpo, tipo=f"multipart/related; boundary={limite}")
    if int(r.get("size") or 0) != len(dados):
        raise RuntimeError(f"upload incompleto de {nome}: {r.get('size')} de {len(dados)} bytes")
    return r["id"]


def compartilhar(tok, file_id, email, papel="reader"):
    """Dá acesso à pasta para uma pessoa da equipe, sem mandar e-mail de aviso."""
    _pedir(f"{API}/files/{file_id}/permissions?sendNotificationEmail=false&fields=id", tok, "POST",
           {"type": "user", "role": papel, "emailAddress": email})
