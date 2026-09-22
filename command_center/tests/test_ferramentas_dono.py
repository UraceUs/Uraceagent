"""As ferramentas que aplicam decisão do dono. Cada teste veio de um defeito real.

Todos foram pegos pela extensão da VPS em 22/09, rodando a T-002 em modo plano. Ela
leu o plano antes de aplicar, viu que não batia com o que o dono aprovou, e parou.
"""
import os
import subprocess
import sys
import tempfile

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from command_center.db import aplicar_schema, conectar, inserir, todos, um  # noqa: E402


@pytest.fixture()
def quadro():
    """O #15 como está de verdade: 20 serviços do dono + coisa que não é dele."""
    antes = os.environ.get("CC_DB_PATH")
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="cc-ferr-"), "cc.sqlite")
    con = conectar(); aplicar_schema(con)
    c15 = inserir(con, "clients", name="Kenneth Savage", pilot_name="Alexander Savage",
                  status="ACTIVE", source="asana")
    for t in ("Savage_RWC RD2", "Savage_RWC", "Savege_RWC RD2",
              "Alexander Savage_Preatice [Urace Academy] x30",
              "Lucas Oil  Winter Series Race | Sebring International Raceway"):
        inserir(con, "tasks", client_id=c15, title=t, project="U-RACE")
    con.commit()
    try:
        yield con, c15
    finally:
        con.close()
        if antes is None:
            os.environ.pop("CC_DB_PATH", None)
        else:
            os.environ["CC_DB_PATH"] = antes


def _rodar(*args):
    return subprocess.run([sys.executable, os.path.join(RAIZ, "adminai", *args[:1]), *args[1:]],
                          capture_output=True, text=True, cwd=RAIZ)


def test_carimbo_exige_filtro(quadro):
    """Sem `--nome`, carimbar "tudo que está no card" carimba também o que está lá por
    engano. O dono aprovou 20 serviços; a ferramenta ia carimbar 70."""
    _con, c15 = quadro
    r = _rodar("confirmar_servicos.py", str(c15))
    assert r.returncode != 0 and "--nome" in (r.stdout + r.stderr)


def test_carimbo_so_pega_o_que_o_dono_aprovou(quadro):
    con, c15 = quadro
    r = _rodar("confirmar_servicos.py", str(c15), "--nome", "Savage", "--nome", "Savege", "--aplicar")
    assert r.returncode == 0, r.stderr
    carimbadas = [t["title"] for t in todos(con, "SELECT title FROM tasks WHERE client_by='human'")]
    assert sorted(carimbadas) == ["Savage_RWC", "Savage_RWC RD2", "Savege_RWC RD2"]
    livres = [t["title"] for t in todos(con, "SELECT title FROM tasks WHERE COALESCE(client_by,'')<>'human'")]
    assert any("Lucas Oil" in t for t in livres), "a corrida NÃO pode ser carimbada como serviço dele"
    assert any("Alexander Savage_" in t for t in livres), "nome completo resolve sozinho, não precisa carimbo"


def test_carimbo_mostra_o_que_ficou_de_fora(quadro):
    """O dono tem de ver o que a ferramenta NÃO vai tocar — senão o filtro esconde."""
    _con, c15 = quadro
    r = _rodar("confirmar_servicos.py", str(c15), "--nome", "Savage")
    assert "FORA do filtro" in r.stdout and "Lucas Oil" in r.stdout


def test_unir_acha_o_card_pelo_nome_do_piloto(quadro):
    """O card do Luciano está como "Alonso Delgado" (o pai), com "Luciano Delgado" no
    piloto. Procurar só pelo responsável não achava, e o script parava ali."""
    con, _c15 = quadro
    pai = inserir(con, "clients", name="Alonso Delgado", pilot_name="Luciano Delgado",
                  status="ACTIVE", source="asana", email="ad@x.com")
    inserir(con, "clients", name="Luciano", status="ACTIVE", source="asana")
    con.commit()
    r = _rodar("unir_cards.py", "--unir", "Luciano+Luciano Delgado=Luciano Delgado", "--aplicar")
    assert r.returncode == 0, r.stderr
    assert not um(con, "SELECT id FROM clients WHERE name='Luciano'")
    ficou = um(con, "SELECT name, pilot_name FROM clients WHERE id=?", (pai,))
    assert ficou["name"] == "Alonso Delgado", "o responsável não vira o nome do piloto"
    assert ficou["pilot_name"] == "Luciano Delgado"


def test_plano_nao_para_no_grupo_que_falha(quadro):
    """A união do Luciano quebrou e as outras 4 nem chegaram a ser planejadas — o dono
    ficou sem ver o plano inteiro."""
    con, _c15 = quadro
    inserir(con, "clients", name="Martin Jaramillo", status="ACTIVE", source="asana", email="mj@x.com")
    inserir(con, "clients", name="Martin", status="ACTIVE", source="asana")
    con.commit()
    r = _rodar("unir_cards.py", "--unir", "Fantasma+Outro=X",
               "--unir", "Martin+Martin Jaramillo=Martin Jaramillo")
    assert "NÃO DÁ PARA PLANEJAR" in r.stdout
    assert "Martin Jaramillo + Martin" in r.stdout, "o grupo bom tem de aparecer mesmo assim"
    assert um(con, "SELECT id FROM clients WHERE name='Martin'"), "plano não escreve nada"


def test_aplicar_ainda_para_no_primeiro_erro(quadro):
    """No plano, seguir em frente ajuda. No --aplicar, não: meio grupo unido é pior."""
    con, _c15 = quadro
    inserir(con, "clients", name="Martin Jaramillo", status="ACTIVE", source="asana", email="mj@x.com")
    inserir(con, "clients", name="Martin", status="ACTIVE", source="asana")
    con.commit()
    r = _rodar("unir_cards.py", "--unir", "Martin+Martin Jaramillo=Martin Jaramillo",
               "--unir", "Fantasma+Outro=X", "--aplicar")
    assert r.returncode != 0
    assert um(con, "SELECT id FROM clients WHERE name='Martin'"), "nada foi unido"
