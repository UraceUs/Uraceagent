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
import { TextoComVoz } from '../components/Voz'

interface Canal {
  id: number; name: string; kind: string; entity_type: string | null; entity_id: number | null
  topic: string | null; membros: number; ultima: string | null; ultimo_autor: string | null
  ultima_em: string | null; nao_lidas: number; bridge: string | null
}
interface Msg {
  id: number; channel_id: number; user_id: number | null; author: string; text: string
  at: string; origem: string; usuario: string | null
}
interface Membro { id: number; name: string; email: string; role: string }
interface Conversa { canal: Canal; mensagens: Msg[]; membros: Membro[]; participo: boolean }

const TIPO_PT: Record<string, string> = {
  EQUIPE: 'Equipe', CORRIDA: 'Corrida', SERVICO: 'Serviço', CLIENTE: 'Cliente', DIRETO: 'Direto',
}
const ORIGEM_PT: Record<string, string> = { gchat: 'Google Chat', whatsapp: 'WhatsApp' }

export function Equipe() {
  const [params, setParams] = useSearchParams()
  const aberto = Number(params.get('c') || 0) || null
  const { data, error, loading, reload } = useGet<{ canais: Canal[]; total_nao_lidas: number }>('/equipe/canais', 15000)
  const { can } = useAuth()
  const toast = useToast()
  const [busca, setBusca] = useState('')
  const [criando, setCriando] = useState(false)
  const [novo, setNovo] = useState({ name: '', kind: 'EQUIPE' })

  const canais = useMemo(() => (data?.canais || []).filter(c =>
    !busca || `${c.name} ${c.topic || ''} ${c.ultima || ''}`.toLowerCase().includes(busca.toLowerCase())), [data, busca])

  async function criar() {
    if (!novo.name.trim()) return
    try {
      const r = await api.post<{ id: number }>('/equipe/canais', { name: novo.name, kind: novo.kind })
      setNovo({ name: '', kind: 'EQUIPE' }); setCriando(false); reload(); setParams({ c: String(r.id) })
    } catch (e) { toast((e as ApiError).message, 'crit') }
  }

  return <>
    <PageHeader title="Equipe" help={<>A conversa do dia a dia dentro do painel: ligada à corrida, ao serviço ou ao cliente, com quem precisa ver. O que for do cliente continua no Chat do Kommo.</>}>
      {can('OPERATOR') && <button className="btn primary" onClick={() => setCriando(v => !v)}>Nova conversa</button>}
    </PageHeader>

    {criando && <Section title="Nova conversa">
      <div className="row wrap" style={{ gap: 8 }}>
        <input className="input" style={{ flex: '1 1 240px' }} autoFocus placeholder="Nome — ex.: Corrida Ocala, Box 2, Serviço do Pedro"
          value={novo.name} onChange={e => setNovo({ ...novo, name: e.target.value })}
          onKeyDown={e => { if (e.key === 'Enter') criar() }} />
        <select className="input" style={{ width: 150 }} value={novo.kind} onChange={e => setNovo({ ...novo, kind: e.target.value })}>
          {Object.entries(TIPO_PT).filter(([k]) => k !== 'DIRETO').map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <button className="btn primary" onClick={criar} disabled={!novo.name.trim()}>Criar</button>
        <button className="btn" onClick={() => setCriando(false)}>Cancelar</button>
      </div>
    </Section>}

    <div className="grid" style={{ gridTemplateColumns: aberto ? 'minmax(0,340px) minmax(0,1fr)' : 'minmax(0,1fr)' }}>
      <div className={aberto ? 'so-desktop' : ''}>
        <Section title="Conversas" count={canais.length} tight>
          <div style={{ padding: '8px 10px' }}>
            <input className="input" placeholder="Buscar conversa…" value={busca} onChange={e => setBusca(e.target.value)} />
          </div>
          {error && !data ? <ErrorState error={error} retry={reload} /> : loading && !data ? <Loading /> :
            canais.length === 0 ? <Empty title="Nenhuma conversa ainda">
              {can('OPERATOR') ? 'Crie a primeira em "Nova conversa" — vale ligar à corrida ou ao serviço.' : 'Quando alguém abrir uma conversa com você, ela aparece aqui.'}
            </Empty> :
              <div className="stack" style={{ gap: 0 }}>
                {canais.map(c => <button key={c.id} className={`tcard${c.id === aberto ? ' on' : ''}`} onClick={() => setParams({ c: String(c.id) })}>
                  <div className="row" style={{ justifyContent: 'space-between', gap: 8 }}>
                    <div className="from">{!!c.nao_lidas && <span style={{ color: 'var(--warn)' }}>● </span>}{c.name}</div>
                    <span className="small muted nowrap">{c.ultima_em ? ago(c.ultima_em) : ''}</span>
                  </div>
                  <div className="row wrap" style={{ gap: 6 }}>
                    <Chip tone="neutral">{TIPO_PT[c.kind] || c.kind}</Chip>
                    {!!c.nao_lidas && <Chip tone="warn">{c.nao_lidas > 99 ? '99+' : c.nao_lidas} nova(s)</Chip>}
                    <span className="small muted">{c.membros} pessoa(s)</span>
                  </div>
                  <div className="subj">{c.ultima ? <>{c.ultimo_autor ? <b>{c.ultimo_autor.split(' ')[0]}: </b> : null}{c.ultima}</> : <span className="muted">sem mensagem ainda</span>}</div>
                </button>)}
              </div>}
        </Section>
      </div>
      {aberto && <Conversa id={aberto} onVoltar={() => setParams({})} onMudou={reload} />}
    </div>
  </>
}

function Conversa({ id, onVoltar, onMudou }: { id: number; onVoltar: () => void; onMudou: () => void }) {
  const { user, can } = useAuth()
  const toast = useToast()
  const [conversa, setConversa] = useState<Conversa | null>(null)
  const [erro, setErro] = useState<ApiError | null>(null)
  const [texto, setTexto] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [falhou, setFalhou] = useState<string | null>(null)
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
          if (!prev || ultimo.current === 0) return d
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
        <button className="btn sm so-mobile" onClick={onVoltar}><Icon name="left" size={14} /> Conversas</button>
        <b>{c.name}</b>
        <Chip tone="neutral">{TIPO_PT[c.kind] || c.kind}</Chip>
        <span className="small muted">{conversa.membros.map(m => m.name.split(' ')[0]).join(', ')}</span>
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
