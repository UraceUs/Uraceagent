/** Volta do login para a autorização do conector (OAuth).
 *
 * O claude.ai abre `/ops/oauth/authorize` vindo de OUTRO site, e o cookie de sessão é
 * `SameSite=Strict`: nessa chegada ele não vai junto, então o servidor manda para
 * `/ops/login?next=…`. Esta página precisa devolver a pessoa para lá — antes, ela caía no
 * painel e a tela de "Autorizar" nunca aparecia (25/09).
 *
 * Só esse destino é aceito. Qualquer outro `next` seria redirecionamento aberto: um link
 * de login que manda a pessoa, já autenticada, para onde o autor do link quiser. */
export function destinoOAuth(search: string): string | null {
  const n = new URLSearchParams(search).get('next')
  if (!n || !n.startsWith('/ops/oauth/authorize?')) return null
  if (n.includes('\\') || n.startsWith('//')) return null
  return n
}
