/* #311 (dono, 16/10): o botão vermelho do balcão abre o parts.urace.us já logado, com o mesmo login.
 *
 * O painel dá um passe de uso único (30 s) e ele vai ao parts num POST de formulário: nunca na URL,
 * no histórico ou numa prévia de link. O parts só aceita o passe vindo do painel que o deu, pelo
 * cabeçalho `Origin`. O painel responde com `Referrer-Policy: no-referrer`, e com ela o navegador
 * mandaria `Origin: null` neste POST; por isso, só nesta saída, a página passa a dizer a origem (o
 * endereço do site, nunca o caminho). */
import { api } from '../api/client'

export type Passe = { acao: string | null; passe?: string; vence_em?: string }

export async function pedirPasse() {
  return api.post<Passe>('/auth/passe')
}

export function irComPasse(acao: string, passe: string) {
  const m = document.createElement('meta')
  m.name = 'referrer'
  m.content = 'strict-origin'
  document.head.appendChild(m)
  const f = document.createElement('form')
  f.method = 'POST'
  f.action = acao
  f.style.display = 'none'
  const i = document.createElement('input')
  i.type = 'hidden'
  i.name = 'passe'
  i.value = passe
  f.appendChild(i)
  document.body.appendChild(f)
  f.submit()
  f.remove()
}

/** Voltando pelo "voltar" do navegador (página guardada): a página volta a não dizer de onde vem. */
export function restaurarReferrer() {
  const m = document.createElement('meta')
  m.name = 'referrer'
  m.content = 'no-referrer'
  document.head.appendChild(m)
}
