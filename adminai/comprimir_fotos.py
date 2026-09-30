#!/usr/bin/env python3
"""Comprime as fotos que já estão salvas (issue #21): peças do estoque, grupos da equipe e
chassis/motores da garagem.

Sem `--aplicar` só mostra quanto cada foto encolheria. Com `--aplicar` grava a versão
.webp AO LADO da original e aponta o banco para ela. **Não apaga a original** — depois de
conferir no painel, quem quiser remove à mão.

    python3 adminai/comprimir_fotos.py            # só mostra
    python3 adminai/comprimir_fotos.py --aplicar  # grava .webp e aponta o banco
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adminai._venv import garantir_venv  # noqa: E402

garantir_venv()

from command_center.db import conectar, todos  # noqa: E402
from command_center.providers import imagem  # noqa: E402

URACE = os.environ.get("URACE_DIR", os.path.expanduser("~/.urace"))


def alvos(con):
    """(tabela, id, caminho absoluto, valor a gravar no banco, lado máximo)."""
    for r in todos(con, "SELECT id, image_path FROM stock_items WHERE image_path IS NOT NULL"):
        pasta = os.path.join(URACE, "estoque")
        yield "stock_items", r["id"], os.path.join(pasta, os.path.basename(r["image_path"])), "nome", 1600
    for r in todos(con, "SELECT id, image_path FROM team_channels WHERE image_path IS NOT NULL"):
        yield "team_channels", r["id"], os.path.join(URACE, "equipe", os.path.basename(r["image_path"])), "nome", 512
    for tabela in ("catalog_chassis", "catalog_engines"):
        try:
            linhas = todos(con, f"SELECT id, image_path FROM {tabela} WHERE image_path IS NOT NULL")
        except Exception:
            continue
        for r in linhas:
            yield tabela, r["id"], r["image_path"], "caminho", 1600


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aplicar", action="store_true", help="grava as .webp e aponta o banco (sem apagar as originais)")
    a = ap.parse_args()
    con = conectar()
    antes = depois = n = 0
    for tabela, rid, caminho, modo, lado in alvos(con):
        if not os.path.isfile(caminho) or caminho.endswith(".webp"):
            continue
        with open(caminho, "rb") as f:
            original = f.read()
        try:
            novo, ext = imagem.comprimir(original, lado_max=lado)
        except imagem.ImagemInvalida:
            print(f"  ! {tabela} #{rid}: {os.path.basename(caminho)} não abre como imagem — ficou como está")
            continue
        n += 1; antes += len(original); depois += len(novo)
        print(f"  {tabela} #{rid}: {len(original) / 1024:.0f} KB → {len(novo) / 1024:.0f} KB")
        if a.aplicar:
            destino = os.path.splitext(caminho)[0] + ext
            with open(destino, "wb") as f:
                f.write(novo)
            valor = os.path.basename(destino) if modo == "nome" else destino
            con.execute(f"UPDATE {tabela} SET image_path=? WHERE id=?", (valor, rid))
            con.commit()
    if not n:
        print("Nenhuma foto para comprimir.")
        return 0
    print(f"\n{n} foto(s): {antes / 1024 / 1024:.1f} MB → {depois / 1024 / 1024:.1f} MB"
          + ("" if a.aplicar else "   (nada gravado: rode com --aplicar)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
