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
