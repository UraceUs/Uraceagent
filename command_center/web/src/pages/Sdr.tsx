/* Robô SDR (dono, 12/10): "uma sessão robô SDR onde ele consiga ligar e desligar, passar o
 * que precisa ser feito pelo robô, reportar alguma coisa, gerir o robô".
 *
 * O comercial manda nas instruções: valem acima da persona, com duas exceções fixas — o preço
 * (vem da tabela do sistema) e as travas de segurança. O nível (observar, organizar, atender)
 * continua só do ADMIN; o resto da página é de quem vende. */
import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, PageHeader, Section } from '../components/ui'
import { ago, fmtDateTime } from '../components/fmt'
import { usePerguntar } from '../components/Perguntar'
import { useToast } from '../components/Toast'
import { Icon } from '../components/Icon'
import { LOCALE, tr } from '../i18n'

type Nivel = 'observar' | 'organizar' | 'atender'
interface Painel {
  nivel: Nivel; chase_ligado: boolean; ponte_no_ar: boolean; reiniciando: boolean; instalado: boolean
  pode_trocar: boolean; pode_instruir: boolean; decisoes_24h: number | null; ultima_decisao: string | null
  ponte_sem_auditoria: boolean; instrucoes_em_vigor: number; relatos_abertos: number; conversas_pausadas?: number
  horario_humano: { texto: string }; niveis: Nivel[]
}
interface Instrucao { id: number; categoria: string; texto: string; status: 'ativa' | 'aplicada' | 'arquivada'; quem: string | null; created_at: string; applied_at: string | null; aplicada_por: string | null; aviso_preco: boolean }
interface Instrucoes { itens: Instrucao[]; categorias: Record<string, string>; aviso_preco: string; limite: number }
interface Relato { id: number; tipo: string; texto: string; lead_ref: string | null; status: 'aberto' | 'resolvido'; quem: string | null; created_at: string; resolved_at: string | null; resolvido_por: string | null }
interface Relatos { itens: Relato[]; tipos: Record<string, string>; abertos: number }
interface Decisao { id: number; quando: string; lead_id: number | null; acao: string | null; motivo: string | null; nivel: string | null; fez: string }
interface Auditoria { itens: Decisao[]; acoes?: string[]; motivo?: string }

const NIVEL_NOME: Record<Nivel, string> = { observar: tr("Observar"), organizar: tr("Organizar"), atender: tr("Atender") }
const NIVEL_TEXTO: Record<Nivel, string> = {
  observar: tr("Decide e registra. Não escreve no Kommo e não responde ao lead."),
  organizar: tr("Etiqueta, nota, tarefa e etapa no Kommo. Não responde ao lead."),
  atender: tr("Organiza e responde: o robô falando com o lead."),
}
const NIVEL_CONFIRMA: Record<Nivel, string> = {
  observar: tr("O robô vai parar de escrever no Kommo e de responder; só registra as decisões. A ponte reinicia em segundos."),
  organizar: tr("O robô vai etiquetar, anotar e mover os leads no Kommo, sem responder a ninguém. A ponte reinicia em segundos."),
  atender: tr("O robô vai responder aos leads no Kommo, com as instruções abaixo. A ponte reinicia em segundos."),
}
const CATEGORIA_NOME: Record<string, string> = {
  tom: tr("tom"), idioma: tr("idioma"), preco: tr("preço e condições"), horario: tr("horário"), pessoa: tr("passar para pessoa"),
  followup: tr("follow-up"), canal: tr("canal"), nunca: tr("nunca dizer"), outro: tr("outro"),
}
const TIPO_NOME: Record<string, string> = {
  respondeu_errado: tr("o robô respondeu errado"), preco_errado: tr("preço errado"), ignorou_lead: tr("ignorou o lead"), outro: tr("outro"),
}
const temPreco = (t: string) => /\$|pre[çc]o|price/i.test(t)
/** Hora em Orlando; com o dia na frente quando não é hoje. */
function horaOrlando(iso: string) {
  const tz = 'America/New_York'
  const hoje = new Date().toLocaleDateString('en-CA', { timeZone: tz })
  const dia = new Date(iso).toLocaleDateString('en-CA', { timeZone: tz })
  const hora = new Date(iso).toLocaleTimeString('en-US', { timeZone: tz, hour: '2-digit', minute: '2-digit', hour12: false })
  return dia === hoje ? hora : `${new Date(iso).toLocaleDateString('en-US', { timeZone: tz, month: '2-digit', day: '2-digit' })} ${hora}`
}

// ------------------------------------------------------------------ ligar e desligar
function LigarDesligar({ p, onMudou }: { p: Painel; onMudou: () => void }) {
  const toast = useToast()
  const perguntar = usePerguntar()
  const [indo, setIndo] = useState(false)
  async function trocar(nivel: Nivel) {
    if (nivel === p.nivel || indo) return
    const ok = await perguntar({ titulo: tr("Mudar o robô para {0}?", NIVEL_NOME[nivel]), texto: NIVEL_CONFIRMA[nivel], ok: tr("Mudar"), perigo: nivel === 'atender' })
    if (!ok) return
    setIndo(true)
    try { await api.put('/sdr', { nivel }); toast(tr("Nível gravado: {0}. A ponte reinicia em segundos.", NIVEL_NOME[nivel]), 'ok'); onMudou() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  return <Section title={tr("Ligar e desligar")}>
    {!p.pode_trocar && <p className="small muted" style={{ marginTop: 0 }}>{tr("Só o administrador muda o nível. Você vê em que nível o robô está.")}</p>}
    {!p.instalado && <Banner tone="warn">{tr("O interruptor passa a valer depois do próximo deploy no servidor.")}</Banner>}
    <div className="sdr-niveis" role="radiogroup" aria-label={tr("Nível do robô")}>
      {p.niveis.map(n => <label key={n} className={`sdr-nivel${p.nivel === n ? ' on' : ''}`}>
        <input type="radio" name="nivel" value={n} checked={p.nivel === n} disabled={!p.pode_trocar || indo || p.reiniciando} onChange={() => trocar(n)} />
        <span><b>{NIVEL_NOME[n]}</b><small>{NIVEL_TEXTO[n]}</small></span>
      </label>)}
    </div>
  </Section>
}

// ------------------------------------------------------------------ IA pausada por conversa
export interface Pausa { lead_id: number; por?: string | null; em?: string | null; motivo?: string | null }
function PausasCard({ pode, onMudou }: { pode: boolean; onMudou: () => void }) {
  const d = useGet<{ itens: Pausa[] }>('/sdr/pausas', 30000)
  const toast = useToast()
  const [lead, setLead] = useState('')
  const [motivo, setMotivo] = useState('')
  const [busy, setBusy] = useState<number | 'novo' | null>(null)
  async function trocar(id: number, pausada: boolean, m?: string) {
    setBusy(pausada ? 'novo' : id)
    try {
      await api.put(`/sdr/pausas/${id}`, { pausada, motivo: m || null })
      toast(pausada ? tr("IA pausada nesta conversa. A pessoa responde a partir de agora.") : tr("IA reativada nesta conversa."), 'ok')
      if (pausada) { setLead(''); setMotivo('') }
      d.reload(); onMudou()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  const id = Number(lead.replace(/\D/g, ''))
  return <Section title={tr("Conversas com a IA pausada")} count={d.data?.itens.length}>
    {d.error ? <ErrorState error={d.error} retry={d.reload} /> : !d.data ? <Loading rows={2} /> : <div className="stack" style={{ gap: 12 }}>
      <p className="small muted" style={{ margin: 0 }}>{tr("Numa conversa pausada o robô não responde, não manda follow-up nem resgate: quem fala é a pessoa. O card continua sendo organizado. Também dá para pausar direto no Chat do Kommo.")}</p>
      {!d.data.itens.length ? <Empty title={tr("Nenhuma conversa pausada")}>{tr("O robô responde todas as conversas no escopo dele.")}</Empty>
        : <ul className="sdr-lista">{d.data.itens.map(x => <li key={x.lead_id}>
          <div className="grow" style={{ minWidth: 0 }}>
            <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}><Chip tone="warn">{tr("IA pausada")}</Chip>
              <a className="mono" href={`https://urace.kommo.com/leads/detail/${x.lead_id}`} target="_blank" rel="noopener noreferrer">{tr("lead {0}", x.lead_id)} ↗</a></div>
            {x.motivo && <div style={{ marginTop: 4 }}>{x.motivo}</div>}
            <div className="small muted">{x.por || '—'}{x.em ? ` · ${ago(x.em)}` : ''}</div>
          </div>
          {pode && <button className="btn sm" style={{ alignSelf: 'start' }} disabled={busy === x.lead_id} onClick={() => trocar(x.lead_id, false)}>{busy === x.lead_id ? <span className="spin" /> : tr("Reativar IA")}</button>}
        </li>)}</ul>}
      {pode && <form className="sdr-form" onSubmit={e => { e.preventDefault(); if (id > 0) trocar(id, true, motivo.trim()) }}>
        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
          <label className="fld" style={{ minWidth: 180 }}><span>{tr("Lead no Kommo (id)")}</span><input value={lead} onChange={e => setLead(e.target.value)} inputMode="numeric" placeholder="31764961" /></label>
          <label className="fld grow" style={{ minWidth: 200 }}><span>{tr("Motivo (opcional)")}</span><input value={motivo} onChange={e => setMotivo(e.target.value)} maxLength={200} /></label>
        </div>
        <div className="row" style={{ justifyContent: 'flex-end' }}><button className="btn primary" disabled={!(id > 0) || busy === 'novo'}>{busy === 'novo' ? <span className="spin" /> : tr("Pausar IA")}</button></div>
      </form>}
    </div>}
  </Section>
}

// ------------------------------------------------------------------ teste no painel (14/10)
interface Turno { quem: 'voce' | 'robo'; textos: string[]; hora: string; nota?: string; acoes?: string[]; cortes?: string[] }
interface TesteOut { mensagens: string[]; rota: string | null; motivo: string | null; diretivas: string[]; cortes: string[]; nota: string }
const novaSessao = () => 'cc-' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36)
const horaAgora = () => new Date().toLocaleTimeString(LOCALE(), { hour: '2-digit', minute: '2-digit' })
// O que a guarda e as diretivas fizeram, em português de gente (o código fica no title).
const CORTE: Record<string, string> = {
  link_na_primeira_resposta: "tirou o link (1ª resposta vai sem link)", mais_de_um_link: "deixou só um link",
  mais_de_uma_pergunta: "deixou só uma pergunta", emoji: "tirou emoji", travessao: "trocou travessão por vírgula",
}
const ACAO: Record<string, string> = {
  escalate: "passaria a conversa para a equipe", crm: "anotaria no card do Kommo", qualify: "registraria a qualificação",
  followup: "agendaria um follow-up", price: "buscaria o link do programa", kb: "consultaria a base de conhecimento",
  unknown: "registraria uma dúvida sem resposta",
}
function nomeCorte(c: string) {
  if (c.startsWith('nunca_dizer:')) return tr("tirou a frase com “{0}”", c.slice(12))
  return CORTE[c] ? tr(CORTE[c]) : c
}
function nomeAcao(d: string) {
  const m = /^\[\[\s*(\w+)/.exec(d)
  return m && ACAO[m[1]] ? tr(ACAO[m[1]]) : d
}
const SUGESTOES = ["Oi, quanto custa?", "É meu filho, 8 anos", "Nunca andou de kart", "Quais dias vocês têm?", "Onde fica?", "Faria se fosse mais barato"]

function TesteCard() {
  const toast = useToast()
  const [sessao, setSessao] = useState(novaSessao)
  const [turnos, setTurnos] = useState<Turno[]>([])
  const [texto, setTexto] = useState('')
  const [nome, setNome] = useState('')
  const [busy, setBusy] = useState(false)
  const fim = useRef<HTMLDivElement>(null)
  useEffect(() => { const el = fim.current; if (el) el.scrollTop = el.scrollHeight }, [turnos, busy])
  async function enviar(msg?: string) {
    const t = (msg ?? texto).trim(); if (!t || busy) return
    setBusy(true); setTexto('')
    setTurnos(x => [...x, { quem: 'voce', textos: [t], hora: horaAgora() }])
    try {
      const r = await api.post<TesteOut>('/sdr/teste', { sessao, texto: t, nome: nome.trim() || null })
      setTurnos(x => [...x, { quem: 'robo', textos: r.mensagens || [], hora: horaAgora(), nota: r.nota || undefined,
        acoes: r.diretivas || [], cortes: r.cortes || [] }])
    } catch (e) { toast((e as ApiError).message, 'crit'); setTurnos(x => x.slice(0, -1)); setTexto(t) }
    finally { setBusy(false) }
  }
  function recomecar() { setSessao(novaSessao()); setTurnos([]); setTexto('') }
  return <Section title={tr("Testar o robô")}
    right={<button className="btn sm" disabled={busy || !turnos.length} onClick={recomecar}><Icon name="refresh" size={14} />{tr("Nova conversa")}</button>}>
    <div className="sdr-play">
      <div className="sdr-fone">
        <div className="sdr-fone-h">
          <span className="sdr-av">U</span>
          <div className="grow" style={{ minWidth: 0 }}>
            <div className="sdr-fone-n">urace.us</div>
            <div className="small muted">{busy ? tr("digitando…") : tr("Conversa comercial · teste")}</div>
          </div>
          <Icon name="instagram" size={18} />
        </div>
        <div className="sdr-teste" ref={fim} aria-live="polite">
          {!turnos.length && !busy && <div className="sdr-vazio">
            <Icon name="chat" size={28} />
            <div>{tr("Escreva como o lead escreveria, ou toque numa sugestão.")}</div>
          </div>}
          {turnos.map((t, i) => <div key={i} className={`sdr-teste-turno ${t.quem}`}>
            {t.textos.length ? t.textos.map((m, j) => <div key={j} className="sdr-balao">{m}</div>)
              : <div className="sdr-balao mudo">{tr("o robô não responderia")}</div>}
            <div className="sdr-hora">{t.hora}</div>
            {(t.nota || !!t.acoes?.length || !!t.cortes?.length) && <div className="sdr-info">
              {t.nota && <Chip tone="info">{t.nota}</Chip>}
              {t.acoes?.map((d, j) => <Chip key={'a' + j} tone="neutral" title={d}>{nomeAcao(d)}</Chip>)}
              {t.cortes?.map((c, j) => <Chip key={'c' + j} tone="warn" title={c}>{tr("guarda: {0}", nomeCorte(c))}</Chip>)}
            </div>}
          </div>)}
          {busy && <div className="sdr-teste-turno robo"><div className="sdr-balao sdr-digitando" aria-label={tr("digitando…")}><i /><i /><i /></div></div>}
        </div>
        <form className="sdr-compor" onSubmit={e => { e.preventDefault(); enviar() }}>
          <input className="inp" value={texto} onChange={e => setTexto(e.target.value)} maxLength={1000}
            placeholder={tr("Mensagem do lead")} aria-label={tr("Mensagem do lead")} disabled={busy} />
          <button className="btn primary" disabled={!texto.trim() || busy} aria-label={tr("Enviar")}>{busy ? <span className="spin" /> : tr("Enviar")}</button>
        </form>
      </div>
      <div className="sdr-lado stack" style={{ gap: 12 }}>
        <p className="small muted" style={{ margin: 0 }}>{tr("Converse com o robô como se fosse um lead. Mesma persona e mesmas regras da resposta real, mas nada vai para o Kommo nem para ninguém, e as ações (passar para a equipe, tags) só aparecem aqui.")}</p>
        <label className="fld"><span>{tr("Nome do lead (opcional)")}</span><input value={nome} onChange={e => setNome(e.target.value)} maxLength={60} placeholder="Eduardo" /></label>
        <div>
          <div className="small muted" style={{ marginBottom: 6 }}>{tr("Sugestões")}</div>
          <div className="sug row" style={{ gap: 6, flexWrap: 'wrap' }}>
            {SUGESTOES.map(x => <button key={x} type="button" className="btn sm" disabled={busy} onClick={() => enviar(tr(x))}>{tr(x)}</button>)}
          </div>
        </div>
      </div>
    </div>
  </Section>
}

// ------------------------------------------------------------------ instruções
function Instrucoes({ pode, onMudou }: { pode: boolean; onMudou: () => void }) {
  const d = useGet<Instrucoes>('/sdr/instrucoes')
  const toast = useToast()
  const [cat, setCat] = useState('tom')
  const [texto, setTexto] = useState('')
  const [busy, setBusy] = useState<number | 'novo' | 'kommo' | null>(null)
  const [kommo, setKommo] = useState<string | null>(null)
  async function criar() {
    const t = texto.trim(); if (!t || busy) return
    setBusy('novo')
    try { await api.post('/sdr/instrucoes', { categoria: cat, texto: t }); setTexto(''); toast(tr("Instrução gravada. O robô lê na próxima mensagem."), 'ok'); d.reload(); onMudou() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  async function mudar(i: Instrucao, status: Instrucao['status']) {
    setBusy(i.id)
    try { await api.patch(`/sdr/instrucoes/${i.id}`, { status }); toast(status === 'arquivada' ? tr("Instrução arquivada.") : tr("Marcada como aplicada no Kommo."), 'ok'); d.reload(); onMudou() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  async function gerar() {
    setBusy('kommo')
    try { const r = await api.get<{ texto: string; linhas: number }>('/sdr/instrucoes/texto-kommo'); setKommo(r.texto || '') }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  async function copiar() {
    try { await navigator.clipboard.writeText(kommo || ''); toast(tr("Copiado. Cole na tela do agente de IA do Kommo."), 'ok') }
    catch { toast(tr("Não deu para copiar: selecione o texto e copie à mão."), 'crit') }
  }
  const limite = d.data?.limite || 1000
  return <Section title={tr("Instruções para o robô")} count={d.data?.itens.length}
    right={<button className="btn sm" disabled={busy === 'kommo' || !d.data?.itens.length} onClick={gerar}>{busy === 'kommo' ? <span className="spin" /> : tr("Gerar texto para o agente do Kommo")}</button>}>
    {d.error ? <ErrorState error={d.error} retry={d.reload} /> : !d.data ? <Loading rows={3} /> : <div className="stack" style={{ gap: 12 }}>
      <p className="small muted" style={{ margin: 0 }}>{tr("O que você escreve aqui vale acima da persona do robô, com duas exceções fixas: o preço (vem da tabela) e as travas de segurança.")}</p>
      {kommo !== null && <div className="sdr-kommo">
        <div className="row" style={{ justifyContent: 'space-between', gap: 8 }}><b>{tr("Texto para a tela do agente do Kommo (cada linha cabe em 300 caracteres)")}</b>
          <div className="row" style={{ gap: 6 }}><button className="btn sm" onClick={copiar}>{tr("Copiar")}</button><button className="btn sm ghost" onClick={() => setKommo(null)}>{tr("Fechar")}</button></div></div>
        <textarea readOnly value={kommo} rows={Math.min(12, Math.max(3, kommo.split('\n').length + 1))} aria-label={tr("Texto para o agente do Kommo")} />
      </div>}
      {!d.data.itens.length ? <Empty title={tr("Nenhuma instrução ainda")}>{tr("O robô segue a persona padrão. Escreva abaixo o que ele deve fazer diferente.")}</Empty>
        : <ul className="sdr-lista">{d.data.itens.map(i => <li key={i.id}>
          <div className="grow" style={{ minWidth: 0 }}>
            <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}><Chip tone="info">{CATEGORIA_NOME[i.categoria] || i.categoria}</Chip>
              {i.status === 'aplicada' && <Chip tone="ok" title={i.applied_at ? fmtDateTime(i.applied_at) : undefined}>{tr("aplicada no Kommo")}</Chip>}
              {i.aviso_preco && <Chip tone="warn">{tr("fala de preço")}</Chip>}</div>
            <div style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', marginTop: 4 }}>{i.texto}</div>
            <div className="small muted">{i.quem || '—'} · {ago(i.created_at)}{i.aplicada_por ? ` · ${tr("aplicada por {0}", i.aplicada_por)}` : ''}</div>
          </div>
          {pode && <div className="row" style={{ gap: 6, flexWrap: 'wrap', alignSelf: 'start' }}>
            {i.status === 'ativa' && <button className="btn sm" disabled={busy === i.id} onClick={() => mudar(i, 'aplicada')}>{tr("Marcar como aplicada no Kommo")}</button>}
            <button className="btn sm ghost" disabled={busy === i.id} onClick={() => mudar(i, 'arquivada')}>{tr("Arquivar")}</button>
          </div>}
        </li>)}</ul>}
      {pode && <form className="sdr-form" onSubmit={e => { e.preventDefault(); criar() }}>
        <Banner tone={temPreco(texto) ? 'warn' : 'info'}>{d.data.aviso_preco}</Banner>
        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
          <label className="fld" style={{ minWidth: 200 }}><span>{tr("Categoria")}</span>
            <select value={cat} onChange={e => setCat(e.target.value)}>{Object.keys(d.data.categorias).map(k => <option key={k} value={k}>{CATEGORIA_NOME[k] || d.data!.categorias[k]}</option>)}</select></label>
        </div>
        <label className="fld"><span>{tr("Instrução")}</span>
          <textarea value={texto} onChange={e => setTexto(e.target.value.slice(0, limite))} rows={3} maxLength={limite}
            placeholder={tr("Ex.: responda sempre em inglês quando o lead escrever em inglês; não prometa data de corrida sem confirmar com a equipe.")} /></label>
        <div className="row" style={{ justifyContent: 'space-between', gap: 8 }}>
          <span className="small muted">{texto.length}/{limite}</span>
          <button className="btn primary" disabled={!texto.trim() || busy === 'novo'}>{busy === 'novo' ? <span className="spin" /> : tr("Gravar instrução")}</button>
        </div>
      </form>}
    </div>}
  </Section>
}

// ------------------------------------------------------------------ relatos
function RelatosCard({ podeResolver, onMudou }: { podeResolver: boolean; onMudou: () => void }) {
  const d = useGet<Relatos>('/sdr/relatos')
  const toast = useToast()
  const [tipo, setTipo] = useState('respondeu_errado')
  const [texto, setTexto] = useState('')
  const [lead, setLead] = useState('')
  const [busy, setBusy] = useState<number | 'novo' | null>(null)
  const [verResolvidos, setVerResolvidos] = useState(false)
  async function criar() {
    const t = texto.trim(); if (!t || busy) return
    setBusy('novo')
    try { await api.post('/sdr/relatos', { tipo, texto: t, lead_ref: lead.trim() || null }); setTexto(''); setLead(''); toast(tr("Relato registrado."), 'ok'); d.reload(); onMudou() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  async function resolver(r: Relato) {
    setBusy(r.id)
    try { await api.patch(`/sdr/relatos/${r.id}`, { status: 'resolvido' }); toast(tr("Relato resolvido."), 'ok'); d.reload(); onMudou() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  const itens = (d.data?.itens || []).filter(r => verResolvidos || r.status === 'aberto')
  return <Section title={tr("Relatos")} count={d.data?.abertos}
    right={<label className="check small"><input type="checkbox" checked={verResolvidos} onChange={e => setVerResolvidos(e.target.checked)} /> {tr("ver resolvidos")}</label>}>
    {d.error ? <ErrorState error={d.error} retry={d.reload} /> : !d.data ? <Loading rows={2} /> : <div className="stack" style={{ gap: 12 }}>
      {!itens.length ? <Empty title={tr("Nenhum relato aberto")}>{tr("O robô errou? Conte aqui: quem cuida do robô lê e resolve.")}</Empty>
        : <ul className="sdr-lista">{itens.map(r => <li key={r.id}>
          <div className="grow" style={{ minWidth: 0 }}>
            <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}><Chip tone={r.status === 'aberto' ? 'warn' : 'neutral'}>{r.status === 'aberto' ? tr("aberto") : tr("resolvido")}</Chip>
              <Chip tone="info">{TIPO_NOME[r.tipo] || r.tipo}</Chip>{r.lead_ref && <Chip tone="neutral">{tr("lead {0}", r.lead_ref)}</Chip>}</div>
            <div style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', marginTop: 4 }}>{r.texto}</div>
            <div className="small muted">{r.quem || '—'} · {ago(r.created_at)}{r.resolvido_por ? ` · ${tr("resolvido por {0}", r.resolvido_por)}` : ''}</div>
          </div>
          {podeResolver && r.status === 'aberto' && <button className="btn sm" style={{ alignSelf: 'start' }} disabled={busy === r.id} onClick={() => resolver(r)}>{tr("Resolver")}</button>}
        </li>)}</ul>}
      <form className="sdr-form" onSubmit={e => { e.preventDefault(); criar() }}>
        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
          <label className="fld" style={{ minWidth: 200 }}><span>{tr("O que aconteceu")}</span>
            <select value={tipo} onChange={e => setTipo(e.target.value)}>{Object.keys(d.data.tipos).map(k => <option key={k} value={k}>{TIPO_NOME[k] || d.data!.tipos[k]}</option>)}</select></label>
          <label className="fld" style={{ minWidth: 200 }}><span>{tr("Lead (id ou nome, se souber)")}</span><input value={lead} onChange={e => setLead(e.target.value)} maxLength={120} /></label>
        </div>
        <label className="fld"><span>{tr("Relato")}</span><textarea value={texto} onChange={e => setTexto(e.target.value.slice(0, 1000))} rows={3} maxLength={1000} /></label>
        <div className="row" style={{ justifyContent: 'flex-end' }}><button className="btn primary" disabled={!texto.trim() || busy === 'novo'}>{busy === 'novo' ? <span className="spin" /> : tr("Relatar")}</button></div>
      </form>
    </div>}
  </Section>
}

// ------------------------------------------------------------------ o que o robô decidiu
function Decisoes() {
  const [lead, setLead] = useState('')
  const [acao, setAcao] = useState('')
  const [q, setQ] = useState('')
  useEffect(() => { const t = setTimeout(() => setQ(lead.trim()), 300); return () => clearTimeout(t) }, [lead])
  const d = useGet<Auditoria>(`/sdr/auditoria?n=50${q ? `&lead=${encodeURIComponent(q)}` : ''}${acao ? `&acao=${encodeURIComponent(acao)}` : ''}`, 60000)
  return <Section title={tr("O que o robô decidiu")} count={d.data?.itens.length}
    right={<div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
      <input value={lead} onChange={e => setLead(e.target.value)} placeholder={tr("lead (id)")} aria-label={tr("Filtrar por lead")} style={{ width: 120 }} />
      <select value={acao} onChange={e => setAcao(e.target.value)} aria-label={tr("Filtrar por ação")}><option value="">{tr("todas as ações")}</option>{(d.data?.acoes || []).map(a => <option key={a} value={a}>{a}</option>)}</select>
    </div>}>
    {d.error ? <ErrorState error={d.error} retry={d.reload} /> : !d.data ? <Loading rows={4} /> : d.data.motivo ? <Empty title={tr("Ponte sem auditoria")}>{tr("O banco da ponte de vendas ainda não existe neste servidor.")}</Empty>
      : !d.data.itens.length ? <Empty title={tr("Nenhuma decisão")}>{tr("Nada registrado com esse filtro.")}</Empty>
        : <div className="tbl-wrap"><table className="tbl sdr-tbl"><thead><tr><th>{tr("Hora (Orlando)")}</th><th>{tr("Lead")}</th><th>{tr("Ação")}</th><th>{tr("Motivo")}</th><th>{tr("O que fez ou faria")}</th><th>{tr("Nível")}</th></tr></thead>
          <tbody>{d.data.itens.map(x => <tr key={x.id}><td className="mono small">{horaOrlando(x.quando)}</td><td className="mono">{x.lead_id ?? '—'}</td><td>{x.acao || '—'}</td><td className="small">{x.motivo || '—'}</td><td className="small">{x.fez || '—'}</td><td className="small">{x.nivel || '—'}</td></tr>)}</tbody></table></div>}
  </Section>
}

// ------------------------------------------------------------------ página
export function Sdr() {
  const { can } = useAuth()
  const p = useGet<Painel>('/sdr/painel', 60000)
  const [tick, setTick] = useState(0)
  useEffect(() => { if (tick) p.reload() }, [tick]) // eslint-disable-line react-hooks/exhaustive-deps
  const reiniciando = !!p.data?.reiniciando
  useEffect(() => { if (!reiniciando) return; const t = setInterval(() => setTick(x => x + 1), 15000); return () => clearInterval(t) }, [reiniciando])
  const d = p.data
  return <>
    <PageHeader title={tr("Robô SDR")} help={tr("O robô de vendas no Kommo: ligue e desligue, diga o que ele deve fazer, relate o que saiu errado e acompanhe o que ele decidiu.")}>
      {d && <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
        <Chip tone={d.nivel === 'atender' ? 'ok' : d.nivel === 'organizar' ? 'info' : 'neutral'} dot>{tr("nível: {0}", NIVEL_NOME[d.nivel])}</Chip>
        <Chip tone={d.ponte_no_ar ? 'ok' : 'crit'}>{d.ponte_no_ar ? tr("ponte no ar") : tr("ponte fora do ar")}</Chip>
        {d.reiniciando && <Chip tone="run">{tr("aplicando…")}</Chip>}
        {d.decisoes_24h !== null && <Chip tone="neutral">{tr("{0} decisão(ões) nas últimas 24 h", d.decisoes_24h)}</Chip>}
        {d.ultima_decisao && <Chip tone="neutral" title={ago(d.ultima_decisao)}>{tr("última decisão {0}", horaOrlando(d.ultima_decisao))}</Chip>}
        {!!d.conversas_pausadas && <Chip tone="warn">{tr("{0} conversa(s) com a IA pausada", d.conversas_pausadas)}</Chip>}
      </div>}
    </PageHeader>
    {p.error ? <ErrorState error={p.error} retry={p.reload} /> : !d ? <Loading rows={4} /> : <div className="stack">
      <p className="small muted" style={{ margin: 0 }}>{tr("Horário de atendimento humano: {0}", d.horario_humano.texto)}</p>
      <LigarDesligar p={d} onMudou={() => setTick(x => x + 1)} />
      {can('OPERATOR') && <TesteCard />}
      <PausasCard pode={can('OPERATOR')} onMudou={() => setTick(x => x + 1)} />
      <Instrucoes pode={d.pode_instruir || can('MANAGER')} onMudou={() => setTick(x => x + 1)} />
      <RelatosCard podeResolver={can('MANAGER')} onMudou={() => setTick(x => x + 1)} />
      <Decisoes />
    </div>}
  </>
}
