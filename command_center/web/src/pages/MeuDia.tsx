/* Meu dia (#92): a tela inicial do mecânico e do coach — e o calendário deles.
 * Os serviços, as corridas e as sessões do site do dia, cada um com o checklist que é do cargo
 * de quem abriu. Sem valor e sem contato do cliente. */
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiError, qs } from '../api/client'
import { useGet } from '../api/hooks'
import { Chip, Empty, ErrorState, Loading, PageHeader, Section } from '../components/ui'
import { useToast } from '../components/Toast'

interface Ck { template_id: number; nome: string; cargo: string; ctx: Record<string, unknown>; run_id: number | null; status: string; feitos: number; total: number | null }
interface Servico { id: number; title: string; status: string; client_id: number | null; cliente: string | null; checklists: Ck[] }
interface Corrida { id: number; name: string; track: string | null; city: string | null; date_start: string; date_end: string | null
  checklists: Ck[]; pilotos: { client_id: number; piloto: string; checklists: Ck[] }[] }
interface Dia { data: string; servicos: Servico[]; corridas: Corrida[]; sessoes: { id: number; period: string; status: string; piloto: string | null; servico: string | null }[]
  do_dia: Ck[]; avulsos: { template_id: number; nome: string; quando: string }[]; cargo: string | null }

const PERIODO: Record<string, string> = { manha: 'Manhã', tarde: 'Tarde', dia: 'Dia todo' }
const hojeFL = () => new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' })
const somar = (iso: string, n: number) => { const d = new Date(iso + 'T12:00:00'); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10) }
const rotuloData = (iso: string) => new Date(iso + 'T12:00:00').toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: '2-digit' })

function BotaoCk({ c, data }: { c: Ck; data: string }) {
  const nav = useNavigate()
  const toast = useToast()
  const [indo, setIndo] = useState(false)
  async function abrir() {
    if (c.run_id) { nav(`/checklists/${c.run_id}`); return }
    setIndo(true)
    try { const r = await api.post<{ id: number }>('/checklists/runs', { template_id: c.template_id, ctx: { ...c.ctx, data } }); nav(`/checklists/${r.id}`) }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  const estado = c.status === 'completo' ? <Chip tone="ok">completo</Chip> : c.run_id ? <Chip tone="warn">{c.feitos}/{c.total}</Chip> : <Chip tone="neutral">a fazer</Chip>
  return <button className="btn sm meudia-ck" disabled={indo} onClick={abrir}><span className="grow">{c.nome}</span>{indo ? <span className="spin" /> : estado}</button>
}

export function MeuDia() {
  const [data, setData] = useState(hojeFL)
  const d = useGet<Dia>(`/meu-dia${qs({ data })}`, 60000)
  return <>
    <PageHeader title="Meu dia" help="Os serviços, as corridas e as sessões do dia, com o checklist de cada um. Toque no checklist para preencher; dá para tirar foto em qualquer item.">
      <Link className="btn primary" to="/balcao">Balcão</Link>
    </PageHeader>
    <div className="row wrap" style={{ gap: 8 }}>
      <button className="btn sm ghost" aria-label="Dia anterior" onClick={() => setData(x => somar(x, -1))}>‹</button>
      <b className="grow" style={{ textTransform: 'capitalize', textAlign: 'center' }}>{rotuloData(data)}</b>
      {data !== hojeFL() && <button className="btn sm ghost" onClick={() => setData(hojeFL())}>Hoje</button>}
      <button className="btn sm ghost" aria-label="Próximo dia" onClick={() => setData(x => somar(x, 1))}>›</button>
    </div>
    {d.error && !d.data ? <ErrorState error={d.error} retry={d.reload} /> : !d.data ? <Loading /> : <>
      {d.data.do_dia.length > 0 && <Section title="Checklists do dia">
        <div className="stack" style={{ gap: 8 }}>{d.data.do_dia.map(c => <BotaoCk key={c.template_id} c={c} data={data} />)}</div>
      </Section>}
      <Section title="Serviços" count={d.data.servicos.length}>
        {!d.data.servicos.length ? <Empty title="Nenhum serviço neste dia" /> : <div className="stack" style={{ gap: 10 }}>{d.data.servicos.map(s => <div key={s.id} className="card card-b stack" style={{ gap: 8 }}>
          <div className="row wrap" style={{ gap: 8 }}><h3 className="h3 grow" style={{ margin: 0 }}>{s.cliente || s.title}</h3>
            {s.client_id && <Link className="btn sm ghost" to={`/clients/${s.client_id}`}>Card</Link>}
            {s.client_id && <Link className="btn sm ghost" to={`/balcao/${s.client_id}`}>Peças</Link>}</div>
          <div className="small muted">{s.title}</div>
          {s.checklists.map(c => <BotaoCk key={c.template_id} c={c} data={data} />)}
        </div>)}</div>}
      </Section>
      {d.data.corridas.length > 0 && <Section title="Corridas" count={d.data.corridas.length}>
        <div className="stack" style={{ gap: 10 }}>{d.data.corridas.map(r => <div key={r.id} className="card card-b stack" style={{ gap: 8 }}>
          <h3 className="h3" style={{ margin: 0 }}>{r.name}</h3>
          <div className="small muted">{[r.track, r.city].filter(Boolean).join(' · ')}</div>
          {r.checklists.map(c => <BotaoCk key={c.template_id} c={c} data={data} />)}
          {r.pilotos.map(p => <div key={p.client_id} className="stack" style={{ gap: 6 }}><b className="small">{p.piloto}</b>
            {p.checklists.map(c => <BotaoCk key={c.template_id} c={c} data={data} />)}</div>)}
        </div>)}</div>
      </Section>}
      {d.data.sessoes.length > 0 && <Section title="Sessões marcadas pelo site" count={d.data.sessoes.length}>
        <div className="card"><div className="tbl">{d.data.sessoes.map(x => <div className="tr" key={x.id}>
          <span style={{ width: 80 }} className="small">{PERIODO[x.period] || x.period}</span>
          <span className="grow">{x.piloto || '—'}{x.servico && <span className="small muted"> · {x.servico}</span>}</span>
          <Chip tone={x.status === 'confirmada' ? 'ok' : 'warn'}>{x.status === 'confirmada' ? 'confirmada' : 'esperando'}</Chip></div>)}</div></div>
      </Section>}
    </>}
  </>
}
