#!/usr/bin/env python3
"""Diagnóstico e recuperação do ACESSO ao painel do OpenClaw.

Por que existe: o login no dashboard falha mesmo com token e senha
"encontrados na VPS". Este ambiente tem DUAS camadas de autenticação que
se confundem uma com a outra, e três causas prováveis conhecidas:

  CAMADA 1 — Caddy (basic_auth): usuário "urace" + a senha definida no
    setup_claw_ui.sh. Protege https://urace-claw.duckdns.org.
  CAMADA 2 — Gateway do OpenClaw: token, passado como FRAGMENTO de URL
    (#token=..., nunca ?token=...). Sem ele o painel abre e recusa.

  Causas prováveis, por ordem:
  1. Token antigo: `openclaw doctor --generate-gateway-token` foi rodado
     em 27/08 -- QUALQUER token copiado antes disso é inválido.
  2. Token no lugar errado: colado como senha do basic_auth (camada 1),
     ou como ?token= na query em vez de #token= no fragmento.
  3. Senha do basic_auth trocada (setup_claw_ui.sh rodou de novo) e o
     navegador insistindo na senha antiga em cache.
  4. DISPOSITIVO NÃO PAREADO (descoberto em 27/08 pela tela real do VPS):
     esta versão do OpenClaw autentica navegadores por "Browser Device
     Pairing" -- o MOTD interativo anuncia "Dashboard URL:
     https://<IP-público>/overview" + token e pergunta "Continue with
     browser device pairing? (y/n)". Tentar logar na URL de IP cru falha
     (o 443 é do Caddy, roteado por hostname -- IP cru não casa com site
     nenhum), e mesmo na URL certa o painel pode exigir que o DISPOSITIVO
     do navegador esteja aprovado (`openclaw devices approve`), não só o
     token. Três falhas se compondo: URL errada + device não pareado +
     token regenerado.

O script DESCOBRE o estado real (processo, porta, config, token efetivo,
Caddy, systemd, env) e testa cada elo separadamente, imprimindo no final
um bloco "COMO LOGAR" com a URL pronta. Correções com efeito colateral
são gated por flag explícita -- nada de regenerar credencial sem pedido:

  --show-token             imprime o token e a URL completa de login
                           (por padrão o token sai mascarado)
  --reset-ui-password SENHA  redefine a senha do basic_auth (camada 1)
  --regen-token            regenera o token do gateway (INVALIDA o atual;
                           só use se o token efetivo estiver comprometido)

Uso (no VPS):
    python3 salesagent/tools/openclaw_access_doctor.py
    python3 salesagent/tools/openclaw_access_doctor.py --show-token
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REL: list[str] = []


def say(t=""):
    REL.append(t)
    print(t, flush=True)


def run(cmd, timeout=60):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, stdin=subprocess.DEVNULL)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as exc:
        return 1, str(exc)


def json_da_saida(texto):
    i, j = texto.find("{"), texto.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        return json.loads(texto[i:j + 1])
    except json.JSONDecodeError:
        return None


def mascarar(tok):
    return (tok[:6] + "..." + tok[-4:]) if tok and len(tok) > 12 else "(curto/vazio)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show-token", action="store_true")
    ap.add_argument("--reset-ui-password")
    ap.add_argument("--regen-token", action="store_true")
    args = ap.parse_args()

    say(f"# openclaw_access_doctor — {time.strftime('%d/%m/%Y %H:%M')}")
    problemas: list[str] = []

    # ---------------- 1. onde e como o gateway roda
    say("\n== GATEWAY (processo, porta, unit) ==")
    rc, st = run(["openclaw", "gateway", "status"])
    say(f"  gateway status: rc={rc}")
    rc, ss = run(["bash", "-c", "ss -ltnp 2>/dev/null | grep 18789 || true"])
    say(f"  porta 18789: {ss.strip()[:120] or 'NINGUÉM escutando'}")
    if not ss.strip():
        problemas.append("gateway não está escutando em 18789 — 'openclaw gateway restart'")
    rc, unit = run(["bash", "-c",
                    "systemctl cat openclaw-gateway 2>/dev/null | grep -E 'ExecStart|Environment' || true"])
    say("  unit systemd:")
    for ln in unit.splitlines():
        say(f"    {ln.strip()[:130]}")
    env_tok = ""
    m = re.search(r"OPENCLAW_GATEWAY_TOKEN=(\S+)", unit)
    if m:
        env_tok = m.group(1).strip('"')

    # ---------------- 2. o token EFETIVO
    # Lição da rodada de 27/08 21:36: `openclaw config get` devolveu
    # "__OPENCLAW_REDACTED__" -- ou o CLI REDIGE segredos na saída (e o
    # valor real vive só no arquivo), ou a config foi corrompida com o
    # próprio placeholder (copy/paste de uma saída redigida). Ler o
    # ARQUIVO direto é o único jeito de distinguir as duas.
    say("\n== TOKEN (lido do ARQUIVO, com CLI só de conferência) ==")

    def eh_placeholder(tk):
        return bool(tk) and "REDACT" in tk.upper()

    cfg_file = Path.home() / ".openclaw" / "openclaw.json"
    file_tok = ""
    if cfg_file.exists():
        try:
            raw_cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
            ft = ((raw_cfg.get("gateway") or {}).get("auth") or {}).get("token")
            if isinstance(ft, str):
                file_tok = ft
            elif ft is not None:
                say(f"  token no arquivo não é string (SecretRef?): {type(ft).__name__}")
        except Exception as exc:
            say(f"  falha lendo {cfg_file}: {exc}")
    else:
        say(f"  {cfg_file} não existe")
    rc, out = run(["openclaw", "config", "get", "gateway"])
    gcfg = json_da_saida(out) or {}
    cli_tok = ((gcfg.get("auth") or {}).get("token")) or ""
    modo = (gcfg.get("auth") or {}).get("mode", "?")
    say(f"  gateway.auth.mode: {modo}")
    say(f"  token via CLI:     {mascarar(cli_tok)}"
        + ("  <- placeholder (CLI redige OU config corrompida)"
           if eh_placeholder(cli_tok) else ""))
    say(f"  token no ARQUIVO:  "
        + (mascarar(file_tok) if file_tok else "(ausente)")
        + ("  <- PLACEHOLDER LITERAL: config corrompida!"
           if eh_placeholder(file_tok) else
           ("  <- REAL (o CLI só redige na saída)" if file_tok else "")))
    if env_tok and not eh_placeholder(env_tok):
        say(f"  token no systemd:  {mascarar(env_tok)}")

    if eh_placeholder(file_tok):
        problemas.append(
            "H1 CONFIRMADA: gateway.auth.token no ARQUIVO é literalmente "
            "'__OPENCLAW_REDACTED__' — nenhum token real funciona. Reparo: "
            "rodar de novo com --regen-token (não perde nada: o atual é o "
            "placeholder).")
    candidatos = [tk for tk in (file_tok, env_tok, cli_tok)
                  if tk and not eh_placeholder(tk)]
    efetivo = candidatos[0] if candidatos else ""
    if not efetivo and not eh_placeholder(file_tok):
        problemas.append("nenhum token utilizável encontrado — gere com --regen-token")

    # ---------------- 3. loopback: o painel responde por dentro?
    say("\n== PAINEL no loopback ==")
    rc, code = run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                    "-m", "8", "http://127.0.0.1:18789/"])
    say(f"  GET 127.0.0.1:18789 -> HTTP {code.strip() or 'sem resposta'}")
    if code.strip() not in ("200", "301", "302", "401"):
        problemas.append(f"painel não responde no loopback (HTTP {code.strip()!r})")

    # ---------------- 4. Caddy (camada 1)
    say("\n== CADDY (basic_auth + proxy) ==")
    rc, val = run(["bash", "-c",
                   "sudo caddy validate --config /etc/caddy/Caddyfile 2>&1 | tail -2"])
    say(f"  validate: {val.strip()[:140]}")
    if "Valid" not in val and "valid" not in val:
        problemas.append("Caddyfile inválido — o site do painel pode estar fora")
    rc, ativo = run(["systemctl", "is-active", "caddy"])
    say(f"  serviço caddy: {ativo.strip()}")
    site = Path("/etc/caddy/claw-ui.caddy")
    dominio = "urace-claw.duckdns.org"
    if site.exists():
        txt = site.read_text()
        m = re.match(r"\s*([^\s{]+)\s*\{", txt.split("\n", 2)[-1] if txt.startswith("#") else txt, re.M)
        m2 = re.search(r"^([a-z0-9.-]+)\s*\{", txt, re.M)
        if m2:
            dominio = m2.group(1)
        say(f"  site do painel: {dominio} (basic_auth usuário 'urace')")
        say("  (a senha não é recuperável — só o hash é guardado; se perdeu, "
            "use --reset-ui-password)")
    else:
        problemas.append("claw-ui.caddy não existe — painel nunca exposto ou removido")
    # testa o caminho completo por dentro da máquina (sem depender de DNS/hairpin)
    rc, code2 = run(["curl", "-sk", "-o", "/dev/null", "-w", "%{http_code}",
                     "-m", "8", "--resolve", f"{dominio}:443:127.0.0.1",
                     f"https://{dominio}/"])
    say(f"  GET via Caddy (interno) -> HTTP {code2.strip() or 'sem resposta'} "
        f"{'(401 = basic_auth pedindo senha: caminho SAUDÁVEL)' if code2.strip() == '401' else ''}")
    if code2.strip() not in ("401", "200"):
        problemas.append(f"caminho via Caddy devolveu {code2.strip()!r} — proxy/cert/rota")

    # ---------------- 4b. pareamento de dispositivos (versões novas)
    say("\n== DISPOSITIVOS PAREADOS (auth de navegador) ==")
    rc, dev = run(["openclaw", "devices", "list"], timeout=45)
    if rc == 0 and dev.strip():
        for ln in [l for l in dev.splitlines() if l.strip()][:12]:
            say(f"  {ln.strip()[:130]}")
        if re.search(r"operator\.read", dev) and "operator " not in dev:
            say("  nota: o device pareado tem escopo de LEITURA "
                "(operator.read) — pode logar e não conseguir operar; o "
                "pareamento novo (rota A) resolve com escopo completo.")
        if re.search(r"pending|aguard", dev, re.I):
            say("  !! há dispositivo PENDENTE — o dono aprova com: "
                "openclaw devices approve")
            problemas.append("dispositivo de navegador aguardando aprovação "
                             "(openclaw devices approve) — provável causa do login falhar")
    else:
        say("  (comando 'devices list' indisponível ou vazio nesta versão)")
    # como o gateway se anuncia (bind/porta/URL pública)
    interess = {k: v for k, v in gcfg.items()
                if k != "auth" and not isinstance(v, (dict, list))}
    if interess:
        say(f"  gateway (bind/porta/etc): {interess}")

    # ---------------- 5. correções sob flag
    if args.reset_ui_password:
        say("\n== RESET da senha do painel (camada 1) ==")
        rc, out = run(["bash",
                       str(Path(__file__).resolve().parent.parent / "deploy/setup_claw_ui.sh"),
                       dominio, args.reset_ui_password], timeout=120)
        say("  " + out.strip().splitlines()[-1][:120] if out.strip() else "  (sem saída)")
        say("  senha redefinida — use a nova no prompt do navegador (usuário urace)")
    if args.regen_token:
        say("\n== REGENERANDO token do gateway (invalida o anterior!) ==")
        run(["openclaw", "doctor", "--generate-gateway-token"], timeout=120)
        run(["openclaw", "gateway", "restart"], timeout=90)
        time.sleep(3)
        rc, out = run(["openclaw", "config", "get", "gateway"])
        efetivo = (((json_da_saida(out) or {}).get("auth") or {}).get("token")) or efetivo
        say(f"  novo token: {mascarar(efetivo)}")

    # ---------------- 6. veredito + como logar
    say("\n" + "=" * 56)
    if problemas:
        say("PROBLEMAS ENCONTRADOS:")
        for p in problemas:
            say(f"  - {p}")
    else:
        say("NENHUM defeito de infraestrutura: as camadas respondem. O login "
            "falhando é quase certamente credencial errada/na camada errada.")
    say("\nCOMO LOGAR — três rotas, da mais simples à mais completa:")
    say("  ROTA A (pareamento, versões novas): abra a URL do painel no SEU "
        "navegador; se aparecer pedido de pareamento, aprove NO VPS com "
        "'openclaw devices approve' (ou responda y no prompt interativo do "
        "terminal SE o pedido for do seu próprio navegador). Aprovar "
        "pareamento concede acesso ao gateway: só o dono faz isso.")
    say("  ROTA B (túnel, sem senha nenhuma): ssh -N -L 18789:127.0.0.1:18789 "
        "ubuntu@IP e abrir http://localhost:18789/ — localhost é confiável.")
    say("  ROTA C (Caddy + token):")
    say(f"  1) Abra: https://{dominio}/  (NUNCA o IP cru — o 443 "
        "roteia por hostname e o IP não casa com site nenhum)")
    say("     O NAVEGADOR pede usuário/senha -> usuário: urace  senha: a do "
        "setup_claw_ui.sh (não é o token!)")
    if args.show_token and efetivo:
        say(f"  2) Depois entre com a URL completa (token no FRAGMENTO):")
        say(f"     https://{dominio}/#token={efetivo}")
    else:
        say("  2) Depois acrescente o token como FRAGMENTO na URL: "
            f"https://{dominio}/#token=SEU_TOKEN")
        say("     (rode com --show-token para imprimir a URL pronta; o token "
            "atual está mascarado acima)")
    say("  Alternativa sem Caddy/token: ssh -N -L 18789:127.0.0.1:18789 "
        "ubuntu@IP e abrir http://localhost:18789/")

    destino = Path.home() / ".urace" / f"access-doctor-{time.strftime('%Y%m%d-%H%M')}.md"
    try:
        destino.write_text("\n".join(REL), encoding="utf-8")
        say(f"\nRelatório: {destino}")
    except Exception:
        pass
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
