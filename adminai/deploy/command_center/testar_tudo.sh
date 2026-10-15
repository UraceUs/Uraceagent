#!/usr/bin/env bash
# #253 — prova o site e o processo de vendas inteiros na VPS, SEM TOCAR NA OPERAÇÃO.
#
# Dono, 15/10: "me de um bloco para a extensão testar todo o site e processo de vendas criando uma
# conta fictícia para testar de ponta a ponta" e "de o comando para a extensão capturar tela a cada
# passo para poder te passar e testar todas as funcionalidades".
#
# O que ele faz, nesta ordem:
#   1. confere o ambiente: nenhuma chave real, nenhum caminho do banco de produção (falha na hora)
#   2. acha o Python do Command Center e o Chromium do Playwright (ou diz como instalar)
#   3. constrói o frontend, se faltar
#   4. roda a suíte end-to-end inteira num banco descartável e numa porta livre própria
#      (CC_DB_PATH temporário, CC_AUTOSYNC=0, URACE_ENV=/nao/existe, Stripe/Google falsos locais)
#   5. percorre a venda de ponta a ponta com conta fictícia e fotografa cada passo em 390 px e
#      1280 px, mais uma foto de cada tela do painel, e escreve o RESUMO.md em português
#   6. junta tudo num pacote só (~/.urace/teste-<data>.tar.gz) e imprime o caminho e o tamanho
#   7. apaga o banco temporário e derruba o servidor do teste no fim, inclusive se der erro
#
# O que ele NÃO prova: cobrança de verdade no Stripe (chave real), e-mail de verdade saindo, e
# Asana, QuickBooks, DocuSign ou Google de verdade — aqui tudo isso é falso, de propósito.
#
# Uso (no VPS, uma linha):  bash adminai/deploy/command_center/testar_tudo.sh
set -uo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
URACE_DIR="${URACE_DIR:-$HOME/.urace}"
VENV="$URACE_DIR/cc-venv"
BANCO_PROD="$URACE_DIR/command-center.sqlite"
AGORA="$(date +%Y%m%d-%H%M%S)"
PACOTE="$URACE_DIR/teste-$AGORA.tar.gz"
# as chaves reais que nunca podem chegar ao teste (o conftest já apaga a maioria; aqui é a trava)
REAIS=(ASANA_TOKEN ASANA_WORKSPACE DOCUSIGN_INTEGRATION_KEY DOCUSIGN_PRIVATE_KEY DOCUSIGN_USER_ID
       DOCUSIGN_ACCOUNT_ID QBO_CLIENT_ID QBO_CLIENT_SECRET QBO_REFRESH_TOKEN QBO_REALM_ID
       GOOGLE_TOKEN_JSON GOOGLE_TOKEN_JSON_SUPPORT GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET
       CC_GOOGLE_WEB_CREDENTIALS ANTHROPIC_API_KEY CLAUDE_CODE_OAUTH_TOKEN KOMMO_TOKEN
       DIALPAD_TOKEN CC_COFRE_CHAVE STRIPE_WEBHOOK_SECRET)

echo "== Prova do site e do processo de vendas (nada da operação é tocado) =="

# ------------------------------------------------------------- 1. o ambiente tem de estar limpo
achadas=()
for k in "${REAIS[@]}"; do
    [ -n "${!k:-}" ] && achadas+=("$k")
done
# o Stripe só pode ser de teste: sk_live (ou qualquer coisa que não seja sk_test/rk_test) é chave real
case "${STRIPE_SECRET_KEY:-}" in
    ""|sk_test*|rk_test*) ;;
    *) achadas+=(STRIPE_SECRET_KEY) ;;
esac
if [ "${#achadas[@]}" -gt 0 ]; then
    echo "!! PAREI: há chave real neste ambiente, e o teste nunca roda com credencial de verdade."
    echo "   Encontrei (só o nome, nunca o valor): ${achadas[*]}"
    printf '   Rode assim, num terminal limpo:\n   env'
    for k in "${achadas[@]}"; do printf ' -u %s' "$k"; done
    echo " bash adminai/deploy/command_center/testar_tudo.sh"
    exit 2
fi
if [ -n "${CC_DB_PATH:-}" ]; then
    echo "!! PAREI: CC_DB_PATH está definido ($CC_DB_PATH). O teste usa banco descartável próprio."
    echo "   Rode assim: env -u CC_DB_PATH bash adminai/deploy/command_center/testar_tudo.sh"
    exit 2
fi
echo "-- 1/6 ambiente limpo: nenhuma chave real, e o banco de produção ($BANCO_PROD) fica intocado"

# ------------------------------------------------------------- 2. Python e Chromium
if [ -x "$VENV/bin/python" ]; then PY="$VENV/bin/python"; else PY="$(command -v python3 || true)"; fi
[ -n "$PY" ] || { echo "!! sem python3 nesta máquina"; exit 1; }
if ! "$PY" -c "import pytest, playwright, fastapi, uvicorn" 2>/dev/null; then
    echo "!! falta dependência de teste. Rode:"
    echo "   $PY -m pip install -r $REPO/command_center/requirements.txt pytest httpx playwright"
    echo "   $PY -m playwright install --with-deps chromium"
    exit 1
fi
CHROMIUM="${PW_CHROMIUM:-}"
if [ -z "$CHROMIUM" ]; then
    for c in /opt/pw-browsers/chromium /opt/pw-browsers/chromium-*/chrome-linux/chrome \
             "$HOME/.cache/ms-playwright"/chromium-*/chrome-linux/chrome \
             /root/.cache/ms-playwright/chromium-*/chrome-linux/chrome; do
        [ -x "$c" ] && { CHROMIUM="$c"; break; }
    done
fi
if [ -z "$CHROMIUM" ]; then
    # o Playwright pode achar o navegador sozinho; se não achar, dizemos como instalar
    if "$PY" - <<'EOF' 2>/dev/null
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    p.chromium.launch().close()
EOF
    then echo "-- 2/6 $("$PY" -V) · Chromium: o do Playwright instalado"
    else
        echo "!! PAREI: não achei o Chromium do Playwright. Instale com:"
        echo "   $PY -m playwright install --with-deps chromium"
        echo "   (ou aponte o seu: PW_CHROMIUM=/caminho/do/chrome bash $0)"
        exit 1
    fi
else
    echo "-- 2/6 $("$PY" -V) · Chromium: $CHROMIUM"
fi

# ------------------------------------------------------------- 3. pastas do teste (e a limpeza)
mkdir -p "$URACE_DIR"; chmod 700 "$URACE_DIR" 2>/dev/null || true
TRABALHO="$(mktemp -d "${TMPDIR:-/tmp}/urace-teste-XXXXXX")"
PROVAS="$TRABALHO/provas"
mkdir -p "$PROVAS/fotos"
LOG="$PROVAS/teste.log"
limpar() {
    # o banco descartável e o servidor do teste moram sob $TRABALHO/pytest: saem inteiros aqui,
    # mesmo se o teste quebrar no meio ou o terminal cair
    rm -rf "$TRABALHO"
}
trap limpar EXIT INT TERM

# ------------------------------------------------------------- 4. frontend
if [ ! -f "$REPO/command_center/web/dist/index.html" ]; then
    command -v npm >/dev/null || { echo "!! frontend não construído e sem npm. Instale Node 20+ e rode de novo"; exit 1; }
    echo "-- 3/6 frontend ainda não construído: npm ci + vite (1-3 min)"
    ( cd "$REPO/command_center/web" && npm ci --no-audit --no-fund --silent && npm run build --silent ) \
        || { echo "!! o build do frontend falhou"; exit 1; }
else
    echo "-- 3/6 frontend já construído ($(du -sh "$REPO/command_center/web/dist" | cut -f1))"
fi

# ------------------------------------------------------------- 5. a suíte e as fotos
echo "-- 4/6 rodando a suíte end-to-end e fotografando cada passo (10-20 min; o log fica no pacote)"
cd "$REPO"
# cinto e suspensório: além do conftest, nenhum caminho de credencial real chega ao pytest, e o
# Stripe, o Google e o e-mail são os falsos que os próprios testes sobem (STRIPE_API_BASE etc.)
LIMPO=(env -u CC_DB_PATH -u STRIPE_API_BASE -u STRIPE_CHECKOUT_ORIGEM)
for k in "${REAIS[@]}"; do LIMPO+=(-u "$k"); done
LIMPO+=(CC_E2E=1 "CC_FOTOS=$PROVAS/fotos" CC_AUTOSYNC=0 URACE_ENV=/nao/existe
        STRIPE_SECRET_KEY=sk_test_prova_do_site "PYTHONPATH=$REPO")
[ -n "$CHROMIUM" ] && LIMPO+=("PW_CHROMIUM=$CHROMIUM")
"${LIMPO[@]}" "$PY" -m pytest -q -rf --basetemp="$TRABALHO/pytest" command_center/tests/e2e > "$LOG" 2>&1
RC=$?
tail -3 "$LOG" | sed 's/^/   /'

# ------------------------------------------------------------- 6. o pacote
echo "-- 5/6 montando o pacote"
cp "$REPO/command_center/tests/e2e/README.md" "$PROVAS/COMO-O-AMBIENTE-DE-TESTE-FUNCIONA.md" 2>/dev/null || true
{
    echo "# Como este pacote foi gerado"
    echo
    echo "Comando: bash adminai/deploy/command_center/testar_tudo.sh"
    echo "Quando: $(date '+%d/%m/%Y %H:%M:%S %Z')"
    echo "Repositório: $REPO ($(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo 'sem git'))"
    echo "Python: $("$PY" -V 2>&1) · Chromium: ${CHROMIUM:-o do Playwright}"
    echo "Banco: descartável, em $TRABALHO/pytest (apagado no fim). Produção ($BANCO_PROD) intocada."
    echo "Resultado do pytest: rc=$RC"
} > "$PROVAS/COMO-FOI-GERADO.md"
tar -czf "$PACOTE" -C "$TRABALHO" provas 2>/dev/null
TAM="$(du -h "$PACOTE" 2>/dev/null | cut -f1)"

# ------------------------------------------------------------- 7. o resumo na tela, em português
echo
echo "================= RESUMO ================="
if [ -f "$PROVAS/fotos/RESUMO.md" ]; then
    # cada bloco do RESUMO.md até o próximo título (nada de linha de outra seção se misturar)
    awk '/^## Resumo/{f=1;next} /^## /{f=0} f && NF' "$PROVAS/fotos/RESUMO.md"
    echo
    echo "Telas com rolagem lateral ou alvo de toque pequeno:"
    awk '/^## Telas com rolagem/{f=1;next} /^## /{f=0} f && NF' "$PROVAS/fotos/RESUMO.md" | head -8 | sed 's/^/  /'
else
    echo "As fotos não foram geradas: veja o fim do log dentro do pacote (provas/teste.log)."
fi
echo
if [ "$RC" -eq 0 ]; then
    echo "TUDO PASSOU: a suíte end-to-end inteira e o caminho de venda de ponta a ponta com conta fictícia."
else
    echo "ALGO FALHOU (rc=$RC). O que o pytest acusou:"
    grep -E '^(FAILED|ERROR)' "$LOG" | head -20 | sed 's/^/  /'
    echo "  (o log inteiro e as fotos do estado do erro estão no pacote)"
fi
echo
echo "Dentro do pacote: provas/fotos/RESUMO.md (passo a passo, em português), provas/fotos/390/ e"
echo "provas/fotos/1280/ (as fotos numeradas de cada passo e de cada tela), provas/teste.log (o log"
echo "inteiro) e provas/COMO-FOI-GERADO.md (comando, data e versão do repositório)."
echo
echo "O que este teste prova: site, reserva (kart/dia/turno), conta fictícia criada no site, carrinho,"
echo "checkout no Stripe FALSO, pedido pago, sessão em Agendamentos do site, venda GANHO e card do piloto,"
echo "mais todas as telas do painel abrindo em 390 px e 1280 px."
echo "O que NÃO prova: cobrança de verdade no Stripe, e-mail de verdade, Asana/QuickBooks/DocuSign/Google reais."
echo
echo "=========================================="
echo ">> MANDE ESTE ARQUIVO PARA O CLAUDE: $PACOTE  ($TAM)"
exit "$RC"
