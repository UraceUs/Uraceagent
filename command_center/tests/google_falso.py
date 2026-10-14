"""Um Google de mentira (#220), num servidor HTTP local: OAuth (autorizar, token, renovar, revogar)
e a API do Calendar (listar, criar, mudar, apagar evento). Nada sai da máquina.

Usado pelos testes da API (`CC_GOOGLE_BASE` aponta para cá) e pelo end-to-end, em que o navegador
de verdade passa pela "tela de consentimento" daqui e volta para o painel.
"""
import base64
import hashlib
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit

CLIENT_ID = "cliente-web-teste.apps.googleusercontent.com"
CLIENT_SECRET = "segredo-do-cliente-de-teste"


def credenciais_json(tipo="web"):
    return json.dumps({tipo: {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "project_id": "urace-teste",
                              "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                              "token_uri": "https://oauth2.googleapis.com/token"}})


def _t(v):
    """Instante comparável (com fuso); dia inteiro vale meia-noite UTC — basta para o teste."""
    from datetime import datetime, timezone
    d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _id_token(email):
    corpo = base64.urlsafe_b64encode(json.dumps({"email": email, "email_verified": True}).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJub25lIn0.{corpo}.assinatura"


class GoogleFalso:
    def __init__(self, email="vendedor.teste@gmail.com"):
        self.email = email
        self.codigos = {}            # code -> {challenge, redirect_uri, client_id}
        self.access = {}             # access token -> email
        self.refresh = {}            # refresh token -> email
        self.revogados = []
        self.eventos = {}            # id -> evento
        self.pedidos = []            # (método, caminho) — para conferir que nada mexeu no que não é nosso
        self.recusar_refresh = False
        self.conceder_escopo = True
        self.expira_em = 3600
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, d, status=200):
                b = json.dumps(d).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def _corpo(self):
                n = int(self.headers.get("Content-Length") or 0)
                return self.rfile.read(n) if n else b""

            def _autorizado(self):
                cab = self.headers.get("Authorization") or ""
                return cab.startswith("Bearer ") and cab[7:] in fake.access

            def do_GET(self):
                u = urlsplit(self.path)
                fake.pedidos.append(("GET", u.path))
                q = {k: v[0] for k, v in parse_qs(u.query).items()}
                if u.path == "/auth":                        # a "tela de consentimento"
                    b = (f"<!doctype html><html lang='pt'><head><title>Google (teste)</title></head><body>"
                         f"<h1>Escolha uma conta</h1><p>{fake.email}</p>"
                         f"<a id='permitir' href='/auth/ok?{u.query}'>Permitir</a> "
                         f"<a id='negar' href='/auth/negar?{u.query}'>Cancelar</a></body></html>").encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(b)))
                    self.end_headers()
                    return self.wfile.write(b)
                if u.path in ("/auth/ok", "/auth/negar"):
                    destino = fake.aprovar(q) if u.path == "/auth/ok" else \
                        q["redirect_uri"] + "?" + urlencode({"error": "access_denied", "state": q.get("state", "")})
                    self.send_response(302)
                    self.send_header("Location", destino)
                    return self.end_headers()
                if u.path == "/calendar/v3/calendars/primary/events":
                    if not self._autorizado():
                        return self._json({"error": {"status": "UNAUTHENTICATED"}}, 401)
                    ini, fim = _t(q["timeMin"]), _t(q["timeMax"])
                    itens = [e for e in fake.eventos.values()
                             if _t(e["start"].get("dateTime") or e["start"].get("date")) < fim
                             and _t(e["end"].get("dateTime") or e["end"].get("date")) > ini]
                    itens.sort(key=lambda e: _t(e["start"].get("dateTime") or e["start"].get("date")))
                    return self._json({"items": itens})
                self._json({"error": "not_found"}, 404)

            def do_POST(self):
                u = urlsplit(self.path)
                fake.pedidos.append(("POST", u.path))
                if u.path == "/token":
                    f = dict(parse_qsl(self._corpo().decode()))
                    if f.get("client_id") != CLIENT_ID or f.get("client_secret") != CLIENT_SECRET:
                        return self._json({"error": "invalid_client"}, 401)
                    if f.get("grant_type") == "authorization_code":
                        c = fake.codigos.pop(f.get("code"), None)
                        if not c or c["redirect_uri"] != f.get("redirect_uri"):
                            return self._json({"error": "invalid_grant"}, 400)
                        desafio = base64.urlsafe_b64encode(hashlib.sha256((f.get("code_verifier") or "").encode()).digest()).decode().rstrip("=")
                        if desafio != c["challenge"]:
                            return self._json({"error": "invalid_grant"}, 400)
                        at, rt = "ya29.at-" + secrets.token_hex(8), "1//rt-" + secrets.token_hex(8)
                        fake.access[at], fake.refresh[rt] = fake.email, fake.email
                        escopo = "openid https://www.googleapis.com/auth/userinfo.email"
                        if fake.conceder_escopo:
                            escopo += " https://www.googleapis.com/auth/calendar.events"
                        return self._json({"access_token": at, "refresh_token": rt, "expires_in": fake.expira_em,
                                           "scope": escopo, "token_type": "Bearer", "id_token": _id_token(fake.email)})
                    if f.get("grant_type") == "refresh_token":
                        if fake.recusar_refresh or f.get("refresh_token") not in fake.refresh:
                            return self._json({"error": "invalid_grant"}, 400)
                        at = "ya29.at-" + secrets.token_hex(8)
                        fake.access[at] = fake.email
                        return self._json({"access_token": at, "expires_in": 3600, "token_type": "Bearer"})
                    return self._json({"error": "unsupported_grant_type"}, 400)
                if u.path == "/revoke":
                    f = dict(parse_qsl(self._corpo().decode()))
                    fake.revogados.append(f.get("token"))
                    fake.refresh.pop(f.get("token"), None)
                    return self._json({})
                if u.path == "/calendar/v3/calendars/primary/events":
                    if not self._autorizado():
                        return self._json({"error": {"status": "UNAUTHENTICATED"}}, 401)
                    ev = json.loads(self._corpo())
                    ev["id"] = "ev" + secrets.token_hex(6)
                    ev["status"] = "confirmed"
                    fake.eventos[ev["id"]] = ev
                    return self._json(ev)
                self._json({"error": "not_found"}, 404)

            def do_PATCH(self):
                u = urlsplit(self.path)
                fake.pedidos.append(("PATCH", u.path))
                eid = u.path.rsplit("/", 1)[-1]
                if not self._autorizado():
                    return self._json({"error": {"status": "UNAUTHENTICATED"}}, 401)
                if eid not in fake.eventos:
                    return self._json({"error": {"status": "NOT_FOUND"}}, 404)
                fake.eventos[eid].update(json.loads(self._corpo()))
                self._json(fake.eventos[eid])

            def do_DELETE(self):
                u = urlsplit(self.path)
                fake.pedidos.append(("DELETE", u.path))
                eid = u.path.rsplit("/", 1)[-1]
                if not self._autorizado():
                    return self._json({"error": {"status": "UNAUTHENTICATED"}}, 401)
                if fake.eventos.pop(eid, None) is None:
                    return self._json({"error": {"status": "NOT_FOUND"}}, 410)
                self.send_response(204)
                self.end_headers()

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.origem = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def aprovar(self, q):
        """A pessoa clicou em Permitir: o código volta para o redirect_uri com o state."""
        assert q.get("client_id") == CLIENT_ID and q.get("code_challenge_method") == "S256"
        assert q.get("access_type") == "offline" and q.get("prompt") == "consent"
        code = "4/code-" + secrets.token_hex(8)
        self.codigos[code] = {"challenge": q["code_challenge"], "redirect_uri": q["redirect_uri"]}
        return q["redirect_uri"] + "?" + urlencode({"code": code, "state": q["state"], "scope": q.get("scope", "")})

    def evento_alheio(self, titulo, inicio, fim, **extra):
        """Um compromisso que a PRÓPRIA pessoa marcou no Google (o painel não pode tocar)."""
        eid = "alheio" + secrets.token_hex(4)
        self.eventos[eid] = {"id": eid, "status": "confirmed", "summary": titulo,
                             "start": {"dateTime": inicio}, "end": {"dateTime": fim}, **extra}
        return eid

    def nossos(self):
        return {k: v for k, v in self.eventos.items()
                if ((v.get("extendedProperties") or {}).get("private") or {}).get("urace_opp")}

    def parar(self):
        self.srv.shutdown()
