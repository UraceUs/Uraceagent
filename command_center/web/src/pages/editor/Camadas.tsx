/* Editor do site como o Canva (#315): as camadas, a página em lista. É a outra forma de fazer tudo o que o arrastar
 * faz (quem usa teclado ou leitor de tela, ou prefere botões): escolher, subir, descer, mudar de coluna, esconder e
 * apagar. A escolha aqui é a mesma da prévia; escolher de novo o que já está escolhido escreve nele (como o segundo
 * clique na prévia). */
import { tr } from '../../i18n'
import { NOMES, NOMES_FUNDO, nomeDe, resumo } from './modelo'
import type { Conteudo, Sel } from './tipos'

interface Props {
  c: Conteudo
  originais: string[]
  sel: Sel
  erros: Record<string, string>
  gerente: boolean
  selecionar(s: NonNullable<Sel>): void
  passo(s: NonNullable<Sel>, p: number): void
  coluna(s: NonNullable<Sel>, p: number): void
  apagar(s: NonNullable<Sel>): void
  oculto(id: string): void
}

export function Camadas({ c, originais, sel, erros, gerente, selecionar, passo, coluna, apagar, oculto }: Props) {
  const ehSel = (tipo: 'w' | 's', id: string) => sel?.tipo === tipo && sel.id === id
  return <ol className="ed-camadas" aria-label={tr("Camadas da página")}>
    {c.itens.map((it, s) => {
      const si: NonNullable<Sel> = { tipo: 's', id: it.id }
      const nome = nomeDe(c, si, originais)
      return <li key={it.id}>
        <div className={`ed-camada${ehSel('s', it.id) ? ' on' : ''}${it.tipo === 'original' && it.oculto ? ' apagada' : ''}`}>
          <button type="button" className="ed-camada-nome" data-camada={it.id} aria-current={ehSel('s', it.id) || undefined} onClick={() => selecionar(si)}>
            <b>{nome}</b> <span className="small muted">{it.tipo === 'secao' ? `${NOMES_FUNDO[it.fundo] || ''} · ${tr("{0} col.", it.colunas)}`
              : it.oculto ? tr("escondida") : ''}</span></button>
          {gerente && <>
            <button type="button" className="btn sm ghost" aria-label={tr("Subir {0}", nome)} disabled={s === 0} onClick={() => passo(si, -1)}>↑</button>
            <button type="button" className="btn sm ghost" aria-label={tr("Descer {0}", nome)} disabled={s === c.itens.length - 1} onClick={() => passo(si, 1)}>↓</button>
            {it.tipo === 'original'
              ? <button type="button" className="btn sm ghost" onClick={() => oculto(it.id)}>{it.oculto ? tr("Mostrar") : tr("Esconder")}</button>
              : <button type="button" className="btn sm ghost" aria-label={tr("Apagar {0}", nome)} onClick={() => apagar(si)}>✕</button>}
          </>}
        </div>
        {it.tipo === 'secao' && it.itens.some(col => col.length > 0) && <ol>
          {it.itens.map((col, ci) => col.map((w, wi) => {
            const wsel: NonNullable<Sel> = { tipo: 'w', id: w.id }
            const n = NOMES[w.tipo]
            return <li key={w.id} className={`ed-camada${ehSel('w', w.id) ? ' on' : ''}${erros[w.id] ? ' erro' : ''}`}>
              <button type="button" className="ed-camada-nome" data-camada={w.id} aria-current={ehSel('w', w.id) || undefined} onClick={() => selecionar(wsel)}>
                {it.colunas > 1 && <span className="small muted">{ci + 1} · </span>}<b>{n}</b> <span className="small muted">{resumo(w)}</span></button>
              {gerente && <>
                <button type="button" className="btn sm ghost" aria-label={tr("Subir {0}", n)} disabled={s === 0 && ci === 0 && wi === 0 && !c.itens.slice(0, s).some(x => x.tipo === 'secao')} onClick={() => passo(wsel, -1)}>↑</button>
                <button type="button" className="btn sm ghost" aria-label={tr("Descer {0}", n)} onClick={() => passo(wsel, 1)}>↓</button>
                {it.colunas > 1 && ci > 0 && <button type="button" className="btn sm ghost" aria-label={tr("{0} para a coluna da esquerda", n)} onClick={() => coluna(wsel, -1)}>←</button>}
                {it.colunas > 1 && ci < it.colunas - 1 && <button type="button" className="btn sm ghost" aria-label={tr("{0} para a coluna da direita", n)} onClick={() => coluna(wsel, 1)}>→</button>}
                <button type="button" className="btn sm ghost" aria-label={tr("Apagar {0}", n)} onClick={() => apagar(wsel)}>✕</button>
              </>}
            </li>
          }))}
        </ol>}
      </li>
    })}
  </ol>
}
