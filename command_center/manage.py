#!/usr/bin/env python3
"""Administração pela linha de comando.

    python3 -m command_center.manage create-admin      # primeiro usuário
    python3 -m command_center.manage set-password EMAIL
    python3 -m command_center.manage list-users
"""
import sys
from getpass import getpass

from command_center.api import auth
from command_center.db import aplicar_schema, conectar, todos, um


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
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
