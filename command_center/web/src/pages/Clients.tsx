import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, ApiError, qs } from '../api/client'
import { useGet } from '../api/hooks'
import type { Client } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, Section, Spinner, WAIVER_LABEL, statusTone } from '../components/ui'
import { daysUntil, fmtDate, fmtDateTime } from '../components/fmt'
import { useToast } from '../components/Toast'
import { ClientCard } from './Client360'

type Par = { a: Client; b: Client; why: string }
type Parecer = { mesma_pessoa: boolean | null; confianca: string; motivo: string }

function Duplicados({ onChanged }: { onChanged: () => void }) {
  const { can } = useAuth()
  const toast = useToast()
  const { data, loading, reload } = useGet<{ pairs: Par[]; merged: { id: number; keep_id: number; drop_name: string; reason: string; merged_by: string; merged_at: string }[] }>('/client-duplicates')
  const [ia, setIa] = useState<Record<string, Parecer> | null>(null)
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState(false)
  async function unir(keep: Client, drop: Client) {
    if (!window.confirm(`Unir "${drop.pilot_name || drop.name}" em "${keep.pilot_name || keep.name}"?\n\nServiços, waivers e e-mails do segundo passam para o primeiro. O registro unido fica guardado e auditado.`)) return
    try { await api.post('/client-merge', { keep_id: keep.id, drop_id: drop.id, reason: 'mesma pessoa (revisão humana)' }); toast('Unidos.', 'ok'); reload(); onChanged() } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function perguntar() {
    setBusy(true)
    try {
      await api.post('/client-duplicates/ai')
      for (let i = 0; i < 90; i++) {
        await new Promise(r => setTimeout(r, 4000))
        const st = await api.get<{ running: boolean; result: { pareceres?: Record<string, Parecer>; erro?: string } | null }>('/client-duplicates/ai')
        if (!st.running) { if (st.result?.erro) toast(`IA falhou: ${st.result.erro}`, 'crit'); else { setIa(st.result?.pareceres || {}); toast('A IA deu o parecer de cada par.', 'ok') } break }
      }
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  const n = data?.pairs.length ?? 0
  if (!loading && n === 0 && !(data?.merged.length)) return null
  return <Section title="Possíveis duplicados" count={n} right={<div className="row">{n > 0 && can('OPERATOR') && <button className="btn sm" disabled={busy} onClick={perguntar}>{busy ? <Spinner /> : '✦'} Pedir parecer da IA</button>}<button className="btn ghost sm" onClick={() => setOpen(o => !o)}>{open ? 'esconder' : 'ver'}</button></div>}>
    {!open ? <div className="small muted">{n} par(es) com nomes quase iguais esperando decisão{data?.merged.length ? ` · ${data.merged.length} união(ões) feitas` : ''}.</div> : <>
      {n === 0 && <div className="small muted">Nenhum par pendente.</div>}
      {(data?.pairs || []).map(p => { const par = ia?.[`${p.a.id}-${p.b.id}`]; return <div className="act" key={`${p.a.id}-${p.b.id}`}>
        <div className="grow"><b>{p.a.pilot_name || p.a.name}</b> <span className="muted small">{p.a.email || 'sem e-mail'} · {p.a.phone || 'sem tel'}</span> <span className="muted">×</span> <b>{p.b.pilot_name || p.b.name}</b> <span className="muted small">{p.b.email || 'sem e-mail'} · {p.b.phone || 'sem tel'}</span>
          <div className="small muted">{p.why}</div>
          {par && <div className="small" style={{ marginTop: 4 }}><Chip tone={par.mesma_pessoa === true ? 'ok' : par.mesma_pessoa === false ? 'crit' : 'neutral'}>✦ {par.mesma_pessoa === true ? 'mesma pessoa' : par.mesma_pessoa === false ? 'pessoas diferentes' : 'não deu para saber'} · {par.confianca}</Chip> {par.motivo}</div>}</div>
        {can('OPERATOR') && <div className="row"><button className="btn sm primary" onClick={() => unir(p.a, p.b)}>Unir → {p.a.pilot_name || p.a.name}</button><button className="btn sm" onClick={() => unir(p.b, p.a)}>Unir → {p.b.pilot_name || p.b.name}</button></div>}
      </div> })}
      {!!data?.merged.length && <div className="small muted" style={{ marginTop: 10 }}>Uniões: {data.merged.slice(0, 8).map(m => `${m.drop_name} (${m.reason}, ${m.merged_by === 'sync' ? 'automático' : 'à mão'})`).join(' · ')}</div>}
    </>}
  </Section>
}

export function Clients() {
  const { can } = useAuth()
  const toast = useToast()
  const [sp, setSp] = useSearchParams()
  const [q, setQ] = useState(sp.get('q') || '')
  const status = sp.get('status') || ''
  const vip = sp.get('vip') || ''
  const openId = sp.get('open') ? Number(sp.get('open')) : null
  const [scanning, setScanning] = useState(false)
  useEffect(() => {
    if ((sp.get('q') || '') === q) return
    const t = setTimeout(() => { const n = new URLSearchParams(window.location.search); if (q) n.set('q', q); else n.delete('q'); setSp(n, { replace: true }) }, 250)
    return () => clearTimeout(t)
  }, [q]) // eslint-disable-line react-hooks/exhaustive-deps
  const { data, error, loading, reload } = useGet<Client[]>('/clients' + qs({ q: sp.get('q'), status, vip: vip === '' ? undefined : vip === '1' }))
  const set = (k: string, v: string) => { const n = new URLSearchParams(sp); if (v) n.set(k, v); else n.delete(k); setSp(n) }
  const open = (id: number | null) => { const n = new URLSearchParams(sp); if (id) n.set('open', String(id)); else n.delete('open'); setSp(n) }
  const rows = data || []                                       // ordem do servidor: serviço mais recente primeiro
  const ativos = rows.filter(c => c.status === 'ACTIVE').length
  async function scanAll() {
    setScanning(true)
    try {
      const r = await api.post<{ started: boolean; total: number }>('/client-scan-all')
      toast(r.started ? 'Varrendo Gmail e DocuSign de todos os clientes ativos. Pode levar vários minutos.' : 'Já há uma varredura rodando.')
      for (let i = 0; i < 300; i++) {
        await new Promise(res => setTimeout(res, 5000))
        const st = await api.get<{ running: boolean; done: number; total: number; result: { gmail?: number; docusign?: number; erro?: string } | null }>('/client-scan-all')
        if (!st.running) { toast(st.result?.erro ? `Varredura falhou: ${st.result.erro}` : `Varredura: ${st.result?.gmail ?? 0} threads de e-mail e ${st.result?.docusign ?? 0} waivers ligadas.`, st.result?.erro ? 'crit' : 'ok'); break }
      }
      reload()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setScanning(false) }
  }
  return <>
    <div className="page-h"><div><h1 className="h1">Clientes</h1><div className="sub small">Uma pessoa, um card. Corrida não é cliente. Ativo = serviço nos últimos 6 meses. Ordem: serviço mais recente primeiro. Clique para abrir o card completo.</div></div>
      <div className="row wrap">{can('OPERATOR') && <button className="btn" disabled={scanning} onClick={scanAll} title="Gmail (as duas caixas) e DocuSign de cada cliente ativo">{scanning ? <Spinner /> : '⌕'} Varrer plataformas ({ativos} ativos)</button>}</div></div>
    <div className="row wrap">
      <input className="input" style={{ maxWidth: 320 }} placeholder="Piloto, responsável ou e-mail" value={q} onChange={e => setQ(e.target.value)} aria-label="Filtrar" />
      <select className="input" style={{ width: 190 }} value={status} onChange={e => set('status', e.target.value)} aria-label="Status">
        <option value="">Ativos e inativos</option><option value="ACTIVE">Ativos (6 meses)</option><option value="INACTIVE">Inativos</option>{['NEW', 'PENDING', 'AT_RISK', 'COMPLETED'].map(s => <option key={s}>{s}</option>)}
      </select>
      <select className="input" style={{ width: 130 }} value={vip} onChange={e => set('vip', e.target.value)} aria-label="VIP">
        <option value="">VIP e não</option><option value="1">Só VIP</option><option value="0">Sem VIP</option>
      </select>
      <div className="grow" /><button className="btn" onClick={reload}>↻</button>
    </div>
    <Duplicados onChanged={reload} />
    <Section title="Clientes" count={rows.length} tight>
      {error && !data ? <ErrorState error={error} retry={reload} /> : loading && !data ? <Loading rows={8} /> :
        rows.length === 0 ? <Empty title="Nenhum cliente">Sem registros com esse filtro. Se a lista está vazia, rode “Sincronizar agora” no Dashboard.</Empty> :
        <div className="tbl-wrap"><table className="tbl">
          <thead><tr><th>Piloto</th><th>Responsável</th><th>Status</th><th>Último serviço</th><th>Próximo</th><th>Waiver</th><th>Serviços</th><th>E-mails</th><th>Varrido</th></tr></thead>
          <tbody>{rows.map(c => {
            const dias = daysUntil(c.next_service)
            const w = (c.waiver_status || '').toLowerCase()
            const semWaiver = dias !== null && dias <= 2 && w !== 'completed' && !c.vip
            return <tr key={c.id} className="click" onClick={() => open(c.id)}>
              <td><div className="row"><b>{c.pilot_name || c.name}</b>{!!c.vip && <Chip tone="warn">VIP</Chip>}</div>{!c.pilot_name && <div className="small muted">piloto é o próprio</div>}</td>
              <td>{c.pilot_name ? c.name : <span className="muted">—</span>}<div className="small muted">{c.email || ''}{c.phone ? ` · ${c.phone}` : ''}</div></td>
              <td><Chip tone={statusTone(c.status)}>{c.status === 'ACTIVE' ? 'ativo' : c.status === 'INACTIVE' ? 'inativo' : c.status}</Chip>{!!c.status_locked && <span className="small muted" title="mudado à mão"> 🔒</span>}</td>
              <td className="mono">{c.last_service ? fmtDate(c.last_service) : <span className="muted">—</span>}</td>
              <td className="mono">{c.next_service ? <>{fmtDate(c.next_service)} <span className="muted small">{dias === 0 ? 'hoje' : dias === 1 ? 'amanhã' : `${dias} d`}</span></> : <span className="muted">—</span>}</td>
              <td>{c.vip ? <Chip tone="neutral">dispensada (VIP)</Chip> : w ? <Chip tone={semWaiver ? 'crit' : statusTone(w)}>{WAIVER_LABEL[w] || w}</Chip> : <Chip tone={semWaiver ? 'crit' : 'neutral'}>nenhuma</Chip>}</td>
              <td className="mono">{c.open_tasks ?? 0} abertos · {c.done_tasks ?? 0} feitos</td>
              <td className="mono">{c.emails_open ? <span style={{ color: 'var(--warn)' }}>{c.emails_open}</span> : 0}</td>
              <td className="mono small muted">{c.scanned_at ? fmtDateTime(c.scanned_at) : '—'}</td>
            </tr>
          })}</tbody>
        </table></div>}
    </Section>
    {openId && <div className="modal-scrim" onMouseDown={() => open(null)}>
      <div className="modal" onMouseDown={e => e.stopPropagation()} role="dialog" aria-label="Card do cliente">
        <button className="btn ghost sm close" onClick={() => open(null)} aria-label="Fechar">✕ fechar</button>
        <ClientCard id={openId} onClose={() => open(null)} />
      </div>
    </div>}
    {false && <Banner tone="info">.</Banner>}
  </>
}
