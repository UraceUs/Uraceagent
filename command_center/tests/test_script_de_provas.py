"""O script de provas nunca manda mexer no venv da produção (#264).

Dono, 15/10, rodando `testar_tudo.sh` na VPS: o script parou dizendo para instalar pytest,
httpx e playwright em `~/.urace/cc-venv` — que é o venv do **serviço no ar**. Seguir aquilo
resolveria as versões de produção de novo, com risco de derrubar o Command Center. O script
existe para provar o sistema sem tocar na operação; a instrução dele contradizia isso.

Agora ele usa um venv só de teste (`CC_TEST_PY` ou `~/.urace/teste-venv`) e é isso que a
mensagem manda criar.
"""
import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "adminai" / "deploy" / "command_center" / "testar_tudo.sh"


def test_o_script_tem_sintaxe_valida():
    assert subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True).returncode == 0


def test_sem_dependencia_ele_manda_criar_o_venv_do_teste_e_nunca_tocar_no_da_producao(tmp_path):
    """Com um 'python' de produção que não tem as dependências, a mensagem tem de ser a do
    venv isolado. Nada é instalado: o script para no passo 2."""
    casa = tmp_path / "casa"
    binario = casa / ".urace" / "cc-venv" / "bin"
    binario.mkdir(parents=True)
    falso = binario / "python"
    falso.write_text("#!/bin/sh\nexit 1\n")          # sem pytest/playwright: a checagem falha
    falso.chmod(0o755)

    ambiente = {k: v for k, v in os.environ.items() if not k.startswith(("STRIPE_", "QBO_", "GOOGLE_"))}
    ambiente.update(HOME=str(casa), PATH=os.environ.get("PATH", ""))
    for k in ("CC_TEST_PY", "CC_TEST_VENV", "CC_DB_PATH", "URACE_DIR"):
        ambiente.pop(k, None)

    r = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=ambiente, timeout=120)
    saida = r.stdout + r.stderr

    assert r.returncode == 1, saida
    assert "teste-venv" in saida, saida
    for linha in saida.splitlines():
        if "pip install" in linha or "playwright install" in linha:
            assert "cc-venv" not in linha, f"manda instalar no venv da produção: {linha}"


def test_o_python_do_teste_vem_antes_do_da_producao():
    texto = SCRIPT.read_text(encoding="utf-8")
    escolha = texto.split("# ------------------------------------------------------------- 2.")[1]
    i_teste = min(escolha.index("CC_TEST_PY"), escolha.index("TESTE_VENV"))
    assert i_teste < escolha.index('"$VENV/bin/python"'), "o venv da produção não pode ser a primeira escolha"


def test_o_caminho_do_chromium_e_sempre_resolvido_e_repassado_ao_pytest():
    """A suíte roda com um HOME descartável, e o Playwright procura o navegador em
    `$HOME/.cache/ms-playwright`. Então o caminho tem de ser resolvido fora do pytest e
    repassado em `PW_CHROMIUM` SEMPRE — senão todo teste de tela vira erro
    ("Executable doesn't exist at /tmp/.../cc-home-.../"), como aconteceu na VPS em 15/10.

    Conferência no texto do script, de propósito: rodar o passo 2 de verdade exigiria um
    navegador instalado nesta máquina de teste."""
    texto = SCRIPT.read_text(encoding="utf-8")
    assert "p.chromium.executable_path" in texto, "pergunte ao Playwright onde está o navegador"
    assert '[ -n "$CHROMIUM" ] && LIMPO+=' not in texto, "PW_CHROMIUM não pode ser opcional no pytest"
    assert 'LIMPO+=("PW_CHROMIUM=$CHROMIUM")' in texto
    assert "chrome-linux*/chrome" in texto, "o Chromium novo vem em chrome-linux64/"
