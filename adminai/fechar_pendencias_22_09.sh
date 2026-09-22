#!/usr/bin/env bash
# Fecha, numa passada só, o que o dono aprovou em 22/09.
#
#   bash adminai/fechar_pendencias_22_09.sh            # plano: não escreve nada
#   bash adminai/fechar_pendencias_22_09.sh --aplicar
#
# 1. Carimba SÓ os serviços que ele aprovou: os "Savage"/"Savege" do #15 e o "Alex" do
#    #238. Com filtro por nome, de propósito — sem ele a ferramenta carimbava os 70
#    serviços do card, incluindo uma corrida (a extensão da VPS pegou em 22/09).
# 2. Une os cinco pares que ele aprovou.
# 3. Varredura depois, para provar que nada se mexeu.
# 4. Waivers em aberto, separadas por risco real.
set -uo pipefail
cd "$(dirname "$0")/.."

APLICAR=""
[ "${1:-}" = "--aplicar" ] && APLICAR="--aplicar"
[ -z "$APLICAR" ] && echo ">>> MODO PLANO — nada será escrito. Repita com --aplicar." || echo ">>> APLICANDO"

PARES=(
  "Martin+Martin Jaramillo=Martin Jaramillo"
  "Mikey+Mikey Collins=Mikey Collins"
  "Sanghera+Levi Sanghera=Levi Sanghera"
  "Luciano+Luciano Delgado=Luciano Delgado"   # acha o #105 pelo PILOTO; responsável fica Alonso Delgado
  "Mauricio+Mauricio Pardomo=Mauricio Pardomo"
)
ARGS=(); for p in "${PARES[@]}"; do ARGS+=(--unir "$p"); done

echo; echo "################ 1. CARIMBO (dono confirmou de quem são) ################"
python3 adminai/confirmar_servicos.py 15 --nome Savage --nome Savege $APLICAR
python3 adminai/confirmar_servicos.py 238 --nome Alex $APLICAR

echo; echo "################ 2. UNIÕES APROVADAS ################"
python3 adminai/unir_cards.py "${ARGS[@]}" $APLICAR

echo; echo "################ 3. VARREDURA (só leitura) ################"
python3 adminai/atribuir_servicos.py --limite 30 | grep -E "RESUMO|cards que nasceriam|PARA VOCÊ UNIR" || true

echo; echo "################ 4. WAIVERS EM ABERTO ################"
python3 adminai/waivers_em_aberto.py

echo; echo ">>> FIM."
[ -z "$APLICAR" ] && echo ">>> Nada foi escrito. Para valer: bash adminai/fechar_pendencias_22_09.sh --aplicar"
exit 0
