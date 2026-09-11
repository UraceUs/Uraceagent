#!/usr/bin/env bash
# Desliga o Chase (agente de vendas) — decisão do dono em 28/08/2026,
# durante a migração para o Administrative AI.
#
# O que este script FAZ: para e desabilita o serviço sales-bridge.
# O que ele NÃO faz: não apaga nada. Banco (~/.urace/salesbridge.db),
# vault (brain/), config do OpenClaw, Caddy e o painel ficam intactos.
# O gateway do OpenClaw continua de pé (o Admin AI vai usá-lo).
#
# Consequência operacional: leads no Kommo voltam a ser 100% humanos.
# O webhook do Kommo passará a receber 502 do Caddy — inofensivo, mas o
# ideal é o dono também PAUSAR o salesbot/webhook na interface do Kommo.
#
# Para religar: bash salesagent/deploy/install_bridge_service.sh
#           ou: sudo systemctl enable --now sales-bridge
#
# Uso (no VPS): bash salesagent/deploy/shutdown_chase.sh
set -euo pipefail

if ! systemctl list-unit-files sales-bridge.service >/dev/null 2>&1; then
    echo "-- sales-bridge.service nem existe nesta máquina: nada a fazer"
    exit 0
fi

echo "== estado antes =="
systemctl is-active sales-bridge || true
systemctl is-enabled sales-bridge || true

sudo systemctl disable --now sales-bridge

echo "== prova real (nunca confiar só no rc=0) =="
ATIVO="$(systemctl is-active sales-bridge || true)"
echo "-- systemd: $ATIVO (esperado: inactive)"
if curl -sf -m 5 http://127.0.0.1:8800/health >/dev/null 2>&1; then
    echo "!! /health AINDA RESPONDE -- o serviço não caiu de verdade. Investigar:"
    echo "   sudo systemctl status sales-bridge; sudo ss -ltnp | grep 8800"
    exit 1
fi
echo "-- http://127.0.0.1:8800/health não responde mais: ponte desligada"
echo "-- gateway do OpenClaw segue de pé?"
curl -sf -m 5 http://127.0.0.1:18789/ >/dev/null 2>&1 \
    && echo "   gateway OK (intacto, como planejado)" \
    || echo "   gateway não respondeu na raiz (normal se exigir token; conferir: openclaw status)"

echo
echo "CHASE DESLIGADO. Leads no Kommo agora são 100% humanos."
echo "AÇÃO DO DONO no Kommo (recomendada): pausar o salesbot/desativar o"
echo "webhook para https://urace-bridge.duckdns.org/kommo/hook — evita 502s."
