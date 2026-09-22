#!/usr/bin/env python3
"""Waiver em aberto: quem abriu e não assinou, e se já houve serviço mesmo assim.

    python3 adminai/waivers_em_aberto.py
    python3 adminai/waivers_em_aberto.py --dias 60

`delivered` quer dizer que a pessoa ABRIU e NÃO assinou — não é "quase assinado".
Waiver aberta só importa por uma razão: serviço acontecendo sem waiver assinada. Então
não basta listar; o que vale é cruzar com os serviços do cliente:

  JÁ RODOU SEM WAIVER  serviço concluído depois do envio e nada assinado. O risco já
                       correu — é o que o dono precisa ver primeiro.
  VAI RODAR SEM WAIVER  serviço marcado para frente. Dá tempo de cobrar.
  só esquecida          nenhum serviço de um lado nem do outro.

Só lê. Não envia lembrete, não cobra ninguém, não apaga nada.
"""
import argparse
import datetime as dt
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from adminai._venv import garantir_venv  # noqa: E402

garantir_venv()

from command_center.db import aplicar_schema, conectar, todos, um  # noqa: E402

ABERTAS = ("sent", "delivered")


def _dias(iso):
    if not iso:
        return None
    try:
        d = dt.datetime.fromisoformat(str(iso)[:19].replace("Z", ""))
    except ValueError:
        return None
    return (dt.datetime.utcnow() - d).days


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dias", type=int, default=400, help="olhar waivers enviadas nos últimos N dias")
    a = ap.parse_args()

    con = conectar()
    aplicar_schema(con)
    hoje = dt.date.today().isoformat()
    try:
        marcas = ",".join("?" * len(ABERTAS))
        abertas = todos(con, f"SELECT * FROM waivers WHERE status IN ({marcas}) "
                             "AND COALESCE(hidden,0)=0 ORDER BY sent_at", ABERTAS)
        print(f"\n{len(abertas)} waiver(s) em aberto\n" + "=" * 78)
        grupos = {"JÁ RODOU SEM WAIVER": [], "VAI RODAR SEM WAIVER": [], "só esquecida": []}
        for w in abertas:
            idade = _dias(w["sent_at"])
            cid = w["client_id"]
            passado = futuro = 0
            cliente = None
            if cid:
                cliente = um(con, "SELECT name, pilot_name FROM clients WHERE id=?", (cid,))
                passado = um(con, "SELECT COUNT(*) n FROM tasks WHERE client_id=? AND status='completed' "
                                  "AND due_on IS NOT NULL AND due_on >= ? AND due_on <= ?",
                             (cid, (w["sent_at"] or "")[:10], hoje))["n"]
                futuro = um(con, "SELECT COUNT(*) n FROM tasks WHERE client_id=? AND status='open' "
                                 "AND due_on >= ?", (cid, hoje))["n"]
            onde = "JÁ RODOU SEM WAIVER" if passado else "VAI RODAR SEM WAIVER" if futuro else "só esquecida"
            grupos[onde].append((w, cliente, idade, passado, futuro))

        for titulo, linhas in grupos.items():
            if not linhas:
                continue
            print(f"\n--- {titulo} ({len(linhas)}) ---")
            for w, c, idade, passado, futuro in sorted(linhas, key=lambda x: -(x[2] or 0)):
                quem = (c["pilot_name"] or c["name"]) if c else "(sem card)"
                print(f"  #{w['id']:<5} {w['status']:<10} {str(w['signer_name'] or '-')[:26]:<26} "
                      f"{str(w['signer_email'] or '-')[:32]:<32} {idade if idade is not None else '?'} dias")
                print(f"         cliente: {quem}  ·  serviços já feitos desde o envio: {passado}"
                      f"  ·  marcados à frente: {futuro}")
        print("\n(só leitura — nada foi enviado nem alterado)")
    finally:
        con.close()


if __name__ == "__main__":
    main()
