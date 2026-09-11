# D-2026-09-09 — Aprovar = enviar; mensalidade montada no dia 1, com prévia

**Dono, 09/09/2026:** *"Sempre que for para mandar algo relacionado a
esses modelos, peça aprovação, coloque no quadro de aprovação. Toda
recorrente é enviada no dia 1 do mês: a IA monta todas, uma por cliente,
já pronta só para a aprovação do envio. Tudo que precisar de aprovação
vem com pré-visualização; o botão de aprovar é o de enviar."*

**Como ficou:**
- Ação composta `qbo_criar_e_enviar_invoice` (REQUIRES_APPROVAL): cria e
  envia num clique. Na tela de Aprovações a prévia mostra cliente,
  linhas, unitário, quantidade e total; o botão diz **"Aprovar e enviar"**.
  Waiver idem (modelo, quem assina, e-mail).
- **Dia 1**: regra `mensalidade_dia_1` gera um evento `billing.monthly`
  por cliente com **plano mensal** (campo novo no card: Academy Baby Kart /
  4 stroke / 2 stroke / kart próprio / + mecânico / contratos), uma vez por
  mês. A IA monta a invoice pela aba Academy da [[Rate Card]] e deixa
  esperando aprovação.
- Sem os dados exatos (argumentos), a prévia avisa e aprovar falha
  explicando: nada sai "no escuro".

**Preços ditados hoje** (na memória da IA e em [[Rate Card]]): diária
tudo incluso (Own Kart $500 · Baby Kart $719 · 4T $719 · 2T $819 · Adult
Shifter $899); Lead and Follow fechado antes $769 (last-minute só o
operador na pista); mensal sem contrato conforme a planilha; **+$250 por
sessão fora do OKC**.

Relacionado: [[D-2026-09-04 - Invoice sai depois de aprovada no painel]], [[Invoice e estimate no QuickBooks]].
