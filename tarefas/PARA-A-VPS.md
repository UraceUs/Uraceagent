# Tarefas do Claude para a extensão da VPS

A extensão lê este arquivo **no começo de cada rodada**, faz o que está em ABERTO, e
move a linha para FEITO no relatório. É por aqui que o Claude manda trabalho — o dono
não é o carteiro.

Regra que não muda: as travas do `docs/extensao/PROMPT-VPS.md` continuam valendo. Uma
tarefa aqui só autoriza o que ela **diz explicitamente** que o dono autorizou, e nada além.

---

## ABERTO

### T-001 — Fechar as pendências aprovadas em 22/09

**Autorização do dono, nesta conversa, em 22/09** (é o que libera o `--aplicar` de
`unir_cards`, que normalmente você nunca roda):

- Savage: *"18 serviços Savage + 2 Savege estão no #15… são todos do Alexander?"* → **"sim"**
- Alex: *"1 serviço no #238 Alex Donnell… o solitário é mesmo do Donnell?"* → **"sim"**
- Unir Martin/Martin Jaramillo · Mikey/Mikey Collins · Sanghera/Levi Sanghera ·
  Luciano/Luciano Delgado · Mauricio/Mauricio Pardomo → **"sim"**
- E sobre as três: *"rode e resolva sozinho"*, *"olhe e resolva sozinho"*

**Faça:**

1. `git pull --rebase origin claude/configurar-open-claw-ooqo8x`
2. `bash adminai/fechar_pendencias_22_09.sh` (modo plano, não escreve nada)
3. **Confira o plano** antes de aplicar. Aplique só se as três forem verdade:
   - o carimbo do `#15` for de serviços cujo título começa com `Savage`/`Savege`, e o
     do `#238` for **um** serviço `Alex`;
   - cada união mostrar `FICA` no card de nome completo e `SAI` no de nome curto —
     nunca o contrário;
   - a linha `->` de cada união disser **responsável** e **piloto** separados, e o
     responsável não for trocado pelo nome do piloto quando forem pessoas diferentes.
   Qualquer uma falhando: **não aplique**, e reporte o plano inteiro.
4. Se passou: `bash adminai/fechar_pendencias_22_09.sh --aplicar`
5. Reporte, no formato de sempre, incluindo:
   - a linha `RESUMO` da varredura depois de aplicar (esperado: `0 movidos`, e
     `20 confirmados por você`);
   - **a seção inteira de waivers em aberto**, sem cortar. O que interessa ali é o
     grupo `JÁ RODOU SEM WAIVER` — se tiver alguém, é serviço que já aconteceu sem
     waiver assinada, e o dono precisa ver nome e data.

**Não faça:** enviar lembrete de waiver, cobrar ninguém, anular envelope, ou unir
qualquer par que não esteja na lista acima.

---

## FEITO

_(mova para cá com a data e o commit do relatório)_
