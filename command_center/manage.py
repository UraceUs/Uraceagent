#!/usr/bin/env python3
"""Administração pela linha de comando.

    python3 -m command_center.manage create-admin      # primeiro usuário
    python3 -m command_center.manage set-password EMAIL
    python3 -m command_center.manage list-users
    python3 -m command_center.manage conferir-chat [DIAS]   # o que não foi e o que não chegou
"""
import sys
from getpass import getpass

from command_center.api import auth
from command_center.db import aplicar_schema, conectar, todos, um


def _conferir_chat(con, dias):
    """Lê a conversa de cada lead no Kommo e confronta com a do painel. Só leitura."""
    from command_center.providers import conferencia
    r = conferencia.conferir(con, dias=dias)
    print(f"Conferência do chat — desde {r['desde'][:16].replace('T', ' ')} (UTC), {len(r['leads'])} conversa(s)\n")
    for c in r["leads"]:
        l = c["lead"]
        nome = (l.get("name") or l["external_id"])[:34]
        if c["erro"]:
            print(f"⚠ {nome:<34} não deu para ler no Kommo: {c['erro']}"); continue
        if not (c["nao_chegou"] or c["nao_foi"] or c["pendentes"]):
            continue
        print(f"— {nome}  (lead {l['external_id']}{' · ' + l['source'] if l.get('source') else ''})")
        for m in c["nao_foi"]:
            print(f"    NÃO FOI     {str(m['at'])[:16].replace('T', ' ')}  {(m['text'] or '')[:60]}")
        for m in c["pendentes"]:
            print(f"    NA FILA     {str(m['at'])[:16].replace('T', ' ')}  {(m['text'] or '')[:60]}  [{m['status']}]")
        for k in c["nao_chegou"]:
            print(f"    NÃO CHEGOU  {str(k.get('em'))[:16].replace('T', ' ')}  {(k.get('texto') or '(o Kommo não deu o texto)')[:60]}")
        if l.get("link"):
            print(f"    no Kommo: {l['link']}")
        print()
    print(f"Total: {r['nao_foi']} não foi(ram) · {r['nao_chegou']} não chegou(aram) · "
          f"{r['pendentes']} ainda na fila · {r['erros']} conversa(s) que não deu para ler")
    print("Lembre: a API do Kommo não devolve o texto de toda mensagem de chat, e o que é anterior")
    print("à integração não vem pela API — por isso a conferência olha só a janela recente.")
    return 0


def main(argv):
    con = conectar()
    aplicar_schema(con)
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "create-admin":
        email = input("e-mail: ").strip().lower()
        name = input("nome: ").strip()
        while True:
            s1 = getpass(f"senha (mín. {auth.SENHA_MIN}, não aparece): ")
            if len(s1) < auth.SENHA_MIN:
                print(f"   curta demais: precisa de {auth.SENHA_MIN} ou mais. De novo."); continue
            if s1 != getpass("repita: "):
                print("   as duas não conferem. De novo."); continue
            break
        uid = auth.criar_usuario(con, email, name, "ADMIN", s1)
        print(f"✅ ADMIN criado: {email} (id {uid})")
    elif cmd == "set-password" and len(argv) > 2:
        u = um(con, "SELECT id FROM users WHERE email = ?", (argv[2].strip().lower(),))
        if not u:
            sys.exit("usuário não existe")
        while True:
            s1 = getpass(f"senha nova (mín. {auth.SENHA_MIN}): ")
            if len(s1) < auth.SENHA_MIN:
                print("   curta demais. De novo."); continue
            if s1 != getpass("repita: "):
                print("   as duas não conferem. De novo."); continue
            break
        auth.trocar_senha(con, u["id"], s1, u["id"])
        print("✅ senha trocada; sessões abertas foram derrubadas")
    elif cmd == "list-users":
        for r in todos(con, "SELECT id, email, name, role, active, last_login_at FROM users ORDER BY id"):
            print(f"{r['id']:>3}  {r['email']:<30} {r['role']:<9} {'ativo' if r['active'] else 'INATIVO':<8} {r['last_login_at'] or '—'}")
    elif cmd == "conferir-chat":
        return _conferir_chat(con, int(argv[2]) if len(argv) > 2 else 7)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
