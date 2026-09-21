/* Rolagem lateral no celular: só acusa quem realmente empurra a página
   (ignora o que está dentro de um contêiner que recorta/rola). */
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs'
const EXEC = process.env.PW_CHROME || undefined
const B = 'http://127.0.0.1:8800/ops'
const br = await chromium.launch({ executablePath: EXEC }); const pg = await br.newPage({ viewport: { width: 390, height: 844 } })
await pg.goto(B + '/login'); await pg.fill('#email', 'italo@urace.us'); await pg.fill('#pw', 'senha-de-teste-123'); await pg.click('button.primary'); await pg.waitForSelector('.kpi')
let ruins = 0
const ROTAS = ['/', '/attention', '/clients', '/clients/1', '/races', '/gmail', '/gmail/manual', '/asana',
  '/docusign', '/quickbooks', '/crm/chat', '/crm/funil', '/sales', '/sales/agenda', '/sales/1',
  '/ai', '/ai/capabilities', '/approvals', '/integrations', '/automation', '/activity', '/users', '/audit',
  '/policies', '/account']
for (const rota of ROTAS) {
  await pg.goto(B + rota); await pg.waitForTimeout(1100)
  const r = await pg.evaluate(() => {
    const W = document.documentElement.clientWidth
    const recortado = el => { for (let p = el.parentElement; p && p !== document.documentElement; p = p.parentElement) { const o = getComputedStyle(p).overflowX; if (o === 'auto' || o === 'scroll' || o === 'hidden') return true } return false }
    const culpados = []
    document.querySelectorAll('body *').forEach(el => {
      const b = el.getBoundingClientRect()
      if (b.width < 8 || b.height < 4) return
      if (b.right > W + 1 && !recortado(el)) culpados.push(`${el.tagName}.${(el.className || '').toString().split(' ').slice(0, 2).join('.')} right=${Math.round(b.right)}`)
    })
    const pequenos = []
    document.querySelectorAll('button,a[href],input,select,summary,[role="button"]').forEach(el => {
      const b = el.getBoundingClientRect()
      if (b.width < 2 || b.height < 2) return
      if (getComputedStyle(el).display === 'none') return
      if (b.height < 34 && !el.closest('.tbl,.rc,.pal,.menu,.tabbar')) pequenos.push(`${el.tagName}.${(el.className || '').toString().split(' ')[0]}=${Math.round(b.height)}`)
    })
    return { scroll: document.documentElement.scrollWidth, janela: W, culpados: [...new Set(culpados)].slice(0, 5),
             pequenos: [...new Set(pequenos)].slice(0, 6) }
  })
  const mau = r.scroll > r.janela + 1
  if (mau) ruins++
  console.log(`${mau ? 'ESTOURA' : 'ok     '} ${rota.padEnd(18)} scroll=${r.scroll}${mau ? ' — ' + (r.culpados.join(' ; ') || '(nada visível fora; ver conteúdo recortado)') : ''}${r.pequenos.length ? '  · toque<34px: ' + r.pequenos.join(', ') : ''}`)
}
console.log(ruins === 0 ? '\nNenhuma tela com rolagem lateral no celular.' : `\n${ruins} tela(s) ainda estouram.`)
await br.close()
