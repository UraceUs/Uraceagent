/** Telas que o mecânico e o coach abrem (#92). O servidor tem a mesma lista para a API. */
const TELAS_DO_BOX = [/^\/$/, /^\/meu-dia$/, /^\/checklists(\/\d+)?$/, /^\/balcao(\/\d+)?$/, /^\/c\/[A-Za-z0-9]+$/, /^\/estoque$/,
  /^\/pedidos$/, /^\/compras(\/\d+)?$/, /^\/clients(\/\d+)?$/, /^\/equipe(\/[^/]+)?$/, /^\/account$/]
export const telaDoBox = (caminho: string) => TELAS_DO_BOX.some(rx => rx.test(caminho))
