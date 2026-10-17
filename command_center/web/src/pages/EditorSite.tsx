/* Editor visual do site (#300): a lista das páginas do editor, criar uma nova e abrir uma do site. Dono, 16/10: "como
 * alterar o design, layout, puxando e arrastando e soltando de uma forma bem simples". A página em si abre no editor
 * como o Canva (#315, `editor/Editor.tsx`, em arquivo próprio): a prévia é a área de trabalho. */
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { Empty, ErrorState, Loading, Section } from '../components/ui'
import { InserirNoTopo } from '../components/Inserir'
import { Cartao } from '../components/Cartao'
import { useToast } from '../components/Toast'
import { fmtDateTime } from '../components/fmt'
import { tr } from '../i18n'
import type { Pagina, Saida } from './editor/tipos'

const ESTADO: Record<string, [string, 'neutral' | 'ok' | 'warn']> = {
  rascunho: [tr("rascunho, fora do ar"), 'neutral'], publicada: [tr("no ar"), 'ok'], mudou: [tr("no ar, com mudanças não publicadas"), 'warn'] }

// ------------------------------------------------------------------ a lista de páginas
export function PaginasDoEditor() {
  const { can } = useAuth()
  const nav = useNavigate()
  const toast = useToast()
  const l = useGet<{ paginas: Pick<Pagina, 'id' | 'path' | 'base' | 'title' | 'estado' | 'published_at' | 'updated_at'>[]; existentes: { caminho: string; titulo: string }[] }>('/site/editor/paginas')
  const [nova, setNova] = useState({ title: '', path: '' })
  async function criar(corpo: Record<string, string>) {
    try { const r = await api.post<Saida>('/site/editor/paginas', corpo); toast(tr("Página aberta no editor: nada muda no site até publicar."), 'ok'); nav(`/site/editor/${r.pagina.id}`) }
    catch (er) { toast((er as ApiError).message, 'crit') }
  }
  if (l.error && !l.data) return <ErrorState error={l.error} retry={l.reload} />
  if (!l.data) return <Loading />
  return <div className="stack" style={{ gap: 14 }}>
    {/* #312: criar uma página (nova ou a partir de uma do site) fica no topo, antes da lista das páginas no editor */}
    {can('MANAGER') && <InserirNoTopo rotulo={tr("Adicionar página")} titulo={tr("Nova página no editor")} primario>
      <div className="stack" style={{ gap: 16 }}>
        <div className="stack" style={{ gap: 8 }}>
          <h3 className="h3" style={{ margin: 0 }}>{tr("Nova página")}</h3>
          <div className="loja-grade">
            <label className="fld"><span>{tr("Título da aba")} <i>{tr("o cliente lê, em inglês")}</i></span><input value={nova.title} onChange={e => setNova({ ...nova, title: e.target.value })} /></label>
            <label className="fld"><span>{tr("Endereço")} <i>{tr("ex.: /summer-camp/ (vazio: sai do título)")}</i></span><input value={nova.path} onChange={e => setNova({ ...nova, path: e.target.value })} /></label>
            <div><button className="btn primary" disabled={nova.title.trim().length < 3} onClick={() => criar(nova)}>{tr("Criar e abrir")}</button></div>
          </div>
        </div>
        <div className="stack" style={{ gap: 8 }}>
          <h3 className="h3" style={{ margin: 0 }}>{tr("Abrir uma página do site")} <span className="count">{l.data.existentes.length}</span></h3>
          <ul className="ed-lista-paginas">{l.data.existentes.map(x => <li key={x.caminho} className="card card-b">
            <div className="grow" style={{ minWidth: 0 }}><b style={{ overflowWrap: 'anywhere' }}>{x.titulo}</b><div className="small muted">{x.caminho}</div></div>
            <button className="btn sm ghost" onClick={() => criar({ base: x.caminho })}>{tr("Abrir no editor")}</button></li>)}</ul>
        </div>
      </div>
    </InserirNoTopo>}
    <p className="small muted" style={{ margin: 0 }}>{tr("Abra uma página e mexa nela como no Canva: clique no que quer mudar, escreva no lugar, arraste e solte. Numa página que já existe, as faixas dela se movem e se escondem. Nada muda no site até você publicar; cada publicação guarda uma versão para voltar.")}</p>
    <Section title={tr("Páginas no editor")} count={l.data.paginas.length}>
      {!l.data.paginas.length ? <Empty title={tr("Nenhuma página ainda")}>{tr("Use \"Adicionar página\", em cima: abra uma página do site ou crie uma nova.")}</Empty>
        : <div className="cd-grade">{l.data.paginas.map(p => <Cartao key={p.id} id={`pagina-${p.id}`} estado={ESTADO[p.estado][0]} tom={ESTADO[p.estado][1]}
          avatar={p.title} avatarTom="azul" nome={<Link to={`/site/editor/${p.id}`}>{p.title}</Link>}
          sub={[p.base ? tr("página do site") : tr("página nova")]} detalhe={`${p.path}${p.updated_at ? ` · ${fmtDateTime(p.updated_at)}` : ''}`}
          acoes={<Link className="btn" to={`/site/editor/${p.id}`}>{tr("Editar")}</Link>} />)}</div>}
    </Section>
  </div>
}
