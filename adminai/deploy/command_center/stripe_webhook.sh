#!/usr/bin/env bash
# #174: liga o webhook do Stripe da loja, uma vez. Cria o endpoint pela API do Stripe com a chave
# que já está no ~/.urace/adminai.env e grava o segredo (whsec_…) no mesmo arquivo, sem mostrar
# na tela. Rodar de novo não cria outro endpoint. Se a chave não puder criar webhook (restrita sem
# "Webhook Endpoints: Write"), pede para criar no painel do Stripe e colar o segredo escondido.
set -euo pipefail
URACE_DIR="${URACE_DIR:-$HOME/.urace}"
ENVF="$URACE_DIR/adminai.env"
URL="${STRIPE_WEBHOOK_URL:-https://ops.urace.us/ops/api/stripe/webhook}"
export ENVF URL

set +e
python3 - <<'PY'
import json, os, sys, urllib.error, urllib.parse, urllib.request
envf, url = os.environ["ENVF"], os.environ["URL"]
env = {}
for linha in open(envf):
    if "=" in linha and not linha.lstrip().startswith("#"):
        k, v = linha.rstrip("\n").split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
sk = env.get("STRIPE_SECRET_KEY", "")
if not sk:
    sys.exit("✗ falta STRIPE_SECRET_KEY no adminai.env")
EVENTOS = ["checkout.session.completed", "checkout.session.async_payment_succeeded",
           "checkout.session.async_payment_failed", "checkout.session.expired"]

def chamar(metodo, caminho, campos=None):
    dados = urllib.parse.urlencode(campos).encode() if campos else None
    req = urllib.request.Request("https://api.stripe.com" + caminho, data=dados, method=metodo,
                                 headers={"Authorization": "Bearer " + sk})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)

try:
    existentes = [w for w in chamar("GET", "/v1/webhook_endpoints?limit=100")["data"] if w.get("url") == url]
except urllib.error.HTTPError as e:
    print(f"· a chave não lê webhooks (HTTP {e.code})")
    sys.exit(3)
if existentes:
    w = existentes[0]
    falta = sorted(set(EVENTOS) - set(w.get("enabled_events") or []))
    if falta and "*" not in (w.get("enabled_events") or []):
        chamar("POST", f"/v1/webhook_endpoints/{w['id']}", [("enabled_events[]", e) for e in EVENTOS])
        print(f"✓ endpoint {w['id']} atualizado com os eventos da loja")
    else:
        print(f"✓ endpoint {w['id']} já existe para {url}")
    if env.get("STRIPE_WEBHOOK_SECRET", "").startswith("whsec_"):
        print("✓ STRIPE_WEBHOOK_SECRET já está no adminai.env")
        sys.exit(0)
    print("· o endpoint existe mas o segredo não está no servidor (o Stripe só mostra o segredo ao criar)")
    sys.exit(3)
try:
    w = chamar("POST", "/v1/webhook_endpoints", [("url", url), ("description", "URACE loja (#174)")]
               + [("enabled_events[]", e) for e in EVENTOS])
except urllib.error.HTTPError as e:
    print(f"· a chave não cria webhooks (HTTP {e.code})")
    sys.exit(3)
segredo = w.get("secret") or ""
if not segredo.startswith("whsec_"):
    sys.exit("✗ o Stripe não devolveu o segredo")
linhas = [l for l in open(envf) if not l.startswith("STRIPE_WEBHOOK_SECRET=")]
with open(envf, "w") as f:
    f.writelines(linhas + ([] if not linhas or linhas[-1].endswith("\n") else ["\n"]) + [f"STRIPE_WEBHOOK_SECRET={segredo}\n"])
print(f"✓ endpoint {w['id']} criado para {url} e segredo gravado ({segredo[:10]}…{segredo[-4:]})")
PY
rc=$?
set -e
if [ "$rc" = 3 ]; then
    echo "No painel do Stripe: Developers › Webhooks › Add endpoint (ou abra o que já existe)"
    echo "  URL: $URL"
    echo "  Eventos: checkout.session.completed, checkout.session.async_payment_succeeded,"
    echo "           checkout.session.async_payment_failed, checkout.session.expired"
    echo "Depois: Signing secret › Reveal, copie e cole aqui (não aparece na tela)."
    read -rsp "Stripe — signing secret (whsec_…): " WS; echo
    case "$WS" in whsec_*) ;; *) echo "✗ não parece um whsec_…"; unset WS; exit 1;; esac
    sed -i '/^STRIPE_WEBHOOK_SECRET=/d' "$ENVF"
    printf 'STRIPE_WEBHOOK_SECRET=%s\n' "$WS" >> "$ENVF"
    echo "✓ segredo gravado (${WS:0:10}…${WS: -4})"
    unset WS
elif [ "$rc" != 0 ]; then
    exit "$rc"
fi
chmod 600 "$ENVF"
