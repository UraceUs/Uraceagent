/* Atendimento humano (missão de 14/10): quando a IA precisa de uma pessoa, o caso cai aqui.
 *
 * A fila mostra o que está pendente, em atendimento, atrasado, sem responsável e resolvido. A
 * pessoa assume, responde pelo canal oficial (o chat do Kommo — o WhatsApp da URACE mora lá),
 * transfere, encerra ou devolve a conversa à IA com o contexto. Enquanto o caso está aberto a IA
 * fica travada nesta conversa pelo sistema (não pelo prompt). */
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import { Banner, Chip, Empty, ErrorState, Loading, PageHeader, Section } from '../components/ui'
import { ago, fmtDateTime } from '../components/fmt'
import { useToast } from '../components/Toast'
import { tr } from '../i18n'

type Estado = 'HUMAN_PENDING' | 'HUMAN_ACTIVE' | 'RESOLVED' | 'RETURNED_TO_AI'
type Filtro = 'pendentes' | 'em_atendimento' | 'atrasados' | 'sem_responsavel' | 'resolvidos'
interface Caso {
  id: number; conversa: string; kommo_lead_id: number; crm_lead_id: number | null; canal: string | null
  cliente_nome: string | null; estado: Estado; prioridade: 'baixa' | 'normal' | 'alta' | 'urgente'
  motivo: string; motivo_rotulo: string; motivo_texto: string | null; resumo: string | null; acao_pedida: string | null
  origem: string; responsavel_id: number | null; responsavel_nome: string | null; prazo_em: string | null
  criado_em: string; assumido_em: string | null; fechado_em: string | null; resultado: string | null
  nota_devolucao: string | null; ponte_pendente: string | null; ponte_erro: string | null
  atrasado: boolean; sem_responsavel: boolean; espera_min: number; kommo_url: string
}
interface Evento { id: number; tipo: string; de_estado: string | null; para_estado: string | null; ator_nome: string | null; ator: string; em: string }
interface Aviso { id: number; tipo: string; canal: 'push' | 'equipe' | 'whatsapp'; status: string; tentativas: number; erro: string | null; enviado_em: string | null }
interface Detalhe extends Caso {
  eventos: Evento[]; avisos: Aviso[]; ia_bloqueada: boolean; historico: { id: number; estado: Estado; motivo: string; criado_em: string }[]
  pode: { assumir: boolean; transferir: boolean; encerrar: boolean; devolver: boolean; responder: boolean }
}
interface Lista { itens: Caso[]; total: number; contagem: Record<Filtro, number> }

const FILTROS: [Filtro, string][] = [['pendentes', tr("Pendentes")], ['em_atendimento', tr("Em atendimento")],
  ['atrasados', tr("Atrasados")], ['sem_responsavel', tr("Sem responsável")], ['resolvidos', tr("Resolvidos")]]
const ESTADO: Record<Estado, [string, 'warn' | 'ok' | 'neutral' | 'crit']> = {
  HUMAN_PENDING: [tr("Esperando alguém assumir"), 'warn'], HUMAN_ACTIVE: [tr("Em atendimento"), 'ok'],
  RESOLVED: [tr("Resolvido"), 'neutral'], RETURNED_TO_AI: [tr("Devolvido à IA"), 'neutral'],
}
const PRIORIDADE: Record<Caso['prioridade'], [string, 'crit' | 'warn' | 'neutral']> = {
  urgente: [tr("Urgente"), 'crit'], alta: [tr("Alta"), 'crit'], normal: [tr("Normal"), 'warn'], baixa: [tr("Baixa"), 'neutral'],
}
const CANAL: Record<Aviso['canal'], string> = { push: tr("Celular (push)"), equipe: tr("Chat da equipe"), whatsapp: tr("WhatsApp oficial") }
const AVISO: Record<string, [string, 'ok' | 'warn' | 'crit' | 'neutral']> = {
  enviado: [tr("enviado"), 'ok'], entregue: [tr("entregue"), 'ok'], lido: [tr("lido"), 'ok'], pendente: [tr("na fila"), 'warn'],
  simulado: [tr("simulado (não saiu)"), 'warn'], bloqueado: [tr("não saiu"), 'crit'], falhou: [tr("falhou"), 'crit'], desistiu: [tr("desistiu"), 'crit'],
}
const EVENTO: Record<string, string> = {
  criado: tr("caso aberto"), ia_travada: tr("IA travada nesta conversa"), ia_trava_falhou: tr("falhou ao travar a IA (o sistema tenta de novo)"),
  assumido: tr("assumiu o atendimento"), transferido: tr("transferiu o caso"), resolvido: tr("encerrou o caso"),
  devolvido_ia: tr("devolveu a conversa à IA"), ia_destravada: tr("IA liberada"), escalonamento_repetido: tr("a IA pediu de novo"),
  prioridade_subiu: tr("prioridade subiu"), ponte_pendente: tr("esperando a ponte confirmar"), ponte_aviso_falhou: tr("a ponte não respondeu"),
  atrasado: tr("atrasado: equipe avisada de novo"), resposta_humana: tr("respondeu ao cliente"), cliente_escreveu: tr("o cliente escreveu"),
}

function Fila({ filtro, setFiltro, atual }: { filtro: Filtro; setFiltro: (f: Filtro) => void; atual: number | null }) {
  const d = useGet<Lista>(`/atendimento/casos?filtro=${filtro}&limit=100`, 15000)
  return <Section title={tr("Fila")} count={d.data?.total}>
    <div className="tabs" role="tablist" aria-label={tr("Filtro da fila")} style={{ flexWrap: 'wrap', borderRadius: 18, marginBottom: 12 }}>
      {FILTROS.map(([f, rot]) => <button key={f} role="tab" aria-selected={filtro === f} className={filtro === f ? 'on' : ''} onClick={() => setFiltro(f)}>
        {rot} <span className="count">{d.data?.contagem?.[f] ?? ''}</span></button>)}
    </div>
    {d.error ? <ErrorState error={d.error} retry={d.reload} /> : !d.data ? <Loading rows={3} /> : !d.data.itens.length
      ? <Empty title={tr("Nada nesta fila")}>{filtro === 'pendentes' ? tr("Nenhuma conversa esperando uma pessoa agora.") : tr("Nenhum caso aqui.")}</Empty>
      : <ul className="sdr-lista">{d.data.itens.map(c => <li key={c.id} className={c.id === atual ? 'on' : ''}>
        <Link to={`/atendimento/${c.id}`} className="grow" style={{ minWidth: 0, color: 'inherit', textDecoration: 'none', minHeight: 40 }}>
          <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
            <Chip tone={PRIORIDADE[c.prioridade][1]}>{PRIORIDADE[c.prioridade][0]}</Chip>
            <Chip tone={ESTADO[c.estado][1]}>{ESTADO[c.estado][0]}</Chip>
            {c.atrasado && <Chip tone="crit">{tr("Atrasado")}</Chip>}
            <b>{c.cliente_nome || tr("sem nome no Kommo")}</b>
          </div>
          <div style={{ marginTop: 4 }}>{c.motivo_rotulo}{c.resumo ? ` · ${c.resumo.slice(0, 120)}` : ''}</div>
          <div className="small muted">#{c.id} · {ago(c.criado_em)}{c.responsavel_nome ? ` · ${c.responsavel_nome}` : ''}</div>
        </Link>
      </li>)}</ul>}
  </Section>
}

function Acao({ titulo, rotulo, ajuda, botao, perigo, onEnviar }: { titulo: string; rotulo: string; ajuda: string; botao: string; perigo?: boolean; onEnviar: (t: string) => Promise<void> }) {
  const [texto, setTexto] = useState('')
  const [indo, setIndo] = useState(false)
  return <form className="sdr-form" onSubmit={async e => { e.preventDefault(); if (!texto.trim() || indo) return; setIndo(true); try { await onEnviar(texto.trim()); setTexto('') } finally { setIndo(false) } }}>
    <h3 style={{ margin: '0 0 6px' }}>{titulo}</h3>
    <label className="fld"><span>{rotulo}</span><textarea value={texto} onChange={e => setTexto(e.target.value)} maxLength={1500} /></label>
    <p className="small muted" style={{ marginTop: -6 }}>{ajuda}</p>
    <div className="row" style={{ justifyContent: 'flex-end' }}><button className={`btn ${perigo ? '' : 'primary'}`} disabled={!texto.trim() || indo}>{indo ? <span className="spin" /> : botao}</button></div>
  </form>
}

function Caso({ id }: { id: number }) {
  const d = useGet<Detalhe>(`/atendimento/casos/${id}`, 10000)
  const pessoas = useGet<{ pessoas: { id: number; name: string }[] }>(d.data?.pode.transferir ? '/atendimento/pessoas' : null)
  const toast = useToast()
  const [para, setPara] = useState('')
  const [busy, setBusy] = useState(false)
  async function fazer(caminho: string, corpo: unknown, ok: string) {
    try {
      const r = await api.post<{ aviso?: string }>(`/atendimento/casos/${id}/${caminho}`, corpo)
      toast(r?.aviso || ok, r?.aviso ? 'warn' : 'ok'); d.reload()
    } catch (e) { toast((e as ApiError).message, 'crit'); throw e }
  }
  if (d.error) return <ErrorState error={d.error} retry={d.reload} />
  if (!d.data) return <Loading rows={4} />
  const c = d.data
  return <Section title={<>{tr("Caso #{0}", c.id)} · {c.cliente_nome || tr("sem nome no Kommo")}</>}>
    <div className="stack" style={{ gap: 12 }}>
      <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
        <Chip tone={PRIORIDADE[c.prioridade][1]}>{PRIORIDADE[c.prioridade][0]}</Chip>
        <Chip tone={ESTADO[c.estado][1]}>{ESTADO[c.estado][0]}</Chip>
        {c.atrasado && <Chip tone="crit">{tr("Atrasado")}</Chip>}
        <Chip tone={c.ia_bloqueada ? 'warn' : 'neutral'}>{c.ia_bloqueada ? tr("IA travada nesta conversa") : tr("IA livre nesta conversa")}</Chip>
      </div>
      {c.ponte_pendente && <Banner tone="warn">{tr("A ponte ainda não confirmou ({0}). A conversa continua com a pessoa e a IA segue travada; o sistema tenta de novo a cada meio minuto.", c.ponte_erro || c.ponte_pendente)}</Banner>}
      <dl className="dl">
        <dt>{tr("Motivo")}</dt><dd>{c.motivo_rotulo}{c.motivo_texto ? ` — ${c.motivo_texto}` : ''}</dd>
        {c.resumo && <><dt>{tr("Resumo")}</dt><dd style={{ whiteSpace: 'pre-wrap' }}>{c.resumo}</dd></>}
        {c.acao_pedida && <><dt>{tr("Ação pedida")}</dt><dd>{c.acao_pedida}</dd></>}
        <dt>{tr("Conversa")}</dt><dd className="mono">{c.conversa}{c.canal ? ` · ${c.canal}` : ''}</dd>
        <dt>{tr("Aberto")}</dt><dd>{fmtDateTime(c.criado_em)} ({ago(c.criado_em)})</dd>
        <dt>{tr("Responsável")}</dt><dd>{c.responsavel_nome || tr("ninguém ainda")}</dd>
        {c.resultado && <><dt>{tr("Resultado")}</dt><dd>{c.resultado}</dd></>}
        {c.nota_devolucao && <><dt>{tr("Contexto para a IA")}</dt><dd>{c.nota_devolucao}</dd></>}
      </dl>
      <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
        <a className="btn sm" href={c.kommo_url} target="_blank" rel="noopener noreferrer">{tr("Abrir no Kommo")} ↗</a>
        {c.crm_lead_id && <Link className="btn sm" to={`/crm/chat/${c.crm_lead_id}`}>{tr("Ver a conversa no painel")}</Link>}
      </div>
      {c.pode.assumir && <div className="row" style={{ justifyContent: 'flex-start' }}>
        <button className="btn primary" disabled={busy} onClick={async () => { setBusy(true); try { await fazer('assumir', undefined, tr("Caso assumido. A IA continua travada nesta conversa.")) } catch { /* toast já mostrou */ } finally { setBusy(false) } }}>
          {busy ? <span className="spin" /> : tr("Assumir atendimento")}</button></div>}
      {c.pode.responder && <Acao titulo={tr("Responder ao cliente")} rotulo={tr("Mensagem")} botao={tr("Enviar")}
        ajuda={tr("Sai pelo canal em que o cliente falou (Kommo → WhatsApp/Instagram), com o seu nome no registro.")}
        onEnviar={t => fazer('responder', { texto: t }, tr("Mensagem enviada ao cliente."))} />}
      {c.estado === 'HUMAN_ACTIVE' && !c.crm_lead_id && <p className="small muted">{tr("Este lead ainda não está no espelho do painel: responda pelo Kommo (botão acima).")}</p>}
      {c.pode.transferir && <form className="sdr-form" onSubmit={async e => { e.preventDefault(); if (!para) return; try { await fazer('transferir', { para_user_id: Number(para) }, tr("Caso transferido.")); setPara('') } catch { /* toast */ } }}>
        <h3 style={{ margin: '0 0 6px' }}>{tr("Transferir")}</h3>
        <div className="row gap"><label className="fld grow"><span>{tr("Para quem")}</span>
          <select value={para} onChange={e => setPara(e.target.value)}><option value="">{tr("Escolha")}</option>
            {(pessoas.data?.pessoas || []).filter(p => p.id !== c.responsavel_id).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
          <button className="btn" style={{ marginTop: 22 }} disabled={!para}>{tr("Transferir")}</button></div>
      </form>}
      {c.pode.devolver && <Acao titulo={tr("Devolver à IA")} rotulo={tr("O que a IA precisa saber para continuar")} botao={tr("Devolver à IA")}
        ajuda={tr("A IA só volta a responder depois disto. O que você escrever entra na memória desta conversa.")}
        onEnviar={t => fazer('devolver', { texto: t }, tr("Conversa devolvida à IA."))} />}
      {c.pode.encerrar && <Acao titulo={tr("Encerrar o caso")} rotulo={tr("Resultado do atendimento")} botao={tr("Encerrar")} perigo
        ajuda={tr("Uma nova mensagem do cliente abre um ciclo novo com a IA.")}
        onEnviar={t => fazer('encerrar', { texto: t }, tr("Caso encerrado."))} />}
      <h3 style={{ margin: '8px 0 0' }}>{tr("Avisos à equipe")}</h3>
      {!c.avisos.length ? <p className="small muted">{tr("Nenhum aviso registrado.")}</p> : <ul className="sdr-lista">{c.avisos.map(a => <li key={a.id}>
        <div className="grow" style={{ minWidth: 0 }}>
          <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}><b>{CANAL[a.canal]}</b><Chip tone={(AVISO[a.status] || [a.status, 'neutral'])[1]}>{(AVISO[a.status] || [a.status])[0]}</Chip></div>
          {a.erro && <div className="small muted">{a.erro}</div>}
        </div></li>)}</ul>}
      <h3 style={{ margin: '8px 0 0' }}>{tr("Linha do tempo")}</h3>
      <ul className="sdr-lista">{c.eventos.map(e => <li key={e.id}><div className="grow" style={{ minWidth: 0 }}>
        <div>{e.ator_nome ? <b>{e.ator_nome}</b> : null}{e.ator_nome ? ' ' : ''}{EVENTO[e.tipo] || e.tipo}</div>
        <div className="small muted">{fmtDateTime(e.em)}</div></div></li>)}</ul>
      {c.historico.length > 0 && <><h3 style={{ margin: '8px 0 0' }}>{tr("Casos anteriores desta conversa")}</h3>
        <ul className="sdr-lista">{c.historico.map(h => <li key={h.id}><Link to={`/atendimento/${h.id}`} className="grow" style={{ color: 'inherit' }}>
          #{h.id} · {ESTADO[h.estado][0]} · {ago(h.criado_em)}</Link></li>)}</ul></>}
    </div>
  </Section>
}

export default function Atendimento() {
  const { id } = useParams()
  const nav = useNavigate()
  const [filtro, setFiltro] = useState<Filtro>('pendentes')
  const atual = id && /^\d+$/.test(id) ? Number(id) : null
  return <div className="page">
    <PageHeader title={tr("Atendimento humano")}
      help={tr("Quando a IA precisa de uma pessoa, a conversa cai aqui e a equipe é avisada. Assuma, responda pelo Kommo, e devolva à IA ou encerre. Enquanto o caso está aberto a IA não responde nessa conversa.")}>
      {atual && <button className="btn sm" onClick={() => nav('/atendimento')}>{tr("Voltar à fila")}</button>}
    </PageHeader>
    <div className="grid g2">
      <Fila filtro={filtro} setFiltro={setFiltro} atual={atual} />
      {atual ? <Caso id={atual} /> : <Section title={tr("Caso")}><Empty title={tr("Escolha um caso na fila")}>{tr("Os pendentes e atrasados aparecem primeiro, por prioridade.")}</Empty></Section>}
    </div>
  </div>
}
