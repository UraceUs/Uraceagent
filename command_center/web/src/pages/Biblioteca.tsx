/* Biblioteca (#88): contratos, waivers, invoices, recibos e histórico de serviço de cada
 * cliente, com o PDF de cada um. Gerente para cima. A rodada é do timer do VPS, toda
 * madrugada, sem IA; o mesmo conteúdo vai para o Drive (urace@), por cliente. */
import { useState } from 'react'
import { Link, NavLink, useParams } from 'react-router-dom'
import { api, ApiError, qs } from '../api/client'
import { useGet } from '../api/hooks'
import { Banner, Chip, Empty, ErrorState, Loading, PageHeader } from '../components/ui'
import { fmtDate, fmtDateTime } from '../components/fmt'
import { useToast } from '../components/Toast'
import { tr } from '../i18n'

type Kind = 'invoice' | 'recibo' | 'contrato' | 'waiver' | 'historico'
interface Doc { id: number; kind: Kind; client_id: number | null; cliente: string | null; title: string; number: string | null
  doc_date: string | null; amount: number | null; status: string | null; error: string | null; no_drive: number; drive_error: string | null
  tem_pdf: number; updated_at: string }
interface Resumo { contagem: Record<Kind, number>; sem_cliente: number; com_erro: number; a_subir: number; rodando: boolean
  drive: string | null; compartilhado_com: string[]; ultima_rodada: { inicio: string; fim: string } | null }

const ABAS: [string, Kind, string][] = [['invoices', 'invoice', tr("Invoices")], ['recibos', 'recibo', tr("Recibos")], ['contratos', 'contrato', tr("Contratos")],
  ['waivers', 'waiver', tr("Waivers")], ['historicos', 'historico', tr("Histórico de serviço")]]
const POR_PAGINA = 50
const usd = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })

export function Biblioteca() {
  const { aba } = useParams()
  const toast = useToast()
  const [, kind, rotulo] = ABAS.find(a => a[0] === aba) || ABAS[0]
  const [q, setQ] = useState('')
  const [busca, setBusca] = useState('')
  // a página volta para o começo quando muda a aba ou a busca (sem efeito: derivado da chave)
  const chave = `${kind}|${busca}`
  const [pag, setPag] = useState({ chave, offset: 0 })
  const offset = pag.chave === chave ? pag.offset : 0
  const setOffset = (n: number) => setPag({ chave, offset: n })
  const res = useGet<Resumo>('/biblioteca/resumo', 15000)
  const l = useGet<{ itens: Doc[]; total: number }>(`/biblioteca${qs({ tipo: kind, q: busca, limit: POR_PAGINA, offset })}`)
  async function atualizar() {
    try { await api.post('/biblioteca/atualizar'); toast(tr("Atualizando a Biblioteca. Pode levar alguns minutos."), 'ok'); res.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }
  const r = res.data
  return <>
    <PageHeader title={tr("Biblioteca")} help={tr("Todos os documentos de cada cliente, com o PDF. Atualiza sozinha toda madrugada (sem IA) e manda a mesma coisa para o Drive, na pasta Command Center, por cliente.")}>
      {r?.drive && <a className="btn ghost" href={r.drive} target="_blank" rel="noreferrer">{tr("Abrir no Drive ↗")}</a>}
      <button className="btn" disabled={r?.rodando} onClick={atualizar}>{r?.rodando ? <><span className="spin" /> {tr("Atualizando")}</> : tr("Atualizar agora")}</button>
    </PageHeader>
    {r && <div className="small muted">
      {r.ultima_rodada ? <>{tr("Última atualização")} {fmtDateTime(r.ultima_rodada.fim)}</> : tr("Ainda não rodou.")}
      {r.a_subir > 0 && <> · {r.a_subir} {tr("para subir ao Drive")}</>}
      {r.compartilhado_com.length > 0 && <> {tr("· pasta compartilhada com")} {r.compartilhado_com.join(', ')}</>}
    </div>}
    {r && r.sem_cliente > 0 && <Banner tone="warn">{r.sem_cliente} {tr("documento(s) sem cliente certo: estão em \"Sem cliente\" (por exemplo, família com dois pilotos no mesmo cliente do QuickBooks). Ligue a invoice ao card no QuickBooks para ela ir para o lugar certo.")}</Banner>}
    <div className="tabs">{ABAS.map(([path, kk, rot]) => <NavLink key={path} to={`/biblioteca/${path}`} className={() => kk === kind ? 'on' : ''}>
      {rot}{r ? ` (${r.contagem[kk]})` : ''}</NavLink>)}</div>
    <form className="row wrap" style={{ gap: 8 }} onSubmit={e => { e.preventDefault(); setBusca(q.trim()) }}>
      <input className="input grow" aria-label={tr("Buscar em {0}", rotulo)} placeholder={tr("Cliente, número ou título")} value={q} onChange={e => setQ(e.target.value)} />
      <button className="btn">{tr("Buscar")}</button>
    </form>
    {l.error && !l.data ? <ErrorState error={l.error} retry={l.reload} /> : !l.data ? <Loading />
      : !l.data.itens.length ? <div className="card"><Empty title={tr("Nenhum documento em {0}", rotulo)}>{busca ? tr("Nada com esta busca.") : tr("Aparece aqui depois da próxima atualização.")}</Empty></div>
      : <div className="card"><div className="tbl">{l.data.itens.map(d => <div className="tr" key={d.id}>
        <span className="mono small" style={{ width: 92 }}>{fmtDate(d.doc_date)}</span>
        <span className="grow" style={{ minWidth: 0 }}><b>{d.title}</b>
          <div className="small muted">{d.client_id ? <Link to={`/clients/${d.client_id}`}>{d.cliente}</Link> : tr("Sem cliente")}
            {d.status && <> · {d.status}</>}</div>
          {d.error && <div className="small" style={{ color: 'var(--crit)' }}>{tr("Não baixou:")} {d.error}</div>}</span>
        {d.amount != null && <span className="mono">{usd(d.amount)}</span>}
        {d.drive_error ? <Chip tone="crit" title={d.drive_error}>{tr("Drive: erro")}</Chip> : d.no_drive ? <Chip tone="ok">{tr("no Drive")}</Chip> : <Chip tone="neutral">{tr("a subir")}</Chip>}
        {d.tem_pdf ? <a className="btn sm" href={`/ops/api/biblioteca/${d.id}/pdf`} target="_blank" rel="noreferrer">{tr("PDF")}</a> : <span className="small muted">{tr("sem PDF")}</span>}
      </div>)}</div></div>}
    {l.data && l.data.total > POR_PAGINA && <div className="row" style={{ gap: 8 }}>
      <button className="btn sm ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - POR_PAGINA))}>{tr("Anteriores")}</button>
      <span className="small muted grow" style={{ textAlign: 'center' }}>{offset + 1}–{Math.min(offset + POR_PAGINA, l.data.total)} {tr("de")} {l.data.total}</span>
      <button className="btn sm ghost" disabled={offset + POR_PAGINA >= l.data.total} onClick={() => setOffset(offset + POR_PAGINA)}>{tr("Próximas")}</button></div>}
  </>
}
