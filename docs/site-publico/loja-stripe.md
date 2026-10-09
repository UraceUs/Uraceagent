# Loja paga no ato com Stripe Checkout (#174)

Dono, 08/10: *"Stripe Checkout"* para a loja própria; 09/10: *"tbm tenho a conta da stripe"*.

## Como funciona

| Passo | Onde |
|---|---|
| Produto com preço e em estoque mostra **Buy now** (opção, quantidade, retirada na pista ou envio) | `/store/p/<slug>/` |
| O servidor confere produto, variação e preço **no catálogo** (nunca no formulário), grava o pedido `aberto` e abre a sessão do Checkout | `POST /ops/api/vitrine/checkout` → 303 para `checkout.stripe.com` |
| A pessoa paga (cartão, Apple Pay, Google Pay — os meios ligados na conta do Stripe) | Stripe |
| Volta para o obrigado, que também confere a sessão no Stripe (se o webhook atrasar, nada se perde) | `/store/thanks/?session_id=…` (noindex, fora do sitemap) |
| Desistiu: nada cobrado, botão de volta ao produto e "Ask a question" | `/store/cancelled/?p=<slug>` |
| O Stripe avisa, com assinatura conferida; cada evento entra uma vez só | `POST /ops/api/stripe/webhook` |

Pago → **oportunidade em Vendas** (origem Site) com produto, valor pago, entrega e endereço:
- **GANHO** e ligada ao card quando o e-mail **e** o nome do pagamento batem com um card;
  sem card com esse e-mail, nasce um card novo;
- **FECHAMENTO**, sem card, quando o e-mail é de um card com outro nome (pai comprando no e-mail do
  filho, e-mail da empresa): a equipe vincula à mão. Nunca no card de outra pessoa.

Depois, em segundo plano: e-mail de confirmação para quem comprou, aviso em `support@urace.us`
para separar e entregar, e o **Sales Receipt** no QuickBooks (número `WEB-<pedido>`, cliente pelo
e-mail ou criado, item com o nome do produto — achado pelo nome ou criado). Se o QuickBooks ou o
e-mail falharem, a rotina de 15 min tenta de novo; o erro aparece na ficha da venda.

O dinheiro entra em *Undeposited Funds* no QuickBooks. Quando o financeiro quiser uma conta própria
para os repasses do Stripe, é só pôr o id dela em `QBO_CONTA_STRIPE` no `adminai.env`.

Continua como **pedido para a equipe** (#164): produto "Ask for price", fora de estoque, e qualquer
dúvida ("Questions, sizes or a custom order? Send an order request", na própria página).
Frete: o envio pede o endereço no Checkout e a equipe confirma e cobra o frete à parte.

## Chaves (só no VPS, em `~/.urace/adminai.env`)

- `STRIPE_SECRET_KEY` (sk_live_… ou rk_live_… restrita: Checkout Sessions *Write*, Products e
  Prices *Read*), `STRIPE_PUBLISHABLE_KEY` — gravadas pelo dono em 09/10 e testadas.
- `STRIPE_WEBHOOK_SECRET` (whsec_…) — criada pelo bloco abaixo, direto no servidor.
- Sem `STRIPE_SECRET_KEY`, a loja volta sozinha ao pedido para a equipe.

## Ligar o webhook (uma vez)

Endereço: `https://ops.urace.us/ops/api/stripe/webhook`, eventos
`checkout.session.completed`, `checkout.session.async_payment_succeeded`,
`checkout.session.async_payment_failed`, `checkout.session.expired`.

O bloco de deploy do PR cria o endpoint pela API do Stripe com a chave que já está no servidor e
grava o `whsec_…` no `adminai.env` sem mostrar na tela. Se a chave restrita não tiver permissão de
*Webhook Endpoints*, o bloco pede para criar no painel do Stripe (Developers › Webhooks) e colar o
segredo com a digitação escondida.
