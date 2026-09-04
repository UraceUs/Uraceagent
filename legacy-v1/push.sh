#!/usr/bin/env bash
# Primeiro push para github.com/UraceUs/Uraceagent
#
# Precisa de um Personal Access Token com escopo 'repo':
#   github.com > Settings > Developer settings > Personal access tokens
#
# O token NÃO vai neste arquivo. O git pede na hora, ou use o gh CLI.
set -euo pipefail

git init -b main
git add .
git commit -m "AI Sales Agent URace — arquitetura, schema, prompts, catálogo, agente e testes"
git remote add origin https://github.com/UraceUs/Uraceagent.git
git push -u origin main

echo
echo "Confirme que .env NÃO foi commitado:"
git ls-files | grep -E '^\.env$' && echo "ATENÇÃO: .env commitado, remova antes de publicar" || echo "ok — .env fora do repositório"
