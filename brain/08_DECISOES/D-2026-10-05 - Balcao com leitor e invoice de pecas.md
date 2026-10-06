---
tipo: decisao
tipo_info: DECISION
data: 2026-10-05
fonte: [[Administrative AI]]
responsavel: Como a peça usada vira cobrança: leitor no balcão, invoice de peças por dia no QuickBooks.
status: ativo
---

# D-2026-10-05 — Balcão com leitor: QR do cliente + código da peça → invoice de peças

issue #87, 05/10/2026

## O que foi decidido
Tela **Balcão** no Command Center, feita para um coletor Android com leitor 1D/2D (o leitor
"digita" o código no campo, como teclado). O mecânico lê o **QR do cliente** e depois **cada peça**.

- **A invoice nasce no QuickBooks na hora**, na primeira peça cobrada. Cada peça seguinte
  vira mais uma linha nela.
- **Uma invoice de peças por cliente por dia** (Flórida). Memo:
  "Parts invoice — parts used | piloto | Service date: MM/DD/AAAA".
- **Não é enviada sozinha.** Fica em *Precisa de atenção* e no Balcão.
- **Duas vias para o cliente pagar** (dono, 06/10: *"tenha tanto a opção desse leitor
  quanto de montar invoice para poder enviar"*), lado a lado em "Como o cliente paga?":
  - **"Enviar invoice por e-mail"**: o gerente envia pelo QuickBooks; o cliente paga pelo link;
  - **"Cobrar no cartão"**: o leitor Bluetooth do QuickBooks com o app GoPayment, em
    *Invoice payment* → cliente → esta invoice → *Charge*. Paga a PRÓPRIA invoice (nada em
    dobro); o número do cartão nunca passa pelo Command Center. "Já passei o cartão" confere
    o saldo no QuickBooks e marca **paga**: sai da fila "a enviar" e de *Precisa de atenção*,
    e a próxima peça do dia abre outra invoice.
  - Sem leitor no balcão, `CC_BALCAO_CARTAO=0` esconde o botão do cartão.
- **O mecânico lança** (OPERATOR) e cada leitura já salva. Errou, desfaz, enquanto a
  invoice não foi enviada.
- **Código novo:** o gerente diz o preço e a categoria do QuickBooks, e o Command Center
  **cria o item lá**, dentro da categoria. Se já existe um com o mesmo nome na categoria,
  ele usa esse.
- **COBRAR × GUARDAR** são dois modos com cor diferente (verde × laranja) e aviso fixo no topo.
  - GUARDAR põe a peça no estoque do cliente e não cobra.
  - Cobrar uma peça que o cliente tem guardada pergunta antes: "usar a dele (sem cobrar)"
    ou "cobrar uma nova".
- **QR do cliente:** um código aleatório por card, não o número do card. Ele aparece no
  card (aba Peças, com "Imprimir") e na área do cliente ("Show my URACE QR"), depois que o
  piloto está ligado ao card.
- **Peça sem código na embalagem:** etiqueta URACE (`URC` + número da peça), em Code 128,
  impressa em 62 × 29 mm.

## Por quê
Dono, 05/10: *"o mecânico vai ler o QR Code do cliente e vai ler o código de barras da peça,
e já vai subir para aquele cliente, no card daquele cliente, uma invoice aberta de partes"*.

## Regras que continuam valendo
- A trava do estoque continua: **peça de um cliente nunca sai para outro**, e saldo não fica
  negativo. Cobrar uma peça que a URACE não tem na prateleira é recusado: primeiro conte ou
  dê entrada.
- Peça **sem preço final** não é cobrada; quem define o preço é o gerente.
- O QuickBooks é espelho da invoice do painel. Se ele falhar, a leitura fica salva e a
  tela mostra "Tentar de novo".
- Invoice sem nenhuma linha (tudo desfeito) é **anulada (void)**, nunca apagada.

## Fonte
issue #87 · `command_center/providers/balcao.py`
