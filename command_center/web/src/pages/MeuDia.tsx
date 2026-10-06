/* Meu dia (#92): a tela inicial do mecânico e do coach — e o calendário deles.
 * Os serviços, as corridas e as sessões do site do dia, cada um com o checklist que é do cargo
 * de quem abriu. Sem valor e sem contato do cliente.
 * Dono, 06/10: no celular, além do dia, a semana e o mês — tocar num dia abre o dia. */
import { useState, type ReactNode } from 'react'
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

interface Resumo { servicos: { id: number; title: string; cliente: string | null }[]; corridas: { id: number; name: string; series: string | null; track: string | null }[]
  sessoes: { id: number; period: string; status: string; piloto: string | null; servico: string | null }[] }
interface Periodo { de: string; ate: string; hoje: string; dias: Record<string, Resumo> }
type Vista = 'dia' | 'semana' | 'mes'

const MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
const DIAS = ['seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom']
const segunda = (iso: string) => somar(iso, -((new Date(iso + 'T12:00:00').getDay() + 6) % 7))
const ultimo = (mes: string) => { const [a, m] = mes.split('-').map(Number); return `${mes}-${String(new Date(a, m, 0).getDate()).padStart(2, '0')}` }
const outroMes = (iso: string, n: number) => { const [a, m] = iso.split('-').map(Number); const d = new Date(a, m - 1 + n, 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01` }
const ddmm = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`
const vazio = (r?: Resumo) => !r || (!r.servicos.length && !r.corridas.length && !r.sessoes.length)

/** O que tem no dia, em linhas curtas: serviço (cliente), corrida e sessão do site. */
function Itens({ r }: { r: Resumo }) {
  return <ul className="md-itens">
    {r.corridas.map(c => <li key={`c${c.id}`} className="corrida">🏁 {c.series || c.name}{c.track && <span className="muted"> · {c.track}</span>}</li>)}
    {r.servicos.map(s => <li key={`s${s.id}`}>{s.cliente || s.title}</li>)}
    {r.sessoes.map(x => <li key={`x${x.id}`} className="sessao">{PERIODO[x.period] || x.period} · {x.piloto || 'site'}{x.status !== 'confirmada' && <span className="muted"> (esperando)</span>}</li>)}
  </ul>
}

function Semana({ data, abrir, nav }: { data: string; abrir: (iso: string) => void; nav: ReactNode }) {
  const de = segunda(data), ate = somar(de, 6)
  const p = useGet<Periodo>(`/meu-dia/periodo${qs({ de, ate })}`, 60000)
  if (p.error && !p.data) return <ErrorState error={p.error} retry={p.reload} />
  if (!p.data) return <Loading />
  const hoje = p.data.hoje
  return <Section title={`Semana de ${ddmm(de)} a ${ddmm(ate)}`} right={nav}>
    <div className="stack" style={{ gap: 8 }}>{Array.from({ length: 7 }, (_, i) => somar(de, i)).map(iso => {
      const r = p.data!.dias[iso]
      return <button key={iso} className={`card card-b md-semana-d${iso === hoje ? ' hoje' : ''}`} onClick={() => abrir(iso)}>
        <h3 className="h3" style={{ margin: 0, textTransform: 'capitalize' }}>{rotuloData(iso)}{iso === hoje && <Chip tone="accent">hoje</Chip>}</h3>
        {vazio(r) ? <span className="small muted">Nada marcado</span> : <Itens r={r} />}
      </button>
    })}</div>
  </Section>
}

function Mes({ data, abrir, nav }: { data: string; abrir: (iso: string) => void; nav: ReactNode }) {
  const mes = data.slice(0, 7), [a, m] = mes.split('-').map(Number)
  const p = useGet<Periodo>(`/meu-dia/periodo${qs({ de: `${mes}-01`, ate: ultimo(mes) })}`, 60000)
  if (p.error && !p.data) return <ErrorState error={p.error} retry={p.reload} />
  if (!p.data) return <Loading />
  const { dias, hoje } = p.data
  const brancos = (new Date(a, m - 1, 1).getDay() + 6) % 7
  const proximos = Object.keys(dias).filter(iso => iso >= hoje && !vazio(dias[iso]))
  return <Section title={`${MESES[m - 1][0].toUpperCase()}${MESES[m - 1].slice(1)} de ${a}`} right={nav}>
    <div className="md-cal" role="grid" aria-label={`Calendário de ${MESES[m - 1]}`}>
      {DIAS.map((d, i) => <div key={d} className={`md-cal-s${i >= 5 ? ' fds' : ''}`} role="columnheader">{d}</div>)}
      {Array.from({ length: brancos }, (_, i) => <div key={`b${i}`} />)}
      {Object.keys(dias).map(iso => {
        const r = dias[iso], n = r.servicos.length + r.sessoes.length
        return <button key={iso} role="gridcell" className={`md-cal-d${iso === hoje ? ' hoje' : ''}${iso < hoje ? ' passou' : ''}`} onClick={() => abrir(iso)}
          aria-label={`${Number(iso.slice(8))} de ${MESES[m - 1]}: ${vazio(r) ? 'nada marcado' : [r.corridas.length && 'corrida', n && `${n} marcado${n > 1 ? 's' : ''}`].filter(Boolean).join(', ')}`}>
          <b>{Number(iso.slice(8))}</b>
          <span className="md-cal-m">{r.corridas.length > 0 && <span aria-hidden="true">🏁</span>}{n > 0 && <span className="md-cal-n">{n}</span>}</span>
        </button>
      })}
    </div>
    <p className="small muted" style={{ margin: '6px 0 0' }}>🏁 corrida · número = serviços e sessões do dia. Toque no dia para abrir.</p>
    <h3 className="h3" style={{ margin: '14px 0 6px' }}>Próximos</h3>
    {!proximos.length ? <span className="small muted">Nada marcado no resto do mês.</span>
      : <div className="stack" style={{ gap: 8 }}>{proximos.map(iso => <button key={iso} className="card card-b md-semana-d" onClick={() => abrir(iso)}>
        <b style={{ textTransform: 'capitalize' }}>{rotuloData(iso)}</b><Itens r={dias[iso]} /></button>)}</div>}
  </Section>
}

export function MeuDia() {
  const [data, setData] = useState(hojeFL)
  const [vista, setVista] = useState<Vista>('dia')
  const d = useGet<Dia>(`/meu-dia${qs({ data })}`, 60000)
  const passo = (n: number) => setData(x => vista === 'mes' ? outroMes(x, n) : somar(x, vista === 'semana' ? 7 * n : n))
  const abrirDia = (iso: string) => { setData(iso); setVista('dia'); window.scrollTo({ top: 0 }) }
  const nome = { dia: 'dia', semana: 'semana', mes: 'mês' }[vista]
  const nav = <div className="row" style={{ gap: 4 }}>
    <button className="btn sm ghost" aria-label={`${nome[0].toUpperCase()}${nome.slice(1)} anterior`} onClick={() => passo(-1)}>‹</button>
    {data.slice(0, vista === 'mes' ? 7 : 10) !== hojeFL().slice(0, vista === 'mes' ? 7 : 10) && <button className="btn sm ghost" onClick={() => setData(hojeFL())}>Hoje</button>}
    <button className="btn sm ghost" aria-label={`Próximo ${nome}`} onClick={() => passo(1)}>›</button>
  </div>
  return <>
    <PageHeader title="Meu dia" help="Os serviços, as corridas e as sessões do dia, com o checklist de cada um. Toque no checklist para preencher; dá para tirar foto em qualquer item.">
      <Link className="btn primary" to="/balcao">Balcão</Link>
    </PageHeader>
    <div className="md-vistas" role="group" aria-label="Ver por">
      {(['dia', 'semana', 'mes'] as Vista[]).map(v => <button key={v} className={`btn sm${vista === v ? ' primary' : ' ghost'}`} aria-pressed={vista === v}
        onClick={() => setVista(v)}>{{ dia: 'Dia', semana: 'Semana', mes: 'Mês' }[v]}</button>)}
    </div>
    {vista !== 'dia' && (vista === 'semana' ? <Semana data={data} abrir={abrirDia} nav={nav} /> : <Mes data={data} abrir={abrirDia} nav={nav} />)}
    {vista === 'dia' && <><div className="row wrap" style={{ gap: 8 }}>
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
    </>}
  </>
}
