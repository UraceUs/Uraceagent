---
tipo: decisao
tipo_info: DECISION
status: ativo
owner: Italo Silveira
data: 2026-09-21
fonte: dono, 21/09/2026
---

# D-2026-09-21 — Celular: PWA, sem app nativo

[[URACE]] · [[Command Center - Proximos passos]]

## A pergunta

Dono: *"para o celular o que acha de montar um aplicativo mesmo?"*

## O que decidiu

O pagamento do PDV: *"todos os pagamentos são pela plataforma de pagamento que está no
Command Center, que é o QuickBooks"*.

**Isso resolve a questão do app.** O único gatilho forte para app nativo era a maquininha
de cartão: leitor Bluetooth exige SDK nativo, porque o Safari do iPhone não tem Web
Bluetooth. Com o pagamento indo por **link ou QR do QuickBooks, aberto no celular do
próprio cliente**, não há hardware e não há SDK. O PWA cobre o PDV inteiro.

Então: **PWA** — o painel instalado na tela inicial, com notificação push.

## Por que isso é o certo aqui, e não preguiça

- São ~10 pessoas de dentro. Loja de app não traz descoberta nenhuma; traz fila de revisão.
- **Zero código duplicado**: chat, checklist, estoque e PDV aparecem no celular no mesmo
  dia em que ficam prontos.
- Entre "consertei o bug" e "o mecânico tem o conserto" há 3 minutos de deploy. Com app na
  loja seriam de 1 a 3 dias de revisão da Apple — num sistema que muda todo dia, isso dói.
- O que matava PWA no iPhone — não ter notificação — acabou: push funciona desde o iOS
  16.4, com o site adicionado à tela inicial.

## O que faria mudar de ideia (fica registrado para não rediscutir do zero)

- Maquininha de cartão ou qualquer periférico Bluetooth
- Leitura pesada de código de barras no estoque (bipar dezenas de peças seguidas)
- Box sem sinal por horas, com necessidade real de trabalhar offline
- Notificação que não pode falhar de jeito nenhum (push em PWA no iPhone depende de a
  pessoa ter adicionado à tela inicial)

Se algum aparecer, o caminho **não é recomeçar**: o mesmo código React vira app nativo via
Capacitor — empacotar, não reescrever. Custo de entrada: conta de desenvolvedor Apple
(US$ 99/ano), assinatura e distribuição.

## Consequência para o PDV

Venda do mecânico pelo celular → item sai do estoque → QuickBooks emite a cobrança →
**link/QR de pagamento vai para o cliente**. Sem dinheiro em espécie no fluxo e sem
hardware no box.
