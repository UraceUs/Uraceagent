/* Manual dos marcadores do Gmail — pedido do dono em 11/09.

   "Em momento nenhum eu falei que era para criar marcadores… leia marcador por marcador
   que existia antes, entenda o que se coloca em cada um, me dê o manual e eu confirmo —
   só daí ela sabe como agir."

   Esta tela é esse manual: o que a IA entendeu de cada marcador, família por família,
   com o volume real da caixa. Nada é usado na triagem antes de o dono confirmar; o que
   ele marcar como "não usar" fica fora para sempre. */
import { useMemo, useState } from 'react'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, Spinner } from '../components/ui'
import { ago } from '../components/fmt'
import { usePerguntar } from '../components/Perguntar'
import { useToast } from '../components/Toast'

interface Marcador {
  id: number; name: string; family: string | null; what: string | null; threads: number | null
  status: 'pendente' | 'confirmado' | 'fora'; in_gmail: number
  confirmed_by: string | null; confirmed_at: string | null
}
interface Manual {
  labels: Marcador[]; resumo: Record<string, number>; exemplos: { chega: string; vai_para: string }[]
  confirmado: boolean; confirmado_em: string | null
}
const TOM = { confirmado: 'ok', pendente: 'warn', fora: 'neutral' } as const
const ROTULO = { confirmado: 'confirmado', pendente: 'esperando você', fora: 'não usar' } as const

function Linha({ m, reload }: { m: Marcador; reload: () => void }) {
  const { can } = useAuth()
  const toast = useToast()
  const [texto, setTexto] = useState(m.what || '')
  const [busy, setBusy] = useState(false)
  const mudou = texto.trim() !== (m.what || '').trim()
  async function salvar(status?: Marcador['status']) {
    setBusy(true)
    try {
      await api.patch(`/gmail/manual/${m.id}`, { what: mudou ? texto : undefined, status })
      toast(status === 'confirmado' ? `“${m.name}” confirmado.` : status === 'fora' ? `“${m.name}” fica fora da triagem.` : 'Descrição guardada.', 'ok')
      reload()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  return <tr className={m.status === 'fora' ? 'dim' : ''} style={{ opacity: m.status === 'fora' ? 0.6 : 1 }}>
    <td style={{ minWidth: 0 }}>
      <div className="mono small" style={{ wordBreak: 'break-word' }}>{m.name}</div>
      <div className="row wrap small muted" style={{ gap: 6 }}>
        <Chip tone={TOM[m.status]}>{ROTULO[m.status]}</Chip>
        {!!m.threads && <span>{m.threads.toLocaleString('pt-BR')} conversas</span>}
        {!m.in_gmail && <Chip tone="crit">não existe mais na caixa</Chip>}
      </div>
    </td>
    <td style={{ minWidth: 0 }}>
      {can('MANAGER') ? <textarea className="input" rows={2} value={texto} placeholder="o que vai neste marcador…"
        onChange={e => setTexto(e.target.value)} onBlur={() => { if (mudou) salvar() }} />
        : <div className="small">{m.what || <span className="muted">—</span>}</div>}
    </td>
    {can('MANAGER') && <td className="nowrap">
      {busy ? <Spinner /> : <div className="row" style={{ gap: 4 }}>
        {m.status !== 'confirmado' && <button className="btn sm" onClick={() => salvar('confirmado')}>confirmar</button>}
        {m.status !== 'fora' && <button className="btn ghost sm" onClick={() => salvar('fora')}>não usar</button>}
        {m.status === 'fora' && <button className="btn ghost sm" onClick={() => salvar('pendente')}>voltar</button>}
      </div>}
    </td>}
  </tr>
}

export function GmailManual() {
  const { can } = useAuth()
  const toast = useToast()
  const perguntar = usePerguntar()
  const d = useGet<Manual>('/gmail/manual')
  const [filtro, setFiltro] = useState('')
  const [so, setSo] = useState<'todos' | 'pendente' | 'confirmado' | 'fora'>('todos')
  const [busy, setBusy] = useState<string | null>(null)

  const familias = useMemo(() => {
    const fs = new Map<string, Marcador[]>()
    for (const m of d.data?.labels || []) {
      if (so !== 'todos' && m.status !== so) continue
      if (filtro && !`${m.name} ${m.what || ''}`.toLowerCase().includes(filtro.toLowerCase())) continue
      const k = m.family || '—'
      if (!fs.has(k)) fs.set(k, [])
      fs.get(k)!.push(m)
    }
    return [...fs.entries()].sort((a, b) => a[0].localeCompare(b[0]))
  }, [d.data, filtro, so])

  async function confirmar(familia?: string) {
    const quantos = familia ? (d.data?.labels || []).filter(m => m.family === familia && m.status === 'pendente').length
      : (d.data?.resumo?.pendente || 0)
    if (!quantos) return
    if (!await perguntar({
      titulo: familia ? `Confirmar os ${quantos} marcadores de “${familia}”?` : `Confirmar os ${quantos} marcadores que faltam?`,
      texto: 'A partir daí a IA pode classificar e-mail — e só com estes marcadores, do jeito que está escrito aqui. O que estiver errado, corrija antes.',
      ok: 'Confirmar',
    })) return
    setBusy(familia || 'tudo')
    try { const r = await api.post<{ confirmados: number }>('/gmail/manual/confirm', { familia }); toast(`${r.confirmados} marcador(es) confirmado(s).`, 'ok'); d.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  async function reler() {
    setBusy('reler')
    try { const r = await api.post<{ novos: string[]; total_na_caixa: number }>('/gmail/manual/refresh', {}); toast(r.novos.length ? `${r.novos.length} marcador(es) novo(s) na caixa: ${r.novos.slice(0, 3).join(', ')}${r.novos.length > 3 ? '…' : ''}` : `Nenhum marcador novo (${r.total_na_caixa} na caixa).`, 'ok'); d.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }

  if (d.loading && !d.data) return <Loading rows={6} />
  if (d.error) return <ErrorState error={d.error} retry={d.reload} />
  const r = d.data?.resumo || {}
  return <div className="stack">
    <div className="card-h">
      <div><h1 className="h1">Manual dos marcadores · Gmail</h1>
        <div className="small ink2">O que a IA entendeu de cada marcador da sua caixa. Ela só classifica com o que você confirmar.</div></div>
      <div className="grow" />
      <div className="row wrap">
        {can('MANAGER') && <button className="btn" disabled={busy === 'reler'} onClick={reler}>{busy === 'reler' ? <Spinner /> : '⟳ Reler a caixa'}</button>}
        {can('MANAGER') && !!r.pendente && <button className="btn primary" disabled={!!busy} onClick={() => confirmar()}>{busy === 'tudo' ? <Spinner /> : `Confirmar tudo (${r.pendente})`}</button>}
      </div>
    </div>

    {!d.data?.confirmado
      ? <Banner tone="warn"><b>A triagem está parada.</b> Enquanto nenhum marcador estiver confirmado, a IA não classifica nem move e-mail nenhum. Confira família por família abaixo e confirme o que estiver certo.</Banner>
      : <Banner tone="ok"><b>{r.confirmado} marcador(es) confirmado(s)</b>{d.data.confirmado_em && <> · último {ago(d.data.confirmado_em)}</>}. A IA só usa estes; qualquer outro que apareça na caixa é ignorado.</Banner>}

    {/* Só avisa enquanto os marcadores ainda existirem na caixa. Os 11 foram
        apagados em 11/09 a pedido do dono; um "Reler a caixa" zera este aviso.
        As linhas continuam no manual como `fora`: se algo recriá-los, já nascem ignorados. */}
    {!!(d.data?.labels || []).some(m => m.family === 'Email Review' && m.in_gmail) &&
      <Banner tone="crit"><b>“Email Review/…” não é seu.</b> São 11 marcadores aplicados em ~700 conversas entre 9 e 12 de agosto. Não foi o Command Center — o painel não cria marcador, o código recusa. O log de tokens OAuth do domínio mostrou que naquela data o único app com escrita no Gmail era o conector <b>Claude for Gmail</b> do claude.ai (autorizado em 16/07): foram sessões suas no Claude com esse conector ligado. Estão marcados como <b>não usar</b> e a IA os ignora — inclusive na sugestão de destino. Some da caixa apagando os marcadores no Gmail; some daqui com <b>⟳ Reler a caixa</b>.</Banner>}

    <div className="card"><div className="card-b">
      <div className="h2" style={{ marginBottom: 8 }}>O que chega → onde vai</div>
      <div className="tbl-wrap"><table className="tbl"><tbody>
        {(d.data?.exemplos || []).map((e, i) => <tr key={i}><td style={{ width: '45%' }}>{e.chega}</td><td className="mono small">{e.vai_para}</td></tr>)}
      </tbody></table></div>
    </div></div>

    <div className="row wrap">
      <input className="input" style={{ maxWidth: 320 }} placeholder="Buscar marcador…" value={filtro} onChange={e => setFiltro(e.target.value)} />
      <div className="tabs">{(['todos', 'pendente', 'confirmado', 'fora'] as const).map(t =>
        <button key={t} className={so === t ? 'on' : ''} onClick={() => setSo(t)}>{t === 'todos' ? 'Todos' : ROTULO[t]} <span className="count">{t === 'todos' ? (d.data?.labels.length || 0) : (r[t] || 0)}</span></button>)}</div>
    </div>

    {familias.length === 0 ? <Empty title="Nada aqui">Mude o filtro acima.</Empty> : familias.map(([fam, itens]) => {
      const pend = itens.filter(m => m.status === 'pendente').length
      return <section className="card" key={fam}>
        <div className="card-h"><h2 className="h2">{fam}<span className="count">{itens.length}</span></h2><div className="grow" />
          {can('MANAGER') && !!pend && <button className="btn sm" disabled={!!busy} onClick={() => confirmar(fam)}>{busy === fam ? <Spinner /> : `Confirmar os ${pend}`}</button>}</div>
        <div className="card-b tight"><div className="tbl-wrap"><table className="tbl">
          <thead><tr><th style={{ width: '38%' }}>Marcador</th><th>O que vai aqui</th>{can('MANAGER') && <th></th>}</tr></thead>
          <tbody>{itens.map(m => <Linha key={m.id} m={m} reload={d.reload} />)}</tbody>
        </table></div></div>
      </section>
    })}
  </div>
}
