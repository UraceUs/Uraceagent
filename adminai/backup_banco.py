#!/usr/bin/env python3
"""Backup do banco — cópia consistente, verificada, com rodízio.

A auditoria de 23/09 achou o buraco: **não havia backup nenhum.** Clientes, financeiro,
estoque, waivers e a auditoria inteira viviam num arquivo só, numa máquina só. Disco que
morre, `rm` errado ou VPS que some levavam tudo junto.

    python3 adminai/backup_banco.py                 # diz o que faria
    python3 adminai/backup_banco.py --aplicar       # copia e verifica
    python3 adminai/backup_banco.py --restaurar ARQUIVO --aplicar

**Cópia consistente, não `cp`.** Copiar um SQLite com `cp` enquanto alguém escreve gera
arquivo quebrado — e o pior tipo de backup é o que parece existir e não abre. Aqui é
`VACUUM INTO`, que o próprio SQLite faz em transação e já sai desfragmentado.

**Verificada na hora.** Toda cópia é aberta e passa por `integrity_check` antes de
contar como backup. Sem isso, a descoberta de que o backup estava corrompido acontece no
dia em que ele é a única coisa que resta.

**Não apaga o que não conseguiu substituir.** A limpeza das cópias velhas só roda depois
de a nova existir e estar íntegra.
"""
import argparse
import gzip
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from adminai._venv import garantir_venv  # noqa: E402

garantir_venv()

from command_center.db import db_path  # noqa: E402

GUARDAR = 14          # dias de cópias diárias


def pasta_backups(caminho_banco=None):
    p = os.path.join(os.path.dirname(caminho_banco or db_path()), "backups")
    os.makedirs(p, exist_ok=True)
    os.chmod(p, 0o700)        # o backup tem exatamente os mesmos dados do banco
    return p


def copiar(origem, destino):
    """`VACUUM INTO`: cópia transacional feita pelo próprio SQLite."""
    con = sqlite3.connect(origem, timeout=30)
    try:
        con.execute("PRAGMA busy_timeout = 30000")
        con.execute("VACUUM INTO ?", (destino,))
    finally:
        con.close()
    os.chmod(destino, 0o600)


def verificar(caminho):
    """Abre a cópia e confere. Backup que não abre não é backup."""
    con = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True, timeout=30)
    try:
        estado = con.execute("PRAGMA integrity_check").fetchone()[0]
        tabelas = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        clientes = con.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    finally:
        con.close()
    if str(estado).lower() != "ok":
        raise RuntimeError(f"a cópia não passou no integrity_check: {estado}")
    if tabelas < 10:
        raise RuntimeError(f"a cópia só tem {tabelas} tabela(s): algo saiu errado")
    return {"tabelas": tabelas, "clientes": clientes}


def comprimir(caminho):
    alvo = caminho + ".gz"
    with open(caminho, "rb") as e, gzip.open(alvo, "wb", compresslevel=6) as s:
        shutil.copyfileobj(e, s)
    os.chmod(alvo, 0o600)
    os.remove(caminho)
    return alvo


def antigas(pasta, guardar=GUARDAR):
    """As que passaram do prazo. Devolve a lista; quem apaga é quem chamou."""
    limite = time.time() - guardar * 86400
    saida = []
    for nome in os.listdir(pasta):
        if not nome.startswith("command-center-") or not nome.endswith((".sqlite", ".sqlite.gz")):
            continue
        caminho = os.path.join(pasta, nome)
        if os.path.getmtime(caminho) < limite:
            saida.append(caminho)
    return sorted(saida)


def fazer(caminho_banco=None, aplicar=False, guardar=GUARDAR, comprimida=True):
    origem = caminho_banco or db_path()
    if not os.path.exists(origem):
        raise SystemExit(f"o banco não existe: {origem}")
    pasta = pasta_backups(origem)
    carimbo = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    destino = os.path.join(pasta, f"command-center-{carimbo}.sqlite")
    velhas = antigas(pasta, guardar)
    plano = {"origem": origem, "destino": destino, "pasta": pasta,
             "tamanho_origem": os.path.getsize(origem), "apagaria": velhas, "aplicado": False}
    if not aplicar:
        return plano

    copiar(origem, destino)
    plano["conferido"] = verificar(destino)          # antes de qualquer limpeza
    if comprimida:
        destino = comprimir(destino)
    plano["destino"] = destino
    plano["tamanho_copia"] = os.path.getsize(destino)
    # Só agora: a cópia nova existe e está íntegra.
    apagadas = []
    for v in velhas:
        try:
            os.remove(v)
            apagadas.append(v)
        except OSError:
            pass
    plano["apagadas"] = apagadas
    plano["aplicado"] = True
    return plano


def restaurar(arquivo, caminho_banco=None, aplicar=False):
    """Põe uma cópia no lugar do banco. **Guarda o atual antes**, sempre: restaurar por
    engano não pode ser um caminho sem volta."""
    destino = caminho_banco or db_path()
    if not os.path.exists(arquivo):
        raise SystemExit(f"cópia não encontrada: {arquivo}")
    temp = arquivo
    if arquivo.endswith(".gz"):
        temp = arquivo[:-3] + ".restaurando"
        with gzip.open(arquivo, "rb") as e, open(temp, "wb") as s:
            shutil.copyfileobj(e, s)
    info = verificar(temp)                            # nunca restaura cópia quebrada
    salvo = f"{destino}.antes-de-restaurar-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
    if not aplicar:
        if temp != arquivo:
            os.remove(temp)
        return {"aplicado": False, "copia": arquivo, "conferido": info,
                "guardaria_atual_em": salvo, "destino": destino}
    if os.path.exists(destino):
        shutil.copy2(destino, salvo)
        os.chmod(salvo, 0o600)
    shutil.move(temp, destino)
    os.chmod(destino, 0o600)
    return {"aplicado": True, "copia": arquivo, "conferido": info,
            "atual_guardado_em": salvo, "destino": destino}


def main():
    ap = argparse.ArgumentParser(description="Backup do banco do Command Center")
    ap.add_argument("--aplicar", action="store_true", help="faz de verdade")
    ap.add_argument("--guardar", type=int, default=GUARDAR, help="dias de cópias (padrão 14)")
    ap.add_argument("--sem-compressao", action="store_true")
    ap.add_argument("--restaurar", metavar="ARQUIVO", help="põe esta cópia no lugar do banco")
    ap.add_argument("--listar", action="store_true", help="mostra as cópias existentes")
    a = ap.parse_args()

    if a.listar:
        pasta = pasta_backups()
        copias = sorted(os.listdir(pasta), reverse=True)
        print(f"{pasta}\n" + "-" * 60)
        for c in copias:
            p = os.path.join(pasta, c)
            idade = (time.time() - os.path.getmtime(p)) / 3600
            print(f"  {c:<44} {os.path.getsize(p)/1024/1024:>6.1f} MB  há {idade:>5.1f} h")
        if not copias:
            print("  (nenhuma cópia ainda)")
        return 0

    if a.restaurar:
        r = restaurar(a.restaurar, aplicar=a.aplicar)
        print(f"cópia: {r['copia']}")
        print(f"conferida: {r['conferido']['tabelas']} tabelas, {r['conferido']['clientes']} clientes")
        if r["aplicado"]:
            print(f"RESTAURADO em {r['destino']}")
            print(f"o banco que estava lá foi guardado em {r['atual_guardado_em']}")
            print("Reinicie o serviço: sudo systemctl restart urace-command-center")
        else:
            print(f"Nada foi feito. O banco atual seria guardado em {r['guardaria_atual_em']}")
            print("Para restaurar de verdade, repita com --aplicar")
        return 0

    p = fazer(aplicar=a.aplicar, guardar=a.guardar, comprimida=not a.sem_compressao)
    print(f"banco:  {p['origem']}  ({p['tamanho_origem']/1024/1024:.1f} MB)")
    print(f"cópia:  {p['destino']}")
    if p["aplicado"]:
        c = p["conferido"]
        print(f"CONFERIDA: {c['tabelas']} tabelas, {c['clientes']} clientes, "
              f"{p['tamanho_copia']/1024/1024:.1f} MB no disco")
        if p["apagadas"]:
            print(f"{len(p['apagadas'])} cópia(s) com mais de {a.guardar} dias removida(s)")
    else:
        if p["apagaria"]:
            print(f"apagaria {len(p['apagaria'])} cópia(s) com mais de {a.guardar} dias")
        print("\nNada foi feito. Para fazer o backup: --aplicar")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
