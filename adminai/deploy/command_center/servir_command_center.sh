#!/usr/bin/env bash
# Publica o Command Center em https://<dominio>/ops/ (login próprio, RBAC
# no servidor, auditoria imutável).
#
# O que faz, nesta ordem, e para se qualquer passo falhar:
#   1. venv em ~/.urace/cc-venv com fastapi/uvicorn (sem tocar no Python do sistema)
#   2. build do frontend (npm ci && npm run build) -> command_center/web/dist
#   3. testes do backend (pytest) contra um banco temporário
#   4. primeiro ADMIN, se ainda não existe nenhum usuário (interativo)
#   5. unit systemd urace-command-center em 127.0.0.1:8790
#   6. handle /ops* no bloco existente do Caddyfile (mesma técnica do /painel)
#   7. prova real: /ops/ responde 200 com o SPA, /ops/api/dashboard sem sessão
#      responde 401, e as páginas legais seguem 200
#
# Uso (no VPS):  bash adminai/deploy/command_center/servir_command_center.sh
set -euo pipefail

# ---------------------------------------------------------------- 0. sobrevive à queda do SSH
# O terminal do dono cai toda hora (17/09). O deploy leva 2-3 min: se a sessão cai no meio,
# o script morria junto. Agora ele se solta do terminal (setsid + nohup), grava tudo em
# ~/.urace/deploy-<data>.log e o terminal só acompanha o log. Caiu? Reconecte e rode:
#   tail -n 60 "$(ls -t ~/.urace/deploy-*.log | head -1)"
if [ -z "${URACE_DEPLOY_DETACHED:-}" ] && [ -t 1 ]; then
  mkdir -p "${URACE_DIR:-$HOME/.urace}"
  _LOG="${URACE_DIR:-$HOME/.urace}/deploy-$(date +%Y%m%d-%H%M%S).log"
  URACE_DEPLOY_DETACHED=1 setsid nohup bash "${BASH_SOURCE[0]}" "$@" > "$_LOG" 2>&1 < /dev/null &
  _PID=$!
  echo "-- deploy em segundo plano (sobrevive à queda do SSH) · log: $_LOG"
  echo "-- PODE FECHAR O TERMINAL ou apertar Ctrl+C: isso encerra só este acompanhamento."
  echo "   O deploy continua. Para ver como terminou, depois:  tail -n 20 $_LOG"
  tail -n +1 -f "$_LOG" --pid="$_PID" 2>/dev/null || true
  wait "$_PID" 2>/dev/null || true
  exit 0
fi

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DOMINIO="${DOMINIO:-urace-bridge.duckdns.org}"
CADDYFILE="/etc/caddy/Caddyfile"
PORTA="${CC_PORT:-8790}"
URACE_DIR="${URACE_DIR:-$HOME/.urace}"
VENV="$URACE_DIR/cc-venv"
UNIT=urace-command-center

echo "== Command Center -> https://ops.urace.us/ops/ (o antigo https://$DOMINIO/ops/ continua respondendo) =="
mkdir -p "$URACE_DIR"; chmod 700 "$URACE_DIR"

# ---------------------------------------------------------------- 1. venv
if ! python3 -c "import venv, ensurepip" 2>/dev/null; then
    echo "!! python3-venv ausente. Rode: sudo apt-get install -y python3-venv"; exit 1
fi
echo "-- 1/7 venv + fastapi/uvicorn (silencioso, 1-2 min na primeira vez)"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip >/dev/null
"$VENV/bin/pip" install -q -r "$REPO/command_center/requirements.txt"
"$VENV/bin/pip" install -q pytest httpx >/dev/null; "$VENV/bin/pip" install -q httpx2 >/dev/null 2>&1 || true   # starlette novo pede httpx2
echo "-- venv pronto: $("$VENV/bin/python" -c 'import fastapi; print("fastapi", fastapi.__version__)')"

# ------------------------------------------------------------- 2. frontend
if ! command -v npm >/dev/null; then
    echo "!! npm ausente. Instale Node 20+ (ex.: NodeSource) e rode de novo"; exit 1
fi
echo "-- 2/7 build do frontend: npm ci + vite (silencioso, 1-3 min)"
( cd "$REPO/command_center/web" && npm ci --no-audit --no-fund --silent && npm run build --silent )
[ -f "$REPO/command_center/web/dist/index.html" ] || { echo "!! build do frontend não gerou dist/index.html"; exit 1; }
echo "-- frontend construído: $(du -sh "$REPO/command_center/web/dist" | cut -f1)"

# --------------------------------------------------------------- 3. testes
echo "-- 3/7 testes do backend"
# cinto e suspensório: além do conftest, nenhum caminho de credencial real chega ao pytest
( cd "$REPO" && env -u ASANA_TOKEN -u DOCUSIGN_INTEGRATION_KEY -u GOOGLE_TOKEN_JSON URACE_ENV=/nao/existe GOOGLE_TOKEN_JSON_SUPPORT=/nao/existe CC_DB_PATH=/tmp/cc-test-$$.sqlite "$VENV/bin/python" -m pytest -q command_center/tests 2>&1 | tail -3 )
rm -f /tmp/cc-test-$$.sqlite*

# ------------------------------------------------------ 4. primeiro ADMIN
echo "-- 4/7 usuários"
N_USERS=$(cd "$REPO" && "$VENV/bin/python" - <<'PY'
from command_center.db import conectar, aplicar_schema, um
con = conectar(); aplicar_schema(con)
print(um(con, "SELECT COUNT(*) AS n FROM users")["n"])
PY
)
if [ "$N_USERS" = "0" ]; then
    echo "-- nenhum usuário ainda; criando o primeiro ADMIN (interativo)"
    ( cd "$REPO" && "$VENV/bin/python" -m command_center.manage create-admin )
fi

# ------------------------------------------------- 4b. chave do hook do Kommo
# O Salesbot bate em /ops/api/crm/hook?key=…; a chave nasce aqui, uma vez, e fica
# só em ~/.urace/kommo.env (600). Sem o arquivo, o CRM só não liga o chat.
KENV="$URACE_DIR/kommo.env"
if [ -f "$KENV" ] && ! grep -q '^KOMMO_HOOK_KEY=' "$KENV"; then
    echo "KOMMO_HOOK_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" >> "$KENV"
    chmod 600 "$KENV"
    echo "-- KOMMO_HOOK_KEY gerada em $KENV (a URL para o bot aparece em CRM → Ligar o chat)"
fi

# ---------------------------------------------------------- 4b. chave do cofre (#162)
# Só CRIA quando ainda não existe: trocar a chave deixaria as senhas guardadas sem abrir. O valor
# nunca aparece no terminal nem no log; fica só no adminai.env (600), que o serviço já lê.
_ENVF="$URACE_DIR/adminai.env"
touch "$_ENVF"; chmod 600 "$_ENVF"
if ! grep -q '^CC_COFRE_CHAVE=.\+' "$_ENVF"; then
    echo "CC_COFRE_CHAVE=$("$VENV/bin/python" -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("="))')" >> "$_ENVF"
    echo "-- cofre: chave criada em $_ENVF (guarde uma cópia desse arquivo fora do VPS)"
else
    echo "-- cofre: chave já existe (mantida)"
fi

# --------------------------------------------------------------- 5. systemd
echo "-- 5/7 serviço systemd"
sudo cp "$REPO/adminai/deploy/command_center/$UNIT.service" "/etc/systemd/system/$UNIT.service"
sudo sed -i "s|/home/ubuntu/Uraceagent|$REPO|g; s|/home/ubuntu/.urace|$URACE_DIR|g; s|^User=ubuntu|User=$(id -un)|; s|8790|$PORTA|g" \
        "/etc/systemd/system/$UNIT.service"
# 17/09: botão "Atualizar sistema" no painel — um path unit vigia ~/.urace/deploy.request e roda
# este mesmo script numa unit própria (fora do cgroup do serviço, então sobrevive ao restart).
_BRANCH="$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
# 06/10: interruptor do Chase no painel — mesmo desenho (urace-sdr.path reinicia a sales-bridge)
for _u in urace-deploy.service urace-deploy.path urace-sdr.service urace-sdr.path; do
    sudo cp "$REPO/adminai/deploy/command_center/$_u" "/etc/systemd/system/$_u"
    sudo sed -i "s|/home/ubuntu/Uraceagent|$REPO|g; s|/home/ubuntu/.urace|$URACE_DIR|g; s|/home/ubuntu|$HOME|g; s|^User=ubuntu|User=$(id -un)|; s|BRANCH|$_BRANCH|g" "/etc/systemd/system/$_u"
done
sudo systemctl daemon-reload
sudo systemctl enable "$UNIT.service" >/dev/null
sudo systemctl enable --now urace-deploy.path >/dev/null 2>&1 || true
sudo systemctl enable --now urace-sdr.path >/dev/null 2>&1 || true
sudo systemctl restart "$UNIT.service"
# 16/09: com 2 s fixos o script acusou falha numa subida que só estava lenta (o serviço
# aplica migrações e semeia o manual ao iniciar). Espera até 60 s, olhando a cada 2.
pronto=""
for _ in $(seq 1 30); do
    sleep 2
    systemctl is-active --quiet "$UNIT.service" \
        || { echo "!! o serviço não subiu:"; journalctl -u "$UNIT" -n 20 --no-pager; exit 1; }
    if curl -sf "http://127.0.0.1:$PORTA/ops/ready" >/dev/null; then pronto=1; break; fi
done
[ -n "$pronto" ] || { echo "!! /ops/ready não respondeu em 60 s"; journalctl -u "$UNIT" -n 20 --no-pager; exit 1; }
echo "-- serviço no ar em 127.0.0.1:$PORTA"
# 09/09: a triagem do Gmail passou para o Command Center (07/13/21h). O timer antigo
# das 07:00 rodaria um segundo agente ao mesmo tempo — e o VPS não aguenta dois.
if systemctl is-enabled --quiet urace-triagem-email.timer 2>/dev/null; then
    sudo systemctl disable --now urace-triagem-email.timer >/dev/null 2>&1 || true
    echo "-- urace-triagem-email.timer desligado: a triagem agora é do painel (Automação > Triagem do Gmail)"
fi

# páginas legais (issue #25: canonical, descrição e schema markup): se já foram publicadas
# uma vez por servir_legal.sh, cada deploy leva a versão nova
if [ -d /var/www/urace-legal ]; then
    sudo cp "$REPO/adminai/deploy/legal/privacy.html" "$REPO/adminai/deploy/legal/eula.html" /var/www/urace-legal/
    sudo chmod 644 /var/www/urace-legal/*.html
    echo "-- páginas legais atualizadas em /var/www/urace-legal"
fi

# ----------------------------------------------------------------- 6. Caddy
echo "-- 6/7 Caddy"
sudo cp "$CADDYFILE" "$CADDYFILE.bak-$(date +%Y%m%d-%H%M%S)"
sudo DOMINIO="$DOMINIO" PORTA="$PORTA" python3 - <<'PY'
import os, re
caddyfile = "/etc/caddy/Caddyfile"
dominio, porta = os.environ["DOMINIO"], os.environ["PORTA"]
s = open(caddyfile).read()
# handle (não handle_path): o FastAPI espera o prefixo /ops
# `/.well-known/oauth-*` vai junto porque a descoberta do OAuth mora na RAIZ do domínio,
# não sob /ops — é a especificação que manda assim (RFC 8414 e 9728), e sem isso o
# conector do claude.ai não acha o serviço de login (24/09).
bloco = ("\n\thandle /ops* {\n"
         f"\t\treverse_proxy 127.0.0.1:{porta}\n"
         "\t}\n"
         "\n\thandle /.well-known/oauth-* {\n"
         f"\t\treverse_proxy 127.0.0.1:{porta}\n"
         "\t}\n"
         # issue #25: o que os buscadores podem ver (o painel fica de fora; /legal/ entra)
         "\n\thandle /robots.txt {\n"
         f"\t\treverse_proxy 127.0.0.1:{porta}\n"
         "\t}\n"
         "\n\thandle /sitemap.xml {\n"
         f"\t\treverse_proxy 127.0.0.1:{porta}\n"
         "\t}\n")
def bloco_do_site(s, nome):
    """(início, fim) do corpo do site `nome { ... }`, contando as chaves — ou None.
    #71: a limpeza abaixo só pode mexer no site principal; antes ela rodava no arquivo
    inteiro, apagava os handle de ops.urace.us e my.urace.us e o Caddyfile saía inválido."""
    m = re.search(r"(^|\n)" + re.escape(nome) + r"\s*\{", s)
    if not m:
        return None
    i = m.end()
    nivel = 1
    while i < len(s) and nivel:
        nivel += {"{": 1, "}": -1}.get(s[i], 0)
        i += 1
    return m.end(), i - 1
faixa = bloco_do_site(s, dominio)
if faixa and "/ops*" in s[faixa[0]:faixa[1]]:
    corpo = s[faixa[0]:faixa[1]]
    # tira os blocos deste deploy (ops, oauth, robots, sitemap) e põe o conjunto novo no topo:
    # rodar de novo dá o mesmo arquivo, sem duplicar nem acumular linha em branco
    corpo = re.sub(r"\n\thandle /(ops\*|\.well-known/oauth-\*|robots\.txt|sitemap\.xml)\s*\{.*?\n\t\}\n", "\n", corpo, flags=re.S)
    corpo = bloco + "\n" + re.sub(r"\n{3,}", "\n\n", corpo).lstrip("\n")
    s = s[:faixa[0]] + corpo + s[faixa[1]:]
    open(caddyfile, "w").write(s); print("-- blocos /ops e /.well-known/oauth-* atualizados")
elif faixa:
    s = re.sub(re.escape(dominio) + r"\s*\{", lambda m: m.group(0) + bloco, s, count=1)
    open(caddyfile, "w").write(s); print("-- handle /ops inserido no bloco existente")
else:
    open(caddyfile, "a").write(f"\n{dominio} {{{bloco}}}\n"); print("-- bloco de site criado")
PY
# Endereço da URACE (dono, 30/09: "conseguimos deixar a url do site como o da urace?"; e 04/10,
# #79: "preciso que todas tenham a url urace.us"). Cada nome de CC_DOMINIOS_EXTRAS vira um site
# no Caddy com o MESMO servidor e TUDO o que o duckdns serve: painel, login do MCP (OAuth),
# páginas legais, robots/sitemap e os webhooks da ponte do Kommo. O duckdns continua no ar
# (Kommo, Dialpad, Intuit e conectores antigos batem lá até serem trocados). Só entra se o DNS
# do nome novo já aponta para ESTE servidor: sem isso o Let's Encrypt falha à toa.
for EXTRA in ${CC_DOMINIOS_EXTRAS:-ops.urace.us my.urace.us novo.urace.us parts.urace.us}; do
    IP_NOVO="$(getent ahostsv4 "$EXTRA" | awk 'NR==1{print $1}')"
    IP_NOSSO="$(getent ahostsv4 "$DOMINIO" | awk 'NR==1{print $1}')"
    if [ -z "$IP_NOVO" ] || [ "$IP_NOVO" != "$IP_NOSSO" ]; then
        echo "!! $EXTRA ainda não aponta para este servidor (DNS: ${IP_NOVO:-nada}; aqui: $IP_NOSSO) — pulei. Crie o registro A e rode de novo."
        continue
    fi
    sudo EXTRA="$EXTRA" PORTA="$PORTA" CADDYFILE="$CADDYFILE" python3 - <<'PY2'
import os, re
caddyfile = os.environ.get("CADDYFILE", "/etc/caddy/Caddyfile")
extra, porta = os.environ["EXTRA"], os.environ["PORTA"]
ponte = os.environ.get("PONTE_PORTA", "8800")
legal = os.environ.get("LEGAL_DIR", "/var/www/urace-legal")
# my.urace.us é o endereço do CLIENTE (dono, 01/10): a raiz abre a área do cliente. Os
# outros (ops.urace.us) abrem o painel da equipe e recebem também os webhooks da ponte.
cliente = extra.split(".")[0] == "my"
# #148: novo.urace.us é o SITE novo. O FastAPI responde tudo nele (as páginas, a agenda pública,
# a área do cliente em /ops/portal); o Caddy só serve as páginas legais, como nos outros.
site = extra.split(".")[0] == "novo"
# #180: parts.urace.us é o balcão do celular e só ele. O FastAPI trava a API nesse endereço;
# aqui só passam /ops (a tela e a API do balcão) e as páginas legais.
balcao = extra.split(".")[0] in ("parts", "balcao")
destino = "/ops/portal" if cliente else "/ops/"
corpo = (f"\n\tredir / {destino} 302\n"
         f"\thandle /ops* {{\n\t\treverse_proxy 127.0.0.1:{porta}\n\t}}\n"
         f"\thandle /.well-known/oauth-* {{\n\t\treverse_proxy 127.0.0.1:{porta}\n\t}}\n"
         f"\thandle /robots.txt {{\n\t\treverse_proxy 127.0.0.1:{porta}\n\t}}\n"
         f"\thandle /sitemap.xml {{\n\t\treverse_proxy 127.0.0.1:{porta}\n\t}}\n"
         f"\thandle_path /legal/* {{\n\t\troot * {legal}\n\t\tfile_server\n\t}}\n")
if balcao:
    corpo = (f"\n\tredir / /ops/ 302\n"
             f"\thandle /ops* {{\n\t\treverse_proxy 127.0.0.1:{porta}\n\t}}\n"
             f"\thandle_path /legal/* {{\n\t\troot * {legal}\n\t\tfile_server\n\t}}\n")
elif site:
    corpo = (f"\n\thandle_path /legal/* {{\n\t\troot * {legal}\n\t\tfile_server\n\t}}\n"
             f"\thandle {{\n\t\treverse_proxy 127.0.0.1:{porta}\n\t}}\n")
elif not cliente and not balcao:
    # #79: os mesmos webhooks públicos da ponte do Kommo que o duckdns expõe — nada além deles
    corpo += ("\t@ponte path /kommo/hook /kommo/eventos /health /human/whatsapp\n"
              f"\thandle @ponte {{\n\t\treverse_proxy 127.0.0.1:{ponte}\n\t}}\n")
if not site:
    corpo += "\thandle {\n\t\trespond \"not found\" 404\n\t}\n"
s = open(caddyfile).read()
m = re.search(r"(^|\n)" + re.escape(extra) + r"\s*\{", s)
if m:
    # reescreve o corpo inteiro (contando as chaves): rodar de novo dá o mesmo arquivo, e um
    # site criado pela versão antiga (só /ops) ganha o resto
    i, nivel = m.end(), 1
    while i < len(s) and nivel:
        nivel += {"{": 1, "}": -1}.get(s[i], 0)
        i += 1
    s = s[:m.end()] + corpo + s[i - 1:]
    open(caddyfile, "w").write(s)
    print(f"-- {extra}: site atualizado")
else:
    open(caddyfile, "a").write(f"\n{extra} {{{corpo}}}\n")
    print(f"-- {extra}: site criado (o certificado sai sozinho no primeiro acesso)")
PY2
done
sudo caddy fmt --overwrite "$CADDYFILE"
if VALIDA="$(sudo caddy validate --config "$CADDYFILE" 2>&1)"; then
    echo "-- Caddyfile válido"
else
    # #71: mostra o motivo e guarda a versão recusada, para dar para ver o que saiu errado
    RECUSADO="$CADDYFILE.invalido-$(date +%Y%m%d-%H%M%S)"
    sudo cp "$CADDYFILE" "$RECUSADO"
    echo "!! Caddyfile INVÁLIDO — restaurando backup (a versão recusada ficou em $RECUSADO)"
    echo "$VALIDA" | grep -i "error" | tail -3
    sudo cp "$(ls -t $CADDYFILE.bak-* | head -1)" "$CADDYFILE"; sudo systemctl reload caddy; exit 1
fi
sudo systemctl reload caddy

# ------------------------------------------------------------ 7. prova real
echo; echo "================= PROVA REAL ================="
SPA="$(curl -s -o /tmp/ops.html -w '%{http_code}' "https://$DOMINIO/ops/" || echo 000)"
TEM_APP=$(grep -c 'id="root"' /tmp/ops.html 2>/dev/null || echo 0)
VAZOU=$(grep -ciE 'Renato|Hubbard|Pionti|envelope' /tmp/ops.html 2>/dev/null || true); VAZOU=${VAZOU:-0}
API="$(curl -s -o /dev/null -w '%{http_code}' "https://$DOMINIO/ops/api/dashboard" || echo 000)"
LEGAL="$(curl -s -o /dev/null -w '%{http_code}' "https://$DOMINIO/legal/privacy.html" || echo 000)"
ROBOTS="$(curl -s "https://$DOMINIO/robots.txt" | grep -c 'Disallow: /ops/' || true)"
PAINEL="$(curl -s -o /dev/null -w '%{http_code}' "https://$DOMINIO/painel/" || echo 000)"
rm -f /tmp/ops.html
echo "   /ops/ sem sessão           -> HTTP $SPA  (200, SPA com login)"
echo "   SPA montado                -> $TEM_APP  (tem que ser 1)"
echo "   dado de cliente no HTML    -> $VAZOU  (tem que ser 0)"
echo "   /ops/api/dashboard sem sessão -> HTTP $API  (tem que ser 401)"
echo "   /legal/privacy.html        -> HTTP $LEGAL  (continua 200)"
echo "   /robots.txt bloqueia /ops/ -> $ROBOTS  (tem que ser 1)"
echo "   /painel/                   -> HTTP $PAINEL  (404 esperado: Pit Wall aposentado pelo dono em 18/09)"
echo
if [ "$SPA" = "200" ] && [ "$TEM_APP" = "1" ] && [ "$VAZOU" = "0" ] && [ "$API" = "401" ] && [ "$LEGAL" = "200" ]; then
    echo "✅ https://ops.urace.us/ops/ no ar (e https://$DOMINIO/ops/). Entre com o ADMIN criado; a API só responde com sessão."
else
    echo "❌ Algo não bate. Para voltar atrás:"
    echo "   sudo cp \$(ls -t $CADDYFILE.bak-* | head -1) $CADDYFILE && sudo systemctl reload caddy"
    exit 1
fi
