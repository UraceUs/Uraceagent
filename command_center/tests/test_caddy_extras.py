"""Endereços da URACE no Caddy (#57): ops.urace.us abre o painel da equipe e my.urace.us
abre a área do cliente. Roda o mesmo trecho Python que o deploy roda, num Caddyfile de teste."""
import os
import re
import subprocess
import sys

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "..", "adminai", "deploy", "command_center", "servir_command_center.sh")


def _trecho():
    s = open(SCRIPT, encoding="utf-8").read()
    return re.search(r"<<'PY2'\n(.*?)\nPY2\n", s, re.S).group(1)


def _roda(tmp_path, extra):
    caddy = tmp_path / "Caddyfile"
    if not caddy.exists():
        caddy.write_text("urace-bridge.duckdns.org {\n}\n")
    subprocess.run([sys.executable, "-c", _trecho()], check=True, capture_output=True,
                   env={**os.environ, "EXTRA": extra, "PORTA": "8787", "CADDYFILE": str(caddy)})
    return caddy.read_text()


def test_my_abre_a_area_do_cliente_e_ops_o_painel(tmp_path):
    s = _roda(tmp_path, "ops.urace.us")
    s = _roda(tmp_path, "my.urace.us")
    ops = re.search(r"\nops\.urace\.us \{(.*?)\n\}", s, re.S).group(1)
    my = re.search(r"\nmy\.urace\.us \{(.*?)\n\}", s, re.S).group(1)
    assert "redir / /ops/ 302" in ops
    assert "redir / /ops/portal 302" in my
    assert "reverse_proxy 127.0.0.1:8787" in my, "o mesmo servidor"


def test_rodar_de_novo_nao_duplica(tmp_path):
    _roda(tmp_path, "my.urace.us")
    s = _roda(tmp_path, "my.urace.us")
    assert s.count("my.urace.us {") == 1


def _passo6():
    s = open(SCRIPT, encoding="utf-8").read()
    return re.search(r"6/7 Caddy.*?<<'PY'\n(.*?)\nPY\n", s, re.S).group(1)


def _deploy(tmp_path):
    caddy = tmp_path / "Caddyfile"
    env = {**os.environ, "DOMINIO": "urace-bridge.duckdns.org", "PORTA": "8790", "CADDYFILE": str(caddy)}
    codigo = _passo6().replace('caddyfile = "/etc/caddy/Caddyfile"', f'caddyfile = {str(caddy)!r}')
    subprocess.run([sys.executable, "-c", codigo], check=True, capture_output=True, env=env)
    for extra in ("ops.urace.us", "my.urace.us"):
        subprocess.run([sys.executable, "-c", _trecho()], check=True, capture_output=True, env={**env, "EXTRA": extra})
    return caddy.read_text()


def _site(s, nome):
    return re.search(r"(?:^|\n)" + re.escape(nome) + r" \{\n(.*?)\n\}\n", s, re.S).group(1)


def test_segundo_deploy_nao_estraga_os_sites_extras(tmp_path):
    """#71 (02/10): a limpeza do passo 6 rodava no arquivo inteiro e apagava os handle de
    ops.urace.us e my.urace.us; o Caddyfile saía inválido ("unrecognized directive: }")."""
    (tmp_path / "Caddyfile").write_text("urace-bridge.duckdns.org {\n\thandle /painel* {\n\t\treverse_proxy 127.0.0.1:8787\n\t}\n}\n")
    primeiro = _deploy(tmp_path)
    segundo = _deploy(tmp_path)
    assert _deploy(tmp_path) == segundo, "rodar de novo não muda nada"
    assert segundo.count("{") == segundo.count("}")
    assert "}\thandle" not in segundo, "chave grudada no próximo bloco"
    for nome in ("ops.urace.us", "my.urace.us"):
        assert _site(segundo, nome) == _site(primeiro, nome), f"{nome} intacto"
        for h in ("handle /ops*", "handle /.well-known/oauth-*", "handle /robots.txt", "handle /sitemap.xml"):
            assert h in _site(segundo, nome), (nome, h)
    principal = _site(segundo, "urace-bridge.duckdns.org")
    assert principal.count("handle /ops*") == 1 and principal.count("handle /robots.txt") == 1
    assert "handle /painel*" in principal, "o que já existia no site principal fica"


def test_ops_serve_tudo_o_que_o_antigo_serve(tmp_path):
    """#79 (dono, 04/10: "preciso que todas tenham a url urace.us"): ops.urace.us leva as
    páginas legais e os webhooks públicos da ponte; my.urace.us (cliente) não leva a ponte."""
    (tmp_path / "Caddyfile").write_text("urace-bridge.duckdns.org {\n}\n")
    s = _deploy(tmp_path)
    ops, my = _site(s, "ops.urace.us"), _site(s, "my.urace.us")
    for h in ("handle_path /legal/*", "file_server", "handle /ops*", "handle /.well-known/oauth-*"):
        assert h in ops and h in my, h
    assert "@ponte path /kommo/hook /kommo/eventos /health /human/whatsapp" in ops
    assert "reverse_proxy 127.0.0.1:8800" in ops
    assert "@ponte" not in my, "o endereço do cliente não recebe webhook"
    assert ops.rindex("handle {") > ops.rindex("handle @ponte"), "o 404 do resto fica por último"


def test_site_antigo_so_com_login_ganha_o_resto(tmp_path):
    """O ops.urace.us que já está no VPS (só /ops) é reescrito, não duplicado."""
    (tmp_path / "Caddyfile").write_text(
        "urace-bridge.duckdns.org {\n}\n\nops.urace.us {\n\tredir / /ops/ 302\n"
        "\thandle /ops* {\n\t\treverse_proxy 127.0.0.1:8787\n\t}\n\thandle {\n\t\trespond \"not found\" 404\n\t}\n}\n")
    s = _roda(tmp_path, "ops.urace.us")
    assert s.count("ops.urace.us {") == 1 and s.count("{") == s.count("}")
    assert "handle_path /legal/*" in _site(s, "ops.urace.us")
    assert _roda(tmp_path, "ops.urace.us") == s, "rodar de novo não muda nada"
