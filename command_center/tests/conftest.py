"""Isola os testes do mundo real ANTES de qualquer import da aplicação.

No VPS os testes rodavam com ~/.urace/google-token.json presente: o
gmail_mcp usa esse caminho por padrão quando GOOGLE_TOKEN_JSON não está
definido, e o teste "sem credencial" chamou o Gmail de verdade
(04/09). Aqui HOME vira um diretório vazio e toda credencial conhecida
é apagada do ambiente. Teste nunca fala com sistema real.
"""
import os
import tempfile

os.environ["HOME"] = tempfile.mkdtemp(prefix="cc-home-")
for k in ("URACE_ENV", "GOOGLE_TOKEN_JSON", "GOOGLE_TOKEN_JSON_SUPPORT"):
    os.environ[k] = "/nao/existe"
for k in list(os.environ):
    if k.startswith(("ASANA_", "DOCUSIGN_", "QBO_", "GOOGLE_CLIENT", "OPENCLAW_GATEWAY")) or k == "APLICAR":
        del os.environ[k]
os.environ["CC_AUTOSYNC"] = "0"          # teste não roda o laço de sincronia
