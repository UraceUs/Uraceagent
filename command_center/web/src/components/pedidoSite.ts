/* #245: o estado do pedido do site (carrinho e loja) como a equipe lê, e o tom do chip. Cada estado
 * é um resultado do Stripe; o cliente vê o mesmo na página do pedido (/order/<token>/). */
import type { Tone } from './ui'
import { tr } from '../i18n'

export const ESTADO_PEDIDO: Record<string, string> = {
  pago: tr("pago"),
  aguardando: tr("processando o pagamento"),
  falhou: tr("pagamento não passou"),
  expirado: tr("checkout expirou"),
  aberto: tr("no checkout"),
}

export const tomDoPedido = (status: string): Tone =>
  status === 'pago' ? 'ok' : status === 'falhou' || status === 'expirado' ? 'crit' : 'warn'
