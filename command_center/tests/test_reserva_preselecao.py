"""#253: o kart escolhido no site só pré-seleciona o serviço desse kart.

Dono, 15/10 (print da tela "Book your session" com "teste · teste de produto $500.00" já escolhido):
*"remova esse produto d teste quando for para essa pagina ja vai com o produto pré selecionado"*.

A tela escolhia o único serviço do painel mesmo sem relação com o kart clicado no site — foi assim
que o serviço "teste" apareceu pré-selecionado para quem veio do site. A regra mora num lugar só,
`command_center/web/src/portal/preselecao.ts`, e é a mesma na reserva do site (#164) e na agenda da
área do cliente. Aqui ela é provada rodando o próprio módulo no Node (nada de cópia em Python) e,
além disso, nenhuma das duas telas pode voltar a cair no "um serviço só, então escolhe esse".
"""
import json
import os
import subprocess

import pytest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PORTAL = os.path.join(RAIZ, "command_center", "web", "src", "portal")
REGRA = os.path.join(PORTAL, "preselecao.ts")

# Os serviços do painel, como a API pública os manda (id e nome é o que a regra olha)
TESTE = [{"id": 7, "name": "teste", "description": "teste de produto"}]
DOIS = [{"id": 1, "name": "Arrive and Drive 4-stroke"}, {"id": 2, "name": "Arrive and Drive 2-stroke"}]
DOIS_DO_KART = [{"id": 1, "name": "Arrive and Drive 2-stroke"}, {"id": 2, "name": "Arrive and Drive 2-stroke VIP"}]

CASOS = [
    # (serviços do painel, kart do site, escolha que já existia) -> (serviço escolhido, mostra o aviso)
    ("só o serviço de teste e o kart do site: não escolhe nada e avisa", TESTE, "2-stroke", None, None, True),
    ("só o serviço de teste e ninguém veio do site: continua escolhido", TESTE, None, None, 7, False),
    ("o serviço do kart entre vários: escolhido", DOIS, "2-stroke", None, 2, False),
    ("kart sem serviço entre vários: não escolhe nada e avisa", DOIS, "Adult Shifter", None, None, True),
    ("dois serviços com o nome do kart: a pessoa escolhe", DOIS_DO_KART, "2-stroke", None, None, False),
    ("vários serviços e ninguém veio do site: a pessoa escolhe", DOIS, None, None, None, False),
    ("a escolha que já existia, sendo do kart, é mantida", DOIS_DO_KART, "2-stroke", 2, 2, False),
    ("a escolha guardada que não é do kart é descartada", DOIS, "2-stroke", 1, 2, False),
    ("a escolha que já existia vale quando não veio kart", DOIS, None, 1, 1, False),
    ("escolha que saiu do painel não sobrevive", DOIS, None, 99, None, False),
    ("o nome do kart não distingue maiúscula nem espaço à toa", DOIS, " 2-STROKE ", None, 2, False),
]


def _no_node(codigo):
    """Roda o módulo da regra no Node (o Node 22+ lê TypeScript direto) e devolve o JSON impresso."""
    try:
        r = subprocess.run(["node", "--input-type=module", "-e", codigo], capture_output=True, text=True, cwd=PORTAL)
    except (FileNotFoundError, PermissionError):
        pytest.skip("sem node nesta máquina (o teste de ponta a ponta cobre a mesma regra na tela)")
    if r.returncode != 0:
        if "ERR_UNKNOWN_FILE_EXTENSION" in r.stderr or "Unknown file extension" in r.stderr:
            pytest.skip("este Node não lê TypeScript direto (precisa do 22.18+)")
        pytest.fail(r.stderr[-2000:])
    return json.loads(r.stdout)


def test_a_regra_da_pre_selecao_existe_num_lugar_so():
    assert os.path.exists(REGRA), "a regra da pré-seleção mora em portal/preselecao.ts"


def test_a_pre_selecao_do_kart_do_site():
    """A regra, caso por caso, rodando o próprio arquivo que as telas importam."""
    entradas = [{"servicos": s, "kart": k, "atual": a} for _, s, k, a, _, _ in CASOS]
    saida = _no_node(
        "import { servicoPreSelecionado, kartSemServico } from " + json.dumps(REGRA) + ";"
        "const casos = " + json.dumps(entradas) + ";"
        "console.log(JSON.stringify(casos.map(c => ["
        "  servicoPreSelecionado(c.servicos, c.kart, c.atual), kartSemServico(c.servicos, c.kart)])))"
    )
    deu = []
    for (nome, _, _, _, servico, aviso), (achou, avisou) in zip(CASOS, saida, strict=True):
        if achou != servico or avisou != aviso:
            deu.append(f"{nome}: esperado serviço={servico} aviso={aviso}, veio serviço={achou} aviso={avisou}")
    assert not deu, "\n".join(deu)


def test_a_lista_ainda_carregando_nao_vira_aviso():
    """Enquanto a lista do painel não chegou (null), a tela não pode acusar kart sem serviço."""
    saida = _no_node("import { kartSemServico } from " + json.dumps(REGRA) + ";"
                     "console.log(JSON.stringify([kartSemServico(null, '2-stroke'), kartSemServico([], '2-stroke'),"
                     " kartSemServico([{ id: 1, name: 'Arrive and Drive 2-stroke' }], '2-stroke')]))")
    assert saida == [False, True, False]


@pytest.mark.parametrize("tela", ["Reservar.tsx", "Agendar.tsx"])
def test_as_telas_usam_a_regra_e_nao_escolhem_o_servico_que_sobrou(tela):
    """Nenhuma das duas telas pode voltar a escolher "o único serviço do painel" por conta própria."""
    with open(os.path.join(PORTAL, tela), encoding="utf-8") as f:
        fonte = f.read()
    assert "servicoPreSelecionado(" in fonte, f"{tela} tem de usar a regra de preselecao.ts"
    assert "kartSemServico(" in fonte, f"{tela} tem de avisar quando o kart não tem serviço no painel"
    for ruim in (".services.length === 1 ? ", "services.length === 1 ? d.services[0]", "servicos.length === 1 ?"):
        assert ruim not in fonte, f"{tela}: escolher o serviço que sobrou é o defeito de #253 ({ruim})"
