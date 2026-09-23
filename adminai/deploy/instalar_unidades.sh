#!/usr/bin/env bash
# Copia TODAS as unidades systemd do repositório e recarrega o systemd.
#
# Existe porque em 22/09 eu passei ao dono um comando que copiava três unidades e
# esquecia a quarta — e o aviso de "Unknown specifier" continuou aparecendo no
# urace-brain-health. Uma lista escrita à mão esquece; um glob não.
set -euo pipefail
cd "$(dirname "$0")"

echo "-- unidades encontradas:"
# -maxdepth é opção GLOBAL: posta depois do -name, o find avisa e a profundidade
# passa a valer para tudo, inclusive o que veio antes. Vem primeiro, e os dois -name
# ficam num parêntese — senão o -o separa a expressão e o resultado é outro (23/09).
mapfile -t UNIDADES < <(find . -maxdepth 2 \( -name '*.service' -o -name '*.timer' \) | sort)
for u in "${UNIDADES[@]}"; do echo "   $(basename "$u")"; done

for u in "${UNIDADES[@]}"; do
    sudo cp "$u" "/etc/systemd/system/$(basename "$u")"
done
sudo systemctl daemon-reload
echo "-- recarregado."

echo "-- procurando aviso de specifier (tem de vir vazio):"
if sudo journalctl -p warning --since '1 min ago' --no-pager 2>/dev/null | grep -i "specifier" ; then
    echo "   !! ainda há aviso acima"
else
    echo "   nenhum."
fi
