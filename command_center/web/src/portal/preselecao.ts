/* #253: qual serviço do painel já vem escolhido quando a pessoa chega do site com um kart.
 *
 * Dono, 15/10 (print da tela "Book your session" com "teste · teste de produto $500.00" escolhido):
 * "remova esse produto d teste quando for para essa pagina ja vai com o produto pré selecionado".
 * O serviço de teste apareceu escolhido porque, com um serviço só no painel, a tela escolhia esse
 * serviço mesmo sem relação com o kart clicado no site. A regra agora é uma só, e vale na reserva
 * do site (#164) e na agenda da área do cliente:
 *
 * - veio kart do site → só o serviço do painel cujo nome contém o nome do kart, e só quando é um
 *   (dois serviços com o nome do kart: a pessoa escolhe);
 * - veio kart e nenhum serviço do painel casa → nada escolhido, e a tela avisa que esse kart não
 *   está aberto para reserva online agora (nunca escolher um serviço que não é do kart);
 * - sem kart → um serviço só já vem escolhido; vários, a pessoa escolhe.
 *
 * O nome e o preço continuam vindo do serviço do painel (#50): aqui só se decide qual.
 */
export interface OpcaoDeServico {
  id: number
  name: string
}

/** Os serviços do painel que são deste kart: o nome do kart dentro do nome do serviço. */
export function servicosDoKart<T extends OpcaoDeServico>(servicos: T[], kart: string | null | undefined): T[] {
  const k = (kart || '').trim().toLowerCase()
  if (!k) return []
  return servicos.filter(x => (x.name || '').toLowerCase().includes(k))
}

/** O kart que veio do site não tem serviço no painel: a tela avisa, em vez de escolher outro. */
export function kartSemServico(servicos: OpcaoDeServico[] | null, kart: string | null | undefined): boolean {
  return !!servicos && !!(kart || '').trim() && servicosDoKart(servicos, kart).length === 0
}

/** O serviço que já vem escolhido, ou null quando a pessoa tem de escolher.
 *  `atual` é a escolha que já existe (o `?service=`, o que ficou guardado, ou o que ela marcou);
 *  ela só é mantida quando ainda está na lista e combina com o kart que veio do site. */
export function servicoPreSelecionado<T extends OpcaoDeServico>(
  servicos: T[], kart: string | null | undefined, atual: number | null,
): number | null {
  if ((kart || '').trim()) {
    const doKart = servicosDoKart(servicos, kart)
    if (atual && doKart.some(x => x.id === atual)) return atual
    return doKart.length === 1 ? doKart[0].id : null
  }
  if (atual && servicos.some(x => x.id === atual)) return atual
  return servicos.length === 1 ? servicos[0].id : null
}
