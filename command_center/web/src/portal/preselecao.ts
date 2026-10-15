/* #253/#263: qual serviço do painel já vem escolhido quando a pessoa chega do site com um kart.
 *
 * Dono, 15/10 (print da tela "Book your session" com "teste · teste de produto $500.00" escolhido):
 * "remova esse produto d teste quando for para essa pagina ja vai com o produto pré selecionado".
 * O serviço de teste apareceu escolhido porque, com um serviço só no painel, a tela escolhia esse
 * serviço mesmo sem relação com o kart clicado no site.
 *
 * #263 (dono, 15/10): o casamento é pela **chave** do kart — `site_kart`, a coluna que o painel
 * guarda para dizer "este serviço é deste kart" — igual e exata. Era "o nome do serviço contém o
 * nome do kart", e foi esse contém que deixou o "teste" passar por produto. A regra mora num lugar
 * só e vale na reserva do site (#164) e na agenda da área do cliente:
 *
 * - veio kart do site → só o serviço cuja chave é a desse kart, e só quando é um (duas linhas com a
 *   mesma chave: a pessoa escolhe);
 * - veio kart e nenhum serviço do painel é desse kart → nada escolhido, e a tela avisa que esse kart
 *   não está aberto para reserva online agora (nunca escolher um serviço que não é do kart);
 * - sem kart → um serviço só já vem escolhido; vários, a pessoa escolhe.
 *
 * O nome e o preço continuam vindo do serviço do painel (#50): aqui só se decide qual.
 */
export interface OpcaoDeServico {
  id: number
  name: string
  /** A chave do kart do site que este serviço vende (`booking_services.site_kart`). */
  site_kart?: string | null
}

/** A chave do kart do jeito que ela é comparada: sem maiúscula e sem espaço à toa. */
function chave(v: string | null | undefined): string {
  return (v || '').trim().replace(/\s+/g, ' ').toLowerCase()
}

/** Os serviços do painel que são deste kart: a chave do serviço é igual à chave do kart. */
export function servicosDoKart<T extends OpcaoDeServico>(servicos: T[], kart: string | null | undefined): T[] {
  const k = chave(kart)
  if (!k) return []
  return servicos.filter(x => chave(x.site_kart) === k)
}

/** O kart que veio do site não tem serviço no painel: a tela avisa, em vez de escolher outro. */
export function kartSemServico(servicos: OpcaoDeServico[] | null, kart: string | null | undefined): boolean {
  return !!servicos && !!chave(kart) && servicosDoKart(servicos, kart).length === 0
}

/** O serviço que já vem escolhido, ou null quando a pessoa tem de escolher.
 *  `atual` é a escolha que já existe (o `?service=`, o que ficou guardado, ou o que ela marcou);
 *  ela só é mantida quando ainda está na lista e combina com o kart que veio do site. */
export function servicoPreSelecionado<T extends OpcaoDeServico>(
  servicos: T[], kart: string | null | undefined, atual: number | null,
): number | null {
  if (chave(kart)) {
    const doKart = servicosDoKart(servicos, kart)
    if (atual && doKart.some(x => x.id === atual)) return atual
    return doKart.length === 1 ? doKart[0].id : null
  }
  if (atual && servicos.some(x => x.id === atual)) return atual
  return servicos.length === 1 ? servicos[0].id : null
}
