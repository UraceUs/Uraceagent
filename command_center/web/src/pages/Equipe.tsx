/* Chat interno da equipe (dono, 21/09).
 *
 * Existe para unificar o que hoje se fala solto. O WhatsApp ficou de fora por decisão do
 * dono no mesmo dia; sobrou o painel e, depois, a ponte do Google Chat. Então esta tela
 * tem uma obrigação a mais que as outras: **ser boa no celular de quem está no box**, com
 * a mão suja e sem paciência. Lista de um lado, conversa do outro no computador; no
 * celular, uma coisa de cada vez.
 *
 * A conversa se atualiza pedindo só o que é novo (`?desde=<último id>`): baixar tudo a
 * cada cinco segundos aparece no celular do mecânico como lentidão e bateria. */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, PageHeader, Section, Spinner } from '../components/ui'
import { Icon } from '../components/Icon'
import { ago, fmtTime } from '../components/fmt'
import { useToast } from '../components/Toast'
import { Avisos } from '../components/Avisos'
import { TextoComVoz } from '../components/Voz'

interface Canal {
  id: number; name: string; kind: string; entity_type: string | null; entity_id: number | null
  topic: string | null; membros: number; ultima: string | null; ultimo_autor: string | null
  ultima_em: string | null; nao_lidas: number; bridge: string | null
  icon: string | null; image_path: string | null; dm_key: string | null; mudo: boolean
}
interface Pessoa { id: number; name: string; email: string; role: string; canal_id: number | null; nao_lidas: number }
interface Msg {
  id: number; channel_id: number; user_id: number | null; author: string; text: string
  at: string; origem: string; usuario: string | null
}
interface Membro { id: number; name: string; email: string; role: string }
interface Conversa { canal: Canal; mensagens: Msg[]; membros: Membro[]; participo: boolean; mudo: boolean }

/** A cara da conversa: foto do grupo, emoji, ou as iniciais. Pessoa não tem foto de
 *  grupo — ela É a foto, então vão as iniciais dela. */
function Cara({ c, size = 36 }: { c: { id: number; name: string; icon?: string | null; image_path?: string | null }; size?: number }) {
  const [erro, setErro] = useState(false)
  const estilo = { width: size, height: size, fontSize: Math.round(size * .42) }
  if (c.image_path && !erro) return <img className="foto" src={`/ops/api/equipe/canais/${c.id}/imagem`} alt=""
    width={size} height={size} style={{ width: size, height: size }} onError={() => setErro(true)} />
  if (c.icon) return <span className="foto ini" style={estilo}>{c.icon}</span>
  return <span className="foto ini" style={{ ...estilo, fontSize: Math.round(size * .36) }}>
    {(c.name || '?').split(/\s+/).slice(0, 2).map(p => p[0]?.toUpperCase() || '').join('')}</span>
}

const TIPO_PT: Record<string, string> = {
  EQUIPE: 'Equipe', CORRIDA: 'Corrida', SERVICO: 'Serviço', CLIENTE: 'Cliente', DIRETO: 'Direto',
}
const ORIGEM_PT: Record<string, string> = { gchat: 'Google Chat', whatsapp: 'WhatsApp' }
const ROLE_PT: Record<string, string> = { ADMIN: 'Administrador', MANAGER: 'Gerente', OPERATOR: 'Operador', VIEWER: 'Leitura' }

export function Equipe() {
  const [params, setParams] = useSearchParams()
  const aberto = Number(params.get('c') || 0) || null
  const { data, error, loading, reload } = useGet<{ canais: Canal[]; total_nao_lidas: number }>('/equipe/canais', 15000)
  const pessoas = useGet<Pessoa[]>('/equipe/pessoas', 60000)
  const { can } = useAuth()
  const toast = useToast()
  const [busca, setBusca] = useState('')
  const [aba, setAba] = useState<'conversas' | 'pessoas'>('conversas')
  const [novoGrupo, setNovoGrupo] = useState(false)

  const canais = useMemo(() => (data?.canais || []).filter(c =>
    !busca || `${c.name} ${c.topic || ''} ${c.ultima || ''}`.toLowerCase().includes(busca.toLowerCase())), [data, busca])
  const gente = useMemo(() => (pessoas.data || []).filter(p =>
    !busca || `${p.name} ${p.email}`.toLowerCase().includes(busca.toLowerCase())), [pessoas.data, busca])

  /** Falar com alguém em um clique: abre a conversa, criando na hora se for a primeira vez. */
  async function abrirDireto(p: Pessoa) {
    try {
      const id = p.canal_id ?? (await api.post<{ id: number }>(`/equipe/direto/${p.id}`)).id
      setParams({ c: String(id) }); reload(); pessoas.reload()
    } catch (e) { toast((e as ApiError).message, 'crit') }
  }

  return <>
    <PageHeader title="Equipe" help={<>Conversa com quem trabalha aqui: direto com uma pessoa ou em grupo. O que for de cliente continua no Chat do Kommo.</>}>
      {can('OPERATOR') && <button className="btn primary" onClick={() => setNovoGrupo(true)}>Novo grupo</button>}
    </PageHeader>

    <div className="card" style={{ padding: '10px 14px', marginBottom: 12 }}><Avisos /></div>

    {novoGrupo && <NovoGrupo pessoas={pessoas.data || []} onPronto={id => {
      setNovoGrupo(false); reload(); setParams({ c: String(id) })
    }} onCancelar={() => setNovoGrupo(false)} />}

    <div className="grid" style={{ gridTemplateColumns: aberto ? 'minmax(0,340px) minmax(0,1fr)' : 'minmax(0,1fr)' }}>
      <div className={aberto ? 'so-desktop' : ''}>
        <Section title="Chat da equipe" count={aba === 'conversas' ? canais.length : gente.length} tight>
          <div className="stack" style={{ padding: '8px 10px', gap: 8 }}>
            <div className="row" style={{ gap: 0 }}>
              <button className={`tab${aba === 'conversas' ? ' on' : ''}`} onClick={() => setAba('conversas')}>
                Conversas{data?.total_nao_lidas ? ` (${data.total_nao_lidas})` : ''}</button>
              <button className={`tab${aba === 'pessoas' ? ' on' : ''}`} onClick={() => setAba('pessoas')}>Pessoas</button>
            </div>
            <input className="input" placeholder={aba === 'conversas' ? 'Buscar conversa…' : 'Buscar pessoa…'}
              value={busca} onChange={e => setBusca(e.target.value)} />
          </div>

          {aba === 'pessoas' ? (
            pessoas.loading && !pessoas.data ? <Loading /> :
              gente.length === 0 ? <Empty>Ninguém mais cadastrado.</Empty> :
                <div className="stack" style={{ gap: 0 }}>
                  {gente.map(p => <button key={p.id} className={`tcard${p.canal_id === aberto ? ' on' : ''}`} onClick={() => abrirDireto(p)}>
                    <div className="row" style={{ gap: 10, alignItems: 'center' }}>
                      <Cara c={{ id: p.canal_id || 0, name: p.name }} size={34} />
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div className="from">{!!p.nao_lidas && <span style={{ color: 'var(--warn)' }}>● </span>}{p.name}</div>
                        <div className="small muted">{ROLE_PT[p.role] || p.role}{p.canal_id ? '' : ' · nunca conversaram'}</div>
                      </div>
                      {!!p.nao_lidas && <Chip tone="warn">{p.nao_lidas}</Chip>}
                    </div>
                  </button>)}
                </div>
          ) : (
            error && !data ? <ErrorState error={error} retry={reload} /> : loading && !data ? <Loading /> :
              canais.length === 0 ? <Empty title="Nenhuma conversa ainda">
                Abra uma em <b>Pessoas</b>, ou crie um grupo em <b>Novo grupo</b>.
              </Empty> :
                <div className="stack" style={{ gap: 0 }}>
                  {canais.map(c => <button key={c.id} className={`tcard${c.id === aberto ? ' on' : ''}`} onClick={() => setParams({ c: String(c.id) })}>
                    <div className="row" style={{ gap: 10, alignItems: 'flex-start' }}>
                      <Cara c={c} size={36} />
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div className="row" style={{ justifyContent: 'space-between', gap: 8 }}>
                          <div className="from">{!!c.nao_lidas && !c.mudo && <span style={{ color: 'var(--warn)' }}>● </span>}{c.name}</div>
                          <span className="small muted nowrap">{c.ultima_em ? ago(c.ultima_em) : ''}</span>
                        </div>
                        <div className="subj">{c.ultima ? <>{c.ultimo_autor && c.kind !== 'DIRETO' ? <b>{c.ultimo_autor.split(' ')[0]}: </b> : null}{c.ultima}</> : <span className="muted">sem mensagem ainda</span>}</div>
                        <div className="row wrap" style={{ gap: 6 }}>
                          {c.kind !== 'DIRETO' && <Chip tone="neutral">{TIPO_PT[c.kind] || c.kind}{c.kind !== 'DIRETO' ? ` · ${c.membros}` : ''}</Chip>}
                          {!!c.nao_lidas && <Chip tone={c.mudo ? 'neutral' : 'warn'}>{c.nao_lidas > 99 ? '99+' : c.nao_lidas} nova(s)</Chip>}
                          {c.mudo && <Chip tone="neutral" title="Silenciada: não avisa no celular">silenciada</Chip>}
                        </div>
                      </div>
                    </div>
                  </button>)}
                </div>
          )}
        </Section>
      </div>
      {aberto && <Conversa id={aberto} onVoltar={() => setParams({})} onMudou={() => { reload(); pessoas.reload() }} />}
    </div>
  </>
}

/** Novo grupo: nome, ícone (emoji) ou foto, e quem participa. */
function NovoGrupo({ pessoas, onPronto, onCancelar }: { pessoas: Pessoa[]; onPronto: (id: number) => void; onCancelar: () => void }) {
  const toast = useToast()
  const [f, setF] = useState({ name: '', icone: '', kind: 'EQUIPE' })
  const [membros, setMembros] = useState<number[]>([])
  const [imagem, setImagem] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const EMOJIS = ['💼', '🔧', '🏁', '📦', '💰', '📣', '🛠️', '🚚', '⭐']

  async function criar() {
    if (!f.name.trim()) return
    setBusy(true)
    try {
      const r = await api.post<{ id: number }>('/equipe/canais', {
        name: f.name, kind: f.kind, icone: f.icone || null, membros,
      })
      if (imagem) {
        const corpo = new FormData(); corpo.append('arquivo', imagem)
        await fetch(`/ops/api/equipe/canais/${r.id}/imagem`, {
          method: 'POST', credentials: 'same-origin', body: corpo,
          headers: { 'X-CSRF': document.cookie.match(/(?:^|;\s*)cc_csrf=([^;]+)/)?.[1] || '' },
        })
      }
      toast('Grupo criado.', 'ok'); onPronto(r.id)
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }

  return <Section title="Novo grupo">
    <div className="stack" style={{ gap: 12 }}>
      <div className="row wrap" style={{ gap: 8, alignItems: 'flex-end' }}>
        <div className="field" style={{ flex: '1 1 240px' }}><label>Nome do grupo</label>
          <input className="input" autoFocus placeholder="Comercial, Mecânicos, Corrida Ocala…"
            value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></div>
        <div className="field" style={{ width: 160 }}><label>Tipo</label>
          <select className="input" value={f.kind} onChange={e => setF({ ...f, kind: e.target.value })}>
            {Object.entries(TIPO_PT).filter(([k]) => k !== 'DIRETO').map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select></div>
      </div>

      <div className="field"><label>Ícone</label>
        <div className="row wrap" style={{ gap: 6, alignItems: 'center' }}>
          {EMOJIS.map(e => <button key={e} type="button" className={`btn sm${f.icone === e ? ' primary' : ''}`}
            onClick={() => { setF({ ...f, icone: f.icone === e ? '' : e }); setImagem(null) }}>{e}</button>)}
          <span className="small muted">ou</span>
          <label className="btn sm" style={{ cursor: 'pointer' }}>
            {imagem ? imagem.name.slice(0, 22) : 'Escolher foto'}
            <input type="file" accept="image/png,image/jpeg,image/webp" style={{ display: 'none' }}
              onChange={e => { const a = e.target.files?.[0] || null; setImagem(a); if (a) setF({ ...f, icone: '' }) }} />
          </label>
          {imagem && <button type="button" className="btn sm" onClick={() => setImagem(null)}>tirar</button>}
        </div>
      </div>

      <div className="field"><label>Participantes ({membros.length})</label>
        <div className="row wrap" style={{ gap: 6 }}>
          {pessoas.map(p => {
            const dentro = membros.includes(p.id)
            return <button key={p.id} type="button" className={`btn sm${dentro ? ' primary' : ''}`}
              onClick={() => setMembros(m => dentro ? m.filter(x => x !== p.id) : [...m, p.id])}>
              {dentro ? '✓ ' : ''}{p.name}</button>
          })}
        </div>
        <span className="small muted">Você entra automaticamente. Dá para acrescentar gente depois.</span>
      </div>

      <div className="row">
        <button className="btn primary" disabled={busy || !f.name.trim()} onClick={criar}>{busy ? <Spinner /> : 'Criar grupo'}</button>
        <button className="btn" onClick={onCancelar}>Cancelar</button>
      </div>
    </div>
  </Section>
}

function Conversa({ id, onVoltar, onMudou }: { id: number; onVoltar: () => void; onMudou: () => void }) {
  const { user, can } = useAuth()
  const toast = useToast()
  const [conversa, setConversa] = useState<Conversa | null>(null)
  const [erro, setErro] = useState<ApiError | null>(null)
  const [texto, setTexto] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [busy, setBusyLocal] = useState<string | null>(null)
  const [falhou, setFalhou] = useState<string | null>(null)
  const [mudo, setMudo] = useState(false)
  const fim = useRef<HTMLDivElement | null>(null)
  const ultimo = useRef(0)
  const chaveRascunho = `cc.equipe.rascunho.${id}`

  // o rascunho sobrevive à sessão caída, como no chat do Kommo (lição de 21/09)
  useEffect(() => {
    try { setTexto(localStorage.getItem(`cc.equipe.rascunho.${id}`) || '') } catch { setTexto('') }
  }, [id])
  useEffect(() => {
    try { if (texto.trim()) localStorage.setItem(chaveRascunho, texto); else localStorage.removeItem(chaveRascunho) } catch { /* sem storage */ }
  }, [texto, chaveRascunho])

  useEffect(() => {
    let vivo = true
    ultimo.current = 0
    setConversa(null); setErro(null)
    async function puxar() {
      try {
        const d = await api.get<Conversa>(`/equipe/canais/${id}?desde=${ultimo.current}`)
        if (!vivo) return
        setErro(null)
        setConversa(prev => {
          if (!prev || ultimo.current === 0) { setMudo(!!d.mudo); return d }
          return { ...d, mensagens: [...prev.mensagens, ...d.mensagens] }   // só o que é novo veio
        })
        const novas = d.mensagens
        if (novas.length) {
          ultimo.current = novas[novas.length - 1].id
          api.post(`/equipe/canais/${id}/lido`, { ate: ultimo.current }).then(onMudou).catch(() => { /* marca de novo depois */ })
        }
      } catch (e) { if (vivo && ultimo.current === 0) setErro(e as ApiError) }
    }
    puxar()
    const t = setInterval(puxar, 5000)
    return () => { vivo = false; clearInterval(t) }
  }, [id, onMudou])

  useEffect(() => { fim.current?.scrollIntoView({ block: 'end' }) }, [conversa?.mensagens.length])

  async function silenciar() {
    setEnviando(false); setBusyLocal('mudo')
    try {
      const r = await api.post<{ mudo: boolean }>(`/equipe/canais/${id}/silenciar`, { mudo: !mudo })
      setMudo(r.mudo); onMudou()
      toast(r.mudo ? 'Silenciada: as mensagens continuam chegando, o celular não toca.' : 'Voltou a avisar.', 'ok')
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusyLocal(null) }
  }

  async function enviar() {
    const t = texto.trim()
    if (!t || enviando) return
    setEnviando(true); setFalhou(null)
    try {
      await api.post(`/equipe/canais/${id}/mensagens`, { text: t })
      setTexto(v => (v.trim() === t ? '' : v))
      const d = await api.get<Conversa>(`/equipe/canais/${id}?desde=${ultimo.current}`)
      setConversa(prev => prev ? { ...d, mensagens: [...prev.mensagens, ...d.mensagens] } : d)
      if (d.mensagens.length) ultimo.current = d.mensagens[d.mensagens.length - 1].id
      onMudou()
    } catch (e) {
      const err = e as ApiError
      setFalhou(err.unauthorized ? 'Sua sessão tinha caído: a mensagem NÃO foi enviada. Entre de novo — o texto continua aqui.'
        : err.offline ? 'Sem conexão: a mensagem NÃO foi enviada. O texto continua aqui.'
          : `A mensagem NÃO foi enviada: ${err.message}`)
      toast('A mensagem não foi enviada.', 'crit')
    } finally { setEnviando(false) }
  }

  if (erro) return <div className="card"><ErrorState error={erro} retry={() => setErro(null)} /></div>
  if (!conversa) return <div className="card"><Loading /></div>
  const c = conversa.canal
  return <div className="stack" style={{ gap: 10, minWidth: 0 }}>
    <div className="card page-h" style={{ padding: '10px 14px' }}>
      <div className="row wrap" style={{ gap: 8, alignItems: 'center' }}>
        <button className="btn sm so-mobile" onClick={onVoltar}><Icon name="left" size={14} /> Voltar</button>
        <Cara c={c} size={34} />
        <b>{c.name}</b>
        {c.kind !== 'DIRETO' && <Chip tone="neutral">{TIPO_PT[c.kind] || c.kind}</Chip>}
        <span className="small muted" style={{ flex: 1 }}>
          {c.kind === 'DIRETO' ? 'conversa direta' : conversa.membros.map(m => m.name.split(' ')[0]).join(', ')}</span>
        {/* silenciar é por pessoa: eu calo para mim, não para os outros */}
        <button className="btn sm" disabled={!!busy} onClick={silenciar}
          title={mudo ? 'Voltar a avisar no celular' : 'Parar de avisar no celular (as mensagens continuam chegando)'}>
          {busy === 'mudo' ? <Spinner /> : mudo ? '🔕 silenciada' : '🔔 avisando'}</button>
      </div>
      {c.topic && <div className="small ink2">{c.topic}</div>}
    </div>

    <div className="card chat" style={{ padding: 12, minHeight: 240, maxHeight: '58vh', overflowY: 'auto' }}>
      {conversa.mensagens.length === 0 ? <Empty>Sem mensagens. Escreva a primeira.</Empty> :
        conversa.mensagens.map(m => {
          const meu = m.user_id && m.user_id === user?.id
          return <div key={m.id} className={`msg ${meu ? 'me' : 'ai'}`}>
            <div className="meta">{m.author}{m.at && ` · ${fmtTime(m.at)}`}
              {m.origem !== 'painel' && <Chip tone="info" title={`Veio do ${ORIGEM_PT[m.origem] || m.origem}`}>{ORIGEM_PT[m.origem] || m.origem}</Chip>}
            </div>
            <div className="bub">{m.text}</div>
          </div>
        })}
      <div ref={fim} />
    </div>

    {can('OPERATOR') ? <div className="stack" style={{ gap: 8 }}>
      {falhou && <Banner tone="crit">{falhou} <button className="btn sm" style={{ marginLeft: 8 }} disabled={enviando || !texto.trim()} onClick={enviar}>Enviar de novo</button></Banner>}
      <div className="field">
        <TextoComVoz valor={texto} onChange={setTexto} linhas={2} placeholder="Escreva ou dite… Enter envia, Shift+Enter quebra a linha" onEnter={enviar} />
        <div className="row"><button className="btn primary sm" disabled={enviando || !texto.trim()} onClick={enviar}>{enviando ? <Spinner /> : 'Enviar'}</button></div>
      </div>
    </div> : <div className="small muted">Seu acesso é de leitura: você acompanha a conversa e não escreve nela.</div>}
  </div>
}
