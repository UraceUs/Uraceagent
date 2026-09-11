---
tipo: decisao
data: 2026-09-11
fonte: dono (chat + confirmação marcador por marcador no manual)
tipo_info: DECISION
responsavel: Italo Silveira
status: ativo
---

# D-2026-09-11 — O manual dos marcadores do Gmail, confirmado pelo dono

**Dono:** *"Em momento nenhum eu falei que era para criar marcadores… eu
preciso que a IA leia marcador por marcador que existia antes, entenda o que
se coloca em cada um, me dê o manual e eu confirmo — só daí ela sabe como
agir."*

## O que ficou decidido

1. **A IA não cria marcador** (já era regra no MCP; agora está dito em voz
   alta) e **não usa marcador que o dono não tenha confirmado**.
2. **O manual é a única regra de classificação**: 156 marcadores lidos da
   caixa em 11/09, com o que vai em cada um e o volume real. O dono
   confirmou **145**; deixou **11 de fora** (`Email Review/…`).
3. **Sem manual confirmado, a triagem não roda.** Com ele, o prompt leva o
   manual inteiro e a lista fechada de marcadores — o que não está lá não
   existe para a IA.
4. **Marcador novo que aparecer na caixa entra como `pendente`** e fica
   invisível para a IA até o dono confirmar (Gmail → Manual dos marcadores).
5. Correções do dono, com a própria mão: `LOC | Practice` = "treino
   independente da pista"; `Shipping Status` cobre também **'purchased'**.

## Sobre os `Email Review/…`

Não são dele e não foram feitos pelo painel. Aplicados em ~700 conversas nos
últimos 14 dias por um filtro do Gmail ou app com acesso à caixa — e erram
(extrato do Home Depot marcado como "Verification Code"). Ficam **fora** do
manual. Sumir de vez é no Gmail (Configurações → Filtros) e na Conta Google
(Segurança → Apps com acesso).

## Ponto que o dono ainda pode querer mudar

Ele confirmou também os 6 marcadores de `Years 2019-2023`, cujo texto diz
"arquivo morto por ano — a triagem NÃO usa". Como está, a IA pode arquivar
e-mail novo lá dentro. Um clique em "não usar" na tela resolve.

Onde vive: `command_center/providers/taxonomia_gmail.py` (o manual),
tabela `gmail_labels` (estado e confirmação), `providers/triagem.py` (a
trava), tela `Gmail → Manual dos marcadores`, artifact do dono.
