"""Área do cliente (#40) — as regras. As rotas moram em `api/portal.py`.

Dono, 30/09: *"uma área do cliente: dados do responsável e do piloto (pode ser uma criança
que está fazendo a conta, ou um adulto); tem que ser maior de idade, de acordo com as leis
dos Estados Unidos, para poder gerenciar a conta; perfil do piloto com medidas, idade,
e-mail, telefone, endereço; o cliente consegue atualizar"*.

- **Maioridade**: quem abre e gerencia a conta tem 18 anos ou mais (a idade de maioridade
  na Flórida e na quase totalidade dos estados). O piloto pode ter qualquer idade.
- **Medidas** em unidades dos EUA (polegadas e libras) e tamanhos como o fornecedor pede.
  Toda troca de medida carimba a data: criança cresce, e macacão se faz pela medida nova.
- **Nada aqui fala com o site interno sozinho**: a conta nasce sem vínculo. Quem liga a
  conta ao cliente do painel é a equipe (#42).

Dono, 01/10 (#54):
- os campos do responsável são **obrigatórios**, e o cliente pode ser de **outro país**:
  o telefone tem código de país (padrão +1) e o CEP só segue o formato americano nos EUA;
- no piloto são obrigatórios o nome completo, a data de nascimento, altura, peso, peito,
  cintura e a **experiência com kart**. Quadril e rede social são opcionais (dono, 01/10:
  *"tire hips das medidas obrigatórias"*);
- *"a cada trinta começa os avisos, com sessenta já tem que estar atualizado"*: medida com
  30 dias pede atualização; com 60, o piloto não marca sessão até atualizar. Salvar o
  formulário com as medidas confirma que estão certas (renova a data, mesmo sem mudar).
"""
import json
import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from command_center.db import agora, atualizar, inserir, todos, um
from command_center.providers import identidade

FUSO = ZoneInfo("America/New_York")
MAIORIDADE = 18

# chave -> (tipo, mínimo, máximo) · número em polegadas/libras; texto é tamanho do fornecedor
MEDIDAS = {
    "height_in": ("num", 20, 90), "weight_lb": ("num", 20, 450),
    "chest_in": ("num", 15, 70), "waist_in": ("num", 15, 70), "hips_in": ("num", 15, 70),
    "inseam_in": ("num", 10, 45), "sleeve_in": ("num", 10, 45),
    "suit_size": ("txt", 1, 12), "helmet_size": ("txt", 1, 12), "glove_size": ("txt", 1, 12),
    "shoe_size": ("txt", 1, 12),
}
MEDIDAS_OBRIGATORIAS = ("height_in", "weight_lb", "chest_in", "waist_in")   # quadril opcional (dono, 01/10)
MEDIDAS_AVISO_DIAS = 30
MEDIDAS_LIMITE_DIAS = 60
CAMPOS_CONTA = ("name", "birth_date", "phone_country", "phone", "address_line1", "address_line2", "city", "state", "zip",
                "country")
OBRIGATORIOS_CONTA = ("name", "birth_date", "phone", "address_line1", "city")
CAMPOS_PILOTO = ("name", "birth_date", "email", "phone", "notes", "social")
_PAIS = re.compile(r"^[A-Z]{2}$")
_DDI = re.compile(r"^\+\d{1,4}$")
_SOCIAL = re.compile(r"^(@[A-Za-z0-9._]{1,30}|https?://[^\s]{4,200})$")
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[A-Za-z]{2,}$")


class ErroPortal(ValueError):
    """Mensagem em inglês: é o que o cliente lê."""


def hoje():
    return datetime.now(FUSO).date()


def idade(nascimento, em=None):
    em = em or hoje()
    return em.year - nascimento.year - ((em.month, em.day) < (nascimento.month, nascimento.day))


def _data(v, campo):
    try:
        d = date.fromisoformat((v or "").strip()[:10])
    except ValueError:
        raise ErroPortal(f"{campo}: use a valid date.")
    if d > hoje():
        raise ErroPortal(f"{campo} can't be in the future.")
    if d.year < 1900:
        raise ErroPortal(f"{campo}: use a valid date.")
    return d


def _texto(v, n=120):
    v = re.sub(r"\s+", " ", (v or "").strip())
    return v[:n] or None


def email_valido(e):
    e = (e or "").strip().lower()
    if not _EMAIL.match(e):
        raise ErroPortal("Enter a valid email address.")
    return e


def ddi(v):
    """Código do país do telefone: '+1', '55' → '+55'. Padrão +1 (EUA e Canadá)."""
    t = (v or "").strip().replace(" ", "")
    if not t:
        return "+1"
    t = t if t.startswith("+") else "+" + t
    if not _DDI.match(t):
        raise ErroPortal("Country code: use + and up to 4 digits, like +1 or +55.")
    return t


def telefone(v, codigo="+1"):
    """+1: 10 dígitos (407-555-0142, o formato que o painel cruza). Outro país: o número
    com o código na frente (+55 11 98765 4321), de 6 a 14 dígitos."""
    if not (v or "").strip():
        return None
    dig = re.sub(r"\D", "", v)
    if codigo == "+1":
        if len(dig) == 11 and dig.startswith("1"):
            dig = dig[1:]
        t = identidade.normaliza_telefone(dig)
        if len(dig) != 10 or not t:
            raise ErroPortal("Enter a valid phone number, with area code.")
        return t
    if v.strip().startswith(codigo) and dig.startswith(codigo[1:]):
        dig = dig[len(codigo) - 1:]                       # o cliente digitou o código de novo
    if not 6 <= len(dig) <= 14:
        raise ErroPortal("Enter a valid phone number for your country.")
    return f"{codigo} {dig}"


def pais(v):
    t = (v or "US").strip().upper()
    if not _PAIS.match(t):
        raise ErroPortal("Choose your country.")
    return t


def _endereco(d):
    """Nos EUA: estado com 2 letras e ZIP de 5 dígitos (ou 5+4). Fora: região e código
    postal livres (letras, números, espaço e hífen)."""
    s = {k: _texto(d.get(k), 80) for k in ("address_line1", "address_line2", "city")}
    p = pais(d.get("country"))
    estado = _texto(d.get("state"), 30)
    cep = _texto(d.get("zip"), 12)
    if p == "US":
        if estado and not re.fullmatch(r"[A-Za-z]{2}", estado):
            raise ErroPortal("State: use the 2-letter code, like FL.")
        estado = estado.upper() if estado else None
        if cep and not re.fullmatch(r"\d{5}(-\d{4})?", cep):
            raise ErroPortal("ZIP code: use 5 digits (or 5+4).")
    elif cep and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 \-]{1,10}", cep):
        raise ErroPortal("Postal code: use letters, numbers, spaces or hyphens.")
    return {**s, "state": estado, "zip": cep.upper() if cep and p != "US" else cep, "country": p}


def faltando_conta(c):
    """O que falta no cadastro do responsável. Nos EUA, estado e ZIP também."""
    falta = [k for k in OBRIGATORIOS_CONTA if not c.get(k)]
    if (c.get("country") or "US") == "US":
        falta += [k for k in ("state", "zip") if not c.get(k)]
    return falta


def medidas(d):
    """Só as chaves conhecidas; número dentro de uma faixa humana; vazio sai."""
    if d is None:
        return None
    if not isinstance(d, dict):
        raise ErroPortal("Measurements are invalid.")
    saida = {}
    for k, v in d.items():
        if k not in MEDIDAS or v in (None, ""):
            continue
        tipo, mi, ma = MEDIDAS[k]
        if tipo == "num":
            try:
                n = round(float(str(v).replace(",", ".")), 1)
            except ValueError:
                raise ErroPortal(f"{k.replace('_', ' ')}: enter a number.")
            if not mi <= n <= ma:
                raise ErroPortal(f"{k.replace('_', ' ')}: {n:g} looks wrong.")
            saida[k] = n
        else:
            t = _texto(str(v), ma)
            if t:
                saida[k] = t
    return saida


# ------------------------------------------------------------------ conta
_ROTULO_CONTA = {"name": "full name", "birth_date": "date of birth", "phone": "phone", "address_line1": "street address",
                 "city": "city", "state": "state", "zip": "ZIP code"}


def _exige_conta(c):
    falta = faltando_conta(c)
    if falta:
        raise ErroPortal("Please fill in: " + ", ".join(_ROTULO_CONTA[k] for k in falta) + ".")


def _nome_completo(v, quem="your"):
    nome = _texto(v)
    if not nome or len(nome) < 3 or len(nome.split()) < 2:
        raise ErroPortal(f"Enter {quem} full name (first and last).")
    return nome


def criar_conta(con, dados, pw_salt, pw_hash):
    if not dados.get("accept_terms"):
        raise ErroPortal("You need to accept the terms to create an account.")
    email = email_valido(dados.get("email"))
    nome = _nome_completo(dados.get("name"))
    nasc = _data(dados.get("birth_date"), "Date of birth")
    if idade(nasc) < MAIORIDADE:
        raise ErroPortal("The account holder must be 18 or older. A parent or guardian can "
                         "create the account and add the young driver to it.")
    codigo = ddi(dados.get("phone_country"))
    novo = {"name": nome, "birth_date": nasc.isoformat(), "phone_country": codigo,
            "phone": telefone(dados.get("phone"), codigo), **_endereco(dados)}
    _exige_conta(novo)
    if um(con, "SELECT 1 AS x FROM portal_accounts WHERE email=?", (email,)):
        raise ErroPortal("An account with this email already exists. Sign in instead.")
    cid = inserir(con, "portal_accounts", email=email, pw_salt=pw_salt, pw_hash=pw_hash, terms_accepted_at=agora(), **novo)
    if dados.get("i_am_driver"):
        # o próprio responsável como piloto: nasce sem medidas — o painel pede para completar
        criar_piloto(con, cid, {"name": nome, "birth_date": nasc.isoformat(), "is_self": True,
                                "email": email, "phone": novo["phone"]}, completo=False)
    return cid


def conta(con, cid):
    c = um(con, """SELECT id, email, name, birth_date, phone_country, phone, address_line1, address_line2, city, state, zip,
                          country, client_id, linked_at, created_at FROM portal_accounts WHERE id=? AND active=1""", (cid,))
    if not c:
        raise ErroPortal("Account not found.")
    c = dict(c)
    c["phone_country"] = c["phone_country"] or "+1"
    return {**c, "linked": bool(c["client_id"]), "missing": faltando_conta(c), "drivers": pilotos(con, cid)}


def atualizar_conta(con, cid, dados):
    mud = {}
    if "name" in dados:
        nome = _texto(dados["name"])
        if not nome or len(nome) < 3:
            raise ErroPortal("Enter your full name.")
        mud["name"] = nome
    if "birth_date" in dados:
        nasc = _data(dados["birth_date"], "Date of birth")
        if idade(nasc) < MAIORIDADE:
            raise ErroPortal("The account holder must be 18 or older.")
        mud["birth_date"] = nasc.isoformat()
    atual = um(con, "SELECT * FROM portal_accounts WHERE id=?", (cid,))
    if "phone" in dados or "phone_country" in dados:
        codigo = ddi(dados.get("phone_country", atual["phone_country"]))
        mud["phone_country"] = codigo
        mud["phone"] = telefone(dados.get("phone", atual["phone"]), codigo)
    end = ("address_line1", "address_line2", "city", "state", "zip", "country")
    if any(k in dados for k in end):
        mud.update(_endereco({**{k: atual[k] for k in end}, **{k: dados[k] for k in dados if k in end}}))
    # o que é obrigatório não pode ser apagado (conta antiga incompleta pode completar aos poucos)
    for k in OBRIGATORIOS_CONTA + ("state", "zip"):
        if k in mud and not mud[k] and atual[k] and (k not in ("state", "zip") or (mud.get("country") or atual["country"]) == "US"):
            raise ErroPortal(f"The {_ROTULO_CONTA[k]} is required.")
    mud = {k: v for k, v in mud.items() if atual[k] != v}
    if mud:
        atualizar(con, "portal_accounts", cid, **mud, updated_at=agora())
    return sorted(mud)


# ------------------------------------------------------------------ pilotos
def _dias_desde(iso):
    if not iso:
        return None
    t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (hoje() - t.astimezone(FUSO).date()).days


def faltando_piloto(p):
    m = p.get("measures") or {}
    falta = [k for k in ("name", "birth_date") if not p.get(k)]
    if p.get("name") and len(p["name"].split()) < 2:
        falta.append("name")
    falta += [k for k in MEDIDAS_OBRIGATORIAS if m.get(k) in (None, "")]
    if not (p.get("notes") or "").strip():
        falta.append("experience")
    return falta


def situacao_medidas(p):
    """ok · aviso (30+ dias) · vencida (60+ dias) · faltando (sem o obrigatório)."""
    if faltando_piloto(p):
        return "faltando", None
    dias = _dias_desde(p.get("measures_updated_at"))
    if dias is None or dias >= MEDIDAS_LIMITE_DIAS:
        return "vencida", dias
    return ("aviso" if dias >= MEDIDAS_AVISO_DIAS else "ok"), dias


def pilotos(con, cid):
    saida = []
    for p in todos(con, """SELECT p.id, p.name, p.birth_date, p.is_self, p.email, p.phone, p.measures, p.measures_updated_at,
                                  p.notes, p.social,
                                  (SELECT MAX(b.date) FROM bookings b WHERE b.pilot_id=p.id AND b.status='confirmada'
                                      AND b.date<=?) AS last_session
                             FROM portal_pilots p WHERE p.account_id=? AND p.active=1 ORDER BY p.is_self DESC, p.id""",
                   (hoje().isoformat(), cid)):
        p = dict(p)
        p["measures"] = json.loads(p["measures"]) if p["measures"] else {}
        p["age"] = idade(date.fromisoformat(p["birth_date"])) if p["birth_date"] else None
        p["is_self"] = bool(p["is_self"])
        p["missing"] = faltando_piloto(p)
        p["measures_status"], p["measures_days"] = situacao_medidas(p)
        p["days_since_last_session"] = (hoje() - date.fromisoformat(p["last_session"])).days if p["last_session"] else None
        saida.append(p)
    return saida


def pode_marcar(con, cid, pid):
    """Antes de marcar: cadastro do responsável completo e piloto com as medidas em dia.
    Devolve a mensagem para o cliente, ou None."""
    c = um(con, "SELECT * FROM portal_accounts WHERE id=?", (cid,))
    if c and faltando_conta(c):
        return "Please complete the account holder details (Account) before booking."
    p = next((x for x in pilotos(con, cid) if x["id"] == pid), None)
    if not p:
        return None                                   # quem trata piloto inexistente é a agenda
    if p["measures_status"] == "faltando":
        return f"Please complete {p['name']}'s profile (measurements and karting experience) before booking."
    if p["measures_status"] == "vencida":
        return (f"{p['name']}'s measurements are more than {MEDIDAS_LIMITE_DIAS} days old. "
                "Please review and save them in Drivers before booking.")
    return None


def _dados_piloto(d, parcial=False):
    s = {}
    if not parcial or "name" in d:
        s["name"] = _nome_completo(d.get("name"), "the driver's")
    if "birth_date" in d:
        s["birth_date"] = _data(d["birth_date"], "Driver's date of birth").isoformat() if d["birth_date"] else None
    if "email" in d:
        s["email"] = email_valido(d["email"]) if (d["email"] or "").strip() else None
    if "phone" in d:
        s["phone"] = telefone(d["phone"])
    if "notes" in d:                                   # na tela: "Karting experience"
        s["notes"] = _texto(d["notes"], 1000)
    if "social" in d:
        t = (d["social"] or "").strip()
        if t and not t.startswith(("@", "http")):
            t = "@" + t if re.fullmatch(r"[A-Za-z0-9._]{1,30}", t) else "https://" + t
        if t and not _SOCIAL.match(t):
            raise ErroPortal("Social media: paste the profile link or the @username.")
        s["social"] = t or None
    if "measures" in d:
        m = medidas(d["measures"])
        s["measures"] = json.dumps(m, sort_keys=True) if m else None
    return s


_ROTULO_PILOTO = {"name": "full name", "birth_date": "date of birth", "height_in": "height", "weight_lb": "weight",
                  "chest_in": "chest", "waist_in": "waist", "hips_in": "hips", "experience": "karting experience"}


def _exige_piloto(p):
    falta = faltando_piloto(p)
    if falta:
        raise ErroPortal("Please fill in: " + ", ".join(dict.fromkeys(_ROTULO_PILOTO[k] for k in falta)) + ".")


def criar_piloto(con, cid, d, completo=True):
    """`completo=False` só para o próprio responsável no cadastro: nasce sem medidas e o
    painel pede para completar antes de marcar."""
    if um(con, "SELECT COUNT(*) AS n FROM portal_pilots WHERE account_id=? AND active=1", (cid,))["n"] >= 12:
        raise ErroPortal("An account can have up to 12 drivers.")
    s = _dados_piloto(d)
    if completo:
        _exige_piloto({**s, "measures": json.loads(s["measures"]) if s.get("measures") else {}})
    if d.get("is_self"):
        if um(con, "SELECT 1 AS x FROM portal_pilots WHERE account_id=? AND is_self=1 AND active=1", (cid,)):
            raise ErroPortal("You are already on this account as a driver.")
        s["is_self"] = 1
    if s.get("measures"):
        s["measures_updated_at"] = agora()
    return inserir(con, "portal_pilots", account_id=cid, **s)


def atualizar_piloto(con, cid, pid, d):
    p = um(con, "SELECT * FROM portal_pilots WHERE id=? AND account_id=? AND active=1", (pid, cid))
    if not p:
        raise ErroPortal("Driver not found.")                  # de outra conta: igual a não existir
    s = _dados_piloto(d, parcial=True)
    final = {**dict(p), **s}
    _exige_piloto({**final, "measures": json.loads(final["measures"]) if final.get("measures") else {}})
    if "measures" in s:              # salvar as medidas é confirmar que estão certas: a data renova
        s["measures_updated_at"] = agora()
    if s:
        atualizar(con, "portal_pilots", pid, **s, updated_at=agora())
    return sorted(s)
