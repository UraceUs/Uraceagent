import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { qs } from '../api/client'
import { useGet } from '../api/hooks'
import type { Client } from '../api/types'
import { Chip, Empty, ErrorState, Loading, Section, WAIVER_LABEL, statusTone } from '../components/ui'
import { daysUntil, fmtDate } from '../components/fmt'

export function Clients() {
  const nav = useNavigate()
  const [sp, setSp] = useSearchParams()
  const [q, setQ] = useState(sp.get('q') || '')
  const status = sp.get('status') || ''
  const vip = sp.get('vip') || ''
  useEffect(() => {
    const t = setTimeout(() => { const n = new URLSearchParams(sp); if (q) n.set('q', q); else n.delete('q'); setSp(n, { replace: true }) }, 250)
    return () => clearTimeout(t)
  }, [q]) // eslint-disable-line react-hooks/exhaustive-deps
  const { data, error, loading, reload } = useGet<Client[]>('/clients' + qs({ q: sp.get('q'), status, vip: vip === '' ? undefined : vip === '1' }))
  const set = (k: string, v: string) => { const n = new URLSearchParams(sp); if (v) n.set(k, v); else n.delete(k); setSp(n) }
  return <>
    <div className="page-h"><div><h1 className="h1">Clientes</h1><div className="sub small">Responsável, piloto, próximo serviço e situação da waiver. Fonte: Asana + DocuSign + cérebro.</div></div></div>
    <div className="row wrap">
      <input className="input" style={{ maxWidth: 320 }} placeholder="Nome, piloto ou e-mail" value={q} onChange={e => setQ(e.target.value)} aria-label="Filtrar" />
      <select className="input" style={{ width: 170 }} value={status} onChange={e => set('status', e.target.value)} aria-label="Status">
        <option value="">Todos os status</option>{['ACTIVE', 'NEW', 'PENDING', 'AT_RISK', 'COMPLETED', 'INACTIVE'].map(s => <option key={s}>{s}</option>)}
      </select>
      <select className="input" style={{ width: 130 }} value={vip} onChange={e => set('vip', e.target.value)} aria-label="VIP">
        <option value="">VIP e não</option><option value="1">Só VIP</option><option value="0">Sem VIP</option>
      </select>
      <div className="grow" /><button className="btn" onClick={reload}>↻</button>
    </div>
    <Section title="Clientes" count={data?.length} tight>
      {error && !data ? <ErrorState error={error} retry={reload} /> : loading && !data ? <Loading rows={8} /> :
        (data || []).length === 0 ? <Empty title="Nenhum cliente">Sem registros com esse filtro. Se o quadro está vazio, rode a sincronia no Dashboard.</Empty> :
        <div className="tbl-wrap"><table className="tbl">
          <thead><tr><th>Cliente</th><th>Piloto</th><th>Status</th><th>Próximo serviço</th><th>Waiver</th><th>Abertos</th><th>E-mails</th></tr></thead>
          <tbody>{data!.map(c => {
            const dias = daysUntil(c.next_service)
            const w = (c.waiver_status || '').toLowerCase()
            const semWaiver = dias !== null && dias <= 2 && w !== 'completed' && !c.vip
            return <tr key={c.id} className="click" onClick={() => nav(`/clients/${c.id}`)}>
              <td><div className="row"><b>{c.name}</b>{!!c.vip && <Chip tone="warn">VIP</Chip>}</div><div className="small muted">{c.email || c.company || ''}</div></td>
              <td>{c.pilot_name || <span className="muted">—</span>}</td>
              <td><Chip tone={statusTone(c.status)}>{c.stage || c.status}</Chip></td>
              <td className="mono">{c.next_service ? <>{fmtDate(c.next_service)} <span className="muted small">{dias === 0 ? 'hoje' : dias === 1 ? 'amanhã' : `${dias} d`}</span></> : <span className="muted">—</span>}</td>
              <td>{c.vip ? <Chip tone="neutral">dispensada (VIP)</Chip> : w ? <Chip tone={semWaiver ? 'crit' : statusTone(w)}>{WAIVER_LABEL[w] || w}</Chip> : <Chip tone={semWaiver ? 'crit' : 'neutral'}>nenhuma</Chip>}</td>
              <td className="mono">{c.open_tasks ?? 0}</td>
              <td className="mono">{c.emails_open ? <span style={{ color: 'var(--warn)' }}>{c.emails_open}</span> : 0}</td>
            </tr>
          })}</tbody>
        </table></div>}
    </Section>
  </>
}
