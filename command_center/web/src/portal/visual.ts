/* Visual "3D" da área do cliente (#54). Dono, 01/10: "algo um pouco mais 3D... se não,
 * já deixe pronto para a gente poder reverter".
 *
 * Reverter para todos: troque VISUAL_3D_PADRAO para false (uma linha). O visual está todo
 * em styles/portal-3d.css, só sob `.portal.p3d`: sem a classe, a tela volta ao desenho de
 * antes. Cada pessoa também pode alternar no rodapé ("Classic look"), e o navegador guarda
 * a escolha — é só conveniência de quem olha, não muda nada para os outros. */
export const VISUAL_3D_PADRAO = true
const CHAVE = 'urace.portal.visual'

export function visual3d(): boolean {
  try {
    const v = localStorage.getItem(CHAVE)
    return v === null ? VISUAL_3D_PADRAO : v === '3d'
  } catch { return VISUAL_3D_PADRAO }
}

export function guardarVisual(tresD: boolean) {
  try { localStorage.setItem(CHAVE, tresD ? '3d' : 'classico') } catch { /* navegador sem armazenamento: vale só nesta visita */ }
}
