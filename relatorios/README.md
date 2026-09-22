# Relatórios da VPS

A extensão que opera a VPS escreve aqui, um arquivo por rodada
(`vps-AAAAMMDDTHHMMSSZ.md`), e empurra para a branch. É por este caminho que o Claude
fica sabendo o que aconteceu lá — sem o dono no meio.

Formato e limites em `docs/extensao/PROMPT-VPS.md`.

Seções que o Claude lê primeiro: **Precisa do Claude** e **Precisa do dono**.

O caminho de volta — o que o Claude manda para a VPS — é `tarefas/PARA-A-VPS.md`.
