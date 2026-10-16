#!/usr/bin/env python3
"""Backup diário para o Google Drive, cifrado — a cópia que sobrevive a perder a VPS.

Dono, 23/09: *"pode criar uma pasta no drive com o nome Backup urace command center com
o backup semanal"*. 16/10 (#299): *"dados de clientes … armazenados em um banco de dados"*, decisão
**SQLite + backup diário**: a cópia de fora passa a ser **todo dia** (04:00, depois da local das 03:15),
**cifrada** (AES-256-GCM, `adminai/cifra_backup.py`), com o mesmo histórico da local: 30 dias + a primeira
de cada mês por 12 meses. Cada rodada grava `backups/estado-drive.json`, que o painel lê em Sistemas.

    python3 adminai/backup_drive.py                  # diz o que faria
    python3 adminai/backup_drive.py --aplicar        # cria a pasta e envia
    python3 adminai/backup_drive.py --listar         # o que já está lá
    python3 adminai/backup_drive.py --baixar NOME    # traz do Drive, decifra e confere (para restaurar)

**Por que isto existe separado do backup local:** o backup em `~/.urace/backups` protege
de `rm` errado, de banco corrompido e de migração ruim. Ele **não** protege de perder a
máquina — incêndio, conta suspensa, disco que some levam o banco e as cópias juntos.
Esta é a cópia que fica fora.

**Escopo mínimo: `drive.file`.** O app só enxerga o que ele mesmo criou. Ele cria a
pasta e escreve dentro dela, e não consegue ler o resto do seu Drive. Por isso a pasta é
criada por esta ferramenta, e não à mão: com `drive.file`, pasta criada por outro app
seria invisível para ela.

**O que vai dentro é o banco inteiro** — cliente, telefone, e-mail, valor de invoice — **cifrado**.
A pasta nasce privada (só o dono da conta). Não compartilhe mesmo assim. **A chave fica no
`~/.urace/adminai.env` da VPS: guarde uma cópia desse arquivo fora dela**, senão a cópia do Drive
não abre no dia em que a VPS some.

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

# Dono, 05/10 (#88): o backup fica DENTRO da pasta "Command Center", junto da Biblioteca.
# Continua privado: a Biblioteca compartilha com a equipe só a subpasta "Clientes", nunca a
# raiz, então ninguém além do dono da conta vê o banco. A pasta antiga "Backup urace command
# center" não é apagada: as cópias que já estão lá ficam.
RAIZ = os.environ.get("BACKUP_DRIVE_RAIZ", "Command Center")
PASTA = os.environ.get("BACKUP_DRIVE_PASTA", "Backup do banco")
API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
GUARDAR = backup_banco.GUARDAR    # dias de cópias diárias no Drive
MESES = backup_banco.MESES        # e a primeira de cada mês, por este tanto de meses


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


def achar_pasta(token, nome=PASTA, pai=None):
    """A pasta que ESTA ferramenta criou. Com `drive.file` ela não enxerga outras."""
    q = (f"name = '{nome}' and mimeType = 'application/vnd.google-apps.folder' "
         "and trashed = false") + (f" and '{pai}' in parents" if pai else "")
    r = _pedir(f"{API}/files?q={urllib.parse.quote(q)}&fields=files(id,name)", token)
    achadas = r.get("files", [])
    return achadas[0]["id"] if achadas else None


def criar_pasta(token, nome=PASTA, pai=None):
    corpo = {"name": nome, "mimeType": "application/vnd.google-apps.folder"}
    if pai:
        corpo["parents"] = [pai]
    r = _pedir(f"{API}/files?fields=id,name,webViewLink", token, "POST", corpo)
    return r["id"]


def pasta(token, nome=PASTA, criar=True):
    """Command Center/<nome>: a raiz é a mesma da Biblioteca."""
    raiz = achar_pasta(token, RAIZ)
    if not raiz:
        if not criar:
            return None
        raiz = criar_pasta(token, RAIZ)
    ident = achar_pasta(token, nome, pai=raiz)
    if ident or not criar:
        return ident
    return criar_pasta(token, nome, pai=raiz)


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


def baixar_bytes(token, file_id):
    req = urllib.request.Request(f"{API}/files/{file_id}?alt=media")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Drive: HTTP {e.code} ao baixar")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Drive: sem conexão — {e.reason}")


def _epoch(iso):
    from datetime import datetime
    return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()


def diario(aplicar=False, guardar=GUARDAR, meses=MESES, token=None, caminho=None):
    """Envia a cópia local mais recente, cifrada. Se não houver nenhuma, faz uma antes: backup
    de fora que depende de o local ter rodado é backup que falha em silêncio."""
    from adminai import cifra_backup
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
             "pasta": f"{RAIZ}/{PASTA}", "aplicado": False}
    if not aplicar:
        return plano

    cifra_backup.chave()                    # sem chave, nada sobe (e o erro diz o que fazer)
    tok = token or _token()
    pid = pasta(tok)
    plano["pasta_id"] = pid
    # Confere a cópia ANTES de subir: não adianta guardar longe um arquivo quebrado.
    plano["conferido"] = backup_banco.verificar(local if not local.endswith(".gz") else _descompactar(local))
    cifrado = cifra_backup.cifrar(local)
    try:
        plano["enviado"] = enviar(tok, cifrado, pid)
    finally:
        os.remove(cifrado)                  # no disco fica só a cópia local de sempre
    plano["chave"] = cifra_backup.impressao()

    existentes = listar(tok, pid)
    nossos = [f for f in existentes if f["name"].startswith("command-center-")]
    sai = set(backup_banco.apagar_do_historico([(f["id"], _epoch(f["createdTime"])) for f in nossos],
                                               guardar=guardar, meses=meses))
    sai.discard(plano["enviado"].get("id"))
    apagados = []
    for f in nossos:                        # só agora: a nova já está lá e conferida
        if f["id"] in sai:
            apagar(tok, f["id"])
            apagados.append(f["name"])
    plano["apagados"] = apagados
    plano["no_drive"] = len(existentes) - len(apagados)
    plano["aplicado"] = True
    return plano


semanal = diario                            # o nome de antes (o timer agora roda todo dia)


def baixar(nome, token=None):
    """Traz uma cópia do Drive, decifra e confere: devolve o arquivo local pronto para
    `backup_banco.py --restaurar`. Nada no banco muda aqui."""
    from adminai import cifra_backup
    tok = token or _token()
    pid = pasta(tok, criar=False)
    achado = next((f for f in (listar(tok, pid) if pid else []) if f["name"] == nome), None)
    if not achado:
        raise RuntimeError(f"não achei {nome} na pasta do Drive (veja --listar)")
    destino_pasta = backup_banco.pasta_backups()
    cifrado = os.path.join(destino_pasta, "baixado-" + os.path.basename(nome))
    with open(cifrado, "wb") as f:
        f.write(baixar_bytes(tok, achado["id"]))
    os.chmod(cifrado, 0o600)
    claro = os.path.join(destino_pasta, "do-drive-" + os.path.basename(nome).removesuffix(cifra_backup.SUFIXO))
    try:
        cifra_backup.decifrar(cifrado, claro) if nome.endswith(cifra_backup.SUFIXO) else os.replace(cifrado, claro)
    finally:
        if os.path.exists(cifrado):
            os.remove(cifrado)
    conferido = backup_banco.verificar(claro if not claro.endswith(".gz") else _descompactar(claro))
    return {"arquivo": claro, "conferido": conferido}


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
    ap = argparse.ArgumentParser(description="Backup diário do banco para o Google Drive, cifrado")
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--guardar", type=int, default=GUARDAR, help="dias de cópias diárias no Drive (padrão 30; antes, 1 por mês por 12 meses)")
    ap.add_argument("--listar", action="store_true")
    ap.add_argument("--arquivo", help="enviar esta cópia em vez da mais recente")
    ap.add_argument("--baixar", metavar="NOME", help="traz esta cópia do Drive, decifra e confere")
    a = ap.parse_args()

    if a.baixar:
        try:
            r = baixar(a.baixar)
        except RuntimeError as e:
            print(f"!! {e}")
            return 1
        print(f"baixada, decifrada e CONFERIDA: {r['conferido']['tabelas']} tabelas, {r['conferido']['clientes']} clientes")
        print(f"arquivo: {r['arquivo']}")
        print("Para pôr no lugar do banco (o atual é guardado antes):")
        print(f"  python3 adminai/backup_banco.py --restaurar {r['arquivo']} --aplicar")
        return 0

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
        p = diario(aplicar=a.aplicar, guardar=a.guardar, caminho=a.arquivo)
    except Exception as e:                          # noqa: BLE001 — o painel precisa saber que falhou
        if a.aplicar:
            backup_banco.gravar_estado("drive", False, erro=f"{str(e)[:300]}")
        print(f"!! {e}")
        return 1
    if p["aplicado"]:
        backup_banco.gravar_estado("drive", True, arquivo=p["enviado"]["name"], tamanho=int(p["enviado"].get("size") or 0),
                                   clientes=p["conferido"]["clientes"], chave=p["chave"], no_drive=p["no_drive"])
    print(f'pasta no Drive: "{p["pasta"]}"')
    print(f"arquivo: {p['arquivo']}  ({p['tamanho']/1024/1024:.1f} MB)")
    if p["aplicado"]:
        print(f"ENVIADO e conferido: {p['enviado']['name']}")
        print(f"{p['no_drive']} cópia(s) na pasta"
              + (f"; {len(p['apagados'])} antiga(s) removida(s)" if p["apagados"] else ""))
        print(f"cifrado com a chave {p['chave']} (CC_BACKUP_CHAVE do adminai.env: guarde uma cópia fora da VPS)")
        print("\nA pasta é privada. Não compartilhe: dentro dela está a base inteira.")
    else:
        if p.get("erro"):
            print(f"({p['erro']})")
        print("\nNada foi enviado. Para enviar: --aplicar")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
