"""Prateleiras do estoque — como a peça aparece na tela, e quanto ela custa para o cliente.

Dono, 29/09: *"a visualização que eu quero no estoque é por cards, separados em fileiras
horizontais de categorias"* — pneus numa, motores noutra, peças de motor, hardware…, e
vestuário (bonés, suits, camisetas, moletons) **na última** (a fileira "Alpha Line"). Dentro de cada fileira, as
subcategorias: pneu por marca e medida, motor por família.

As listas de marca, medida e família saem da **apostila de kartismo da equipe** (11/06):
são o vocabulário que a equipe já usa, não um catálogo inventado. São **sugestões** —
o campo aceita qualquer texto, porque a peça que ninguém previu também existe.

Prateleira é **onde a peça aparece**, não o que ela é: o `kind` (e com ele o controle por
número de série) é decidido no cadastro e não muda quando alguém troca a prateleira.
Peça antiga, sem prateleira escolhida, ganha uma **sugestão pelo nome** — só na tela; o
banco não é reescrito por palpite.
"""
import re

# Ordem = ordem das fileiras na tela. Vestuário por último: pedido do dono.
PRATELEIRAS = [
    {"code": "pneus", "nome": "Pneus", "kind": "pneu", "unit": "jogo",
     "subcategorias": ["MG", "Evinco", "LeVanto", "Leconte", "Bridgestone", "Maxxis", "MOJO"],
     "medidas": ["4.60-5", "7.10-5", "6.00-5", "4.20-5"],
     "dica": "marca · medida · composto (SH2 vermelho, SM2 amarelo, SW2 chuva)"},
    {"code": "motores", "nome": "Motores", "kind": "motor", "unit": "un",
     "subcategorias": ["IAME", "Vortex ROK", "Rotax", "OKN", "Shifter (KZ)", "Tillotson",
                       "Briggs L206", "Predator"],
     "medidas": ["60cc", "100cc", "125cc", "206cc", "212cc", "225cc"],
     "dica": "família · modelo (KA100, X30, Mini Swift, VLR, GP, DD2…)"},
    {"code": "pecas-motor", "nome": "Peças de motor", "kind": "peca", "unit": "un",
     "subcategorias": ["Carburador Tillotson", "Carburador Dellorto", "Escape / header", "Vela",
                       "Embreagem", "Pistão e anéis", "Juntas", "Radiador", "Filtro"],
     "medidas": [], "dica": "de qual motor é (IAME, ROK, Rotax…)"},
    {"code": "chassis", "nome": "Chassis", "kind": "chassi", "unit": "un",
     "subcategorias": ["Tony Kart", "Parolin", "Birel ART"],
     "medidas": ["Baby", "Mini / Micro", "Adulto (401T)", "Shifter"], "dica": ""},
    {"code": "hardware", "nome": "Hardware e chassi", "kind": "peca", "unit": "un",
     "subcategorias": ["Corrente", "Coroa / pinhão", "Freio", "Direção", "Eixo e rolamentos",
                       "Rodas e cubos", "Para-choque e carenagem", "Banco", "Parafusos e porcas"],
     "medidas": [], "dica": "corrente, coroa, pastilha, terminal, parafuso…"},
    {"code": "fluidos", "nome": "Combustível e óleo", "kind": "peca", "unit": "litro",
     "subcategorias": ["Combustível", "Óleo 2 tempos", "Óleo 4 tempos", "Lubrificante de corrente"],
     "medidas": [], "dica": ""},
    {"code": "eletronica", "nome": "Telemetria e eletrônica", "kind": "peca", "unit": "un",
     "subcategorias": ["MyChron", "Sensores", "Baterias", "Chicote"], "medidas": [], "dica": ""},
    {"code": "outros", "nome": "Outros", "kind": "peca", "unit": "un",
     "subcategorias": ["Adesivos", "Ferramentas", "Oficina"], "medidas": [], "dica": ""},
    # 29/09: a fileira se chama "Alpha Line" — boné, camisa, moletom e o macacão
    # standard da URACE. O código continua 'vestuario' (é o que fica gravado na peça).
    {"code": "vestuario", "nome": "Alpha Line", "kind": "peca", "unit": "un",
     "subcategorias": ["Bonés", "Camisetas", "Moletons", "Macacões", "Luvas", "Capacetes"],
     "medidas": ["PP", "P", "M", "G", "GG", "XG", "Infantil"], "dica": "tipo · tamanho"},
]
POR_CODIGO = {p["code"]: p for p in PRATELEIRAS}
CODIGOS = tuple(POR_CODIGO)

# Palavra do nome → prateleira. Só para a SUGESTÃO de peça antiga sem prateleira.
_PISTAS = [
    ("vestuario", r"\b(suit|shirt|camis|bon[eé]|cap|hoodie|moletom|jacket|glove|luva|helmet|capacete|macac[aã]o)"),
    ("pneus", r"\b(tire|tires|pneu|evinco|levanto|leconte|mojo|sh2|sm2|sw2)"),
    ("fluidos", r"\b(fuel|combust|oil|[oó]leo|mix)\b"),
    ("pecas-motor", r"\b(spark|plug|vela|carb|carburador|clutch|embreagem|piston|pist[aã]o|header|exhaust|escape|radiator|radiador|gasket|junta|filter|filtro)"),
    ("eletronica", r"\b(mychron|sensor|battery|bateria|telemetr)"),
    ("hardware", r"\b(chain|corrente|sprocket|coroa|pinh[aã]o|brake|freio|pads?|pastilha|tie rod|terminal|steering|dire[cç][aã]o|axle|eixo|bearing|rolamento|hub|cubo|wheel|roda|rim|bumper|para-choque|bolt|parafuso|nut|porca|seat|banco|pedal|cable|cabo|sidepod|nassau|nose|floor)"),
    ("outros", r"\b(sticker|adesivo)"),
]
_KIND_PARA_PRATELEIRA = {"pneu": "pneus", "motor": "motores", "chassi": "chassis"}


def sugerir(kind, nome):
    """Em que fileira uma peça sem prateleira escolhida deve aparecer."""
    if kind in _KIND_PARA_PRATELEIRA:
        return _KIND_PARA_PRATELEIRA[kind]
    t = (nome or "").lower()
    for code, rx in _PISTAS:
        if re.search(rx, t):
            return code
    return "outros"


def prateleira_de(item):
    """(código, sugerida?) — a escolhida por gente, ou a sugestão pelo nome."""
    cat = item.get("category") if hasattr(item, "get") else item["category"]
    if cat in POR_CODIGO:
        return cat, False
    return sugerir(item["kind"], item["name"]), True


# ---------------------------------------------------------------- preço para o cliente
class MargemInvalida(ValueError):
    pass


def ler_margem(texto):
    """O campo livre de margem: "15%", "20", "$20", "15% + 10". Devolve [(tipo, valor)].

    Número sozinho é **valor fixo** em dólar; porcentagem leva o %. É o que o dono
    descreveu (29/09): *"15%… ou às vezes um valor fixo"*. A tela mostra o preço final
    antes de salvar, então a leitura nunca fica escondida.
    """
    t = (texto or "").strip()
    if not t:
        return []
    partes = []
    for bruto in re.split(r"\s*\+\s*", t.lstrip("+").strip()):
        p = bruto.replace("US$", "").replace("$", "").replace(" ", "").replace(",", ".")
        m = re.fullmatch(r"(\d+(?:\.\d+)?)(%?)", p)
        if not m:
            raise MargemInvalida(f"Não entendi a margem “{texto}”. Use 15% (porcentagem) ou 20 (valor fixo em dólar).")
        partes.append(("pct" if m.group(2) else "fixo", float(m.group(1))))
    return partes


def preco_final(custo, margem):
    """Custo + margem. Sem custo, ou sem margem, não há o que calcular: None."""
    if custo is None:
        return None
    partes = ler_margem(margem)
    if not partes:
        return None
    v = float(custo)
    for tipo, x in partes:
        v = v * (1 + x / 100) if tipo == "pct" else v + x
    return round(v, 2)
