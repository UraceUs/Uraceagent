#!/usr/bin/env python3
"""Auditoria do banco — estrutura e segurança, sem mexer em nada.

Dono, 23/09: *"preciso garantir que temos hoje um banco de dados estruturado e seguro
para todos os dados de clientes, financeiro, estoque e todos os outros dados"*.

    python3 adminai/auditar_banco.py

**Só lê.** Nenhuma escrita, nenhuma correção automática: auditoria que conserta sozinha
esconde o defeito que produziu o problema, e o que ela acha aqui pode precisar de
decisão de gente antes de qualquer mudança.

Cada checagem devolve OK, ATENÇÃO ou GRAVE, e diz **o que fazer** quando não está bem.
Nada de "parece tudo certo": ou a checagem rodou e tem resposta, ou ela diz que não
conseguiu olhar.
"""
import os
import sqlite3
import stat
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from adminai._venv import garantir_venv  # noqa: E402

garantir_venv()

from command_center.db import conectar, db_path, todos, um  # noqa: E402

OK, ATENCAO, GRAVE = "OK", "ATENÇÃO", "GRAVE"
# Tabelas que guardam o que o dono nomeou: cliente, financeiro, estoque e o resto.
DOMINIOS = {
    "clientes": ["clients", "client_merges", "entity_links", "crm_leads", "crm_messages", "calls"],
    "financeiro": ["invoices", "invoice_reminders", "opportunities", "qbo_items"],
    "estoque": ["stock_items", "stock_units", "stock_levels", "stock_moves", "supplier_products"],
    "contratos": ["waivers", "contracts", "waiver_reminders"],
    "operação": ["tasks", "races", "race_invites", "emails", "calendar_events"],
    "segurança": ["users", "sessions", "api_keys", "audit_logs", "login_attempts"],
}


def _achado(estado, titulo, detalhe, acao=None):
    return {"estado": estado, "titulo": titulo, "detalhe": detalhe, "acao": acao}


def integridade(con):
    """A pergunta mais básica: o arquivo está corrompido?

    PRAGMA volta como tupla no cursor cru — `um()` devolveria dicionário e o valor
    viraria o nome da coluna. Um teste pegou isso na hora."""
    linha = con.execute("PRAGMA integrity_check").fetchone()
    valor = linha[0] if linha else "?"
    if str(valor).lower() == "ok":
        return _achado(OK, "Integridade do arquivo", "sem corrupção")
    return _achado(GRAVE, "Integridade do arquivo", str(valor)[:300],
                   "Pare de escrever e restaure do backup mais recente.")


def chaves_estrangeiras(con):
    """Linha apontando para registro que não existe — cliente apagado com serviço órfão."""
    quebras = con.execute("PRAGMA foreign_key_check").fetchall()
    if not quebras:
        return _achado(OK, "Vínculos entre tabelas", "nenhum órfão")
    por_tabela = {}
    for q in quebras[:500]:
        por_tabela[q[0]] = por_tabela.get(q[0], 0) + 1
    return _achado(GRAVE, "Vínculos entre tabelas",
                   f"{len(quebras)} órfão(s): " + ", ".join(f"{t} ({n})" for t, n in por_tabela.items()),
                   "Cada órfão é um dado que aponta para o vazio. Me traga esta lista.")


def durabilidade(con):
    """`synchronous` é o que decide se uma queda de energia perde a última gravação."""
    modo = con.execute("PRAGMA journal_mode").fetchone()[0]
    sync = con.execute("PRAGMA synchronous").fetchone()[0]
    nomes = {0: "OFF (perde dados em queda)", 1: "NORMAL", 2: "FULL", 3: "EXTRA"}
    if int(sync) == 0:
        return _achado(GRAVE, "Durabilidade", f"synchronous=OFF, journal={modo}",
                       "Em produção isso não pode: uma queda de energia perde gravações.")
    return _achado(OK, "Durabilidade", f"journal={modo}, synchronous={nomes.get(int(sync), sync)}")


def permissoes(caminho):
    """Quem consegue ler o arquivo. Um 644 aqui é o banco inteiro aberto para qualquer
    usuário da máquina — e nele estão e-mail, telefone e valor de cada cliente."""
    if not os.path.exists(caminho):
        return _achado(GRAVE, "Arquivo do banco", f"não existe: {caminho}")
    modo = stat.S_IMODE(os.stat(caminho).st_mode)
    pasta = stat.S_IMODE(os.stat(os.path.dirname(caminho)).st_mode)
    tam = os.path.getsize(caminho) / 1024 / 1024
    if modo & 0o077:
        return _achado(GRAVE, "Permissões do arquivo",
                       f"{oct(modo)} — outros usuários da máquina conseguem ler ({tam:.1f} MB)",
                       f"chmod 600 {caminho}")
    if pasta & 0o077:
        return _achado(ATENCAO, "Permissões da pasta", f"pasta em {oct(pasta)}",
                       f"chmod 700 {os.path.dirname(caminho)}")
    return _achado(OK, "Permissões", f"arquivo {oct(modo)}, pasta {oct(pasta)}, {tam:.1f} MB")


def backup(caminho):
    """A pergunta que decide se um incêndio no datacenter é um susto ou o fim."""
    pasta = os.path.join(os.path.dirname(caminho), "backups")
    if not os.path.isdir(pasta):
        return _achado(GRAVE, "Backup", "não existe nenhum backup deste banco",
                       "Rode: python3 adminai/backup_banco.py --aplicar "
                       "(e instale o timer diário)")
    copias = sorted((f for f in os.listdir(pasta) if f.endswith((".sqlite", ".sqlite.gz"))),
                    key=lambda f: os.path.getmtime(os.path.join(pasta, f)), reverse=True)
    if not copias:
        return _achado(GRAVE, "Backup", f"a pasta {pasta} está vazia",
                       "Rode: python3 adminai/backup_banco.py --aplicar")
    ultima = os.path.join(pasta, copias[0])
    horas = (time.time() - os.path.getmtime(ultima)) / 3600
    tam = os.path.getsize(ultima) / 1024 / 1024
    if horas > 48:
        return _achado(GRAVE, "Backup", f"o mais recente tem {horas / 24:.1f} dia(s): {copias[0]}",
                       "O timer diário não está rodando. Veja: systemctl status urace-backup.timer")
    if horas > 26:
        return _achado(ATENCAO, "Backup", f"o mais recente tem {horas:.0f} h: {copias[0]}")
    return _achado(OK, "Backup", f"{len(copias)} cópia(s), a mais recente há {horas:.1f} h "
                                 f"({tam:.1f} MB)")


def auditoria_imutavel(con):
    """O log de auditoria só vale se ninguém puder reescrevê-lo — nem por engano."""
    gatilhos = {g["name"] for g in todos(
        con, "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='audit_logs'")}
    faltam = {"audit_logs_no_update", "audit_logs_no_delete"} - gatilhos
    if faltam:
        return _achado(GRAVE, "Auditoria imutável", f"faltam os gatilhos: {', '.join(sorted(faltam))}",
                       "Sem eles, um bug ou uma tela pode apagar o rastro.")
    n = um(con, "SELECT COUNT(*) n FROM audit_logs")["n"]
    return _achado(OK, "Auditoria imutável", f"gatilhos no lugar, {n} registro(s)")


def segredo_no_banco(con):
    """Segredo não mora em banco. Confere que senha e chave estão só como hash."""
    problemas = []
    for u in todos(con, "SELECT id, email, pw_hash, pw_salt FROM users LIMIT 200"):
        h, sal = u["pw_hash"] or "", u["pw_salt"] or ""
        # scrypt em base64 passa de 40; sal por usuário é o que impede uma tabela pronta
        # de quebrar todas as senhas de uma vez.
        if len(h) < 40 or not sal:
            problemas.append(f"usuário {u['id']}")
    sais = [u["pw_salt"] for u in todos(con, "SELECT pw_salt FROM users LIMIT 200")]
    if len(sais) > 1 and len(set(sais)) != len(sais):
        problemas.append("sal repetido entre usuários")
    for k in todos(con, "SELECT id, hash FROM api_keys LIMIT 200"):
        if not k["hash"] or len(k["hash"]) < 40:
            problemas.append(f"chave {k['id']}")
    if problemas:
        return _achado(GRAVE, "Senhas e chaves", "guardadas de forma fraca: " + ", ".join(problemas[:5]))
    return _achado(OK, "Senhas e chaves", "só hash (scrypt com sal por usuário); nada reversível")


def acessos(con):
    """Conta demais com poder demais é risco. Sessão vencida acumulada é sujeira."""
    admins = todos(con, "SELECT email FROM users WHERE role='ADMIN' AND active=1")
    velhas = um(con, "SELECT COUNT(*) n FROM sessions WHERE expires_at < strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                     "AND revoked_at IS NULL")["n"]
    inativos = um(con, "SELECT COUNT(*) n FROM users WHERE active=0")["n"]
    if not admins:
        return _achado(GRAVE, "Acessos", "nenhum ADMIN ativo — ninguém consegue administrar")
    estado = ATENCAO if len(admins) > 3 else OK
    detalhe = (f"{len(admins)} ADMIN ativo(s), {inativos} usuário(s) desligado(s), "
               f"{velhas} sessão(ões) vencida(s) sem limpeza")
    return _achado(estado, "Acessos", detalhe,
                   "ADMIN demais: cada um pode tudo, inclusive apagar." if estado == ATENCAO else None)


def dados_por_dominio(con):
    """O que existe de fato, por área. Tabela que devia ter dado e está vazia é sinal."""
    linhas = []
    existentes = {t["name"] for t in todos(con, "SELECT name FROM sqlite_master WHERE type='table'")}
    for dominio, tabelas in DOMINIOS.items():
        partes, faltando = [], []
        for t in tabelas:
            if t not in existentes:
                faltando.append(t)
                continue
            n = um(con, f"SELECT COUNT(*) n FROM {t}")["n"]
            partes.append(f"{t}={n}")
        linhas.append({"dominio": dominio, "contagem": partes, "faltando": faltando})
    return linhas


def rodar(con, caminho):
    return [integridade(con), chaves_estrangeiras(con), durabilidade(con),
            permissoes(caminho), backup(caminho), auditoria_imutavel(con),
            segredo_no_banco(con), acessos(con)]


def main():
    caminho = db_path()
    con = conectar()
    try:
        achados = rodar(con, caminho)
        dominios = dados_por_dominio(con)
    finally:
        con.close()

    print(f"AUDITORIA DO BANCO — {caminho}\n" + "=" * 72)
    graves = [a for a in achados if a["estado"] == GRAVE]
    atencao = [a for a in achados if a["estado"] == ATENCAO]
    for a in achados:
        marca = {OK: "  ok  ", ATENCAO: " ATEN ", GRAVE: " GRAVE"}[a["estado"]]
        print(f"[{marca}] {a['titulo']}: {a['detalhe']}")
        if a["acao"]:
            print(f"           -> {a['acao']}")

    print("\nO QUE EXISTE, POR ÁREA\n" + "-" * 72)
    for d in dominios:
        print(f"  {d['dominio']:<12} {' · '.join(d['contagem'])}")
        if d["faltando"]:
            print(f"               !! tabela ausente: {', '.join(d['faltando'])}")

    print("\n" + "=" * 72)
    if graves:
        print(f"{len(graves)} problema(s) GRAVE(s). Isto não está seguro ainda.")
        return 1
    if atencao:
        print(f"Sem nada grave. {len(atencao)} ponto(s) de atenção acima.")
        return 0
    print("Estrutura e segurança conferidas, sem achados.")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
