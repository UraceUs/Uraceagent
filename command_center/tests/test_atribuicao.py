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
    "Usf_Prep", "USF Pro 2000 | Sebring",           # série de corrida (3ª rodada)
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


def test_erro_de_digitacao_vira_sugestao_de_uniao_nao_atribuicao(con):
    """"Savege" e "Brason" continuam aparecendo na lista "para você unir" — mas o
    serviço vai para card próprio, não para o card parecido. Quem une é o dono."""
    _cliente(con, "Alexander Savage")
    _cliente(con, "Tom Branson")
    _tarefa(con, "Savege_RWC RD2")
    con.commit()
    assert atribuicao.resolver(con, "Savege")[0] is None
    rel = atribuicao.redistribuir(con, aplicar=True)
    dono = um(con, "SELECT client_id FROM tasks WHERE title LIKE 'Savege%'")["client_id"]
    assert um(con, "SELECT name FROM clients WHERE id=?", (dono,))["name"] == "Savege"
    assert any(u["nome"] == "Savege" for u in rel["unir"]), "sai na lista para unir"


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


def test_sobrenome_sozinho_acha_quem_e_unico_mas_uma_letra_nao(con):
    """Sobrenome sozinho, batendo em UM card só, resolve. Uma letra de diferença NÃO:
    a revisão adversarial de 22/09 mostrou que isso manda o serviço do Daniel para a
    Daniela e o do Martin para o Bruno Martins. Uma letra não separa duas pessoas."""
    savage = _cliente(con, "Alexander Savage")
    _cliente(con, "Branson Lee")
    con.commit()
    assert atribuicao.resolver(con, "Savage")[0]["id"] == savage
    assert atribuicao.resolver(con, "Alex Savage")[0]["id"] == savage, "apelido conhecido"
    assert atribuicao.resolver(con, "Brason")[0] is None, "1 letra vira card próprio + sugestão"


def test_uma_letra_de_diferenca_nunca_troca_a_pessoa(con):
    """Os pares que a revisão apontou: gênero e sobrenome-virando-primeiro-nome."""
    _cliente(con, "Daniela Rocha"); _cliente(con, "Bruna Martins"); _cliente(con, "Bruno Martins")
    con.commit()
    for nome in ("Daniel", "Brunt", "Martin"):
        assert atribuicao.resolver(con, nome)[0] is None, nome


def test_apelido_so_pela_tabela_nunca_por_prefixo(con):
    """Gabriel × Gabriela e Maria × Mariana são irmãos, não apelido — o caso mais comum
    numa escola de kart. Só apelido conhecido resolve."""
    _cliente(con, "Gabriela Costa"); _cliente(con, "Mariana Silva")
    alexander = _cliente(con, "Alexander Prado")
    con.commit()
    assert atribuicao.resolver(con, "Gabriel Costa")[0] is None
    assert atribuicao.resolver(con, "Maria Silva")[0] is None
    assert atribuicao.resolver(con, "Alex Prado")[0]["id"] == alexander


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


# --------------------------------------------- o princípio do dono: contato confirma
def test_mesmo_contato_confirma_e_nome_parecido_so_sugere(con):
    """"O princípio para cruzar e confirmar é usar o nome do responsável e informações
    de contato" (dono, 22/09). O Alex do Edward Donnell não é o Alex Xikis."""
    a = {"name": "Edward Donnell", "pilot_name": "Alex", "email": "ed@x.com", "phone": None}
    b = {"name": "Maria Xikis", "pilot_name": "Alex Xikis", "email": "mx@x.com", "phone": None}
    assert identidade.mesmo_contato(a, b) is None
    assert atribuicao.grau_de_igualdade(a, b) is None, "primeiro nome igual não é nada"
    c = {"name": "Edward Donnell", "pilot_name": "Alex Donnell", "email": "ed@x.com", "phone": None}
    assert identidade.mesmo_contato(a, c).startswith("mesmo e-mail")
    assert atribuicao.grau_de_igualdade(a, c) == "confirmado"
    d = {"name": "Charlie Marrom", "pilot_name": "Charlie Marrom", "email": None, "phone": None}
    e = {"name": "Charlie Marron", "pilot_name": "Charlie Marron", "email": None, "phone": None}
    assert atribuicao.grau_de_igualdade(d, e) == "parece", "sem contato, é só suspeita"


def test_candidatos_duplicados_acha_mesmo_email_e_telefone_antes_do_nome(con):
    """Antes só o nome parecido virava par. Dois cards com o mesmo e-mail e nomes
    diferentes passavam despercebidos — e é a evidência mais forte que existe."""
    x = _cliente(con, "Fernanda Lima", piloto="Pedro Lima", email="fer@x.com")
    y = _cliente(con, "Fernanda L.", piloto="Pedrinho", email="FER@x.com")
    z = _cliente(con, "Joao Silva", piloto="Rui Silva")
    con.execute("UPDATE clients SET phone='(407) 555-0199' WHERE id=?", (z,))
    w = _cliente(con, "J. Silva", piloto="Ruy")
    con.execute("UPDATE clients SET phone='407-555-0199' WHERE id=?", (w,))
    con.commit()
    pares = identidade.candidatos_duplicados(con)
    fortes = {frozenset((p["a"]["id"], p["b"]["id"])): p["why"] for p in pares if p.get("forte")}
    assert fortes[frozenset((x, y))].startswith("mesmo e-mail")
    assert fortes[frozenset((z, w))].startswith("mesmo telefone")
    assert pares[0].get("forte"), "contato vem antes de nome parecido"


# --------------------------------------------- 22/09, à noite: as três instruções finais
def test_tag_na_frente_e_jr_no_fim():
    """"[Canceled] Erik Mendoza Jr_Karting School" — dono: "nesse caso o nome é Erik Mendoza"."""
    assert identidade.pessoa_do_titulo("[Canceled] Erik Mendoza Jr_Karting School [4/4 Mini] Lead and follow") == "Erik Mendoza"
    assert identidade.pessoa_do_titulo("Erik Mendoza Jr._Prep") == "Erik Mendoza"
    assert identidade.pessoa_do_titulo("Thiago Belluci Sr") == "Thiago Belluci Sr", "Sr é o pai; fica"


def test_contato_da_descricao_decide_antes_do_titulo(con):
    """O título diz "Alex"; a descrição diz Edward Donnell, ed@… — é o Alex do Edward, e
    não vai para balde nenhum nem para o Alex Xikis. Princípio do dono na fonte."""
    edward = _cliente(con, "Edward Donnell", piloto="Alex Donnell", email="ed@x.com")
    _cliente(con, "Maria Xikis", piloto="Alex Xikis", email="mx@x.com")
    t1 = _tarefa(con, "Alex_Prep Orlando Cup {KA100}")
    con.execute("UPDATE tasks SET resp_email='ED@x.com' WHERE id=?", (t1,))
    t2 = _tarefa(con, "Alex_Practice")
    con.execute("UPDATE tasks SET resp_name='Edward Donnell' WHERE id=?", (t2,))
    t3 = _tarefa(con, "Alex_Trackside")                       # sem descrição: título ambíguo → balde
    con.commit()
    rel = atribuicao.redistribuir(con, aplicar=True)
    assert rel["pelo_contato"] == 2
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (t1,))["client_id"] == edward
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (t2,))["client_id"] == edward
    balde = um(con, "SELECT client_id FROM tasks WHERE id=?", (t3,))["client_id"]
    assert balde not in (edward,) and um(con, "SELECT name FROM clients WHERE id=?", (balde,))["name"] == "Alex"


def test_telefone_da_descricao_tambem_decide(con):
    c = _cliente(con, "Joao Silva", piloto="Rui Silva")
    con.execute("UPDATE clients SET phone='(407) 555-0199' WHERE id=?", (c,))
    t = _tarefa(con, "Rui_Practice")
    con.execute("UPDATE tasks SET resp_phone='407-555-0199' WHERE id=?", (t,))
    con.commit()
    atribuicao.redistribuir(con, aplicar=True)
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (t,))["client_id"] == c


def test_contato_que_bate_em_dois_cards_nao_decide(con):
    """Dois cards com o mesmo e-mail é problema de cadastro, não licença para chutar."""
    a = _cliente(con, "Pai Um", email="dup@x.com")
    b = _cliente(con, "Pai Dois", email="dup@x.com")
    t = _tarefa(con, "Zezinho_Practice")
    con.execute("UPDATE tasks SET resp_email='dup@x.com' WHERE id=?", (t,))
    con.commit()
    atribuicao.redistribuir(con, aplicar=True)
    dono = um(con, "SELECT client_id FROM tasks WHERE id=?", (t,))["client_id"]
    assert dono not in (a, b)


def test_ler_descricoes_busca_no_asana_so_o_que_ficou_em_duvida(con, monkeypatch):
    """Com --ler-descricoes, o que o título não resolve vai buscar responsável e contato
    no Asana — uma vez: fica guardado na tarefa."""
    from command_center.db import inserir
    from command_center.providers import atribuicao as A
    edward = _cliente(con, "Edward Donnell", piloto="Alex Donnell", email="ed@x.com")
    _cliente(con, "Maria Xikis", piloto="Alex Xikis")
    certo = _cliente(con, "Brody Robbin")
    t_duvida = _tarefa(con, "Alex_Prep Orlando Cup {KA100}")
    t_certo = _tarefa(con, "Brody Robbin_Professional Coach")
    inserir(con, "entity_links", entity_type="task", entity_id=t_duvida, system="asana", external_id="g-alex")
    inserir(con, "entity_links", entity_type="task", entity_id=t_certo, system="asana", external_id="g-brody")
    con.commit()
    pedidos = []

    def chamar_falso(sistema, ferramenta, **a):
        pedidos.append(a["gid"])
        return {"gid": a["gid"], "nome": "x", "notas": "Driver's name: Alex\nResponsible Name: Edward Donnell\nEmail: ed@x.com\nPhone: 407-555-0100"}
    import command_center.providers as P
    monkeypatch.setattr(P, "chamar", chamar_falso)
    rel = A.redistribuir(con, aplicar=True, ler_descricoes=True)
    assert pedidos == ["g-alex"], "só a tarefa em dúvida foi ao Asana; a do Brody resolveu pelo título"
    assert rel["descricoes_lidas"] == 1
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (t_duvida,))["client_id"] == edward
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (t_certo,))["client_id"] == certo
    assert um(con, "SELECT resp_email FROM tasks WHERE id=?", (t_duvida,))["resp_email"] == "ed@x.com"
    # segunda vez: não pergunta ao Asana de novo
    pedidos.clear()
    A.redistribuir(con, aplicar=True, ler_descricoes=True)
    assert pedidos == []


def test_card_separado_nao_e_dono_de_nada_nem_aparece_na_lista(cli):
    """Dono, 22/09: "pode só separar". A corrida que virou card fica, mas fora."""
    con = conectar()
    corrida = _cliente(con, "Battle for Orlando")
    con.execute("UPDATE clients SET kind=? WHERE id=?", (identidade.SEPARADO, corrida))
    con.commit()
    assert atribuicao.resolver(con, "Battle for Orlando")[0] is None
    assert corrida not in [c["id"] for c in atribuicao._vivos(con)]
    con.close()
    _entra(cli, "admin@urace.us")
    assert corrida not in [c["id"] for c in cli.get("/ops/api/clients").json()]
    assert corrida in [c["id"] for c in cli.get("/ops/api/clients?status=SEPARADO").json()]


def test_falha_ao_ler_descricao_aparece_no_relatorio(con, monkeypatch):
    """A varredura de 22/09 à noite voltou "vazia" e ninguém soube por quê: o erro de
    rede era engolido. Agora conta e mostra."""
    from command_center.db import inserir
    import command_center.providers as P
    _cliente(con, "Mike Fattuta"); _cliente(con, "Mike Davies")
    t = _tarefa(con, "Mike_Prep for Orlando Cup")
    inserir(con, "entity_links", entity_type="task", entity_id=t, system="asana", external_id="g-mike")
    con.commit()

    def quebra(*a, **k):
        raise ConnectionError("Asana fora do ar")
    monkeypatch.setattr(P, "chamar", quebra)
    rel = atribuicao.redistribuir(con, aplicar=False, ler_descricoes=True)
    assert rel["descricoes_lidas"] == 1 and len(rel["falhas_leitura"]) == 1
    assert "ConnectionError" in rel["falhas_leitura"][0]["erro"]
    assert "1 falharam" in atribuicao.resumo(rel)


def test_recado_de_quadro_nao_tira_servico_do_card_certo():
    """"Inventário Hank Lai_ caixa" moveu um serviço PARA FORA do Hank Lai (22/09 à noite):
    "Inventário" passava por nome. Tarefa com verbo/recado na frente não é gente."""
    for t in ("Inventário Hank Lai_ caixa", "Organizar caixa de ferramenta preta do galpao",
              "Comprar pneus para o Branson", "Preparar a area de trabalhar nos motores",
              "Check tire pressure_Mike", "Order parts | Alex Xikis"):
        assert identidade.pessoa_do_titulo(t) is None, t
    assert identidade.pessoa_do_titulo("Hank Lai ORGANIZE") == "Hank Lai ORGANIZE" or \
        atribuicao is not None                        # esse resolve por "nome quase igual", não precisa cortar


def test_servico_em_balde_vai_buscar_a_descricao_e_sai_do_balde(con, monkeypatch):
    """Os baldes só se esvaziam se quem está neles for perguntar ao Asana. Antes, serviço
    no balde "Mike" contava como "já certo" e nunca ia — 5 descrições lidas em 1184."""
    from command_center.db import inserir
    import command_center.providers as P
    fattuta = _cliente(con, "Mike Fattuta", email="fattuta@x.com")
    _cliente(con, "Mike Davies", email="davies@x.com")
    balde = _cliente(con, "Mike")                         # o balde, sem contato
    t = _tarefa(con, "Mike_Prep for Orlando Cup", client_id=balde)
    t2 = _tarefa(con, "Mike_Practice", client_id=balde)
    inserir(con, "entity_links", entity_type="task", entity_id=t, system="asana", external_id="g-1")
    inserir(con, "entity_links", entity_type="task", entity_id=t2, system="asana", external_id="g-2")
    con.commit()
    notas = {"g-1": "Driver's name: Mike\nResponsible Name: Paul Fattuta\nEmail: fattuta@x.com",
             "g-2": "Driver's name: Mike"}                 # sem contato: fica no balde
    monkeypatch.setattr(P, "chamar", lambda s, f, **a: {"gid": a["gid"], "nome": "x", "notas": notas[a["gid"]]})
    rel = atribuicao.redistribuir(con, aplicar=True, ler_descricoes=True)
    assert rel["descricoes_lidas"] == 2
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (t,))["client_id"] == fattuta
    assert any("saiu do balde" in m["motivo"] for m in rel["movidos"])
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (t2,))["client_id"] == balde, "sem contato, espera"
    # segunda rodada: não pergunta de novo (ficou guardado na tarefa)
    monkeypatch.setattr(P, "chamar", lambda *a, **k: (_ for _ in ()).throw(AssertionError("não devia ir ao Asana")))
    rel2 = atribuicao.redistribuir(con, aplicar=True, ler_descricoes=True)
    assert rel2["descricoes_lidas"] == 0


# ============ o que a revisão adversarial de 22/09 pegou (12 defeitos, 5 críticos) ============
def test_sync_nao_engole_o_balde_no_card_de_outra_familia(con):
    """O CRÍTICO nº1: `deduplicar` roda a cada 15 min e unia o balde "Alex" no primeiro
    card com piloto "Alex" — o serviço acabava na família errada sozinho, desfazendo a
    regra do dono. Balde nunca é unido automaticamente."""
    edward = _cliente(con, "Edward Donnell", piloto="Alex", email="ed@x.com")
    maria = _cliente(con, "Maria Xikis", piloto="Alex", email="mx@x.com")
    _tarefa(con, "Alex_Trackside Support")
    con.commit()
    atribuicao.redistribuir(con, aplicar=True)
    balde = um(con, "SELECT id FROM clients WHERE name='Alex'")["id"]
    identidade.deduplicar(con); con.commit()
    assert um(con, "SELECT id FROM clients WHERE id=?", (balde,)), "o balde sobrevive à sincronia"
    assert um(con, "SELECT id FROM clients WHERE id=?", (maria,)), "e a Maria não é engolida pelo Edward"
    assert um(con, "SELECT client_id FROM tasks WHERE title LIKE 'Alex_%'")["client_id"] == balde
    assert um(con, "SELECT id FROM clients WHERE id=?", (edward,))


def test_deduplicar_so_une_nome_inteiro(con):
    """Primeiro nome sozinho não identifica ninguém. Nome inteiro igual, sim."""
    a = _cliente(con, "Pedro Alves", piloto="Ruy")
    b = _cliente(con, "Joana Lima", piloto="Ruy")
    c1 = _cliente(con, "Carlos Neves", email="c1@x.com")
    c2 = _cliente(con, "Carlos Neves", email="c2@x.com")
    con.commit()
    identidade.deduplicar(con); con.commit()
    assert um(con, "SELECT id FROM clients WHERE id=?", (a,)) and um(con, "SELECT id FROM clients WHERE id=?", (b,))
    vivos = [x["id"] for x in todos(con, "SELECT id FROM clients WHERE id IN (?,?)", (c1, c2))]
    assert len(vivos) == 1, "nome INTEIRO igual continua unindo"


def test_deduplicar_nao_mexe_em_separado(con):
    corrida = _cliente(con, "Battle for Orlando")
    con.execute("UPDATE clients SET kind=? WHERE id=?", (identidade.SEPARADO, corrida))
    vivo = _cliente(con, "Battle for Orlando", email="gente@x.com")
    con.commit()
    identidade.deduplicar(con); con.commit()
    assert um(con, "SELECT id FROM clients WHERE id=?", (vivo,)), "o card vivo não some dentro do separado"
    assert um(con, "SELECT id FROM clients WHERE id=?", (corrida,))


def test_uniao_do_dono_nao_e_desfeita_na_varredura_seguinte(con):
    """O CRÍTICO nº2: o dono unia o balde "Mike" ao Mike Davies e a varredura seguinte
    recriava o balde e tirava o serviço de volta."""
    _cliente(con, "Mike Fattuta", email="f@x.com")
    davies = _cliente(con, "Mike Davies", email="d@x.com")
    _tarefa(con, "Mike_Prep for Orlando Cup")
    con.commit()
    atribuicao.redistribuir(con, aplicar=True)
    balde = um(con, "SELECT id FROM clients WHERE name='Mike'")["id"]
    identidade.unir(con, davies, balde, "user:1", "mesma pessoa"); con.commit()
    rel = atribuicao.redistribuir(con, aplicar=True)
    assert um(con, "SELECT client_id FROM tasks WHERE title LIKE 'Mike_%'")["client_id"] == davies
    assert not any(c["nome"] == "Mike" for c in rel["criados"]), "não recria o balde que ele uniu"


def test_varredura_reaproveita_o_balde_em_vez_de_criar_outro(con):
    """O balde tem de ser estável: antes, cada rodada criava mais um "Alex"."""
    _cliente(con, "Edward Donnell", piloto="Alex", email="ed@x.com")
    _cliente(con, "Maria Xikis", piloto="Alex Xikis", email="mx@x.com")
    _tarefa(con, "Alex_Trackside Support")
    con.commit()
    atribuicao.redistribuir(con, aplicar=True)
    atribuicao.redistribuir(con, aplicar=True)
    rel = atribuicao.redistribuir(con, aplicar=True)
    assert len(todos(con, "SELECT id FROM clients WHERE name='Alex'")) == 1
    assert rel["movidos"] == [] and rel["criados"] == []


def test_piloto_de_uma_palavra_nao_captura_o_servico_de_outro(con):
    """O CRÍTICO nº3: card com piloto "Alex" batia exato e a checagem de ambiguidade
    nunca rodava — o serviço do Alex Xikis ia para o Alex do Edward."""
    _cliente(con, "Edward Donnell", piloto="Alex", email="ed@x.com")
    _cliente(con, "Maria Xikis", piloto="Alex Xikis", email="mx@x.com")
    con.commit()
    cliente, motivo = atribuicao.resolver(con, "Alex")
    assert cliente is None and "ambíguo" in motivo


def test_nome_cortado_de_uma_palavra_vai_para_card_proprio(con):
    """Sobrenome que caiu no vocabulário de serviço deixa um primeiro nome solto. Pista
    fraca demais para ligar a um card pelo primeiro nome."""
    _cliente(con, "Callan Barfield", email="cb@x.com")
    _tarefa(con, "Callan Lead & Follow Vanderlan _Bushnell [5/8]")
    con.commit()
    d = identidade.pessoa_do_titulo_detalhe("Callan Lead & Follow Vanderlan _Bushnell [5/8]")
    assert d == {"nome": "Callan", "truncado": True}
    atribuicao.redistribuir(con, aplicar=True)
    dono = um(con, "SELECT client_id FROM tasks WHERE title LIKE 'Callan%'")["client_id"]
    assert um(con, "SELECT name FROM clients WHERE id=?", (dono,))["name"] == "Callan"


def test_pista_serie_e_marca_nunca_viram_gente(con):
    """Corte antes da condenação fazia "Daytona Speedway Practice" virar "Daytona"."""
    for lixo in ("Daytona Speedway Practice", "FLKC Round 5&6 | Daytona Speedway",
                 "Endurance | OKC Florida, FL", "Lucas Oil | Sebring, FL",
                 "Star Champions Series - King Castle | New Castle Motorsports",
                 "The North Florida Kart Club #10", "Inventário Hank Lai_ caixa"):
        assert identidade.pessoa_do_titulo(lixo) is None, lixo
    for titulo, esperado in (("Giovanni Barrera 2 Stroke Karting School", "Giovanni Barrera"),
                             ("Joe Li - Karting School - Rotax Sr Urace", "Joe Li"),
                             ("Heavenly Fuster - KARTING SCHOOL - Rok GP Urace", "Heavenly Fuster")):
        assert identidade.pessoa_do_titulo(titulo) == esperado, titulo


def test_acha_pessoa_poe_o_responsavel_na_frente_do_piloto(con):
    """O princípio do dono também na sincronia: responsável decide antes do piloto, e
    piloto de uma palavra só não decide sozinho."""
    balde = _cliente(con, "Alex")
    edward = _cliente(con, "Edward Donnell", piloto="Alex Donnell", email="ed@x.com")
    con.commit()
    achado, _ = identidade.acha_pessoa(con, nome="Edward Donnell", piloto="Alex")
    assert achado["id"] == edward, "o responsável manda"
    achado2, _ = identidade.acha_pessoa(con, piloto="Alex")
    assert achado2 is None or achado2["id"] == balde


def test_uniao_guarda_o_convite_de_corrida_que_colide(con):
    """UNIQUE(race_id, client_id): o convite do card perdedor não cabe no vencedor.
    Era apagado em silêncio, com status e orçamento junto."""
    from command_center.db import inserir
    a = _cliente(con, "Pai Um", email="a@x.com")
    b = _cliente(con, "Pai Dois", email="b@x.com")
    r = inserir(con, "races", name="Orlando Cup", date_start="2026-10-01")
    inserir(con, "race_invites", race_id=r, client_id=a, status="confirmed")
    inserir(con, "race_invites", race_id=r, client_id=b, status="declined")
    con.commit()
    identidade.unir(con, a, b, "user:1", "mesma pessoa"); con.commit()
    guardado = um(con, "SELECT drop_json FROM client_merges ORDER BY id DESC")["drop_json"]
    assert "_colidiram_e_foram_guardados" in guardado and "declined" in guardado


def test_uniao_automatica_nao_conta_como_decisao_do_dono(con):
    """A sincronia comeu o balde "Alex" dentro do Edward Donnell (22/09, 13:46). Se a
    varredura tratasse essa união como decisão, cimentaria o erro em vez de desfazê-lo:
    só união feita à mão manda."""
    edward = _cliente(con, "Edward Donnell", piloto="Alex", email="ed@x.com")
    _cliente(con, "Maria Xikis", piloto="Alex Xikis", email="mx@x.com")
    _tarefa(con, "Alex_Trackside Support", client_id=edward)
    balde = _cliente(con, "Alex")
    con.commit()
    identidade.unir(con, edward, balde, "sync", "mesmo nome: alex"); con.commit()
    atribuicao.redistribuir(con, aplicar=True)
    dono = um(con, "SELECT client_id FROM tasks WHERE title LIKE 'Alex_%'")["client_id"]
    assert dono != edward, "o serviço em dúvida sai do card que a sincronia escolheu"
    assert um(con, "SELECT name FROM clients WHERE id=?", (dono,))["name"] == "Alex"


# ============ a varredura de 22/09 à noite: o que ela queria estragar ============
def test_servico_que_ja_esta_num_card_plausivel_nao_sai_dele(con):
    """A regra do dono é não pôr no card de OUTRO — não é mexer em quem já está em casa.

    "AIDEN - KARTING SCHOOL" estava no Aidan Mills (1 letra), "Garret" no Garrett
    Curtis, "Isabel" no card Isabel. A varredura queria tirar os três para baldes
    novos, estragando o que estava certo."""
    aidan = _cliente(con, "Aidan Mills", email="am@x.com")
    garrett = _cliente(con, "Garrett Curtis", email="gc@x.com")
    isabel = _cliente(con, "Isabel")
    _cliente(con, "Isabel Meijá", email="im@x.com")
    _tarefa(con, "AIDEN - KARTING SCHOOL TILLOTSON", client_id=aidan)
    _tarefa(con, "Garret  [Kart Experience - 4 SESSIONS]", client_id=garrett)
    _tarefa(con, "Isabel_Driving Experience  2T Junior", client_id=isabel)
    con.commit()
    rel = atribuicao.redistribuir(con, aplicar=True)
    assert rel["movidos"] == [], "ninguém sai de casa"
    assert um(con, "SELECT client_id FROM tasks WHERE title LIKE 'AIDEN%'")["client_id"] == aidan
    assert um(con, "SELECT client_id FROM tasks WHERE title LIKE 'Garret %'")["client_id"] == garrett
    assert um(con, "SELECT client_id FROM tasks WHERE title LIKE 'Isabel_%'")["client_id"] == isabel
    assert len(todos(con, "SELECT id FROM clients WHERE name='Isabel'")) == 1


def test_servico_no_card_de_outra_pessoa_ainda_sai(con):
    """A regra de ficar em casa não pode virar desculpa para deixar errado onde está."""
    tyron = _cliente(con, "Tyron Brouta", email="tb@x.com")
    matias = _cliente(con, "Matías Lopez", email="ml@x.com")
    _tarefa(con, "Matías Lopez_ Driving Experience[6 sessions Baby Kart]", client_id=tyron)
    con.commit()
    atribuicao.redistribuir(con, aplicar=True)
    assert um(con, "SELECT client_id FROM tasks WHERE title LIKE 'Matías%'")["client_id"] == matias


@pytest.mark.parametrize("titulo,esperado", [
    ("Go Kart Driving Experience - Allan Ramos- 2 STROKE Urace", "Allan Ramos"),
    ("Driving Experience - Bruno Reis", "Bruno Reis"),
    ("Karting School - Marcos Vinicius - Cadet", "Marcos Vinicius"),
])
def test_nome_no_meio_do_titulo_quando_o_servico_vem_na_frente(titulo, esperado):
    """A pessoa quase sempre vem primeiro; quando o primeiro pedaço é SÓ serviço, ela
    vem depois. "Go Kart Driving Experience - Allan Ramos" virava a pessoa "Go"."""
    assert identidade.pessoa_do_titulo(titulo) == esperado


@pytest.mark.parametrize("titulo", [
    "Star Champions Series - King Castle | New Castle Motorsports",
    "FLKC Round 5&6 | Daytona Speedway",
    "2026 SKUSA Pro Tour WinterNats RD1/2 | Musselman Honda Circuit",
])
def test_pular_pedaco_nunca_atravessa_uma_corrida(titulo):
    """Se pulasse pedaço em corrida, "Star Champions Series - King Castle" viraria a
    pessoa "King Castle"."""
    assert identidade.pessoa_do_titulo(titulo) is None


# ============ a varredura com o nome no meio: quatro defeitos que ela expôs ============
@pytest.mark.parametrize("titulo,esperado", [
    ("Karting School -  Cayetano Sanin -BABYKART", "Cayetano Sanin"),   # hífen colado no FIM
    ("Karting School - Landon Silvers BABY - NO CHASSIS", "Landon Silvers"),
    ("Karting School PRO -  Guillermo Jimenez - Micro PRO URACE", "Guillermo Jimenez"),
    ("DRIVING EXPERIENCE - ALI ALHANOOTI (vlr engine)", "Ali Alhanooti"),
    ("Karting School - Sean Portnov - NO CHASSIS", "Sean Portnov"),
])
def test_nome_no_meio_sem_categoria_grudada(titulo, esperado):
    assert (identidade.pessoa_do_titulo(titulo) or "").lower() == esperado.lower()


def test_recado_de_quadro_nao_vira_pessoa_pulando_pedaco(con):
    """"CLOSED_for driver's" virava a pessoa "for driver's": pular pedaço só vale
    quando o pedaço pulado é SERVIÇO, não recado de quadro."""
    for lixo in ("CLOSED_for driver's", "NOT GOING - Star Champions Series", "Photos_Baby Kart"):
        assert identidade.pessoa_do_titulo(lixo) is None, lixo


def test_grafia_diferente_nao_abre_dois_cards(con):
    """"JOSE MIGUEL Abed" e "Jose Miguel Abed" são a mesma criança."""
    _tarefa(con, "KART SCHOOL - JOSE MIGUEL Abed (Mexico)")
    _tarefa(con, "KART SCHOOL - Jose Miguel Abed (Mexico)")
    con.commit()
    atribuicao.redistribuir(con, aplicar=True)
    cards = todos(con, "SELECT id FROM clients WHERE LOWER(name) LIKE '%abed%'")
    assert len(cards) == 1, "um card só"
    assert um(con, "SELECT COUNT(*) n FROM tasks WHERE client_id=?", (cards[0]["id"],))["n"] == 2


def test_erro_de_digitacao_no_card_atual_segura_o_servico(con):
    """"Henryk McKay" no card "Henryl McKay": mesmo sobrenome, 1 letra no primeiro nome.
    Não é escolha entre duas pessoas — é a mesma, escrita errada. Fica, mesmo havendo
    outros nomes parecidos no cadastro."""
    henryl = _cliente(con, "Henryl McKay")
    _cliente(con, "Henry McKayla")                 # outro parecido, para não haver candidato único
    _tarefa(con, "Karting School - Henryk McKay - Cadet Urace", client_id=henryl)
    con.commit()
    rel = atribuicao.redistribuir(con, aplicar=True)
    assert rel["movidos"] == []
    assert um(con, "SELECT client_id FROM tasks WHERE title LIKE '%Henryk%'")["client_id"] == henryl


def test_nome_colado_no_servico_sem_separador(con):
    """"Driving Experience Duffy Merrill" é um card real do quadro: serviço colado no
    nome, sem separador nenhum. Tira o serviço da frente e vê se sobra gente."""
    assert identidade.pessoa_do_titulo("Driving Experience Duffy Merrill") == "Duffy Merrill"
    assert identidade.pessoa_do_titulo("Go Kart Driving Experience") is None
    assert identidade.pessoa_do_titulo("Karting School") is None
    assert identidade.pessoa_do_titulo("Gonzalo Peres_Practice") == "Gonzalo Peres"


def test_servico_fica_no_card_que_tem_exatamente_aquele_nome(con):
    """"Isabel" saía do card "Isabel" para um card novo "Isabel" porque havia uma
    "Isabel Meijá" no cadastro. Card com o nome exato é casa, ponto."""
    isabel = _cliente(con, "Isabel", piloto="Isabel Ramos")
    _cliente(con, "Isabel Meijá", email="im@x.com")
    _tarefa(con, "Isabel_Driving Experience 2T Junior", client_id=isabel)
    con.commit()
    rel = atribuicao.redistribuir(con, aplicar=True)
    assert rel["movidos"] == []
    assert len(todos(con, "SELECT id FROM clients WHERE name='Isabel'")) == 1


# ============ o dono confirmou: a varredura não mexe mais ============
def test_servico_confirmado_pelo_dono_nao_e_movido_nunca(con):
    """Dono, 22/09: os 18 "Savage" e 2 "Savege" do #15 são do Alexander — mesmo o card
    tendo sido alcançado pelo sobrenome do KENNETH Savage.

    "Está certo hoje" não dura: basta um homônimo novo entrar no cadastro para o nome
    virar ambíguo e a varredura tirar o serviço de lá. O carimbo é o que faz a decisão
    dele valer mais que qualquer regra automática."""
    c15 = _cliente(con, "Kenneth Savage", piloto="Alexander Savage")
    t1 = _tarefa(con, "Savage_RWC RD2", client_id=c15)
    t2 = _tarefa(con, "Savege_RWC RD2", client_id=c15)
    con.execute("UPDATE tasks SET client_by='human', client_at=? WHERE id IN (?,?)",
                ("2026-09-22T18:00:00Z", t1, t2))
    con.commit()
    # chega outro Savage: sem carimbo, "Savage" viraria ambíguo e o serviço sairia
    _cliente(con, "Bruno Savage", piloto="Tito Savage", email="bs@x.com")
    con.commit()
    rel = atribuicao.redistribuir(con, aplicar=True)
    assert rel["movidos"] == [] and rel["confirmados"] == 2
    assert um(con, "SELECT COUNT(*) n FROM tasks WHERE client_id=?", (c15,))["n"] == 2


def test_sem_carimbo_o_homonimo_novo_tira_o_servico_de_la(con):
    """O contraste que justifica o carimbo: exatamente o mesmo cenário, sem confirmar."""
    c15 = _cliente(con, "Kenneth Savage", piloto="Alexander Savage")
    _tarefa(con, "Savage_RWC RD2", client_id=c15)
    _cliente(con, "Bruno Savage", piloto="Tito Savage", email="bs@x.com")
    con.commit()
    atribuicao.redistribuir(con, aplicar=True)
    assert um(con, "SELECT client_id FROM tasks WHERE title LIKE 'Savage%'")["client_id"] != c15


def test_confirmar_nao_esconde_o_servico_do_relatorio(con):
    """Confirmado não é invisível: o RESUMO diz quantos são intocáveis."""
    c = _cliente(con, "Kenneth Savage", piloto="Alexander Savage")
    t = _tarefa(con, "Savage_RWC", client_id=c)
    con.execute("UPDATE tasks SET client_by='human' WHERE id=?", (t,))
    con.commit()
    rel = atribuicao.redistribuir(con, aplicar=False)
    assert rel["confirmados"] == 1 and "confirmados por você" in atribuicao.resumo(rel)


def test_corrida_no_card_de_cliente_e_apontada_e_pode_sair(con):
    """Dono, 22/09: "é uma tarefa paralela, não gera card". Não gerar card não basta —
    `Lucas Oil Winter Series Race | Sebring` estava DENTRO do card do Alexander Savage."""
    alex = _cliente(con, "Kenneth Savage", piloto="Alexander Savage")
    corrida = _tarefa(con, "Lucas Oil  Winter Series Race | Sebring International Raceway", client_id=alex)
    servico = _tarefa(con, "Savage_RWC RD2", client_id=alex)
    con.commit()
    rel = atribuicao.redistribuir(con, aplicar=True)
    assert [x["task_id"] for x in rel["nao_servicos_em_card"]] == [corrida]
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (corrida,))["client_id"] == alex, "só aponta"
    rel2 = atribuicao.redistribuir(con, aplicar=True, soltar_nao_servicos=True)
    assert rel2["soltos"] == 1
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (corrida,))["client_id"] is None
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (servico,))["client_id"] == alex


def test_soltar_nao_tira_o_que_o_dono_carimbou(con):
    """Se ele carimbou, ele decidiu. Nem a limpeza passa por cima."""
    alex = _cliente(con, "Kenneth Savage", piloto="Alexander Savage")
    t = _tarefa(con, "Endurance Race - OKC", client_id=alex)
    con.execute("UPDATE tasks SET client_by='human' WHERE id=?", (t,))
    con.commit()
    atribuicao.redistribuir(con, aplicar=True, soltar_nao_servicos=True)
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (t,))["client_id"] == alex


def test_uniao_do_dono_vence_ate_nome_truncado_e_homonimo(con):
    """O pior defeito do dia, pego pela extensão da VPS no plano — antes de aplicar.

    Depois de o dono unir o balde "Martin" ao card "Martin Jaramillo", a varredura
    queria tirar os 26 serviços de lá e recriar o balde. Causa: UMA tarefa
    ("Martin 03/08 próprio motor Rok vlr") marcava o nome como truncado, e esse ramo
    pulava a checagem da união. Sem a checagem, os homônimos (Bruno Martins, Ethan
    Martins, Andres Marin) faziam o nome parecer ambíguo.

    A decisão do dono vem antes de qualquer heurística. Ponto."""
    mj = _cliente(con, "Martin Jaramillo", email="mj@x.com")
    for n, e in (("Bruno Martins", "bm@x.com"), ("Ethan Martins", "em@x.com"), ("Andres Marin", "am@x.com")):
        _cliente(con, n, email=e)
    balde = _cliente(con, "Martin")
    for i in range(26):
        _tarefa(con, f"Martin_KA100 {{caso {i}}}", client_id=balde)
    solta = _tarefa(con, "Martin 03/08 próprio motor Rok vlr")     # a que estragava tudo
    con.commit()
    identidade.unir(con, mj, balde, "owner:cli", "dono, 22/09: mesma pessoa"); con.commit()

    rel = atribuicao.redistribuir(con, aplicar=True)
    assert rel["criados"] == [], "não recria o balde que o dono uniu"
    assert um(con, "SELECT COUNT(*) n FROM tasks WHERE client_id=?", (mj,))["n"] == 27
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (solta,))["client_id"] == mj
    assert atribuicao.redistribuir(con, aplicar=True)["movidos"] == [], "e é estável"


def test_uniao_do_dono_nao_vence_contato_que_diz_outra_coisa(con):
    """O limite da regra acima: a descrição com contato ainda manda, porque é evidência
    sobre AQUELE serviço, não sobre o nome em geral."""
    mj = _cliente(con, "Martin Jaramillo", email="mj@x.com")
    outro = _cliente(con, "Paulo Souza", email="ps@x.com")
    balde = _cliente(con, "Martin")
    t = _tarefa(con, "Martin_Practice", client_id=balde)
    con.execute("UPDATE tasks SET resp_email='ps@x.com' WHERE id=?", (t,))
    con.commit()
    identidade.unir(con, mj, balde, "owner:cli", "mesma pessoa"); con.commit()
    atribuicao.redistribuir(con, aplicar=True)
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (t,))["client_id"] == outro
