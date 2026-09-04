import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useGet } from '../api/hooks'
import type { Attention as A, Level } from '../api/types'
import { Chip, Empty, ErrorState, Ext, Loading, Section, levelTone } from '../components/ui'

const LEVELS: Level[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
const LABEL: Record<Level, string> = { CRITICAL: 'Crítico', HIGH: 'Alto', MEDIUM: 'Médio', LOW: 'Baixo' }

export function AttentionList({ items }: { items: A[] }) {
  if (items.length === 0) return <Empty title="Tudo em ordem">Nenhum item precisa de humano agora.</Empty>
  return <div>{items.map((a, i) => <div className="att" key={i}>
    <div className={`lv ${a.level}`} />
    <div className="grow">
      <div className="row wrap"><span className="ti">{a.title}</span><Chip tone={levelTone(a.level)}>{LABEL[a.level]}</Chip></div>
      <div className="why">{a.why}</div>
      <div className="row wrap small" style={{ marginTop: 6 }}>
        <span className="chip outline">{a.action}</span>
        {a.client_id && <Link to={`/clients/${a.client_id}`}>Abrir cliente</Link>}
        {a.link && <Ext href={a.link}>Abrir na fonte</Ext>}
        {a.entity.type === 'approvals' && <Link to="/approvals">Ir para aprovações</Link>}
        {a.entity.type === 'ai' && <Link to="/ai">Ver comandos</Link>}
        {a.entity.type === 'integration' && <Link to="/integrations">Integrações</Link>}
      </div>
    </div>
  </div>)}</div>
}

export function AttentionPage() {
  const { data, error, loading, reload } = useGet<A[]>('/needs-attention', 60000)
  const [f, setF] = useState<Level | 'ALL'>('ALL')
  if (error && !data) return <ErrorState error={error} retry={reload} />
  const items = (data || []).filter(a => f === 'ALL' || a.level === f)
  const count = (l: Level) => (data || []).filter(a => a.level === l).length
  return <>
    <div className="page-h"><div><h1 className="h1">Precisa de atenção</h1>
      <div className="sub small">Ordenado por impacto, não por idade: dinheiro, prazo do serviço, waiver que bloqueia a pista, VIP, e-mail devolvido.</div></div>
      <button className="btn" onClick={reload}>↻ Atualizar</button></div>
    <div className="tabs">
      <button className={f === 'ALL' ? 'on' : ''} onClick={() => setF('ALL')}>Todos ({data?.length ?? 0})</button>
      {LEVELS.map(l => <button key={l} className={f === l ? 'on' : ''} onClick={() => setF(l)}>{LABEL[l]} ({count(l)})</button>)}
    </div>
    <Section title="Itens" count={items.length} tight>{loading && !data ? <Loading /> : <AttentionList items={items} />}</Section>
  </>
}
