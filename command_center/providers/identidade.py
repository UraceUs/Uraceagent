"""Quem é cliente, quem é a mesma pessoa, quem está ativo.

Regras do dono (04/09/2026):
- Nem tudo no Asana é cliente: corrida não é cliente.
- Ativo = teve serviço nos últimos 6 meses (ou tem serviço marcado);
  senão inativo.
- Um card por pessoa: mesmo e-mail, mesmo telefone ou nome igual/quase
  igual (Alonso/Alonzo) é a mesma pessoa. Casos duvidosos ficam para
  revisão humana (com ajuda da IA), nunca são unidos no escuro.

Regra do dono (22/09/2026), depois do card do David Pera:
- "Nunca colocar serviço de outro cliente em card de outro cliente."
  Na dúvida, card próprio com o nome como está no título.
- "O princípio para cruzar e confirmar é usar o nome do responsável e
  informações de contato." Primeiro nome do piloto parecido é SUSPEITA;
  e-mail, telefone ou responsável igual é CONFIRMAÇÃO (`mesmo_contato`).
"""
import json
import re
import unicodedata
from datetime import date, timedelta

from command_center.db import agora, inserir, todos, um

# palavras que denunciam evento/corrida/coisa, não pessoa
CORRIDA = re.compile(r"\b(series|tour|round|rd\s?\d|rd\d|nats|cup|championship|champions|grand prix|gp\b|race|races|"
                     r"kart center|raceway|speedway|motorsports? park|circuit|track|trackside|test day|practice day|"
                     r"skusa|rok\b|rotax|superkarts|usac|wka|f4\b|fia\b|winter|summer|spring|fall\b|festival|"
                     r"invoice|payment|order|shipping|suit|macac|template|created by|nothing is done|todo|checklist)\b", re.I)
SERVICO_SUFIXO = re.compile(r"\s*[\[({].*$")         # '[4 strokes]', '(created by…)', '{His own kart}'

# O quadro escreve "Piloto_Serviço [categoria]", mas nem sempre com separador. Estas
# palavras abrem a parte do SERVIÇO: da primeira delas em diante não é mais nome de
# gente. Dono, 22/09: "às vezes aparece junto, só separado por um espaço".
# Nunca cortam a PRIMEIRA palavra — "Summer" pode ser primeiro nome de alguém.
_PALAVRA_DE_SERVICO = {
    "lead", "follow", "leads", "practice", "pratice", "preatice", "pretice", "prep", "preparation",
    "trackside", "professional", "coach", "coaching", "racing", "race", "training", "program",
    "academy", "daily", "camp", "school", "session", "setup", "support", "suport", "suportt",
    "arrive", "drive", "test", "using", "use", "used", "motor", "chassi", "chassis", "kart",
    "karting", "engine", "weekend", "cup", "rwc", "skusa", "fwt", "rok", "uspks", "wka",
    "winter", "summer", "spring", "fall", "orlando", "bushnell", "okc", "vanderlan", "matt",
    "urace", "u-race", "tuesday", "monday", "wednesday", "thursday", "friday", "saturday", "sunday",
}
# Categoria/motor colados no nome: "Alex Xikis KA100", "Branson KA100sr".
# "jr" e "sr" NÃO entram: em "Thiago Belluci Sr" é sufixo de nome, não categoria.
# Quando são categoria vêm colados ("KA100sr") ou depois do serviço ("Rotax jr").
_RX_CATEGORIA = re.compile(r"^(ka\d+|x\d+|rok|vlr|gp|rotax|\d+t|mini|micro|junior|senior|cadet|"
                           r"shifter|kz\d*|briggs|lo206)\w*$", re.I)
# Inicial abreviada no fim do nome: "Charlie M", "Liam B", "Callan B.", "G.J".
_RX_INICIAL = re.compile(r"^[A-Za-zÀ-ÿ]\.?$")
_RX_SO_NUMERO = re.compile(r"^[\d/.\-|]+$")      # "01/09", "2026", "4|6": data ou contagem, nunca nome


def normaliza(txt):
    t = unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", t).split()


def so_digitos(tel):
    d = re.sub(r"\D", "", tel or "")
    return d[-10:] if len(d) >= 10 else (d or None)


# Rótulos do modelo de tarefa e nomes de serviço/corrida: NUNCA são gente.
# Nasceu de 10/09: a importação criou "Date of Birth:", "Karting School",
# "Professional Coaching" e "Lucas oil Laguna Seca" como clientes.
_ROTULOS = {"driver", "driver's name", "drivers name", "date of birth", "birth", "age", "height", "weight", "waist",
            "karting experience", "experience", "responsible", "responsible name", "email", "e-mail", "phone",
            "product", "invoice", "invoice link", "price", "security deposit", "service dates", "service date",
            "service dates for this month", "name", "notes", "tbd", "n/a", "na", "none", "-", "--"}
_SERVICOS = {"karting school", "kart school", "kart racing school", "professional coaching", "coaching",
             "arrive and drive", "urace daily", "urace academy", "academy", "summer camp", "test drive",
             "lead and follow", "race support", "trackside support", "trackside", "practice", "pratice",
             "session setup", "shipping orders", "kart setup", "new race", "race weekend", "track day"}
_RX_CORRIDA_EXTRA = re.compile(r"\b(skusa|uspks|rok|fwt|wka|rotax|superkarts|flkc|f4|nola|"                       # séries
                               r"laguna seca|mid[- ]ohio|road america|sebring|daytona|homestead|bushnell|lake erie|"  # pistas
                               r"new castle|barnesville|ozark|jacksonville|canadian tire|vir|okc|"
                               r"supernationals|winter series|pro tour|grand nationals|"
                               r"rd\s*\d|round\s*\d|race\s*\d|cup|series|championship|nationals|karting challenge)\b", re.I)


# Palavra solta que apareceu como "cliente" nas varreduras de 22/09 e não é gente:
# pista, série, marca de equipamento e recado de quadro. Vale como PRIMEIRA palavra.
_NAO_E_GENTE = {"trackhouse", "endurance", "florida", "guardar", "closed", "photos", "goals",
                "mycron", "skapa", "to-do", "todo", "amr", "jfc", "rmc", "ckna", "flkc",
                "van", "box", "old", "new", "no", "nao", "sim", "cancelado", "cancelled", "canceled",
                "pista", "galpao", "galpão", "ferramenta", "ferramentas", "bandeiras", "banners",
                "calendario", "calendário", "chassi", "chassis", "motor", "motores", "pneus",
                "faturas", "fatura", "invoices", "not", "going", "usf",   # USF Pro 2000: série
                # artigo nunca abre nome de gente: "The North Florida Kart Club"
                "the", "a", "an", "o", "os", "as", "um", "uma", "la", "el", "los"}

# Palavra que NUNCA aparece no nome de uma pessoa, em QUALQUER posição. Lista curta de
# propósito: cada uma destas inviabiliza o nome inteiro, então só entra o que não pode
# ser sobrenome de ninguém. ("Lucas Oil" é patrocinador de série, não o Lucas.)
_NUNCA_NO_NOME = {"oil", "club", "clube", "series", "championship", "motorplex", "kartplex",
                  "raceway", "speedway", "faturas", "invoices"}

# Palavra de ligação no meio denuncia FRASE, não nome: "Faturas a cobrar", "Buscar as
# coisas no Mauricio", "Lead and Follow". As partículas de nome em português ("de",
# "da", "do", "dos", "das") ficam de fora — "Maria de Souza" é gente.
_LIGACAO = {"a", "as", "o", "os", "e", "and", "the", "no", "na", "nos", "nas",
            "com", "para", "for", "in", "at", "of", "um", "uma"}


def eh_rotulo_ou_servico(texto):
    """True quando o 'nome' é rótulo do modelo, nome de serviço ou de corrida — não é gente."""
    t = re.sub(r"[:\-–]+\s*$", "", (texto or "").strip()).strip()
    if not t:
        return True
    baixo = t.lower()
    if baixo in _ROTULOS or baixo in _SERVICOS or baixo in _NAO_E_GENTE:
        return True
    if ":" in t:                                   # "Date of Birth: Age: 13" e afins
        return True
    if any(baixo.startswith(r + " ") or baixo.endswith(" " + r) for r in ("email", "phone", "age", "name")):
        return True
    if any(sv in baixo for sv in _SERVICOS):
        return True
    if _RX_CORRIDA_EXTRA.search(t) or CORRIDA.search(t):
        return True
    return False


def _corta_no_separador(t):
    """A parte que vem antes do separador de serviço.

    `_`, `|`, `:`, `,` e o hífen COM espaço separam sempre — é o padrão do quadro
    ("Piloto_Serviço_Categoria [n/t]"). A barra separa quando não está entre números
    ("Jude cook/Harley client" separa; "3/6" e "Junior/Senior" não). O hífen colado
    ("Elliott Hubbard-Summer Camp") é contextual (dono, 16/09): só separa quando o que
    vem depois tem cara de serviço ou tem número; "Jean-Luc Picard" e "Ana-Maria"
    continuam sendo um nome só."""
    t = t.replace("–", "-").replace("—", "-")            # travessão é hífen para esta leitura
    t = re.split(r"\s*[_|:]\s*|\s+-\s+|\s*,\s*", t)[0].strip()
    # hífen COLADO no nome mas com espaço depois ("Alex Savage- Old Chassis") separa
    # sempre: nome composto não tem espaço do outro lado ("Jean-Luc Picard").
    t = re.split(r"-\s+", t)[0].strip()
    t = re.split(r"(?<!\d)\s*/\s*(?!\d)", t)[0].strip()
    m = re.match(r"^([^-–]+?)[-–](.+)$", t)
    if m:
        antes, depois = m.group(1).strip(), m.group(2).strip()
        if antes and depois and (re.search(r"\d", depois) or eh_rotulo_ou_servico(depois)):
            t = antes
    return t


def _corta_na_palavra_de_servico(t):
    """Corta na primeira palavra que abre o serviço, da segunda em diante.

    "David Pera Using his own Kart" → "David Pera".
    "Callan Lead & Follow Vanderlan" → "Callan".
    Nunca corta na primeira palavra: senão "Summer Camp" viraria a pessoa "Summer"."""
    palavras = t.split()
    for i, p in enumerate(palavras):
        if i == 0:
            continue
        limpa = re.sub(r"[^A-Za-zÀ-ÿ0-9-]", "", p).lower()
        if limpa in _PALAVRA_DE_SERVICO:
            return " ".join(palavras[:i]).strip()
        if _RX_SO_NUMERO.match(p):          # "01/09", "03/08", "2026": data, não sobrenome
            return " ".join(palavras[:i]).strip()
    return t


def _tira_categoria(t):
    """Tira a categoria/motor colada no fim do nome: "Alex Xikis KA100" → "Alex Xikis"."""
    palavras = t.split()
    while len(palavras) > 1 and _RX_CATEGORIA.match(palavras[-1]):
        palavras.pop()
    return " ".join(palavras)


def _separa_grudado(t):
    """'MauricioPardomo' → 'Mauricio Pardomo'. Só quando é UMA palavra e a maiúscula
    aparece depois de minúscula — 'McDonald' e 'DeSouza' continuam inteiros porque
    o pedaço da frente teria menos de 3 letras."""
    if len(t.split()) != 1:
        return t
    partido = re.sub(r"(?<=[a-zà-ÿ])(?=[A-ZÀ-Þ])", " ", t)
    pedacos = partido.split()
    if len(pedacos) == 2 and all(len(x) >= 3 for x in pedacos):
        return partido
    return t


def _nome_plausivel(t):
    """O que sobrou tem cara de nome de gente?

    Uma palavra só VALE (dono, 22/09: metade do quadro é "Branson_…", "G.J_…",
    "Charlie_…"). O que segura o lixo não é a contagem de palavras, é o vocabulário:
    rótulo, serviço e corrida continuam sendo recusados antes de chegar aqui."""
    palavras = [p for p in t.split() if p]
    if not (1 <= len(palavras) <= 5):
        return False
    # Se a PRIMEIRA palavra já abre serviço, não sobrou pessoa nenhuma: "Lead and
    # Follow" cortaria em "Follow" e devolveria "Lead and". O corte por palavra de
    # serviço só vale quando existe um nome antes dele.
    limpas = [re.sub(r"[^A-Za-zÀ-ÿ0-9-]", "", x).lower() for x in palavras]
    if limpas[0] in (_PALAVRA_DE_SERVICO | _NAO_E_GENTE):
        return False
    if any(x in _NUNCA_NO_NOME for x in limpas):
        return False
    if any(x in _LIGACAO for x in limpas[1:]):
        return False
    if not all(re.match(r"^[A-Za-zÀ-ÿ'.&-]+$", p) for p in palavras):
        return False
    if len(palavras[0]) < 2:                     # inicial sozinha na frente não é nome
        return False
    # Inicial abreviada é normal no meio ("Bella M Wagner") e no fim ("Charlie M").
    # Na frente não: "M Wagner" sozinho não identifica ninguém — e isso já é barrado
    # pela regra acima, que exige 2 letras na primeira palavra.
    return True


def pessoa_do_titulo(titulo):
    """Nome da pessoa no título da tarefa, ou None quando não é gente.

    O quadro do Asana escreve o cliente ANTES do serviço, em quatro formas — e o dono
    mandou (22/09) a IA reconhecer as quatro, depois de achar 112 serviços de outras
    pessoas dentro do card do David Pera:

      'Aaron Benoit_Trackside Support'          → 'Aaron Benoit'   (underline)
      'Harley Keeble - Rotax [3/3]'             → 'Harley Keeble'  (hífen com espaço)
      'Alexander Jacoby | KA100'                → 'Alexander Jacoby' (barra vertical)
      'David Pera Using his own Kart'           → 'David Pera'     (só espaço)

    E ainda: primeiro nome sozinho ('Branson_Practice KA100' → 'Branson'), inicial
    abreviada ('Charlie M_Racing Program 3/6' → 'Charlie M'), categoria colada
    ('Alex Xikis KA100_Professional Coaching' → 'Alex Xikis') e barra entre pessoas
    ('Jude cook/Harley client - Kart proprio' → 'Jude cook').

    '2026 SKUSA Winter Series RD1/2 | …' → None: corrida não é gente.
    """
    t = (titulo or "").strip()
    t = re.sub(r"^\s*session setup\s*\|\s*", "", t, flags=re.I)
    t = re.sub(r"^\s*[\[(][^\])]*[\])]\s*", "", t)      # "[Canceled] Erik Mendoza Jr_…": a tag na frente sai
    t = SERVICO_SUFIXO.sub("", t)
    t = _corta_no_separador(t)
    t = _corta_na_palavra_de_servico(t)
    t = _separa_grudado(_tira_categoria(t).strip(" &-"))
    # a palavra de corrida/serviço que condena é a que está na PARTE DA PESSOA: "Mike
    # Fattuta_Professional Coach Rotax" tem gente antes do separador e serviço depois
    if not t or re.search(r"\d", t) or CORRIDA.search(t):
        return None
    if eh_rotulo_ou_servico(t):
        return None
    if not _nome_plausivel(t):
        return None
    # "Erik Mendoza Jr" é o Erik Mendoza (dono, 22/09) — no quadro, Jr marca a criança,
    # não faz parte do nome. "Sr" fica: é como o pai se distingue do filho.
    t = re.sub(r"\s+jr\.?$", "", t, flags=re.I)
    return " ".join(p if p.isupper() and len(p) > 3 else p for p in t.split()).title() if t.isupper() else t


def _lev(a, b):
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def mesmo_nome(a, b, folga=1):
    """Mesma pessoa pelo nome: primeiro nome igual e sobrenome igual ou a ≤folga
    letras de distância (Alonso/Alonzo, Pionti/Pionte). 'Renato Frota Pionti' ~ 'Renato Pionti'."""
    pa, pb = normaliza(a), normaliza(b)
    if len(pa) < 2 or len(pb) < 2 or pa[0] != pb[0]:
        return False
    if set(pa) & set(pb) >= {pa[0], pa[-1]} or set(pa) & set(pb) >= {pb[0], pb[-1]}:
        return True
    return _lev(pa[-1], pb[-1]) <= folga and abs(len(pa[-1]) - len(pb[-1])) <= 1


def chave_exata(nome):
    return " ".join(normaliza(nome))


# ------------------------------------------------------------- contato limpo
_RX_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def normaliza_email(texto):
    """'email%3apablo@x.com , bryan@x.com' -> ('pablo@x.com', 'bryan@x.com').
    Tira mailto:/email: (também codificados), separa por vírgula/espaço/';',
    devolve (principal, alternativo). Sem e-mail válido -> (None, None)."""
    from urllib.parse import unquote
    t = unquote(texto or "").replace("%3a", ":").replace("%3A", ":")
    t = re.sub(r"(?i)\b(mailto|e-?mail)\s*:\s*", " ", t)
    achados = []
    for e in _RX_EMAIL.findall(t):
        e = e.lower().strip(".")
        if e not in achados:
            achados.append(e)
    if not achados:
        return None, None
    return achados[0], (achados[1] if len(achados) > 1 else None)


def normaliza_telefone(texto):
    """Só o primeiro telefone, no formato que as pessoas leem: 305-609-7845 / +55 11 9…"""
    t = (texto or "").strip()
    if not t:
        return None
    m = re.search(r"\+?\d[\d\s().\-]{6,}\d", t)
    if not m:
        return None
    dig = re.sub(r"\D", "", m.group(0))
    if len(dig) == 10:
        return f"{dig[:3]}-{dig[3:6]}-{dig[6:]}"
    if len(dig) == 11 and dig.startswith("1"):
        return f"{dig[1:4]}-{dig[4:7]}-{dig[7:]}"
    return m.group(0).strip()


_RX_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def limpar_nascimentos(con):
    """Nascimento só vale como data ISO. Texto solto ("Age: 13") sai do campo (dono, 10/09)."""
    n = 0
    for c in todos(con, "SELECT id, pilot_dob FROM clients WHERE pilot_dob IS NOT NULL AND pilot_dob<>''"):
        if not _RX_ISO.match((c["pilot_dob"] or "").strip()[:10]):
            con.execute("UPDATE clients SET pilot_dob=NULL, updated_at=? WHERE id=?", (agora(), c["id"]))
            n += 1
    return n


def limpar_nomes_de_servico(con):
    """Nome de cliente que carrega o serviço junto ("Elliott Hubbard_Summer Camp 2026 1/4",
    "Mike Fattuta_Professional Coach Rotax") fica só com a pessoa. Dono, 16/09: a IA tem
    de saber diferenciar o nome do piloto do nome do serviço. Idempotente; quando o
    título não tem gente reconhecível, não mexe (isso é assunto de limpar_nao_clientes)."""
    n = 0
    for c in todos(con, "SELECT id, name, pilot_name FROM clients"):
        novo = {}
        for k in ("name", "pilot_name"):
            v = (c[k] or "").strip()
            if not v or not re.search(r"[_|:\[\]]|\s[-–]\s|\d", v):
                continue
            pessoa = pessoa_do_titulo(v)
            if pessoa and pessoa != v:
                novo[k] = pessoa
        if novo:
            sets = ", ".join(f"{k}=?" for k in novo)
            con.execute(f"UPDATE clients SET {sets}, updated_at=? WHERE id=?", (*novo.values(), agora(), c["id"]))
            n += 1
    return n


def limpar_contatos(con):
    """Passa a régua nos contatos já espelhados (idempotente): e-mail com lixo
    vira principal + alternativo; telefone legível. Devolve quantos mudou."""
    n = 0
    for c in todos(con, "SELECT id, email, email_alt, phone FROM clients"):
        principal, alt = normaliza_email(c["email"])
        if c["email"] and principal is None:          # texto sem e-mail nenhum: não inventa
            principal = None
        tel = normaliza_telefone(c["phone"]) if c["phone"] else None
        novo = {"email": principal if c["email"] else None, "email_alt": alt or c["email_alt"], "phone": tel if c["phone"] else None}
        if any(novo[k] != c[k] for k in novo):
            con.execute("UPDATE clients SET email=?, email_alt=?, phone=?, updated_at=? WHERE id=?",
                        (novo["email"], novo["email_alt"], novo["phone"], agora(), c["id"]))
            n += 1
    return n


# ------------------------------------------------------------- busca
def acha_pessoa(con, email=None, telefone=None, nome=None, piloto=None):
    """Cliente existente para esta identidade, na ordem de confiança."""
    if email:
        c = um(con, "SELECT * FROM clients WHERE email = ? AND kind<>?", (email.lower(), SEPARADO))
        if c:
            return c, "e-mail"
    tel = so_digitos(telefone)
    if tel:
        for c in todos(con, "SELECT * FROM clients WHERE phone IS NOT NULL AND kind<>?", (SEPARADO,)):
            if so_digitos(c["phone"]) == tel:
                return c, "telefone"
    for alvo, campo in ((piloto, "pilot_name"), (nome, "name")):
        if not alvo:
            continue
        k = chave_exata(alvo)
        for c in todos(con, "SELECT * FROM clients WHERE kind<>?", (SEPARADO,)):
            if k and (chave_exata(c["pilot_name"]) == k or chave_exata(c["name"]) == k):
                return c, f"{campo} igual"
        for c in todos(con, "SELECT * FROM clients WHERE kind<>?", (SEPARADO,)):
            if (c["pilot_name"] and mesmo_nome(alvo, c["pilot_name"])) or mesmo_nome(alvo, c["name"]):
                return c, f"{campo} quase igual"
    return None, None


# --------------------------------------------- quem aponta para o cliente
# Tabelas com client_id que ACEITA vazio (repontar ou soltar) e as que EXIGEM
# cliente (bloqueiam a remoção: alguém agiu ali e não se apaga sem decisão humana).
LIGACOES_SOLTAVEIS = ("tasks", "waivers", "emails", "invoices", "calendar_events", "ai_workflows", "ai_events", "crm_leads")
LIGACOES_OBRIGATORIAS = ("race_invites", "contracts")


def _repontar(con, de_id, para_id):
    """Passa tudo do cliente `de_id` para `para_id` (união)."""
    for t in LIGACOES_SOLTAVEIS + LIGACOES_OBRIGATORIAS:
        try:
            con.execute(f"UPDATE OR IGNORE {t} SET client_id=? WHERE client_id=?", (para_id, de_id))
            con.execute(f"DELETE FROM {t} WHERE client_id=?", (de_id,)) if t in LIGACOES_OBRIGATORIAS else None
        except Exception:
            pass


def _soltar(con, cid):
    """Solta o vínculo com o cliente `cid` no que aceita vazio. Devolve False quando
    alguma tabela EXIGE cliente (aí não se apaga)."""
    for t in LIGACOES_OBRIGATORIAS:
        try:
            if um(con, f"SELECT 1 FROM {t} WHERE client_id=?", (cid,)):
                return False
        except Exception:
            pass
    for t in LIGACOES_SOLTAVEIS:
        try:
            con.execute(f"UPDATE {t} SET client_id=NULL WHERE client_id=?", (cid,))
        except Exception:
            pass
    con.execute("DELETE FROM entity_links WHERE entity_type='client' AND entity_id=?", (str(cid),))
    return True


# ------------------------------------------------------------- unir
def unir(con, keep_id, drop_id, por, motivo):
    """Um card só: tudo do duplicado passa para o principal; o duplicado sai do espelho."""
    if keep_id == drop_id:
        return
    k = um(con, "SELECT * FROM clients WHERE id=?", (keep_id,)); d = um(con, "SELECT * FROM clients WHERE id=?", (drop_id,))
    if not k or not d:
        return
    _repontar(con, drop_id, keep_id)
    con.execute("UPDATE OR IGNORE entity_links SET entity_id=? WHERE entity_type='client' AND entity_id=?", (str(keep_id), str(drop_id)))
    con.execute("DELETE FROM entity_links WHERE entity_type='client' AND entity_id=?", (str(drop_id),))
    # completa o principal com o que só o duplicado tinha
    campos = {}
    for c in ("email", "phone", "pilot_name", "pilot_dob", "company", "notes"):
        if not k[c] and d[c]:
            campos[c] = d[c]
    if d["vip"] and not k["vip"]:
        campos["vip"] = 1
    if campos:
        sets = ", ".join(f"{c}=?" for c in campos)
        con.execute(f"UPDATE clients SET {sets}, updated_at=? WHERE id=?", (*campos.values(), agora(), keep_id))
    inserir(con, "client_merges", keep_id=keep_id, drop_id=drop_id, drop_name=d["name"], drop_json=json.dumps(d, ensure_ascii=False, default=str),
            merged_by=por, reason=motivo)
    con.execute("DELETE FROM clients WHERE id=?", (drop_id,))


def deduplicar(con, por="sync"):
    """Une o que é certamente a mesma pessoa: mesmo e-mail, mesmo telefone,
    ou nome normalizado idêntico. Devolve quantos uniu."""
    n = 0
    for chave, sql in (("email", "SELECT LOWER(email) AS k, GROUP_CONCAT(id) AS ids FROM clients WHERE email IS NOT NULL AND email<>'' GROUP BY LOWER(email) HAVING COUNT(*)>1"),):
        for g in todos(con, sql):
            ids = sorted(int(i) for i in g["ids"].split(","))
            for dup in ids[1:]:
                unir(con, ids[0], dup, por, f"mesmo {chave}: {g['k']}"); n += 1
    vistos = {}
    for c in todos(con, "SELECT id, phone FROM clients WHERE phone IS NOT NULL ORDER BY id"):
        t = so_digitos(c["phone"])
        if not t:
            continue
        if t in vistos and um(con, "SELECT id FROM clients WHERE id=?", (vistos[t],)):
            unir(con, vistos[t], c["id"], por, f"mesmo telefone: {t}"); n += 1
        else:
            vistos[t] = c["id"]
    vistos = {}
    for c in todos(con, "SELECT id, name, pilot_name FROM clients ORDER BY id"):
        for k in {chave_exata(c["name"]), chave_exata(c["pilot_name"])} - {""}:
            if k in vistos and vistos[k] != c["id"] and um(con, "SELECT id FROM clients WHERE id=?", (vistos[k],)) and um(con, "SELECT id FROM clients WHERE id=?", (c["id"],)):
                unir(con, vistos[k], c["id"], por, f"mesmo nome: {k}"); n += 1
                break
            vistos.setdefault(k, c["id"])
    return n


def parecido(a, b):
    """Mais largo que mesmo_nome — SÓ para sugerir duplicados a uma pessoa, nunca
    para unir sozinho: primeiro nome com uma letra de diferença (Brian/Bryan),
    sobrenome igual; ou um nome contido no outro (Brian Santiago ⊂ Brian S. Santiago Jr)."""
    if mesmo_nome(a, b):
        return True
    pa, pb = normaliza(a), normaliza(b)
    if len(pa) < 2 or len(pb) < 2:
        return False
    if set(pa) <= set(pb) or set(pb) <= set(pa):
        return True
    return len(pa[0]) >= 4 and len(pb[0]) >= 4 and _lev(pa[0], pb[0]) <= 1 and pa[-1] == pb[-1]


def _nomes(c):
    return [n for n in (c.get("pilot_name"), c.get("name")) if n and len(normaliza(n)) >= 2]


def mesmo_contato(a, b):
    """O que CONFIRMA que dois cards são a mesma pessoa, na regra do dono (22/09):
    mesmo e-mail, mesmo telefone ou mesmo responsável. Devolve o motivo, ou None.
    Nome de piloto parecido não entra aqui — isso é só suspeita."""
    ea, eb = (a.get("email") or "").strip().lower(), (b.get("email") or "").strip().lower()
    if ea and ea == eb:
        return f"mesmo e-mail: {ea}"
    ta, tb = so_digitos(a.get("phone")), so_digitos(b.get("phone"))
    if ta and ta == tb:
        return f"mesmo telefone: {a.get('phone')}"
    ra, rb = chave_exata(a.get("name")), chave_exata(b.get("name"))
    if ra and ra == rb and len(ra.split()) >= 2:
        return f"mesmo responsável: {a.get('name')}"
    return None


def candidatos_duplicados(con, para=None):
    """Pares que PARECEM a mesma pessoa (Alonso/Alonzo, Brian/Bryan, piloto de um =
    responsável do outro) — decisão humana, com a IA ajudando. `para` restringe a um cliente."""
    cs = todos(con, "SELECT id, name, pilot_name, email, phone FROM clients WHERE kind<>? ORDER BY name", (SEPARADO,))
    pares, vistos = [], set()
    # Princípio do dono (22/09): "para cruzar e confirmar, use o nome do responsável e
    # as informações de contato". Mesmo e-mail ou mesmo telefone é a evidência mais
    # forte que existe — e vem ANTES do nome parecido.
    for i, a in enumerate(cs):
        for b in cs[i + 1:]:
            if para and para not in (a["id"], b["id"]):
                continue
            porque = mesmo_contato(a, b)
            if porque and (a["id"], b["id"]) not in vistos:
                vistos.add((a["id"], b["id"]))
                pares.append({"a": a, "b": b, "why": porque, "forte": True})
    for i, a in enumerate(cs):
        for b in cs[i + 1:]:
            if para and para not in (a["id"], b["id"]):
                continue
            for na in _nomes(a):
                for nb in _nomes(b):
                    if chave_exata(na) != chave_exata(nb) and parecido(na, nb) and (a["id"], b["id"]) not in vistos:
                        vistos.add((a["id"], b["id"]))
                        pares.append({"a": a, "b": b, "why": f"nomes quase iguais: '{na}' × '{nb}'"})
    return pares[:200]


# ------------------------------------------------------------- limpeza e status
SEPARADO = "separado"          # clients.kind: não é cliente (corrida, tarefa, rótulo); fica, mas fora da lista


def limpar_nao_clientes(con):
    """SEPARA (não apaga) o que virou 'cliente' sem ser gente — corrida, evento, tarefa,
    rótulo do modelo — e não tem nada humano ligado (e-mail, telefone, waiver, VIP).

    Até 22/09 apagava. Dono: "pode só separar". O card fica com kind='separado', sai
    da lista de clientes e de toda busca de identidade; os serviços que apontavam para
    ele ficam sem dono (a atribuição decide depois). Quem tem convite de corrida ou
    contrato não é tocado: alguém agiu ali."""
    n = 0
    for c in todos(con, "SELECT * FROM clients WHERE source='asana' AND kind<>?", (SEPARADO,)):
        falso = eh_rotulo_ou_servico(c["name"]) or (c["pilot_name"] and eh_rotulo_ou_servico(c["pilot_name"]))
        if not falso and (pessoa_do_titulo(c["name"]) or c["email"] or c["phone"] or c["vip"]):
            continue
        if um(con, "SELECT 1 FROM waivers WHERE client_id=?", (c["id"],)) or um(con, "SELECT 1 FROM emails WHERE client_id=?", (c["id"],)):
            continue
        if not _soltar(con, c["id"]):
            continue                                   # tem convite de corrida ou contrato: alguém agiu
        con.execute("UPDATE clients SET kind=?, updated_at=? WHERE id=?", (SEPARADO, agora(), c["id"]))
        n += 1
    return n


def recalcular_status(con, meses=6):
    """ACTIVE = serviço nos últimos 6 meses ou agendado; INACTIVE = mais antigo. Respeita status travado à mão."""
    corte = (date.today() - timedelta(days=30 * meses)).isoformat()
    hoje = date.today().isoformat()
    for c in todos(con, "SELECT id, status, status_locked FROM clients"):
        ult = um(con, "SELECT MAX(due_on) AS d FROM tasks WHERE client_id=? AND due_on IS NOT NULL", (c["id"],))["d"]
        con.execute("UPDATE clients SET last_service_at=? WHERE id=?", (ult, c["id"]))
        if c["status_locked"]:
            continue
        novo = "ACTIVE" if ult and (ult >= corte or ult >= hoje) else "INACTIVE"
        if novo != c["status"] and c["status"] not in ("AT_RISK", "PENDING", "NEW", "COMPLETED"):
            con.execute("UPDATE clients SET status=?, updated_at=? WHERE id=?", (novo, agora(), c["id"]))
        elif c["status"] in ("NEW", "PENDING") and ult and ult < corte:
            con.execute("UPDATE clients SET status='INACTIVE', updated_at=? WHERE id=?", (agora(), c["id"]))
