/* #236: a sessão vai para o carrinho do site (Stripe), no mesmo formato de `vitrine/static/carrinho.js`: só as
 * escolhas — o preço, o depósito e a vaga são do servidor. #314: a Reserva e o Book a session usam este mesmo
 * caminho para o cliente que não é aluno recorrente quando o Stripe está ligado. */
const CARRINHO = 'urace.carrinho'
export type ItemCarrinho = { tipo: 'sessao'; servico: number; data: string; turno: 'manha' | 'tarde' | 'dia'; piloto: number | null }

export function porNoCarrinhoDoSite(item: ItemCarrinho) {
  try {
    const d = JSON.parse(localStorage.getItem(CARRINHO) || '{}')
    const itens: ItemCarrinho[] = Array.isArray(d.itens) ? d.itens : []
    if (!itens.some(x => x.tipo === 'sessao' && x.servico === item.servico && x.data === item.data && x.turno === item.turno && x.piloto === item.piloto))
      itens.push(item)
    localStorage.setItem(CARRINHO, JSON.stringify({ v: 1, itens: itens.slice(0, 20) }))
  } catch { /* navegador sem armazenamento: o carrinho abre vazio e a reserva continua aqui */ }
}
