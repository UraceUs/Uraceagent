#!/usr/bin/env python3
"""Consentimento OAuth do Google para o Administrative AI, sem navegador
no servidor e sem biblioteca nenhuma.

Uso (no VPS, como o usuário que roda o agente):

    python3 adminai/google_auth.py                 # caixa urace@ (padrão)
    python3 adminai/google_auth.py --conta support # caixa support@

O script imprime uma URL. Abra na SUA máquina, logado na caixa certa,
autorize, e o navegador vai tentar abrir http://localhost:1/... e
falhar -- é esperado. Copie o valor de `code=` da barra de endereços e
cole aqui. O script troca o código por um refresh token e grava
~/.urace/google-token.json (ou google-token-support.json), permissão 600.

Precisa de ~/.urace/google-credentials.json: o JSON do cliente OAuth
"Desktop app", criado no Google Cloud Console com o app INTERNO ao
Workspace (ver docs/adminai/google-conexao.md). Interno = sem revisão do
Google, e o refresh token não expira por inatividade de 7 dias.

Escopos pedidos de uma vez, para não voltar aqui depois:
  gmail.modify   -- ler, rotular, criar rascunho (o servidor MCP não
                    expõe envio; a trava é na ferramenta, não no escopo,
                    porque não existe escopo "rascunho sem envio")
  calendar.readonly, drive.readonly, spreadsheets.readonly
"""
import argparse
import json
import os
import stat
import sys
import urllib.parse
import urllib.request

ESCOPOS = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]
REDIRECT = "http://localhost:1/"   # porta 1: garante que nada responde


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conta", default="urace", choices=["urace", "support"])
    ap.add_argument("--credenciais", default=os.path.expanduser("~/.urace/google-credentials.json"))
    a = ap.parse_args()

    if not os.path.isfile(a.credenciais):
        sys.exit(f"ERRO: não existe {a.credenciais}. Baixe o JSON do cliente OAuth "
                 "(Desktop app) no Google Cloud Console e salve nesse caminho.")
    with open(a.credenciais, encoding="utf-8") as f:
        cred = json.load(f)
    # o JSON do Desktop app vem embrulhado em "installed"; o de Web em "web"
    c = cred.get("installed") or cred.get("web") or cred
    client_id, client_secret = c.get("client_id"), c.get("client_secret")
    if not client_id or not client_secret:
        sys.exit("ERRO: o JSON não tem client_id/client_secret. É o arquivo do cliente OAuth?")

    destino = os.path.expanduser("~/.urace/google-token.json" if a.conta == "urace"
                                 else "~/.urace/google-token-support.json")
    esperado = "urace@urace.us" if a.conta == "urace" else "support@urace.us"

    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": REDIRECT, "response_type": "code",
        "scope": " ".join(ESCOPOS), "access_type": "offline", "prompt": "consent",
        "login_hint": esperado,
    })
    print("\n1) Abra esta URL na sua máquina, LOGADO como", esperado, ":\n")
    print(url)
    print("\n2) Autorize. O navegador vai falhar ao abrir localhost:1 — é esperado.")
    print("3) Copie o valor de `code=` da barra de endereços (até o & seguinte) e cole aqui.\n")
    code = input("code= ").strip()
    if not code:
        sys.exit("nada colado.")
    code = urllib.parse.unquote(code)

    dados = urllib.parse.urlencode({
        "code": code, "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": REDIRECT, "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=dados, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            tok = json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"ERRO na troca do código (HTTP {e.code}): {e.read().decode(errors='replace')[:400]}")
    if "refresh_token" not in tok:
        sys.exit("ERRO: o Google não devolveu refresh_token. Refaça com prompt=consent "
                 "(o script já manda) — se persistir, revogue o acesso do app em "
                 "myaccount.google.com/permissions e tente de novo.")

    # quem autorizou? Confere a caixa antes de gravar.
    req = urllib.request.Request("https://www.googleapis.com/gmail/v1/users/me/profile")
    req.add_header("Authorization", f"Bearer {tok['access_token']}")
    with urllib.request.urlopen(req, timeout=30) as r:
        perfil = json.loads(r.read())
    email = perfil.get("emailAddress", "?")
    if email.lower() != esperado:
        sys.exit(f"ERRO: quem autorizou foi {email}, e este token é para {esperado}. "
                 "Nada gravado. Refaça logado na caixa certa (ou use --conta).")

    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        json.dump({"client_id": client_id, "client_secret": client_secret,
                   "refresh_token": tok["refresh_token"], "email": email,
                   "scopes": ESCOPOS}, f, indent=1)
    os.chmod(destino, stat.S_IRUSR | stat.S_IWUSR)
    print(f"\n✅ token gravado em {destino} (600) para {email}")
    print("   mensagens na caixa:", perfil.get("messagesTotal"), "· threads:", perfil.get("threadsTotal"))


if __name__ == "__main__":
    main()
