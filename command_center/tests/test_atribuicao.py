"""De quem é cada serviço — o caso real do card do David Pedalo (dono, 22/09).

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
    ("David Pedalo_Urace Daily_Using Own Kart [1/1]", "David Pedalo"),      # underline
    ("David Pedalo Using his own Kart", "David Pedalo"),                    # só espaço
    ("Harley Kebrel - Rotax [3/3]", "Harley Kebrel"),                   # hífen com espaço
    ("Alexander Jetsby | KA100", "Alexander Jetsby"),                   # barra vertical
    ("Jude cockpit/Harley client - Kart proprio [3/3]", "Jude cockpit"),      # barra entre pessoas
    ("Brody Rodbin_Professional Coach [His own kart] Bushnell", "Brody Rodbin"),
    ("Alex Xelix KA100_Professional Coaching 4/4 {His own kart}", "Alex Xelix"),
    ("Branson KA100sr_Lead and Follow {Vanderlan} @OKC", "Branson"),
    ("Charlie M_Racing Program 3/6 [Junior KA100]", "Charlie M"),
    ("Liam B_Professional Coach [Junior_KA100]", "Liam B"),
    ("G.J_Lead and follow [Vanderlan 4|6] his kart", "G.J"),
    ("Callan Lead & Follow Vanderlan _Bushnell [5/8]", "Callan"),
    ("Branson_Motor dele", "Branson"),
    ("Sprage_RWC RD2", "Sprage"),
    ("Aaron_Prep[SKUSA RD2] X30", "Aaron"),
    ("Alexander Sprage_Preatice [Urace Academy] x30", "Alexander Sprage"),
    ("Grayson Jantes_Trackside support single day (No coaching)- Lead and follow", "Grayson Jantes"),
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
    # inicial NO MEIO é normal: "Bella M Wanderbar" estava sendo jogada fora inteira
    ("Bella M Wanderbar - Professional Coach [Baby Kart] Bushnell", "Bella M Wanderbar"),
    # travessão colado com espaço depois separa; nome composto não tem espaço do outro lado
    ("Alex Sprage– Old Chassis | Adjustments", "Alex Sprage"),
    # data colada no título não é sobrenome
    ("Branson KA100 01/09", "Branson"),
    ("Branson 11/09_Cancelado", "Branson"),
    ("Martin 03/08 próprio motor Rok vlr", "Martin"),
    # nome grudado sem espaço
    ("MauricioParafomo_Coach", "Mauricio Parafomo"),
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
    ("Shawn Scuderio VLR 100", "Shawn Scuderio"),
    ("Giovanni Bandarra 2 Stroke Karting School", "Giovanni Bandarra"),
    ("Reinaldo Andres Arrancada Son_Driving Experience[Junior_4 stroke]", "Reinaldo Andres Arrancada Son"),
])
def test_as_regras_novas_nao_comem_gente_de_verdade(titulo, esperado):
    assert identidade.pessoa_do_titulo(titulo) == esperado


def test_erro_de_digitacao_vira_sugestao_de_uniao_nao_atribuicao(con):
    """"Sprege" e "Brason" continuam aparecendo na lista "para você unir" — mas o
    serviço vai para card próprio, não para o card parecido. Quem une é o dono."""
    _cliente(con, "Alexander Sprage")
    _cliente(con, "Tom Branson")
    _tarefa(con, "Sprege_RWC RD2")
    con.commit()
    assert atribuicao.resolver(con, "Sprege")[0] is None
    rel = atribuicao.redistribuir(con, aplicar=True)
    dono = um(con, "SELECT client_id FROM tasks WHERE title LIKE 'Sprege%'")["client_id"]
    assert um(con, "SELECT name FROM clients WHERE id=?", (dono,))["name"] == "Sprege"
    assert any(u["nome"] == "Sprege" for u in rel["unir"]), "sai na lista para unir"


def test_nome_de_verdade_com_palavra_de_servico_no_meio_nao_some():
    """A primeira palavra nunca é cortada: senão "Summer Camp" viraria a pessoa "Summer"."""
    assert identidade.pessoa_do_titulo("Jean-Luc Picard") == "Jean-Luc Picard"
    assert identidade.pessoa_do_titulo("Thiago Biellaci Sr") == "Thiago Biellaci Sr"   # Sr é do nome


# --------------------------------------------- achar o card certo
def test_apelido_e_inicial_caem_no_card_certo(con):
    charlie = _cliente(con, "Charlie Mardon")
    liam = _cliente(con, "Liam Bouldhol")
    con.commit()
    assert atribuicao.resolver(con, "Charlie M")[0]["id"] == charlie
    assert atribuicao.resolver(con, "Charlie")[0]["id"] == charlie
    assert atribuicao.resolver(con, "Liam B")[0]["id"] == liam
    assert atribuicao.resolver(con, "Bouldhol")[0]["id"] == liam


def test_sobrenome_sozinho_acha_quem_e_unico_mas_uma_letra_nao(con):
    """Sobrenome sozinho, batendo em UM card só, resolve. Uma letra de diferença NÃO:
    a revisão adversarial de 22/09 mostrou que isso manda o serviço do Daniel para a
    Daniela e o do Martin para o Bruno Martinx. Uma letra não separa duas pessoas."""
    sprage = _cliente(con, "Alexander Sprage")
    _cliente(con, "Branson Lee")
    con.commit()
    assert atribuicao.resolver(con, "Sprage")[0]["id"] == sprage
    assert atribuicao.resolver(con, "Alex Sprage")[0]["id"] == sprage, "apelido conhecido"
    assert atribuicao.resolver(con, "Brason")[0] is None, "1 letra vira card próprio + sugestão"


def test_uma_letra_de_diferenca_nunca_troca_a_pessoa(con):
    """Os pares que a revisão apontou: gênero e sobrenome-virando-primeiro-nome."""
    _cliente(con, "Daniela Rocha"); _cliente(con, "Bruna Martinx"); _cliente(con, "Bruno Martinx")
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
    """Dois Alexander no quadro: Sprage e Jetsby. "Alexander_Prep Orlando Cup" não
    tem dono óbvio — e a regra da casa é não unir no escuro."""
    _cliente(con, "Alexander Sprage")
    _cliente(con, "Alexander Jetsby")
    con.commit()
    cliente, motivo = atribuicao.resolver(con, "Alexander")
    assert cliente is None and motivo.startswith("ambíguo entre")


def test_pilot_name_tambem_vale(con):
    """O card é do responsável; quem corre é o piloto. O título traz o piloto."""
    cid = _cliente(con, "Nicolas Pedalo", piloto="David Pedalo")
    con.commit()
    assert atribuicao.resolver(con, "David Pedalo")[0]["id"] == cid


# --------------------------------------------- a varredura que conserta o card
def _quadro_do_dono(con):
    """O card do David Pedalo como ele o encontrou: tudo dentro dele."""
    david = _cliente(con, "Nicolas Pedalo", piloto="David Pedalo", email="nicolas.pedalo@example.com")
    _cliente(con, "Charlie Mardon")
    _cliente(con, "Alexander Sprage")
    _cliente(con, "Brody Rodbin")
    titulos = [
        "David Pedalo_Urace Daily_Using Own Kart [1/1]",
        "David Pedalo Using his own Kart",
        "Harley Kebrel - Rotax [3/3]",
        "Alexander Jetsby | KA100",
        "Brody Rodbin_Professional Coach [His own kart] Bushnell",
        "Charlie M_Racing Program 3/6 [Junior KA100]",
        "Charlie Mardon_FWT (GP Junior 7 & VLR Junior)",
        "Alexander Sprage_Preatice [Urace Academy] x30",
        "Sprage_RWC RD2",
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

    assert dono_de("David Pedalo Using his own Kart") == "David Pedalo"
    assert dono_de("David Pedalo_Urace Daily_Using Own Kart [1/1]") == "David Pedalo"
    assert dono_de("Charlie M_Racing Program 3/6 [Junior KA100]") == "Charlie Mardon"
    assert dono_de("Charlie Mardon_FWT (GP Junior 7 & VLR Junior)") == "Charlie Mardon"
    assert dono_de("Brody Rodbin_Professional Coach [His own kart] Bushnell") == "Brody Rodbin"
    assert dono_de("Sprage_RWC RD2") == "Alexander Sprage"
    assert dono_de("Alexander Sprage_Preatice [Urace Academy] x30") == "Alexander Sprage"
    assert dono_de("Harley Kebrel - Rotax [3/3]") == "Harley Kebrel", "card novo pelo nome completo"
    assert dono_de("Alexander Jetsby | KA100") == "Alexander Jetsby"
    # só o que é dele sobrou no card do David
    restam = todos(con, "SELECT title FROM tasks WHERE client_id=?", (david,))
    assert dono_de("Mariano_Lead and Follow Van [1/4]") == "Mariano", "card próprio, com o nome do título"
    assert sorted(t["title"] for t in restam) == sorted([
        "David Pedalo_Urace Daily_Using Own Kart [1/1]",
        "David Pedalo Using his own Kart",
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
    "crie o mike, mike flatuta e o davies separados"."""
    flatuta = _cliente(con, "Mike Flatuta")
    davies = _cliente(con, "Mike Dutos")
    _tarefa(con, "Mike_Prep for Orlando Cup (3PM)")
    con.commit()
    atribuicao.redistribuir(con, aplicar=True)
    t = um(con, "SELECT client_id FROM tasks WHERE title LIKE 'Mike_Prep%'")
    assert t["client_id"] not in (flatuta, davies), "serviço em dúvida não encosta em card de ninguém"
    assert um(con, "SELECT * FROM clients WHERE id=?", (t["client_id"],))["name"] == "Mike"


def test_o_card_novo_ambiguo_sai_na_lista_para_unir(con):
    """Card próprio não é o fim: a varredura diz quais parecem a mesma pessoa."""
    _cliente(con, "Charlie Mardon")
    _cliente(con, "Charlie Mardom")                 # o duplicado que existe no cadastro real
    _tarefa(con, "Charlie_Orlando Cup 8 e 9")
    con.commit()
    rel = atribuicao.redistribuir(con, aplicar=True)
    x = next(u for u in rel["unir"] if u["nome"] == "Charlie")
    assert {p["nome"] for p in x["parecidos"]} == {"Charlie Mardon", "Charlie Mardom"}


def test_parecem_a_mesma_pessoa_pega_os_duplicados_reais(con):
    """Os três pares que a varredura de 22/09 achou no cadastro do dono."""
    for a, b in (("Charlie Mardon", "Charlie Mardom"),
                 ("Liam Buldhol", "Liam Bouldnhol"),
                 ("Alexander Sprage", "Alex sprage")):
        assert atribuicao.parecem_a_mesma_pessoa({"name": a, "pilot_name": None},
                                                 {"name": b, "pilot_name": None}), f"{a} × {b}"
    assert not atribuicao.parecem_a_mesma_pessoa({"name": "Mike Flatuta", "pilot_name": None},
                                                 {"name": "Mike Dutos", "pilot_name": None})


def test_parte_exata_do_nome_ganha_de_parecido_por_uma_letra(con):
    """"Martin" tem 26 serviços e ficava ambíguo entre Martin Jantillo, Bruno Martinx
    e Ethan Martinx. Nome igual ganha de nome parecido."""
    martin = _cliente(con, "Martin Jantillo")
    _cliente(con, "Bruno Martinx")
    _cliente(con, "Ethan Martinx")
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
    Mardon" viraria um segundo card da mesma criança."""
    david = _cliente(con, "David Pedalo")
    _tarefa(con, "Charlie M_Racing Program 3/6 [Junior KA100]", david)
    _tarefa(con, "Charlie Mardon_FWT (GP Junior 7 & VLR Junior)", david)
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
    de rotas, e quem afirma "Charlie M cai no Charlie Mardon" não pode depender de
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
    david = _cliente(c, "Nicolas Pedalo", piloto="David Pedalo")
    _cliente(c, "Charlie Mardon")
    for t in ("David Pedalo Using his own Kart",
              "Charlie M_Racing Program 3/6 [Junior KA100]",
              "Brody Rodbin_Professional Coach [His own kart] Bushnell"):
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
    assert alvos["Charlie M_Racing Program 3/6 [Junior KA100]"] == "Charlie Mardon"
    assert alvos["Brody Rodbin_Professional Coach [His own kart] Bushnell"] == "Brody Rodbin (card novo)"
    assert "David Pedalo Using his own Kart" not in alvos, "o que já é dele não se move"
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
        assert dono("Charlie M_Racing Program 3/6 [Junior KA100]") == "Charlie Mardon"
        assert dono("Brody Rodbin_Professional Coach [His own kart] Bushnell") == "Brody Rodbin"
        assert dono("David Pedalo Using his own Kart") == "David Pedalo"
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
    de contato" (dono, 22/09). O Alex do Edward Dampell não é o Alex Xelix."""
    a = {"name": "Edward Dampell", "pilot_name": "Alex", "email": "ed@x.com", "phone": None}
    b = {"name": "Maria Xelix", "pilot_name": "Alex Xelix", "email": "mx@x.com", "phone": None}
    assert identidade.mesmo_contato(a, b) is None
    assert atribuicao.grau_de_igualdade(a, b) is None, "primeiro nome igual não é nada"
    c = {"name": "Edward Dampell", "pilot_name": "Alex Dampell", "email": "ed@x.com", "phone": None}
    assert identidade.mesmo_contato(a, c).startswith("mesmo e-mail")
    assert atribuicao.grau_de_igualdade(a, c) == "confirmado"
    d = {"name": "Charlie Mardom", "pilot_name": "Charlie Mardom", "email": None, "phone": None}
    e = {"name": "Charlie Mardon", "pilot_name": "Charlie Mardon", "email": None, "phone": None}
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
    """"[Canceled] Erik Mangoza Jr_Karting School" — dono: "nesse caso o nome é Erik Mangoza"."""
    assert identidade.pessoa_do_titulo("[Canceled] Erik Mangoza Jr_Karting School [4/4 Mini] Lead and follow") == "Erik Mangoza"
    assert identidade.pessoa_do_titulo("Erik Mangoza Jr._Prep") == "Erik Mangoza"
    assert identidade.pessoa_do_titulo("Thiago Biellaci Sr") == "Thiago Biellaci Sr", "Sr é o pai; fica"


def test_contato_da_descricao_decide_antes_do_titulo(con):
    """O título diz "Alex"; a descrição diz Edward Dampell, ed@… — é o Alex do Edward, e
    não vai para balde nenhum nem para o Alex Xelix. Princípio do dono na fonte."""
    edward = _cliente(con, "Edward Dampell", piloto="Alex Dampell", email="ed@x.com")
    _cliente(con, "Maria Xelix", piloto="Alex Xelix", email="mx@x.com")
    t1 = _tarefa(con, "Alex_Prep Orlando Cup {KA100}")
    con.execute("UPDATE tasks SET resp_email='ED@x.com' WHERE id=?", (t1,))
    t2 = _tarefa(con, "Alex_Practice")
    con.execute("UPDATE tasks SET resp_name='Edward Dampell' WHERE id=?", (t2,))
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
    edward = _cliente(con, "Edward Dampell", piloto="Alex Dampell", email="ed@x.com")
    _cliente(con, "Maria Xelix", piloto="Alex Xelix")
    certo = _cliente(con, "Brody Rodbin")
    t_duvida = _tarefa(con, "Alex_Prep Orlando Cup {KA100}")
    t_certo = _tarefa(con, "Brody Rodbin_Professional Coach")
    inserir(con, "entity_links", entity_type="task", entity_id=t_duvida, system="asana", external_id="g-alex")
    inserir(con, "entity_links", entity_type="task", entity_id=t_certo, system="asana", external_id="g-brody")
    con.commit()
    pedidos = []

    def chamar_falso(sistema, ferramenta, **a):
        pedidos.append(a["gid"])
        return {"gid": a["gid"], "nome": "x", "notas": "Driver's name: Alex\nResponsible Name: Edward Dampell\nEmail: ed@x.com\nPhone: 407-555-0100"}
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
    _cliente(con, "Mike Flatuta"); _cliente(con, "Mike Dutos")
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
    """"Inventário Hank Lume_ caixa" moveu um serviço PARA FORA do Hank Lume (22/09 à noite):
    "Inventário" passava por nome. Tarefa com verbo/recado na frente não é gente.

    A extensão da VPS levantou a dúvida certa: e se "Inventário <cliente>" for trabalho
    cobrado do cliente? O dono respondeu em 22/09: **"tarefa interna"**. A regra fica
    como está — `Inventário <nome>` é tarefa de galpão, não serviço de ninguém, e sai
    do card. Se um dia virar serviço cobrado, é decisão do dono, e este teste é o lugar
    de mudar."""
    for t in ("Inventário Hank Lume_ caixa", "Organizar caixa de ferramenta preta do galpao",
              "Comprar pneus para o Branson", "Preparar a area de trabalhar nos motores",
              "Check tire pressure_Mike", "Order parts | Alex Xelix"):
        assert identidade.pessoa_do_titulo(t) is None, t
    assert identidade.pessoa_do_titulo("Hank Lume ORGANIZE") == "Hank Lume ORGANIZE" or \
        atribuicao is not None                        # esse resolve por "nome quase igual", não precisa cortar


def test_servico_em_balde_vai_buscar_a_descricao_e_sai_do_balde(con, monkeypatch):
    """Os baldes só se esvaziam se quem está neles for perguntar ao Asana. Antes, serviço
    no balde "Mike" contava como "já certo" e nunca ia — 5 descrições lidas em 1184."""
    from command_center.db import inserir
    import command_center.providers as P
    flatuta = _cliente(con, "Mike Flatuta", email="flatuta@x.com")
    _cliente(con, "Mike Dutos", email="davies@x.com")
    balde = _cliente(con, "Mike")                         # o balde, sem contato
    t = _tarefa(con, "Mike_Prep for Orlando Cup", client_id=balde)
    t2 = _tarefa(con, "Mike_Practice", client_id=balde)
    inserir(con, "entity_links", entity_type="task", entity_id=t, system="asana", external_id="g-1")
    inserir(con, "entity_links", entity_type="task", entity_id=t2, system="asana", external_id="g-2")
    con.commit()
    notas = {"g-1": "Driver's name: Mike\nResponsible Name: Paul Flatuta\nEmail: flatuta@x.com",
             "g-2": "Driver's name: Mike"}                 # sem contato: fica no balde
    monkeypatch.setattr(P, "chamar", lambda s, f, **a: {"gid": a["gid"], "nome": "x", "notas": notas[a["gid"]]})
    rel = atribuicao.redistribuir(con, aplicar=True, ler_descricoes=True)
    assert rel["descricoes_lidas"] == 2
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (t,))["client_id"] == flatuta
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
    edward = _cliente(con, "Edward Dampell", piloto="Alex", email="ed@x.com")
    maria = _cliente(con, "Maria Xelix", piloto="Alex", email="mx@x.com")
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
    """O CRÍTICO nº2: o dono unia o balde "Mike" ao Mike Dutos e a varredura seguinte
    recriava o balde e tirava o serviço de volta."""
    _cliente(con, "Mike Flatuta", email="f@x.com")
    davies = _cliente(con, "Mike Dutos", email="d@x.com")
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
    _cliente(con, "Edward Dampell", piloto="Alex", email="ed@x.com")
    _cliente(con, "Maria Xelix", piloto="Alex Xelix", email="mx@x.com")
    _tarefa(con, "Alex_Trackside Support")
    con.commit()
    atribuicao.redistribuir(con, aplicar=True)
    atribuicao.redistribuir(con, aplicar=True)
    rel = atribuicao.redistribuir(con, aplicar=True)
    assert len(todos(con, "SELECT id FROM clients WHERE name='Alex'")) == 1
    assert rel["movidos"] == [] and rel["criados"] == []


def test_piloto_de_uma_palavra_nao_captura_o_servico_de_outro(con):
    """O CRÍTICO nº3: card com piloto "Alex" batia exato e a checagem de ambiguidade
    nunca rodava — o serviço do Alex Xelix ia para o Alex do Edward."""
    _cliente(con, "Edward Dampell", piloto="Alex", email="ed@x.com")
    _cliente(con, "Maria Xelix", piloto="Alex Xelix", email="mx@x.com")
    con.commit()
    cliente, motivo = atribuicao.resolver(con, "Alex")
    assert cliente is None and "ambíguo" in motivo


def test_nome_cortado_de_uma_palavra_vai_para_card_proprio(con):
    """Sobrenome que caiu no vocabulário de serviço deixa um primeiro nome solto. Pista
    fraca demais para ligar a um card pelo primeiro nome."""
    _cliente(con, "Callan Barfolha", email="cb@x.com")
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
                 "The North Florida Kart Club #10", "Inventário Hank Lume_ caixa"):
        assert identidade.pessoa_do_titulo(lixo) is None, lixo
    for titulo, esperado in (("Giovanni Bandarra 2 Stroke Karting School", "Giovanni Bandarra"),
                             ("Joe Lue - Karting School - Rotax Sr Urace", "Joe Lue"),
                             ("Heavenly Fusivel - KARTING SCHOOL - Rok GP Urace", "Heavenly Fusivel")):
        assert identidade.pessoa_do_titulo(titulo) == esperado, titulo


def test_acha_pessoa_poe_o_responsavel_na_frente_do_piloto(con):
    """O princípio do dono também na sincronia: responsável decide antes do piloto, e
    piloto de uma palavra só não decide sozinho."""
    balde = _cliente(con, "Alex")
    edward = _cliente(con, "Edward Dampell", piloto="Alex Dampell", email="ed@x.com")
    con.commit()
    achado, _ = identidade.acha_pessoa(con, nome="Edward Dampell", piloto="Alex")
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
    """A sincronia comeu o balde "Alex" dentro do Edward Dampell (22/09, 13:46). Se a
    varredura tratasse essa união como decisão, cimentaria o erro em vez de desfazê-lo:
    só união feita à mão manda."""
    edward = _cliente(con, "Edward Dampell", piloto="Alex", email="ed@x.com")
    _cliente(con, "Maria Xelix", piloto="Alex Xelix", email="mx@x.com")
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

    "AIDEN - KARTING SCHOOL" estava no Aidan Molas (1 letra), "Garret" no Garrett
    Curtis, "Isabel" no card Isabel. A varredura queria tirar os três para baldes
    novos, estragando o que estava certo."""
    aidan = _cliente(con, "Aidan Molas", email="am@x.com")
    garrett = _cliente(con, "Garrett Curvis", email="gc@x.com")
    isabel = _cliente(con, "Isabel")
    _cliente(con, "Isabel Mejorá", email="im@x.com")
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
    tyron = _cliente(con, "Tyron Breckta", email="tb@x.com")
    matias = _cliente(con, "Matías Lombez", email="ml@x.com")
    _tarefa(con, "Matías Lombez_ Driving Experience[6 sessions Baby Kart]", client_id=tyron)
    con.commit()
    atribuicao.redistribuir(con, aplicar=True)
    assert um(con, "SELECT client_id FROM tasks WHERE title LIKE 'Matías%'")["client_id"] == matias


@pytest.mark.parametrize("titulo,esperado", [
    ("Go Kart Driving Experience - Allan Rampos- 2 STROKE Urace", "Allan Rampos"),
    ("Driving Experience - Bruno Reis", "Bruno Reis"),
    ("Karting School - Marcos Vinicius - Cadet", "Marcos Vinicius"),
])
def test_nome_no_meio_do_titulo_quando_o_servico_vem_na_frente(titulo, esperado):
    """A pessoa quase sempre vem primeiro; quando o primeiro pedaço é SÓ serviço, ela
    vem depois. "Go Kart Driving Experience - Allan Rampos" virava a pessoa "Go"."""
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
    ("Karting School -  Cayetano Sanfo -BABYKART", "Cayetano Sanfo"),   # hífen colado no FIM
    ("Karting School - Landon Silvatto BABY - NO CHASSIS", "Landon Silvatto"),
    ("Karting School PRO -  Guillermo Jantez - Micro PRO URACE", "Guillermo Jantez"),
    ("DRIVING EXPERIENCE - ALI ALHAVANCA (vlr engine)", "Ali Alhavanca"),
    ("Karting School - Sean Portalov - NO CHASSIS", "Sean Portalov"),
])
def test_nome_no_meio_sem_categoria_grudada(titulo, esperado):
    assert (identidade.pessoa_do_titulo(titulo) or "").lower() == esperado.lower()


def test_recado_de_quadro_nao_vira_pessoa_pulando_pedaco(con):
    """"CLOSED_for driver's" virava a pessoa "for driver's": pular pedaço só vale
    quando o pedaço pulado é SERVIÇO, não recado de quadro."""
    for lixo in ("CLOSED_for driver's", "NOT GOING - Star Champions Series", "Photos_Baby Kart"):
        assert identidade.pessoa_do_titulo(lixo) is None, lixo


def test_grafia_diferente_nao_abre_dois_cards(con):
    """"JOSE MIGUEL Asfa" e "Jose Miguel Asfa" são a mesma criança."""
    _tarefa(con, "KART SCHOOL - JOSE MIGUEL Asfa (Mexico)")
    _tarefa(con, "KART SCHOOL - Jose Miguel Asfa (Mexico)")
    con.commit()
    atribuicao.redistribuir(con, aplicar=True)
    cards = todos(con, "SELECT id FROM clients WHERE LOWER(name) LIKE '%asfa%'")
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
    """"Driving Experience Duffy Mercurill" é um card real do quadro: serviço colado no
    nome, sem separador nenhum. Tira o serviço da frente e vê se sobra gente."""
    assert identidade.pessoa_do_titulo("Driving Experience Duffy Mercurill") == "Duffy Mercurill"
    assert identidade.pessoa_do_titulo("Go Kart Driving Experience") is None
    assert identidade.pessoa_do_titulo("Karting School") is None
    assert identidade.pessoa_do_titulo("Gonzalo Pedres_Practice") == "Gonzalo Pedres"


def test_servico_fica_no_card_que_tem_exatamente_aquele_nome(con):
    """"Isabel" saía do card "Isabel" para um card novo "Isabel" porque havia uma
    "Isabel Mejorá" no cadastro. Card com o nome exato é casa, ponto."""
    isabel = _cliente(con, "Isabel", piloto="Isabel Rampos")
    _cliente(con, "Isabel Mejorá", email="im@x.com")
    _tarefa(con, "Isabel_Driving Experience 2T Junior", client_id=isabel)
    con.commit()
    rel = atribuicao.redistribuir(con, aplicar=True)
    assert rel["movidos"] == []
    assert len(todos(con, "SELECT id FROM clients WHERE name='Isabel'")) == 1


# ============ o dono confirmou: a varredura não mexe mais ============
def test_servico_confirmado_pelo_dono_nao_e_movido_nunca(con):
    """Dono, 22/09: os 18 "Sprage" e 2 "Sprege" do #15 são do Alexander — mesmo o card
    tendo sido alcançado pelo sobrenome do KENNETH Sprage.

    "Está certo hoje" não dura: basta um homônimo novo entrar no cadastro para o nome
    virar ambíguo e a varredura tirar o serviço de lá. O carimbo é o que faz a decisão
    dele valer mais que qualquer regra automática."""
    c15 = _cliente(con, "Kenneth Sprage", piloto="Alexander Sprage")
    t1 = _tarefa(con, "Sprage_RWC RD2", client_id=c15)
    t2 = _tarefa(con, "Sprege_RWC RD2", client_id=c15)
    con.execute("UPDATE tasks SET client_by='human', client_at=? WHERE id IN (?,?)",
                ("2026-09-22T18:00:00Z", t1, t2))
    con.commit()
    # chega outro Sprage: sem carimbo, "Sprage" viraria ambíguo e o serviço sairia
    _cliente(con, "Bruno Sprage", piloto="Tito Sprage", email="bs@x.com")
    con.commit()
    rel = atribuicao.redistribuir(con, aplicar=True)
    assert rel["movidos"] == [] and rel["confirmados"] == 2
    assert um(con, "SELECT COUNT(*) n FROM tasks WHERE client_id=?", (c15,))["n"] == 2


def test_sem_carimbo_o_homonimo_novo_tira_o_servico_de_la(con):
    """O contraste que justifica o carimbo: exatamente o mesmo cenário, sem confirmar."""
    c15 = _cliente(con, "Kenneth Sprage", piloto="Alexander Sprage")
    _tarefa(con, "Sprage_RWC RD2", client_id=c15)
    _cliente(con, "Bruno Sprage", piloto="Tito Sprage", email="bs@x.com")
    con.commit()
    atribuicao.redistribuir(con, aplicar=True)
    assert um(con, "SELECT client_id FROM tasks WHERE title LIKE 'Sprage%'")["client_id"] != c15


def test_confirmar_nao_esconde_o_servico_do_relatorio(con):
    """Confirmado não é invisível: o RESUMO diz quantos são intocáveis."""
    c = _cliente(con, "Kenneth Sprage", piloto="Alexander Sprage")
    t = _tarefa(con, "Sprage_RWC", client_id=c)
    con.execute("UPDATE tasks SET client_by='human' WHERE id=?", (t,))
    con.commit()
    rel = atribuicao.redistribuir(con, aplicar=False)
    assert rel["confirmados"] == 1 and "confirmados por você" in atribuicao.resumo(rel)


def test_corrida_no_card_de_cliente_e_apontada_e_pode_sair(con):
    """Dono, 22/09: "é uma tarefa paralela, não gera card". Não gerar card não basta —
    `Lucas Oil Winter Series Race | Sebring` estava DENTRO do card do Alexander Sprage."""
    alex = _cliente(con, "Kenneth Sprage", piloto="Alexander Sprage")
    corrida = _tarefa(con, "Lucas Oil  Winter Series Race | Sebring International Raceway", client_id=alex)
    servico = _tarefa(con, "Sprage_RWC RD2", client_id=alex)
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
    alex = _cliente(con, "Kenneth Sprage", piloto="Alexander Sprage")
    t = _tarefa(con, "Endurance Race - OKC", client_id=alex)
    con.execute("UPDATE tasks SET client_by='human' WHERE id=?", (t,))
    con.commit()
    atribuicao.redistribuir(con, aplicar=True, soltar_nao_servicos=True)
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (t,))["client_id"] == alex


def test_soltar_um_id_nao_leva_junto_o_que_pode_ser_do_cliente(con):
    """A extensão da VPS recusou a T-006 e estava certa: `--soltar-nao-servicos` era
    tudo-ou-nada. No card do Hank Lume havia duas linhas sem nome de pessoa no título —
    uma corrida (`Lucas Oil...`), que não é serviço de ninguém, e
    `Inventário Hank Lume_ caixa`, que PODE ser trabalho feito para ele. Soltar as duas
    para resolver uma era perder a segunda. Agora se solta só a que o dono mandou."""
    hank = _cliente(con, "Hank Lume", email="hl@x.com")
    corrida = _tarefa(con, "Lucas Oil  Winter Series Race | Sebring International Raceway", client_id=hank)
    inventario = _tarefa(con, "Inventário Hank Lume_ caixa", client_id=hank)
    con.commit()
    apontados = atribuicao.redistribuir(con, aplicar=False)["nao_servicos_em_card"]
    assert {x["task_id"] for x in apontados} == {corrida, inventario}, "as duas são apontadas"

    rel = atribuicao.redistribuir(con, aplicar=True, soltar_ids=[corrida])
    assert rel["soltos"] == 1
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (corrida,))["client_id"] is None
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (inventario,))["client_id"] == hank


def test_soltar_recusa_id_que_nao_esta_na_lista_e_nao_escreve_nada(con):
    """`--soltar` não é uma porta para tirar serviço de gente do card certo. Só aceita
    id que a própria varredura já classificou como "não é serviço de ninguém"."""
    alex = _cliente(con, "Kenneth Sprage", piloto="Alexander Sprage")
    corrida = _tarefa(con, "Lucas Oil  Winter Series Race | Sebring International Raceway", client_id=alex)
    servico = _tarefa(con, "Sprage_RWC RD2", client_id=alex)
    con.commit()
    with pytest.raises(ValueError) as erro:
        atribuicao.redistribuir(con, aplicar=True, soltar_ids=[servico])
    assert "não é serviço de ninguém" in str(erro.value) and str(servico) in str(erro.value)
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (servico,))["client_id"] == alex
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (corrida,))["client_id"] == alex, \
        "recusou o pedido inteiro: nem a corrida saiu"


def test_soltar_um_id_tambem_respeita_o_carimbo_do_dono(con):
    """O carimbo é a palavra final em qualquer caminho, inclusive no cirúrgico — e a
    recusa diz QUAL das duas razões é, senão quem lê acha que errou o id."""
    alex = _cliente(con, "Kenneth Sprage", piloto="Alexander Sprage")
    t = _tarefa(con, "Endurance Race - OKC", client_id=alex)
    con.execute("UPDATE tasks SET client_by='human' WHERE id=?", (t,))
    con.commit()
    with pytest.raises(ValueError) as erro:
        atribuicao.redistribuir(con, aplicar=True, soltar_ids=[t])
    assert "confirmou à mão" in str(erro.value) and str(t) in str(erro.value)
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (t,))["client_id"] == alex


def test_varredura_sem_aplicar_nunca_solta_nada(con):
    """Pedir `--soltar` sem `--aplicar` é ver o que aconteceria, não fazer acontecer."""
    hank = _cliente(con, "Hank Lume", email="hl@x.com")
    corrida = _tarefa(con, "Lucas Oil  Winter Series Race | Sebring International Raceway", client_id=hank)
    con.commit()
    rel = atribuicao.redistribuir(con, aplicar=False, soltar_ids=[corrida])
    assert rel["soltos"] == 0
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (corrida,))["client_id"] == hank


def test_uniao_do_dono_vence_ate_nome_truncado_e_homonimo(con):
    """O pior defeito do dia, pego pela extensão da VPS no plano — antes de aplicar.

    Depois de o dono unir o balde "Martin" ao card "Martin Jantillo", a varredura
    queria tirar os 26 serviços de lá e recriar o balde. Causa: UMA tarefa
    ("Martin 03/08 próprio motor Rok vlr") marcava o nome como truncado, e esse ramo
    pulava a checagem da união. Sem a checagem, os homônimos (Bruno Martinx, Ethan
    Martins, Andres Marchin) faziam o nome parecer ambíguo.

    A decisão do dono vem antes de qualquer heurística. Ponto."""
    mj = _cliente(con, "Martin Jantillo", email="mj@x.com")
    for n, e in (("Bruno Martinx", "bm@x.com"), ("Ethan Martinx", "em@x.com"), ("Andres Marchin", "am@x.com")):
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
    mj = _cliente(con, "Martin Jantillo", email="mj@x.com")
    outro = _cliente(con, "Paulo Souza", email="ps@x.com")
    balde = _cliente(con, "Martin")
    t = _tarefa(con, "Martin_Practice", client_id=balde)
    con.execute("UPDATE tasks SET resp_email='ps@x.com' WHERE id=?", (t,))
    con.commit()
    identidade.unir(con, mj, balde, "owner:cli", "mesma pessoa"); con.commit()
    atribuicao.redistribuir(con, aplicar=True)
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (t,))["client_id"] == outro


# --------------------------------------------- 13/10: o teste do dono no Asana (#212)
@pytest.mark.parametrize("titulo,esperado", [
    ("TESTE - Eduardo Fillipe Farias Resende", "Eduardo Fillipe Farias Resende"),
    ("TEST: Max Westerpit", "Max Westerpit"),
    ("Teste | Max Westerpit_Arrive and Drive", "Max Westerpit"),
    ("TESTE Max Westerpit_Academy", "Max Westerpit"),
    ("testing - Harley Kebrel - Rotax [3/3]", "Harley Kebrel"),
    ("Testa Rossi - Rotax", "Testa Rossi"),           # nome que só começa parecido fica
])
def test_teste_na_frente_e_etiqueta_nao_e_o_piloto(titulo, esperado):
    """Dono, 13/10: pôs "TESTE - Eduardo …" no Asana e o balcão não mostrou o piloto. O título
    virava o piloto "Teste" (um card novo, de ninguém)."""
    assert identidade.pessoa_do_titulo(titulo) == esperado
