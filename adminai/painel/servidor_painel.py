#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Serve o Pit Wall atrás de uma página de login.

Roda no host, escutando só em 127.0.0.1. O Caddy põe o TLS na frente e
encaminha /painel/* para cá. Sem dependência nenhuma: biblioteca padrão.

Por que não o `basic_auth` do Caddy: ele abre a caixinha cinza do
navegador, não tem como sair, e não dá para explicar nada ao usuário.

Como a senha é guardada: `scrypt` (da stdlib) com sal aleatório. O
arquivo `~/.urace/painel-auth.json` guarda sal e hash — nunca a senha.
A sessão é um cookie assinado com HMAC, com validade, `HttpOnly`,
`Secure` e `SameSite=Strict`.

Uso:
    python3 adminai/painel/servidor_painel.py senha        # define a senha
    python3 adminai/painel/servidor_painel.py              # sobe o servidor
"""
import base64
import hashlib
import hmac
import html
import http.server
import json
import os
import secrets
import socketserver
import sys
import time
import urllib.parse
from getpass import getpass

URACE_DIR = os.environ.get("URACE_DIR", os.path.expanduser("~/.urace"))
AUTH = os.path.join(URACE_DIR, "painel-auth.json")
PAGINA = os.path.join(URACE_DIR, "painel", "index.html")
PORTA = int(os.environ.get("PAINEL_PORTA", "8787"))
BASE = "/painel"
VALIDADE = 12 * 3600          # 12 h: cabe um dia de trabalho, não um mês
MAX_ERROS = 5                 # por IP
CASTIGO = 300                 # 5 min de espera depois de errar demais

_erros = {}                   # ip -> [quantidade, momento_do_ultimo]


# --------------------------------------------------------------- senha
def _params():
    return dict(n=2 ** 15, r=8, p=1, dklen=32)


def _hash(senha, sal):
    # maxmem explícito: o padrão do OpenSSL é 32 MB e n=2**15,r=8 precisa
    # de exatamente isso — sem esta linha o hash falha com
    # "memory limit exceeded" (pego no teste, antes de ir para o VPS).
    return hashlib.scrypt(senha.encode(), salt=sal, maxmem=64 * 1024 * 1024,
                          **_params())


def definir_senha():
    if not os.path.isdir(URACE_DIR):
        sys.exit(f"ERRO: {URACE_DIR} não existe.")
    usuario = input("usuário [italo]: ").strip() or "italo"
    s1 = getpass("senha (não aparece): ")
    if len(s1) < 8:
        sys.exit("ERRO: use pelo menos 8 caracteres.")
    if s1 != getpass("repita: "):
        sys.exit("ERRO: as duas não conferem. Nada foi alterado.")
    sal = secrets.token_bytes(16)
    dados = {"usuario": usuario,
             "sal": base64.b64encode(sal).decode(),
             "hash": base64.b64encode(_hash(s1, sal)).decode(),
             "segredo": base64.b64encode(secrets.token_bytes(32)).decode()}
    with open(AUTH, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=1)
    os.chmod(AUTH, 0o600)
    print(f"\n✅ senha definida para '{usuario}' em {AUTH} (600)")
    print("   A senha não foi guardada — só o hash scrypt.")
    print("   Trocar a senha invalida as sessões abertas.")
    return 0


def _auth():
    try:
        with open(AUTH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def confere(usuario, senha, a):
    ok_u = hmac.compare_digest(usuario, a["usuario"])
    esperado = base64.b64decode(a["hash"])
    ok_s = hmac.compare_digest(_hash(senha, base64.b64decode(a["sal"])), esperado)
    return ok_u and ok_s


# -------------------------------------------------------------- sessão
def assina(a, ate):
    msg = f"{a['usuario']}|{ate}".encode()
    mac = hmac.new(base64.b64decode(a["segredo"]), msg, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(msg).decode().rstrip("=") + "." + mac


def valida(token, a):
    try:
        corpo, mac = token.rsplit(".", 1)
        msg = base64.urlsafe_b64decode(corpo + "=" * (-len(corpo) % 4))
        esperado = hmac.new(base64.b64decode(a["segredo"]), msg,
                            hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac, esperado):
            return False
        usuario, ate = msg.decode().split("|")
        return usuario == a["usuario"] and time.time() < float(ate)
    except Exception:
        return False


# --------------------------------------------------------------- login
LOGIN = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pit Wall — URACE</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=Barlow:wght@400;500;600&display=swap">
<style>
:root{color-scheme:light dark;--paper:#F6F3EF;--surface:#fff;--ink:#191714;--ink-2:#4A443C;--muted:#7A7168;--rule:#DED8D0;--accent:#1F5F63;--crit:#A8352A;--brand:#C4321F}
@media(prefers-color-scheme:dark){:root{--paper:#131211;--surface:#1C1A18;--ink:#EFEBE5;--ink-2:#C4BDB4;--muted:#948B81;--rule:#2E2A27;--accent:#5DAFB2;--crit:#E0705F;--brand:#E8563E}}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--paper);color:var(--ink);font-family:"Barlow",system-ui,sans-serif;padding:24px}
.box{width:100%;max-width:370px;background:var(--surface);border:1px solid var(--rule);border-radius:4px;padding:30px 28px;box-shadow:0 1px 2px rgba(0,0,0,.06),0 18px 40px -28px rgba(0,0,0,.4)}
.marca{font-family:"Barlow Condensed",sans-serif;font-weight:700;font-size:12px;letter-spacing:.22em;text-transform:uppercase;color:var(--brand);margin-bottom:5px}
h1{font-family:"Barlow Condensed",sans-serif;font-weight:700;font-size:31px;letter-spacing:.01em;margin:0 0 4px}
.sub{color:var(--muted);font-size:13.5px;margin:0 0 22px;line-height:1.5}
label{display:block;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:5px}
input{width:100%;padding:10px 12px;font-size:15px;font-family:inherit;color:var(--ink);background:var(--paper);border:1px solid var(--rule);border-radius:3px;margin-bottom:15px}
input:focus{outline:2px solid var(--accent);outline-offset:-1px;border-color:transparent}
button{width:100%;padding:11px;font-size:14px;font-weight:600;font-family:inherit;letter-spacing:.03em;color:#fff;background:var(--accent);border:0;border-radius:3px;cursor:pointer}
button:hover{filter:brightness(1.08)}
.erro{background:color-mix(in srgb,var(--crit) 12%,transparent);border-left:3px solid var(--crit);color:var(--crit);padding:9px 12px;border-radius:2px;font-size:13.5px;margin-bottom:16px}
.rodape{margin-top:18px;padding-top:14px;border-top:1px solid var(--rule);color:var(--muted);font-size:12px;line-height:1.5}
</style></head><body>
<form class=box method=post action="__BASE__/entrar">
  <div class=marca>URACE.US</div>
  <h1>Pit Wall</h1>
  <p class=sub>Painel do Administrative AI. Acesso restrito à equipe.</p>
  __ERRO__
  <label for=u>Usuário</label>
  <input id=u name=usuario autocomplete=username autofocus required>
  <label for=p>Senha</label>
  <input id=p name=senha type=password autocomplete=current-password required>
  <button type=submit>Entrar</button>
  <p class=rodape>Esta página mostra dados de cliente. Não compartilhe o acesso.</p>
</form></body></html>"""


def pagina_login(erro=""):
    bloco = f'<div class=erro>{html.escape(erro)}</div>' if erro else ""
    return LOGIN.replace("__ERRO__", bloco).replace("__BASE__", BASE)


# ------------------------------------------------------------ servidor
class Painel(http.server.BaseHTTPRequestHandler):
    server_version = "urace-painel"
    sys_version = ""

    def log_message(self, fmt, *args):     # nunca registrar senha na url
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # -------------------------------------------------------- utilidades
    def _ip(self):
        return (self.headers.get("X-Forwarded-For", "") or "").split(",")[0].strip() \
            or self.client_address[0]

    def _responde(self, codigo, corpo, tipo="text/html; charset=utf-8", extra=None):
        dados = corpo.encode() if isinstance(corpo, str) else corpo
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or []):
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(dados)

    def _logado(self):
        a = _auth()
        if not a:
            return False
        for parte in (self.headers.get("Cookie") or "").split(";"):
            if parte.strip().startswith("painel="):
                return valida(parte.strip()[7:], a)
        return False

    def _castigado(self):
        n, quando = _erros.get(self._ip(), (0, 0))
        if n >= MAX_ERROS and time.time() - quando < CASTIGO:
            return int(CASTIGO - (time.time() - quando))
        return 0

    # -------------------------------------------------------------- GET
    def do_GET(self):
        caminho = urllib.parse.urlparse(self.path).path.rstrip("/") or "/"
        if caminho in (BASE, "/"):
            if not self._logado():
                return self._responde(200, pagina_login())
            try:
                with open(PAGINA, encoding="utf-8") as f:
                    pagina = f.read()
            except OSError:
                return self._responde(503, "<h1>Painel ainda não foi gerado</h1>"
                                           "<p>Rode <code>systemctl start urace-painel.service</code>.</p>")
            sair = (f'<div style="position:fixed;top:10px;right:12px;z-index:9">'
                    f'<a href="{BASE}/sair" style="font:600 12px/1 Barlow,sans-serif;'
                    'letter-spacing:.05em;text-transform:uppercase;text-decoration:none;'
                    'padding:7px 12px;border-radius:3px;background:rgba(127,127,127,.16);'
                    'color:inherit">Sair</a></div>')
            return self._responde(200, pagina.replace("<body>", "<body>" + sair, 1))
        if caminho == BASE + "/sair":
            return self._responde(303, "", extra=[
                ("Location", BASE + "/"),
                ("Set-Cookie", f"painel=; Path={BASE}; Max-Age=0; HttpOnly; "
                               "Secure; SameSite=Strict")])
        return self._responde(404, "não encontrado", "text/plain; charset=utf-8")

    def do_HEAD(self):
        self.do_GET()

    # ------------------------------------------------------------- POST
    def do_POST(self):
        if urllib.parse.urlparse(self.path).path.rstrip("/") != BASE + "/entrar":
            return self._responde(404, "não encontrado", "text/plain; charset=utf-8")
        espera = self._castigado()
        if espera:
            return self._responde(429, pagina_login(
                f"Muitas tentativas. Tente de novo em {espera // 60 + 1} minuto(s)."))
        tamanho = min(int(self.headers.get("Content-Length") or 0), 4096)
        campos = urllib.parse.parse_qs(self.rfile.read(tamanho).decode("utf-8", "replace"))
        usuario = (campos.get("usuario") or [""])[0]
        senha = (campos.get("senha") or [""])[0]
        a = _auth()
        if not a:
            return self._responde(503, pagina_login(
                "Nenhuma senha definida no servidor. Rode: "
                "python3 adminai/painel/servidor_painel.py senha"))
        if not confere(usuario, senha, a):
            n, _ = _erros.get(self._ip(), (0, 0))
            _erros[self._ip()] = (n + 1, time.time())
            time.sleep(1)                    # atrasa força bruta
            return self._responde(401, pagina_login("Usuário ou senha incorretos."))
        _erros.pop(self._ip(), None)
        token = assina(a, time.time() + VALIDADE)
        return self._responde(303, "", extra=[
            ("Location", BASE + "/"),
            ("Set-Cookie", f"painel={token}; Path={BASE}; Max-Age={VALIDADE}; "
                           "HttpOnly; Secure; SameSite=Strict")])


class Servidor(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "senha":
        return definir_senha()
    if not _auth():
        print("⚠️  nenhuma senha definida — o login vai recusar todo mundo.",
              file=sys.stderr)
        print("   defina com: python3 adminai/painel/servidor_painel.py senha",
              file=sys.stderr)
    with Servidor(("127.0.0.1", PORTA), Painel) as s:
        print(f"painel servindo em http://127.0.0.1:{PORTA}{BASE}/ "
              f"(o TLS é do Caddy)", flush=True)
        s.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
