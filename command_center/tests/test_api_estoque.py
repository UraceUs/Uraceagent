"""A API do estoque — e sobretudo o botão "Adicionar" do mecânico.

Dono, 23/09: *"o acesso de mecânico consiga, ao clicar em estoque, ter um botão de
adicionar; aí ele consegue colocar foto, descrição, nome e quantidade do item que
temos"*. Eu tinha posto o cadastro em MANAGER por conta própria; estava errado. Quem
está na prateleira é quem sabe o que há nela.
"""
import io
import os
import tempfile

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir, um  # noqa: E402

B = "/ops/api/estoque"
SENHA = "senha-forte-123"


@pytest.fixture(scope="module")
def cli():
    pasta = tempfile.mkdtemp()
    os.environ["CC_DB_PATH"] = os.path.join(pasta, "cc.sqlite")
    os.environ["URACE_DIR"] = pasta          # as fotos vão para cá, não para ~/.urace
    con = conectar(); aplicar_schema(con)
    auth.criar_usuario(con, "mec@urace.us", "Mecânico", "OPERATOR", SENHA)
    auth.criar_usuario(con, "ger@urace.us", "Gerente", "MANAGER", SENHA)
    auth.criar_usuario(con, "olho@urace.us", "Visitante", "VIEWER", SENHA)
    inserir(con, "clients", name="Hank Lai", status="ACTIVE", source="manual")
    con.commit(); con.close()
    with TestClient(app, base_url="https://cc.test") as c:
        yield c


def entra(cli, email):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def _png():
    """PNG 1x1 de verdade — o endpoint olha o content-type, mas o arquivo tem de existir."""
    return (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
            b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
            b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")


# --------------------------------------------------- o botão do mecânico
def test_mecanico_cadastra_peca_com_nome_descricao_quantidade_e_foto(cli):
    h = entra(cli, "mec@urace.us")
    res = cli.post(f"{B}/item", headers=h,
                   data={"name": "Pastilha de freio Tonykart", "kind": "peca", "unit": "un",
                         "notes": "a que sai toda semana, prateleira A", "qty": "6"},
                   files={"foto": ("pastilha.png", _png(), "image/png")})
    assert res.status_code == 200, res.text
    corpo = res.json()
    assert corpo["aviso"] is None and corpo["contado"]["depois"] == 6
    iid = corpo["id"]
    ficha = cli.get(f"{B}/{iid}", headers=h).json()
    assert ficha["item"]["name"] == "Pastilha de freio Tonykart"
    assert ficha["item"]["notes"] == "a que sai toda semana, prateleira A"
    assert ficha["total"] == 6
    assert cli.get(f"{B}/item/{iid}/foto", headers=h).status_code == 200


def test_a_quantidade_do_cadastro_entra_como_contagem_nao_como_compra(cli):
    """Ele está dizendo "tem isto aqui agora". Chamar de entrada inventaria uma compra
    que não houve, e o razão contaria uma história falsa."""
    h = entra(cli, "mec@urace.us")
    iid = cli.post(f"{B}/item", headers=h,
                   data={"name": "Vela NGK", "qty": "12"}).json()["id"]
    ficha = cli.get(f"{B}/{iid}", headers=h).json()
    assert [m["kind"] for m in ficha["movimentos"]] == ["contagem"]
    assert ficha["movimentos"][0]["notes"] == "quantidade informada no cadastro"


def test_cadastrar_sem_quantidade_deixa_a_ficha_zerada_sem_movimento(cli):
    """Não saber quanto tem é um estado legítimo — e diferente de ter zero."""
    h = entra(cli, "mec@urace.us")
    iid = cli.post(f"{B}/item", headers=h, data={"name": "Corrente RK 219"}).json()["id"]
    ficha = cli.get(f"{B}/{iid}", headers=h).json()
    assert ficha["total"] == 0 and ficha["movimentos"] == []


def test_foto_ruim_nao_derruba_o_cadastro_da_peca(cli):
    """Perder o cadastro porque a imagem não subiu seria trocar o que importa pelo enfeite."""
    h = entra(cli, "mec@urace.us")
    res = cli.post(f"{B}/item", headers=h, data={"name": "Tie rod Parolin", "qty": "3"},
                   files={"foto": ("x.pdf", b"%PDF-1.4 nao sou imagem", "application/pdf")})
    assert res.status_code == 200
    assert "cadastrada" in res.json()["aviso"] and "PNG" in res.json()["aviso"]
    iid = res.json()["id"]
    assert cli.get(f"{B}/{iid}", headers=h).json()["total"] == 3, "a peça ficou, com o saldo"
    assert cli.get(f"{B}/item/{iid}/foto", headers=h).status_code == 404


def test_visitante_nao_cadastra_nada(cli):
    h = entra(cli, "olho@urace.us")
    assert cli.post(f"{B}/item", headers=h, data={"name": "Não devia entrar"}).status_code == 403


def test_peca_repetida_e_recusada_com_frase_de_gente(cli):
    h = entra(cli, "mec@urace.us")
    cli.post(f"{B}/item", headers=h, data={"name": "Pinhão Z11", "sku": "CKS-Z11"})
    res = cli.post(f"{B}/item", headers=h, data={"name": "Outro nome", "sku": "CKS-Z11"})
    assert res.status_code == 400 and "já é do item" in res.json()["detail"]


def test_trocar_a_foto_depois(cli):
    h = entra(cli, "mec@urace.us")
    iid = cli.post(f"{B}/item", headers=h, data={"name": "Bieleta"}).json()["id"]
    assert cli.get(f"{B}/item/{iid}/foto", headers=h).status_code == 404
    assert cli.post(f"{B}/item/{iid}/foto", headers=h,
                    files={"foto": ("b.png", _png(), "image/png")}).status_code == 200
    assert cli.get(f"{B}/item/{iid}/foto", headers=h).status_code == 200


# --------------------------------------------------- o resto da prateleira
def test_a_lista_separa_o_que_e_nosso_do_que_e_do_cliente(cli):
    h = entra(cli, "mec@urace.us")
    iid = cli.post(f"{B}/item", headers=h, data={"name": "Pneu MG do Hank", "kind": "pneu",
                                                 "unit": "jogo", "qty": "4"}).json()["id"]
    con = conectar()
    hank = um(con, "SELECT id FROM clients WHERE name='Hank Lai'")["id"]
    con.close()
    assert cli.post(f"{B}/entrada", headers=h,
                    json={"item_id": iid, "qty": 2, "client_id": hank}).status_code == 200
    linha = [x for x in cli.get(B, headers=h).json()["itens"] if x["id"] == iid][0]
    assert (linha["total"], linha["nosso"], linha["de_clientes"]) == (6, 4, 2)


def test_mecanico_conta_mas_nao_ajusta(cli):
    """Contagem errada aparece na conferência; ajuste sem dono vira estoque que não bate."""
    h = entra(cli, "mec@urace.us")
    iid = cli.post(f"{B}/item", headers=h, data={"name": "Rolamento 6202"}).json()["id"]
    assert cli.post(f"{B}/contar", headers=h, json={"item_id": iid, "qty": 9}).status_code == 200
    assert cli.post(f"{B}/ajustar", headers=h,
                    json={"item_id": iid, "qty": -1, "motivo": "quebra"}).status_code == 403
    h2 = entra(cli, "ger@urace.us")
    assert cli.post(f"{B}/ajustar", headers=h2,
                    json={"item_id": iid, "qty": -1, "motivo": "quebra"}).status_code == 200


def test_mecanico_nao_vende_peca(cli):
    h = entra(cli, "mec@urace.us")
    iid = cli.post(f"{B}/item", headers=h, data={"name": "Coroa 219", "qty": "5"}).json()["id"]
    res = cli.post(f"{B}/saida", headers=h, json={"item_id": iid, "qty": 1, "motivo": "venda"})
    assert res.status_code == 403 and "gerente" in res.json()["detail"]
    assert cli.post(f"{B}/saida", headers=h,
                    json={"item_id": iid, "qty": 1, "motivo": "uso em serviço"}).status_code == 200


def test_a_peca_do_cliente_nao_sai_para_outro_pela_api(cli):
    """A trava do provider chegando até a tela como frase de gente, em 400."""
    h = entra(cli, "ger@urace.us")
    con = conectar()
    hank = um(con, "SELECT id FROM clients WHERE name='Hank Lai'")["id"]
    outro = inserir(con, "clients", name="Outro Cliente", status="ACTIVE", source="manual")
    con.commit(); con.close()
    iid = cli.post(f"{B}/item", headers=h, data={"name": "Escapamento do Hank"}).json()["id"]
    cli.post(f"{B}/entrada", headers=h, json={"item_id": iid, "qty": 1, "client_id": hank})
    res = cli.post(f"{B}/saida", headers=h, json={"item_id": iid, "qty": 1, "client_id": hank,
                                                  "para_cliente_id": outro, "motivo": "venda"})
    assert res.status_code == 400 and "outro cliente" in res.json()["detail"]


def test_saldo_insuficiente_erra_em_400_e_nao_em_500(cli):
    h = entra(cli, "mec@urace.us")
    iid = cli.post(f"{B}/item", headers=h, data={"name": "Mangueira", "qty": "2"}).json()["id"]
    res = cli.post(f"{B}/saida", headers=h, json={"item_id": iid, "qty": 5})
    assert res.status_code == 400 and "tem 2" in res.json()["detail"]


def test_a_ficha_conta_a_historia_do_saldo(cli):
    h = entra(cli, "mec@urace.us")
    iid = cli.post(f"{B}/item", headers=h, data={"name": "Filtro de ar", "qty": "10"}).json()["id"]
    cli.post(f"{B}/transferir", headers=h, json={"item_id": iid, "qty": 3, "para": "trailer"})
    cli.post(f"{B}/saida", headers=h, json={"item_id": iid, "qty": 1})
    ficha = cli.get(f"{B}/{iid}", headers=h).json()
    assert [m["kind"] for m in ficha["movimentos"]] == ["saida", "transferencia", "contagem"]
    assert ficha["total"] == 9
    assert {s["local"] for s in ficha["saldos"]} == {"Sede", "Trailer de corrida"}


def test_cadastro_fica_na_auditoria(cli):
    h = entra(cli, "mec@urace.us")
    iid = cli.post(f"{B}/item", headers=h, data={"name": "Peça auditada", "qty": "1"}).json()["id"]
    con = conectar()
    linha = um(con, "SELECT * FROM audit_logs WHERE event='stock.item.create' AND entity_id=?",
               (str(iid),))
    con.close()
    assert linha and linha["actor"].startswith("user:")
