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
"""
import json
import re
from datetime import date, datetime
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
CAMPOS_CONTA = ("name", "birth_date", "phone", "address_line1", "address_line2", "city", "state", "zip")
CAMPOS_PILOTO = ("name", "birth_date", "email", "phone", "notes")
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


def telefone(v):
    if not (v or "").strip():
        return None
    t = identidade.normaliza_telefone(v)
    if not t or len(re.sub(r"\D", "", t)) < 10:
        raise ErroPortal("Enter a valid phone number, with area code.")
    return t


def _endereco(d):
    s = {k: _texto(d.get(k), 80) for k in ("address_line1", "address_line2", "city")}
    estado = _texto(d.get("state"), 30)
    if estado and re.fullmatch(r"[A-Za-z]{2}", estado):
        estado = estado.upper()
    cep = _texto(d.get("zip"), 12)
    if cep and not re.fullmatch(r"\d{5}(-\d{4})?", cep):
        raise ErroPortal("ZIP code: use 5 digits (or 5+4).")
    return {**s, "state": estado, "zip": cep}


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
def criar_conta(con, dados, pw_salt, pw_hash):
    if not dados.get("accept_terms"):
        raise ErroPortal("You need to accept the terms to create an account.")
    email = email_valido(dados.get("email"))
    nome = _texto(dados.get("name"))
    if not nome or len(nome) < 3:
        raise ErroPortal("Enter your full name.")
    nasc = _data(dados.get("birth_date"), "Date of birth")
    if idade(nasc) < MAIORIDADE:
        raise ErroPortal("The account holder must be 18 or older. A parent or guardian can "
                         "create the account and add the young driver to it.")
    if um(con, "SELECT 1 AS x FROM portal_accounts WHERE email=?", (email,)):
        raise ErroPortal("An account with this email already exists. Sign in instead.")
    cid = inserir(con, "portal_accounts", email=email, pw_salt=pw_salt, pw_hash=pw_hash, name=nome,
                  birth_date=nasc.isoformat(), phone=telefone(dados.get("phone")),
                  terms_accepted_at=agora(), **_endereco(dados))
    if dados.get("i_am_driver"):
        criar_piloto(con, cid, {"name": nome, "birth_date": nasc.isoformat(), "is_self": True,
                                "email": email, "phone": dados.get("phone")})
    return cid


def conta(con, cid):
    c = um(con, """SELECT id, email, name, birth_date, phone, address_line1, address_line2, city, state, zip,
                          country, client_id, linked_at, created_at FROM portal_accounts WHERE id=? AND active=1""", (cid,))
    if not c:
        raise ErroPortal("Account not found.")
    return {**dict(c), "linked": bool(c["client_id"]), "drivers": pilotos(con, cid)}


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
    if "phone" in dados:
        mud["phone"] = telefone(dados["phone"])
    if any(k in dados for k in ("address_line1", "address_line2", "city", "state", "zip")):
        atual = um(con, "SELECT address_line1, address_line2, city, state, zip FROM portal_accounts WHERE id=?", (cid,))
        mud.update(_endereco({**dict(atual), **{k: dados[k] for k in dados if k in atual.keys()}}))
    if mud:
        atualizar(con, "portal_accounts", cid, **mud, updated_at=agora())
    return sorted(mud)


# ------------------------------------------------------------------ pilotos
def pilotos(con, cid):
    saida = []
    for p in todos(con, """SELECT id, name, birth_date, is_self, email, phone, measures, measures_updated_at, notes
                            FROM portal_pilots WHERE account_id=? AND active=1 ORDER BY is_self DESC, id""", (cid,)):
        p = dict(p)
        p["measures"] = json.loads(p["measures"]) if p["measures"] else {}
        p["age"] = idade(date.fromisoformat(p["birth_date"])) if p["birth_date"] else None
        p["is_self"] = bool(p["is_self"])
        saida.append(p)
    return saida


def _dados_piloto(d, parcial=False):
    s = {}
    if not parcial or "name" in d:
        nome = _texto(d.get("name"))
        if not nome or len(nome) < 2:
            raise ErroPortal("Enter the driver's name.")
        s["name"] = nome
    if "birth_date" in d:
        s["birth_date"] = _data(d["birth_date"], "Driver's date of birth").isoformat() if d["birth_date"] else None
    if "email" in d:
        s["email"] = email_valido(d["email"]) if (d["email"] or "").strip() else None
    if "phone" in d:
        s["phone"] = telefone(d["phone"])
    if "notes" in d:
        s["notes"] = _texto(d["notes"], 500)
    if "measures" in d:
        m = medidas(d["measures"])
        s["measures"] = json.dumps(m, sort_keys=True) if m else None
    return s


def criar_piloto(con, cid, d):
    if um(con, "SELECT COUNT(*) AS n FROM portal_pilots WHERE account_id=? AND active=1", (cid,))["n"] >= 12:
        raise ErroPortal("An account can have up to 12 drivers.")
    s = _dados_piloto(d)
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
    if "measures" in s and s["measures"] != p["measures"]:
        s["measures_updated_at"] = agora()
    if s:
        atualizar(con, "portal_pilots", pid, **s, updated_at=agora())
    return sorted(s)
