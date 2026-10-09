/* Idioma do Command Center (#177). Dono, 09/10: "o command center inteiro com versão português e
 * inglês, com um switch com a bandeira americana e a bandeira brasileira no topo de cada página".
 *
 * - O texto do código é o português. `tr('Clientes')` devolve o próprio texto em português, ou o
 *   inglês do dicionário (`en.json`) quando o inglês está escolhido. Sem tradução, sai o português.
 * - Texto com valor no meio: `tr('Salvo em {0}', data)`.
 * - O dicionário só é baixado quando o inglês é escolhido (o pacote inicial não cresce) e é
 *   carregado antes de o app montar (main.tsx): as constantes das telas já nascem no idioma certo.
 * - Trocar de idioma guarda a escolha no navegador e recarrega a página.
 * - Datas e números seguem o idioma (pt-BR / en-US); o fuso continua o da Flórida.
 */
export type Idioma = 'pt' | 'en'
const CHAVE = 'cc.lang'

function lerEscolha(): Idioma {
  try { return localStorage.getItem(CHAVE) === 'en' ? 'en' : 'pt' } catch { return 'pt' }
}

let atual: Idioma = lerEscolha()
let dicionario: Record<string, string> | null = null

export const idioma = (): Idioma => atual
/** Locale das datas e números: pt-BR ou en-US. */
export const LOCALE = (): string => (atual === 'en' ? 'en-US' : 'pt-BR')

/** Chamado uma vez em main.tsx, antes de o app montar. */
export async function carregarIdioma() {
  document.documentElement.lang = atual === 'en' ? 'en' : 'pt-BR'
  if (atual !== 'en' || dicionario) return
  try {
    dicionario = (await import('./en.json')).default as Record<string, string>
  } catch {
    atual = 'pt'                                           // sem o dicionário (rede caiu): fica em português
    document.documentElement.lang = 'pt-BR'
  }
}

const espacos = (s: string) => s.replace(/\s+/g, ' ').trim()

/** O texto no idioma escolhido. `{0}`, `{1}`… recebem os valores. */
export function tr(pt: string, ...valores: unknown[]): string {
  let s = pt
  if (atual === 'en' && dicionario && pt) s = dicionario[pt] ?? dicionario[espacos(pt)] ?? pt
  if (valores.length) s = s.replace(/\{(\d+)\}/g, (m, i) => (Number(i) < valores.length ? String(valores[Number(i)] ?? '') : m))
  return s
}

export function mudarIdioma(novo: Idioma) {
  if (novo === atual) return
  try { localStorage.setItem(CHAVE, novo) } catch { /* sem armazenamento: vale só até recarregar */ }
  window.location.reload()
}
