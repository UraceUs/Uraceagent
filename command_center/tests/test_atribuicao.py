"""De quem é cada serviço — o caso real do card do David Pera (dono, 22/09).

Ele foi marcar uma sessão nova e encontrou 113 serviços no card, sendo 112 de
outras pessoas. O gabarito destes testes é a lista que ele mandou, com o nome do
cliente marcado por ele em cada formato de título do quadro.
"""
import os
import tempfile

import pytest

from command_center.db import aplicar_schema, conectar, inserir, todos, um
from command_center.providers import atribuicao, identidade


@pytest.fixture()
def con():
    antes = os.environ.get("CC_DB_PATH")
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="cc-atrib-"), "cc.sqlite")
    c = conectar(); aplicar_schema(c)
    try:
        yield c
    finally:
        c.close()
        if antes is None:
            os.environ.pop("CC_DB_PATH", None)
        else:
            os.environ["CC_DB_PATH"] = antes


def _cliente(con, nome, piloto=None, email=None):
    return inserir(con, "clients", source="asana", status="ACTIVE", name=nome,
                   pilot_name=piloto, email=email)


def _tarefa(con, titulo, client_id=None):
    return inserir(con, "tasks", title=titulo, project="U-RACE", section="Finished Services",
                   status="completed", client_id=client_id)


# --------------------------------------------- o nome, nos quatro formatos do quadro
@pytest.mark.parametrize("titulo,esperado", [
    ("David Pera_Urace Daily_Using Own Kart [1/1]", "David Pera"),      # underline
    ("David Pera Using his own Kart", "David Pera"),                    # só espaço
    ("Harley Keeble - Rotax [3/3]", "Harley Keeble"),                   # hífen com espaço
    ("Alexander Jacoby | KA100", "Alexander Jacoby"),                   # barra vertical
    ("Jude cook/Harley client - Kart proprio [3/3]", "Jude cook"),      # barra entre pessoas
    ("Brody Robbin_Professional Coach [His own kart] Bushnell", "Brody Robbin"),
    ("Alex Xikis KA100_Professional Coaching 4/4 {His own kart}", "Alex Xikis"),
    ("Branson KA100sr_Lead and Follow {Vanderlan} @OKC", "Branson"),
    ("Charlie M_Racing Program 3/6 [Junior KA100]", "Charlie M"),
    ("Liam B_Professional Coach [Junior_KA100]", "Liam B"),
    ("G.J_Lead and follow [Vanderlan 4|6] his kart", "G.J"),
    ("Callan Lead & Follow Vanderlan _Bushnell [5/8]", "Callan"),
    ("Branson_Motor dele", "Branson"),
    ("Savage_RWC RD2", "Savage"),
    ("Aaron_Prep[SKUSA RD2] X30", "Aaron"),
    ("Alexander Savage_Preatice [Urace Academy] x30", "Alexander Savage"),
    ("Grayson James_Trackside support single day (No coaching)- Lead and follow", "Grayson James"),
])
def test_tira_o_nome_do_titulo(titulo, esperado):
    assert identidade.pessoa_do_titulo(titulo) == esperado


@pytest.mark.parametrize("lixo", [
    "Lead and Follow", "Trackside Support", "Urace Daily", "Professional Coaching",
    "Karting School", "Arrive and Drive", "Prep", "Practice OKC", "Orlando Cup 8 e 9",
    "Date of Birth:", "Age: 13", "Height", "Summer Camp", "Shipping Orders",
    "2026 SKUSA Winter Series RD1/2 | Musselman Honda Circuit",
])
def test_nome_de_servico_e_de_corrida_nunca_e_gente(lixo):
    """A outra metade da queixa do dono: "tem cliente com nome de serviço"."""
    assert identidade.pessoa_do_titulo(lixo) is None


# --------------------------------------------- o que a varredura real de 22/09 achou
@pytest.mark.parametrize("titulo,esperado", [
    # inicial NO MEIO é normal: "Bella M Wagner" estava sendo jogada fora inteira
    ("Bella M Wagner - Professional Coach [Baby Kart] Bushnell", "Bella M Wagner"),
    # travessão colado com espaço depois separa; nome composto não tem espaço do outro lado
    ("Alex Savage– Old Chassis | Adjustments", "Alex Savage"),
    # data colada no título não é sobrenome
    ("Branson KA100 01/09", "Branson"),
    ("Branson 11/09_Cancelado", "Branson"),
    ("Martin 03/08 próprio motor Rok vlr", "Martin"),
    # nome grudado sem espaço
    ("MauricioPardomo_Coach", "Mauricio Pardomo"),
])
def test_formas_que_a_varredura_de_22_09_pegou(titulo, esperado):
    assert identidade.pessoa_do_titulo(titulo) == esperado


@pytest.mark.parametrize("lixo", [
    "Trackhouse", "Endurance", "Florida", "Closed", "Photos", "Goals", "To-Do",
    "Guardar", "Mycron", "Skapa", "AMR", "JFC", "RMC", "Bandeiras e banners",
    "Arrumar carrinho do desmontador de pneus da pista.",
])
def test_recado_de_quadro_e_pista_nao_viram_cliente(lixo):
    """A varredura real devolveu 27 "pessoas" de uma palavra só, e metade era isto."""
    assert identidade.pessoa_do_titulo(lixo) is None


@pytest.mark.parametrize("lixo", [
    "The North Florida Kart Club #10",              # artigo na frente: clube, não gente
    "Faturas a cobrar",                             # coluna do quadro, com palavra de ligação
    "Lucas Oil | Sebring, FL",                      # patrocinador de série, não o Lucas
    "Lucas Oil  Winter Series Race | Sebring International Raceway",
    "NOT GOING 2026 Star Champions Series -Night Fight | Trackhouse Motorplex",
    "Buscar as coisas no Mauricio",                 # tarefa que tinha virado cliente
])
def test_a_segunda_varredura_real_pegou_cinco_que_nao_sao_gente(lixo):
    """Cinco dos 32 cards que nasceriam na varredura de 22/09 (2ª rodada) não eram
    pessoa. Cada um virou regra: artigo nunca abre nome, palavra de ligação no meio
    denuncia frase, e há palavras que não cabem em nome nenhum ("oil", "club")."""
    assert identidade.pessoa_do_titulo(lixo) is None


@pytest.mark.parametrize("titulo,esperado", [
    ("Maria de Souza", "Maria de Souza"),           # partícula de nome NÃO é ligação
    ("Joao dos Santos", "Joao dos Santos"),
    ("Lucas_Professional Coach 4T Senior", "Lucas"),   # o Lucas continua existindo
    ("Shawn Scioto VLR 100", "Shawn Scioto"),
    ("Giovanni Barrera 2 Stroke Karting School", "Giovanni Barrera"),
    ("Reinaldo Andres Arroyo Son_Driving Experience[Junior_4 stroke]", "Reinaldo Andres Arroyo Son"),
])
def test_as_regras_novas_nao_comem_gente_de_verdade(titulo, esperado):
    assert identidade.pessoa_do_titulo(titulo) == esperado


def test_erro_de_digitacao_no_sobrenome_acha_a_pessoa(con):
    """"Savege" e "Brason" apareceram na varredura com 2 e 4 serviços, sem card. O
    parecido só era comparado com o PRIMEIRO nome; agora também com o último."""
    savage = _cliente(con, "Alexander Savage")
    branson = _cliente(con, "Tom Branson")
    con.commit()
    assert atribuicao.resolver(con, "Savege")[0]["id"] == savage
    assert atribuicao.resolver(con, "Brason")[0]["id"] == branson


def test_nome_de_verdade_com_palavra_de_servico_no_meio_nao_some():
    """A primeira palavra nunca é cortada: senão "Summer Camp" viraria a pessoa "Summer"."""
    assert identidade.pessoa_do_titulo("Jean-Luc Picard") == "Jean-Luc Picard"
    assert identidade.pessoa_do_titulo("Thiago Belluci Sr") == "Thiago Belluci Sr"   # Sr é do nome


# --------------------------------------------- achar o card certo
def test_apelido_e_inicial_caem_no_card_certo(con):
    charlie = _cliente(con, "Charlie Marron")
    liam = _cliente(con, "Liam Bourghol")
    con.commit()
    assert atribuicao.resolver(con, "Charlie M")[0]["id"] == charlie
    assert atribuicao.resolver(con, "Charlie")[0]["id"] == charlie
    assert atribuicao.resolver(con, "Liam B")[0]["id"] == liam
    assert atribuicao.resolver(con, "Bourghol")[0]["id"] == liam


def test_sobrenome_sozinho_e_erro_de_digitacao_acham_a_pessoa(con):
    savage = _cliente(con, "Alexander Savage")
    branson = _cliente(con, "Branson Lee")
    con.commit()
    assert atribuicao.resolver(con, "Savage")[0]["id"] == savage
    assert atribuicao.resolver(con, "Alex Savage")[0]["id"] == savage
    assert atribuicao.resolver(con, "Brason")[0]["id"] == branson, "1 letra trocada ainda é a pessoa"


def test_nome_ambiguo_nao_e_chutado(con):
    """Dois Alexander no quadro: Savage e Jacoby. "Alexander_Prep Orlando Cup" não
    tem dono óbvio — e a regra da casa é não unir no escuro."""
    _cliente(con, "Alexander Savage")
    _cliente(con, "Alexander Jacoby")
    con.commit()
    cliente, motivo = atribuicao.resolver(con, "Alexander")
    assert cliente is None and motivo.startswith("ambíguo entre")


def test_pilot_name_tambem_vale(con):
    """O card é do responsável; quem corre é o piloto. O título traz o piloto."""
    cid = _cliente(con, "Nicolas Pera", piloto="David Pera")
    con.commit()
    assert atribuicao.resolver(con, "David Pera")[0]["id"] == cid


# --------------------------------------------- a varredura que conserta o card
def _quadro_do_dono(con):
    """O card do David Pera como ele o encontrou: tudo dentro dele."""
    david = _cliente(con, "Nicolas Pera", piloto="David Pera", email="peranicolas2106@gmail.com")
    _cliente(con, "Charlie Marron")
    _cliente(con, "Alexander Savage")
    _cliente(con, "Brody Robbin")
    titulos = [
        "David Pera_Urace Daily_Using Own Kart [1/1]",
        "David Pera Using his own Kart",
        "Harley Keeble - Rotax [3/3]",
        "Alexander Jacoby | KA100",
        "Brody Robbin_Professional Coach [His own kart] Bushnell",
        "Charlie M_Racing Program 3/6 [Junior KA100]",
        "Charlie Marron_FWT (GP Junior 7 & VLR Junior)",
        "Alexander Savage_Preatice [Urace Academy] x30",
        "Savage_RWC RD2",
        "Mariano_Lead and Follow Van [1/4]",
        "Lead and Follow",                       # não é serviço de ninguém: é rótulo
    ]
    for t in titulos:
        _tarefa(con, t, client_id=david)
    con.commit()
    return david


def test_varredura_nao_escreve_nada(con):
    david = _quadro_do_dono(con)
    rel = atribuicao.redistribuir(con, aplicar=False)
    assert rel["aplicado"] is False
    assert len(rel["movidos"]) >= 7
    assert all(t["client_id"] == david for t in todos(con, "SELECT client_id FROM tasks")), \
        "varredura é só leitura"


def test_distribui_cada_servico_no_card_de_quem_e(con):
    david = _quadro_do_dono(con)
    atribuicao.redistribuir(con, aplicar=True)

    def dono_de(titulo):
        t = um(con, "SELECT client_id FROM tasks WHERE title=?", (titulo,))
        c = um(con, "SELECT * FROM clients WHERE id=?", (t["client_id"],)) if t["client_id"] else None
        return (c["pilot_name"] or c["name"]) if c else None

    assert dono_de("David Pera Using his own Kart") == "David Pera"
    assert dono_de("David Pera_Urace Daily_Using Own Kart [1/1]") == "David Pera"
    assert dono_de("Charlie M_Racing Program 3/6 [Junior KA100]") == "Charlie Marron"
    assert dono_de("Charlie Marron_FWT (GP Junior 7 & VLR Junior)") == "Charlie Marron"
    assert dono_de("Brody Robbin_Professional Coach [His own kart] Bushnell") == "Brody Robbin"
    assert dono_de("Savage_RWC RD2") == "Alexander Savage"
    assert dono_de("Alexander Savage_Preatice [Urace Academy] x30") == "Alexander Savage"
    assert dono_de("Harley Keeble - Rotax [3/3]") == "Harley Keeble", "card novo pelo nome completo"
    assert dono_de("Alexander Jacoby | KA100") == "Alexander Jacoby"
    # só o que é dele sobrou no card do David
    restam = todos(con, "SELECT title FROM tasks WHERE client_id=?", (david,))
    assert dono_de("Mariano_Lead and Follow Van [1/4]") == "Mariano", "card próprio, com o nome do título"
    assert sorted(t["title"] for t in restam) == sorted([
        "David Pera_Urace Daily_Using Own Kart [1/1]",
        "David Pera Using his own Kart",
        "Lead and Follow",                        # rótulo, não é serviço de ninguém
    ])


def test_na_duvida_abre_card_proprio_com_o_nome_do_titulo(con):
    """Dono, 22/09: "nunca colocar serviço de outro cliente em card de outro cliente".

    "Mariano" não tem card; antes ficava esperando decisão e o serviço continuava no
    card errado. Agora abre o card dele, com o nome exatamente como está no título."""
    _quadro_do_dono(con)
    rel = atribuicao.redistribuir(con, aplicar=True)
    assert any(x["nome"] == "Mariano" for x in rel["criados"])
    novo = um(con, "SELECT * FROM clients WHERE name='Mariano'")
    assert novo and "una pelo painel" in (novo["notes"] or "")


def test_nome_ambiguo_nunca_cai_no_card_de_outro(con):
    """A regra que manda em tudo. Havendo dois Mike, o serviço do "Mike_…" não entra
    em nenhum dos dois — ele ganha o card "Mike". O dono decidiu assim em 22/09:
    "crie o mike, mike fattuta e o davies separados"."""
    fattuta = _cliente(con, "Mike Fattuta")
    davies = _cliente(con, "Mike Davies")
    _tarefa(con, "Mike_Prep for Orlando Cup (3PM)")
    con.commit()
    atribuicao.redistribuir(con, aplicar=True)
    t = um(con, "SELECT client_id FROM tasks WHERE title LIKE 'Mike_Prep%'")
    assert t["client_id"] not in (fattuta, davies), "serviço em dúvida não encosta em card de ninguém"
    assert um(con, "SELECT * FROM clients WHERE id=?", (t["client_id"],))["name"] == "Mike"


def test_o_card_novo_ambiguo_sai_na_lista_para_unir(con):
    """Card próprio não é o fim: a varredura diz quais parecem a mesma pessoa."""
    _cliente(con, "Charlie Marron")
    _cliente(con, "Charlie Marrom")                 # o duplicado que existe no cadastro real
    _tarefa(con, "Charlie_Orlando Cup 8 e 9")
    con.commit()
    rel = atribuicao.redistribuir(con, aplicar=True)
    x = next(u for u in rel["unir"] if u["nome"] == "Charlie")
    assert {p["nome"] for p in x["parecidos"]} == {"Charlie Marron", "Charlie Marrom"}


def test_parecem_a_mesma_pessoa_pega_os_duplicados_reais(con):
    """Os três pares que a varredura de 22/09 achou no cadastro do dono."""
    for a, b in (("Charlie Marron", "Charlie Marrom"),
                 ("Liam Burghol", "Liam Bourgnhol"),
                 ("Alexander Savage", "Alex savage")):
        assert atribuicao.parecem_a_mesma_pessoa({"name": a, "pilot_name": None},
                                                 {"name": b, "pilot_name": None}), f"{a} × {b}"
    assert not atribuicao.parecem_a_mesma_pessoa({"name": "Mike Fattuta", "pilot_name": None},
                                                 {"name": "Mike Davies", "pilot_name": None})


def test_parte_exata_do_nome_ganha_de_parecido_por_uma_letra(con):
    """"Martin" tem 26 serviços e ficava ambíguo entre Martin Jaramillo, Bruno Martins
    e Ethan Martins. Nome igual ganha de nome parecido."""
    martin = _cliente(con, "Martin Jaramillo")
    _cliente(con, "Bruno Martins")
    _cliente(con, "Ethan Martins")
    con.commit()
    assert atribuicao.resolver(con, "Martin")[0]["id"] == martin


def test_titulo_sem_gente_fica_onde_esta_e_e_reportado(con):
    david = _quadro_do_dono(con)
    rel = atribuicao.redistribuir(con, aplicar=True)
    assert any(x["title"] == "Lead and Follow" for x in rel["sem_nome"])
    assert um(con, "SELECT client_id FROM tasks WHERE title='Lead and Follow'")["client_id"] == david


def test_rodar_duas_vezes_nao_muda_nada_na_segunda(con):
    _quadro_do_dono(con)
    atribuicao.redistribuir(con, aplicar=True)
    de_novo = atribuicao.redistribuir(con, aplicar=True)
    assert de_novo["movidos"] == [] and de_novo["criados"] == []


def test_nome_completo_ganha_o_card_antes_do_apelido(con):
    """Ordem importa: se "Charlie M" resolvesse primeiro e abrisse card, "Charlie
    Marron" viraria um segundo card da mesma criança."""
    david = _cliente(con, "David Pera")
    _tarefa(con, "Charlie M_Racing Program 3/6 [Junior KA100]", david)
    _tarefa(con, "Charlie Marron_FWT (GP Junior 7 & VLR Junior)", david)
    con.commit()
    atribuicao.redistribuir(con, aplicar=True)
    charlies = todos(con, "SELECT id FROM clients WHERE name LIKE 'Charlie%'")
    assert len(charlies) == 1, "um card só para o Charlie"
    assert len(todos(con, "SELECT id FROM tasks WHERE client_id=?", (charlies[0]["id"],))) == 2


# --------------------------------------------- pela API do painel
SENHA = "senha-forte-123"


@pytest.fixture()
def cli():
    """Banco e cliente HTTP só deste teste. O quadro é compartilhado entre os testes
    de rotas, e quem afirma "Charlie M cai no Charlie Marron" não pode depender de
    quais clientes outro teste deixou no banco."""
    import tempfile as _t

    from fastapi.testclient import TestClient

    from command_center.api import auth
    from command_center.api.main import app
    antes = os.environ.get("CC_DB_PATH")
    os.environ["CC_DB_PATH"] = os.path.join(_t.mkdtemp(prefix="cc-atrib-api-"), "cc.sqlite")
    c = conectar(); aplicar_schema(c)
    auth.criar_usuario(c, "admin@urace.us", "Admin", "ADMIN", SENHA)
    auth.criar_usuario(c, "viewer@urace.us", "Viewer", "VIEWER", SENHA)
    david = _cliente(c, "Nicolas Pera", piloto="David Pera")
    _cliente(c, "Charlie Marron")
    for t in ("David Pera Using his own Kart",
              "Charlie M_Racing Program 3/6 [Junior KA100]",
              "Brody Robbin_Professional Coach [His own kart] Bushnell"):
        _tarefa(c, t, client_id=david)
    c.commit(); c.close()
    with TestClient(app) as tc:
        yield tc
    if antes is None:
        os.environ.pop("CC_DB_PATH", None)
    else:
        os.environ["CC_DB_PATH"] = antes


def _entra(cli, email):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def test_varredura_pela_api_nao_escreve_nada(cli):
    _entra(cli, "viewer@urace.us")
    assert cli.get("/ops/api/service-attribution").status_code == 403, "varredura é de MANAGER para cima"
    _entra(cli, "admin@urace.us")
    rel = cli.get("/ops/api/service-attribution").json()
    assert rel["aplicado"] is False
    alvos = {m["title"]: m["para_nome"] for m in rel["movidos"]}
    assert alvos["Charlie M_Racing Program 3/6 [Junior KA100]"] == "Charlie Marron"
    assert alvos["Brody Robbin_Professional Coach [His own kart] Bushnell"] == "Brody Robbin (card novo)"
    assert "David Pera Using his own Kart" not in alvos, "o que já é dele não se move"
    con = conectar()
    try:
        donos = {t["client_id"] for t in todos(con, "SELECT client_id FROM tasks")}
        assert len(donos) == 1, "GET não moveu nada"
    finally:
        con.close()


def test_aplicar_pela_api_move_e_fica_auditado(cli):
    h = _entra(cli, "admin@urace.us")
    assert cli.post("/ops/api/service-attribution").status_code in (401, 403), "sem CSRF não escreve"
    r = cli.post("/ops/api/service-attribution", headers=h)
    assert r.status_code == 200 and r.json()["aplicado"] is True
    con = conectar()
    try:
        def dono(titulo):
            t = um(con, "SELECT client_id FROM tasks WHERE title=?", (titulo,))
            c = um(con, "SELECT * FROM clients WHERE id=?", (t["client_id"],))
            return c["pilot_name"] or c["name"]
        assert dono("Charlie M_Racing Program 3/6 [Junior KA100]") == "Charlie Marron"
        assert dono("Brody Robbin_Professional Coach [His own kart] Bushnell") == "Brody Robbin"
        assert dono("David Pera Using his own Kart") == "David Pera"
        assert um(con, "SELECT 1 FROM audit_logs WHERE event='clients.service_attribution'"), \
            "movimento em massa é auditado"
    finally:
        con.close()


def test_operator_nao_aplica(cli):
    from command_center.api import auth
    con = conectar()
    try:
        auth.criar_usuario(con, "op@urace.us", "Op", "OPERATOR", SENHA); con.commit()
    finally:
        con.close()
    h = _entra(cli, "op@urace.us")
    assert cli.post("/ops/api/service-attribution", headers=h).status_code == 403
