#!/usr/bin/env python3
"""Backup semanal para o Google Drive — a cópia que sobrevive a perder a VPS.

Dono, 23/09: *"pode criar uma pasta no drive com o nome Backup urace command center com
o backup semanal"*.

    python3 adminai/backup_drive.py                  # diz o que faria
    python3 adminai/backup_drive.py --aplicar        # cria a pasta e envia
    python3 adminai/backup_drive.py --listar         # o que já está lá

**Por que isto existe separado do backup local:** o backup em `~/.urace/backups` protege
de `rm` errado, de banco corrompido e de migração ruim. Ele **não** protege de perder a
máquina — incêndio, conta suspensa, disco que some levam o banco e as cópias juntos.
Esta é a cópia que fica fora.

**Escopo mínimo: `drive.file`.** O app só enxerga o que ele mesmo criou. Ele cria a
pasta e escreve dentro dela, e não consegue ler o resto do seu Drive. Por isso a pasta é
criada por esta ferramenta, e não à mão: com `drive.file`, pasta criada por outro app
seria invisível para ela.

**O que vai dentro é o banco inteiro** — cliente, telefone, e-mail, valor de invoice.
A pasta nasce privada (só o dono da conta). Não compartilhe: um link "qualquer pessoa
com o link" ali dentro é o vazamento da base inteira.

**Nunca apaga o que não conseguiu substituir.** A limpeza das cópias antigas do Drive só
roda depois de a nova estar lá e ter o tamanho conferido.
"""
import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from adminai._venv import garantir_venv  # noqa: E402

garantir_venv()

from adminai import backup_banco  # noqa: E402

PASTA = os.environ.get("BACKUP_DRIVE_PASTA", "Backup urace command center")
API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
GUARDAR = 8            # semanas no Drive (~2 meses)


def _token():
    from adminai import google_auth
    return google_auth.access_token()


def _pedir(url, token, metodo="GET", corpo=None, tipo="application/json"):
    req = urllib.request.Request(url, method=metodo,
                                 data=corpo if isinstance(corpo, bytes) else
                                 (json.dumps(corpo).encode() if corpo is not None else None))
    req.add_header("Authorization", f"Bearer {token}")
    if corpo is not None:
        req.add_header("Content-Type", tipo)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            dados = r.read()
            return json.loads(dados) if dados else {}
    except urllib.error.HTTPError as e:
        detalhe = e.read()[:400].decode(errors="replace")
        if e.code in (401, 403) and "insufficient" in detalhe.lower():
            raise RuntimeError(
                "O Google recusou: o token da VPS não tem permissão de ESCRITA no Drive.\n"
                "   Rode de novo o consentimento, que agora pede `drive.file`:\n"
                "     python3 adminai/google_auth.py --conta urace")
        raise RuntimeError(f"Drive: HTTP {e.code} — {detalhe}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Drive: sem conexão — {e.reason}")


def achar_pasta(token, nome=PASTA):
    """A pasta que ESTA ferramenta criou. Com `drive.file` ela não enxerga outras."""
    q = (f"name = '{nome}' and mimeType = 'application/vnd.google-apps.folder' "
         "and trashed = false")
    r = _pedir(f"{API}/files?q={urllib.parse.quote(q)}&fields=files(id,name)", token)
    achadas = r.get("files", [])
    return achadas[0]["id"] if achadas else None


def criar_pasta(token, nome=PASTA):
    r = _pedir(f"{API}/files?fields=id,name,webViewLink", token, "POST",
               {"name": nome, "mimeType": "application/vnd.google-apps.folder"})
    return r["id"]


def pasta(token, nome=PASTA, criar=True):
    ident = achar_pasta(token, nome)
    if ident or not criar:
        return ident
    return criar_pasta(token, nome)


def listar(token, pasta_id):
    q = f"'{pasta_id}' in parents and trashed = false"
    r = _pedir(f"{API}/files?q={urllib.parse.quote(q)}"
               "&fields=files(id,name,size,createdTime)&orderBy=createdTime desc", token)
    return r.get("files", [])


def enviar(token, caminho, pasta_id):
    """Upload multipart: metadados + bytes numa requisição. Confere o tamanho no fim —
    upload truncado que ninguém percebe é backup que não existe."""
    nome = os.path.basename(caminho)
    with open(caminho, "rb") as f:
        dados = f.read()
    limite = "===============urace=="
    tipo = mimetypes.guess_type(nome)[0] or "application/octet-stream"
    corpo = (f"--{limite}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
             + json.dumps({"name": nome, "parents": [pasta_id]})
             + f"\r\n--{limite}\r\nContent-Type: {tipo}\r\n\r\n").encode()
    corpo += dados + f"\r\n--{limite}--\r\n".encode()
    r = _pedir(f"{UPLOAD}?uploadType=multipart&fields=id,name,size", token, "POST", corpo,
               tipo=f"multipart/related; boundary={limite}")
    enviado = int(r.get("size") or 0)
    if enviado != len(dados):
        raise RuntimeError(f"upload incompleto: {enviado} de {len(dados)} bytes. "
                           "A cópia NÃO conta — nada foi apagado.")
    return r


def apagar(token, file_id):
    _pedir(f"{API}/files/{file_id}", token, "DELETE")


def semanal(aplicar=False, guardar=GUARDAR, token=None, caminho=None):
    """Envia a cópia local mais recente. Se não houver nenhuma, faz uma antes: backup
    semanal que depende de o diário ter rodado é backup que falha em silêncio."""
    local = caminho
    if not local:
        p = backup_banco.pasta_backups()
        copias = sorted((f for f in os.listdir(p) if f.startswith("command-center-")),
                        key=lambda f: os.path.getmtime(os.path.join(p, f)), reverse=True)
        if copias:
            local = os.path.join(p, copias[0])
        elif aplicar:
            local = backup_banco.fazer(aplicar=True)["destino"]
        else:
            return {"aplicado": False, "erro": "não há cópia local; faria uma antes de enviar"}

    plano = {"arquivo": local, "tamanho": os.path.getsize(local) if local else 0,
             "pasta": PASTA, "aplicado": False}
    if not aplicar:
        return plano

    tok = token or _token()
    pid = pasta(tok)
    plano["pasta_id"] = pid
    # Confere a cópia ANTES de subir: não adianta guardar longe um arquivo quebrado.
    backup_banco.verificar(local if not local.endswith(".gz") else _descompactar(local))
    plano["enviado"] = enviar(tok, local, pid)

    existentes = listar(tok, pid)
    sobrando = existentes[guardar:]
    apagados = []
    for f in sobrando:                      # só agora: a nova já está lá e conferida
        apagar(tok, f["id"])
        apagados.append(f["name"])
    plano["apagados"] = apagados
    plano["no_drive"] = len(existentes) - len(apagados)
    plano["aplicado"] = True
    return plano


def _descompactar(caminho):
    """`.gz` precisa virar arquivo para o `integrity_check` abrir. Some depois."""
    import gzip
    import shutil
    import tempfile
    destino = os.path.join(tempfile.mkdtemp(prefix="cc-verif-"), "copia.sqlite")
    with gzip.open(caminho, "rb") as e, open(destino, "wb") as s:
        shutil.copyfileobj(e, s)
    return destino


def main():
    ap = argparse.ArgumentParser(description="Backup semanal do banco para o Google Drive")
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--guardar", type=int, default=GUARDAR, help="semanas no Drive (padrão 8)")
    ap.add_argument("--listar", action="store_true")
    ap.add_argument("--arquivo", help="enviar esta cópia em vez da mais recente")
    a = ap.parse_args()

    if a.listar:
        tok = _token()
        pid = pasta(tok, criar=False)
        if not pid:
            print(f'A pasta "{PASTA}" ainda não existe no Drive.')
            print("Ela é criada no primeiro envio: python3 adminai/backup_drive.py --aplicar")
            return 0
        arquivos = listar(tok, pid)
        print(f'"{PASTA}" — {len(arquivos)} cópia(s)\n' + "-" * 60)
        for f in arquivos:
            print(f"  {f['name']:<44} {int(f.get('size') or 0)/1024/1024:>6.1f} MB  {f['createdTime'][:10]}")
        return 0

    try:
        p = semanal(aplicar=a.aplicar, guardar=a.guardar, caminho=a.arquivo)
    except RuntimeError as e:
        print(f"!! {e}")
        return 1
    print(f'pasta no Drive: "{p["pasta"]}"')
    print(f"arquivo: {p['arquivo']}  ({p['tamanho']/1024/1024:.1f} MB)")
    if p["aplicado"]:
        print(f"ENVIADO e conferido: {p['enviado']['name']}")
        print(f"{p['no_drive']} cópia(s) na pasta"
              + (f"; {len(p['apagados'])} antiga(s) removida(s)" if p["apagados"] else ""))
        print("\nA pasta é privada. Não compartilhe: dentro dela está a base inteira.")
    else:
        if p.get("erro"):
            print(f"({p['erro']})")
        print("\nNada foi enviado. Para enviar: --aplicar")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
