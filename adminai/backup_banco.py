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

**O histórico (#299):** 30 dias de cópias diárias e, antes disso, a primeira cópia de cada mês dos
últimos 12 meses. Cada rodada grava o resultado em `backups/estado-local.json` (quando, o arquivo, se
passou na conferência ou o erro): é o que o painel lê em Sistemas para avisar quando o backup do dia
falhou ou faltou.
"""
import argparse
import gzip
import json
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

GUARDAR = 30          # dias de cópias diárias
MESES = 12            # e a primeira cópia de cada mês, por este tanto de meses


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


def apagar_do_historico(itens, agora_ts=None, guardar=GUARDAR, meses=MESES):
    """`itens`: [(chave, epoch)]. Fica tudo dos últimos `guardar` dias e, antes disso, a cópia mais antiga de cada
    mês dos últimos `meses` meses. Devolve as chaves que saem. (O mesmo histórico no disco e no Drive.)"""
    agora_ts = agora_ts or time.time()
    limite = agora_ts - guardar * 86400
    hoje = datetime.fromtimestamp(agora_ts, timezone.utc)
    mes_limite = (hoje.year * 12 + hoje.month - 1) - meses        # meses inteiros para trás
    primeiras = {}
    for chave, ts in sorted(itens, key=lambda x: x[1]):
        d = datetime.fromtimestamp(ts, timezone.utc)
        primeiras.setdefault((d.year, d.month), chave)
    saem = []
    for chave, ts in itens:
        if ts >= limite:
            continue
        d = datetime.fromtimestamp(ts, timezone.utc)
        if (d.year * 12 + d.month - 1) > mes_limite and primeiras[(d.year, d.month)] == chave:
            continue
        saem.append(chave)
    return saem


def antigas(pasta, guardar=GUARDAR, meses=MESES):
    """As que passaram do prazo. Devolve a lista; quem apaga é quem chamou."""
    itens = []
    for nome in os.listdir(pasta):
        if not nome.startswith("command-center-") or not nome.endswith((".sqlite", ".sqlite.gz")):
            continue
        caminho = os.path.join(pasta, nome)
        itens.append((caminho, os.path.getmtime(caminho)))
    return sorted(apagar_do_historico(itens, guardar=guardar, meses=meses))


def gravar_estado(tipo, ok, pasta=None, **detalhe):
    """O resultado da rodada (`local` ou `drive`) para o painel. Sem dado de cliente além do número de clientes,
    sem chave, sem caminho de fora da pasta."""
    estado = {"em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "ok": bool(ok), **detalhe}
    caminho = os.path.join(pasta or pasta_backups(), f"estado-{tipo}.json")
    temp = caminho + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False)
    os.chmod(temp, 0o600)
    os.replace(temp, caminho)
    return estado


def ler_estado(tipo, pasta=None):
    try:
        with open(os.path.join(pasta or pasta_backups(), f"estado-{tipo}.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


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
    ap.add_argument("--guardar", type=int, default=GUARDAR, help="dias de cópias diárias (padrão 30; antes disso, uma por mês por 12 meses)")
    ap.add_argument("--sem-compressao", action="store_true")
    ap.add_argument("--restaurar", metavar="ARQUIVO", help="põe esta cópia no lugar do banco")
    ap.add_argument("--listar", action="store_true", help="mostra as cópias existentes")
    a = ap.parse_args()

    if a.listar:
        pasta = pasta_backups()
        copias = sorted((c for c in os.listdir(pasta) if c.startswith("command-center-")), reverse=True)
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

    try:
        p = fazer(aplicar=a.aplicar, guardar=a.guardar, comprimida=not a.sem_compressao)
    except Exception as e:                          # noqa: BLE001 — o painel precisa saber que falhou
        if a.aplicar:
            gravar_estado("local", False, erro=f"{type(e).__name__}: {str(e)[:300]}")
        raise
    if p["aplicado"]:
        gravar_estado("local", True, arquivo=os.path.basename(p["destino"]), tamanho=p["tamanho_copia"],
                      clientes=p["conferido"]["clientes"], tabelas=p["conferido"]["tabelas"])
    print(f"banco:  {p['origem']}  ({p['tamanho_origem']/1024/1024:.1f} MB)")
    print(f"cópia:  {p['destino']}")
    if p["aplicado"]:
        c = p["conferido"]
        print(f"CONFERIDA: {c['tabelas']} tabelas, {c['clientes']} clientes, "
              f"{p['tamanho_copia']/1024/1024:.1f} MB no disco")
        if p["apagadas"]:
            print(f"{len(p['apagadas'])} cópia(s) fora do histórico removida(s) ({a.guardar} dias + 1 por mês por {MESES} meses)")
    else:
        if p["apagaria"]:
            print(f"apagaria {len(p['apagaria'])} cópia(s) fora do histórico ({a.guardar} dias + 1 por mês por {MESES} meses)")
        print("\nNada foi feito. Para fazer o backup: --aplicar")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
