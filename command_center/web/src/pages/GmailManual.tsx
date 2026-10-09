/* Manual dos marcadores do Gmail — pedido do dono em 11/09.

   "Em momento nenhum eu falei que era para criar marcadores… leia marcador por marcador
   que existia antes, entenda o que se coloca em cada um, me dê o manual e eu confirmo —
   só daí ela sabe como agir."

   Esta tela é esse manual: o que a IA entendeu de cada marcador, família por família,
   com o volume real da caixa. Nada é usado na triagem antes de o dono confirmar; o que
   ele marcar como "não usar" fica fora para sempre. */
import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, Spinner } from '../components/ui'
import { ago } from '../components/fmt'
import { usePerguntar } from '../components/Perguntar'
import { useToast } from '../components/Toast'
import { Mic } from '../components/Voz'
import { tr, LOCALE } from '../i18n'

interface Marcador {
  id: number; name: string; family: string | null; what: string | null; threads: number | null
  status: 'pendente' | 'confirmado' | 'fora'; in_gmail: number
  confirmed_by: string | null; confirmed_at: string | null
  origin: string | null; proposed_reason: string | null
}
interface Manual {
  labels: Marcador[]; resumo: Record<string, number>; exemplos: { chega: string; vai_para: string }[]
  confirmado: boolean; confirmado_em: string | null
}
const TOM = { confirmado: 'ok', pendente: 'warn', fora: 'neutral' } as const
const ROTULO = { confirmado: tr("confirmado"), pendente: tr("esperando você"), fora: tr("não usar") } as const

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
      toast(status === 'confirmado' ? tr("“{0}” confirmado.", m.name) : status === 'fora' ? tr("“{0}” fica fora da triagem.", m.name) : tr("Descrição guardada."), 'ok')
      reload()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  return <tr className={m.status === 'fora' ? 'dim' : ''} style={{ opacity: m.status === 'fora' ? 0.6 : 1 }}>
    <td style={{ minWidth: 0 }}>
      <div className="mono small" style={{ wordBreak: 'break-word' }}>{m.name}</div>
      <div className="row wrap small muted" style={{ gap: 6 }}>
        <Chip tone={TOM[m.status]}>{ROTULO[m.status]}</Chip>
        {!!m.threads && <span>{m.threads.toLocaleString(LOCALE())} {tr("conversas")}</span>}
        {m.origin === 'ia'
          ? <Chip tone="warn">{tr("sugestão da IA · ainda não existe no Gmail")}</Chip>
          : !m.in_gmail && <Chip tone="crit">{tr("não existe mais na caixa")}</Chip>}
      </div>
      {m.origin === 'ia' && !!m.proposed_reason &&
        <div className="small muted" style={{ marginTop: 4 }}>{tr("Por quê:")} {m.proposed_reason}</div>}
    </td>
    <td style={{ minWidth: 0 }}>
      {can('MANAGER') ? <div className="row" style={{ gap: 6, alignItems: 'flex-start' }}>
        <textarea className="input" rows={2} value={texto} placeholder={tr("o que vai neste marcador…")}
          onChange={e => setTexto(e.target.value)} onBlur={() => { if (mudou) salvar() }} />
        <Mic valor={texto} onTexto={setTexto} /></div>
        : <div className="small">{m.what || <span className="muted">—</span>}</div>}
    </td>
    {can('MANAGER') && <td className="nowrap">
      {busy ? <Spinner /> : <div className="row" style={{ gap: 4 }}>
        {m.status !== 'confirmado' && <button className="btn sm" onClick={() => salvar('confirmado')}>{tr("confirmar")}</button>}
        {m.status !== 'fora' && <button className="btn ghost sm" onClick={() => salvar('fora')}>{tr("não usar")}</button>}
        {m.status === 'fora' && <button className="btn ghost sm" onClick={() => salvar('pendente')}>{tr("voltar")}</button>}
      </div>}
    </td>}
  </tr>
}

type Caixa = 'urace' | 'support'
interface Filtros { caixa: string; rodando: boolean; existe: boolean; gerado_em: string | null; filtros: number; relatorio: string | null; log: string | null }

/* Filtros nativos do Gmail: gerados no servidor a partir dos remetentes reais, revisados
   aqui e importados no Gmail pelo dono. Antes o arquivo só saía do VPS por scp — e o scp
   falhou. Agora ele baixa daqui. */
function FiltrosNativos({ caixa }: { caixa: Caixa }) {
  const { can } = useAuth()
  const toast = useToast()
  const perguntar = usePerguntar()
  const f = useGet<Filtros>(`/gmail/filtros/${caixa}`, 15000)
  const [ver, setVer] = useState(false)
  const [busy, setBusy] = useState(false)
  const [aplicando, setAplicando] = useState(false)
  async function gerar() {
    setBusy(true)
    try { const r = await api.post<{ started: boolean; motivo?: string }>(`/gmail/filtros/${caixa}/gerar`, {}); toast(r.started ? tr("Gerando: leva alguns minutos, a tela atualiza sozinha.") : tr("Não iniciou: {0}", r.motivo), r.started ? 'ok' : 'crit'); f.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  async function aplicar() {
    if (!await perguntar({
      titulo: tr("Criar os {0} filtros na caixa {1}@?", f.data?.filtros, caixa),
      texto: tr("Vai direto pela API do Gmail, sem importar arquivo. Filtro que já existe igual é pulado, e nenhum filtro seu é apagado ou alterado. Vale só para e-mail novo."),
      ok: tr("Criar filtros"),
    })) return
    setAplicando(true)
    try {
      const r = await api.post<{ criados: number; pulados: number; erros: { marcador: string; erro: string }[] }>(`/gmail/filtros/${caixa}/aplicar`, {})
      toast(tr("{0} criado(s), {1} já existiam{2}.", r.criados, r.pulados, r.erros.length ? `, ${r.erros.length} com erro` : ''), r.erros.length ? 'crit' : 'ok')
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setAplicando(false) }
  }
  const d = f.data
  return <div className="card"><div className="card-h">
    <h2 className="h2">{tr("Filtros nativos do Gmail ·")} {caixa}@</h2><div className="grow" />
    <div className="row wrap">
      {can('MANAGER') && <button className="btn" disabled={busy || !!d?.rodando} onClick={gerar}>{d?.rodando ? <><Spinner /> {tr("gerando…")}</> : d?.existe ? tr("⟳ Gerar de novo") : tr("✦ Gerar filtros")}</button>}
      {can('MANAGER') && d?.existe && <button className="btn primary" disabled={aplicando || !!d.rodando} onClick={aplicar}>{aplicando ? <><Spinner /> {tr("criando…")}</> : tr("✦ Criar no Gmail ({0})", d.filtros)}</button>}
      {can('MANAGER') && d?.existe && <a className="btn" href={`/ops/api/gmail/filtros/${caixa}/download`}>{tr("⬇ Baixar XML")}</a>}
      {d?.relatorio && <button className="btn ghost" onClick={() => setVer(v => !v)}>{ver ? tr("esconder relatório") : tr("ver relatório")}</button>}
    </div></div>
    <div className="card-b">
      {!d?.existe && !d?.rodando && <div className="small muted">{tr("Nenhum filtro gerado ainda para esta caixa. O gerador lê os remetentes reais de cada marcador confirmado e monta um arquivo que o Gmail importa.")}</div>}
      {d?.existe && <div className="small">{d.filtros} {tr("filtro(s) · gerado")} {d.gerado_em ? ago(d.gerado_em) : ''}{tr(". Revise o relatório e clique em")} <b>{tr("Criar no Gmail")}</b>{tr(": vai pela API, pula o que já existe e não toca nos seus filtros. Vale só para e-mail novo. (O XML continua aí para importar à mão, se preferir.)")}</div>}
      {d?.rodando && d.log && <pre className="small mono" style={{ maxHeight: 120, overflow: 'auto', marginTop: 8 }}>{d.log.split('\n').slice(-6).join('\n')}</pre>}
      {ver && d?.relatorio && <pre className="small" style={{ whiteSpace: 'pre-wrap', maxHeight: 480, overflow: 'auto', marginTop: 8 }}>{d.relatorio}</pre>}
    </div></div>
}

export function GmailManual() {
  const { can } = useAuth()
  const toast = useToast()
  const perguntar = usePerguntar()
  const [sp, setSp] = useSearchParams()
  const caixa = ((sp.get('c') as Caixa) || 'urace')
  const trocarCaixa = (c: Caixa) => { const n = new URLSearchParams(window.location.search); n.set('c', c); setSp(n, { replace: true }) }
  const d = useGet<Manual>(`/gmail/manual?mailbox=${caixa}`)
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
      titulo: familia ? tr("Confirmar os {0} marcadores de “{1}”?", quantos, familia) : tr("Confirmar os {0} marcadores que faltam?", quantos),
      texto: tr("A partir daí a IA pode classificar e-mail — e só com estes marcadores, do jeito que está escrito aqui. O que estiver errado, corrija antes."),
      ok: tr("Confirmar"),
    })) return
    setBusy(familia || 'tudo')
    try { const r = await api.post<{ confirmados: number }>('/gmail/manual/confirm', { familia, mailbox: caixa }); toast(tr("{0} marcador(es) confirmado(s).", r.confirmados), 'ok'); d.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  async function reler() {
    setBusy('reler')
    try { const r = await api.post<{ novos: string[]; total_na_caixa: number }>(`/gmail/manual/refresh?mailbox=${caixa}`, {}); toast(r.novos.length ? tr("{0} marcador(es) novo(s) na caixa: {1}{2}", r.novos.length, r.novos.slice(0, 3).join(', '), r.novos.length > 3 ? '…' : '') : tr("Nenhum marcador novo ({0} na caixa).", r.total_na_caixa), 'ok'); d.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }

  if (d.loading && !d.data) return <Loading rows={6} />
  if (d.error) return <ErrorState error={d.error} retry={d.reload} />
  const r = d.data?.resumo || {}
  return <div className="stack">
    <div className="card-h">
      <div><h1 className="h1">{tr("Manual dos marcadores · Gmail")}</h1>
        <div className="small ink2">{tr("O que a IA entendeu de cada marcador da caixa")} <b>{caixa}{tr("@urace.us")}</b>{tr(". Ela só classifica com o que você confirmar — e só nesta caixa.")}</div>
        <div className="tabs" style={{ marginTop: 8 }}>{(['urace', 'support'] as Caixa[]).map(c =>
          <button key={c} className={caixa === c ? 'on' : ''} onClick={() => trocarCaixa(c)}>{c}@</button>)}</div></div>
      <div className="grow" />
      <div className="row wrap">
        {can('MANAGER') && <button className="btn" disabled={busy === 'reler'} onClick={reler}>{busy === 'reler' ? <Spinner /> : tr("⟳ Reler a caixa")}</button>}
        {can('MANAGER') && !!r.pendente && <button className="btn primary" disabled={!!busy} onClick={() => confirmar()}>{busy === 'tudo' ? <Spinner /> : tr("Confirmar tudo ({0})", r.pendente)}</button>}
      </div>
    </div>

    {!d.data?.confirmado
      ? <Banner tone="warn"><b>{tr("A triagem está parada.")}</b> {tr("Enquanto nenhum marcador estiver confirmado, a IA não classifica nem move e-mail nenhum. Confira família por família abaixo e confirme o que estiver certo.")}</Banner>
      : <Banner tone="ok"><b>{r.confirmado} {tr("marcador(es) confirmado(s)")}</b>{d.data.confirmado_em && <> {tr("· último")} {ago(d.data.confirmado_em)}</>}{tr(". A IA só usa estes; qualquer outro que apareça na caixa é ignorado.")}</Banner>}

    {/* Só avisa enquanto os marcadores ainda existirem na caixa. Os 11 foram
        apagados em 11/09 a pedido do dono; um "Reler a caixa" zera este aviso.
        As linhas continuam no manual como `fora`: se algo recriá-los, já nascem ignorados. */}
    {(() => {
      const sug = (d.data?.labels || []).filter(m => m.origin === 'ia' && m.status === 'pendente')
      return sug.length > 0 && <Banner tone="warn">
        <b>{tr("A IA sugeriu")} {sug.length} {tr("marcador(es) novo(s).")}</b> {tr("Ela leu e-mails importantes que não cabiam em nenhum marcador seu. Ela")} <b>{tr("não cria marcador")}</b> {tr("— a sugestão espera você. Se confirmar,")} <b>{tr("crie o marcador no Gmail com o mesmo nome")}</b>{tr("; sem isso a IA não consegue aplicá-lo. Se não fizer sentido, marque como “não usar”.")}
      </Banner>
    })()}

    {!!(d.data?.labels || []).some(m => m.family === 'Email Review' && m.in_gmail) &&
      <Banner tone="crit"><b>{tr("“Email Review/…” não é seu.")}</b> {tr("São 11 marcadores aplicados em ~700 conversas entre 9 e 12 de agosto. Não foi o Command Center — o painel não cria marcador, o código recusa. O log de tokens OAuth do domínio mostrou que naquela data o único app com escrita no Gmail era o conector")} <b>{tr("Claude for Gmail")}</b> {tr("do claude.ai (autorizado em 16/07): foram sessões suas no Claude com esse conector ligado. Estão marcados como")} <b>{tr("não usar")}</b> {tr("e a IA os ignora — inclusive na sugestão de destino. Some da caixa apagando os marcadores no Gmail; some daqui com")} <b>{tr("⟳ Reler a caixa")}</b>.</Banner>}

    <div className="card"><div className="card-b">
      <div className="h2" style={{ marginBottom: 8 }}>{tr("O que chega → onde vai")}</div>
      <div className="tbl-wrap"><table className="tbl"><tbody>
        {(d.data?.exemplos || []).map((e, i) => <tr key={i}><td style={{ width: '45%' }}>{e.chega}</td><td className="mono small">{e.vai_para}</td></tr>)}
      </tbody></table></div>
    </div></div>

    <FiltrosNativos caixa={caixa} />

    <div className="row wrap">
      <input className="input" style={{ maxWidth: 320 }} placeholder={tr("Buscar marcador…")} value={filtro} onChange={e => setFiltro(e.target.value)} />
      <div className="tabs">{(['todos', 'pendente', 'confirmado', 'fora'] as const).map(t =>
        <button key={t} className={so === t ? 'on' : ''} onClick={() => setSo(t)}>{t === 'todos' ? tr("Todos") : ROTULO[t]} <span className="count">{t === 'todos' ? (d.data?.labels.length || 0) : (r[t] || 0)}</span></button>)}</div>
    </div>

    {familias.length === 0 ? <Empty title={tr("Nada aqui")}>{tr("Mude o filtro acima.")}</Empty> : familias.map(([fam, itens]) => {
      const pend = itens.filter(m => m.status === 'pendente').length
      return <section className="card" key={fam}>
        <div className="card-h"><h2 className="h2">{fam}<span className="count">{itens.length}</span></h2><div className="grow" />
          {can('MANAGER') && !!pend && <button className="btn sm" disabled={!!busy} onClick={() => confirmar(fam)}>{busy === fam ? <Spinner /> : tr("Confirmar os {0}", pend)}</button>}</div>
        <div className="card-b tight"><div className="tbl-wrap"><table className="tbl">
          <thead><tr><th style={{ width: '38%' }}>{tr("Marcador")}</th><th>{tr("O que vai aqui")}</th>{can('MANAGER') && <th></th>}</tr></thead>
          <tbody>{itens.map(m => <Linha key={m.id} m={m} reload={d.reload} />)}</tbody>
        </table></div></div>
      </section>
    })}
  </div>
}
