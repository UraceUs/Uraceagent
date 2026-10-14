/* Google Calendar de cada vendedor (#220). Dono, 14/10: "conectar ao Google Calendar e aí coloca um
 * login com o Google, que aí ele consegue logar com a conta dele do Google".
 *
 * O botão leva a pessoa à tela de login do Google e volta conectada. Sem o cliente OAuth na VPS,
 * o botão aparece desligado e o texto diz o que falta (quem configura é o gerente). */
import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import { fmtDateTime } from './fmt'
import { Banner, Spinner } from './ui'
import { Icon } from './Icon'
import { usePerguntar } from './Perguntar'
import { useToast } from './Toast'
import { tr } from '../i18n'

export interface StatusGoogle {
  configurado: boolean; motivo: string | null; conectado: boolean; expirado: boolean
  email: string | null; conectado_em: string | null; sincronizado_em: string | null; erro: string | null
}
export interface EventoGoogle { id: string; titulo: string | null; inicio: string; fim: string; dia_todo: boolean; ocupado: boolean }

const MOTIVO: Record<string, string> = {
  estado: tr("A volta do Google não foi aceita (link vencido, já usado ou aberto em outro navegador). Tente de novo."),
  negado: tr("Você cancelou no Google: nada foi conectado."),
  escopo: tr("O Google não deu a permissão de agenda. Conecte de novo e marque o acesso ao Google Calendar."),
  google: tr("O Google não completou a conexão. Tente de novo em instantes."),
}

/** Lê o `?google=` que a volta do Google deixa no endereço, avisa e limpa o endereço. */
export function useVoltaDoGoogle(onVolta: () => void) {
  const toast = useToast()
  const feito = useRef(false)
  useEffect(() => {
    if (feito.current) return
    const q = new URLSearchParams(window.location.search)
    const r = q.get('google')
    if (!r) return
    feito.current = true
    if (r === 'ok') toast(tr("Google Calendar conectado."), 'ok')
    else toast(MOTIVO[q.get('motivo') || 'google'] || MOTIVO.google, 'crit')
    window.history.replaceState(null, '', window.location.pathname)
    onVolta()
  }, [toast, onVolta])
}

export function ConexaoGoogle({ status, onMudou }: { status: StatusGoogle | null; onMudou: () => void }) {
  const toast = useToast()
  const perguntar = usePerguntar()
  const [busy, setBusy] = useState<string | null>(null)
  if (!status) return null

  async function conectar() {
    setBusy('con')
    try {
      const r = await api.post<{ url: string }>('/google/connect')
      window.location.assign(r.url)                         // a tela de login do Google
    } catch (e) { toast((e as ApiError).message, 'crit'); setBusy(null) }
  }
  async function sincronizar() {
    setBusy('sync')
    try {
      const r = await api.post<{ ok: boolean; erro: string | null }>('/google/sync')
      toast(r.ok ? tr("Retornos acertados no seu Google Calendar.") : (r.erro || tr("Falhou")), r.ok ? 'ok' : 'crit')
      onMudou()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  async function desconectar() {
    if (!await perguntar({ titulo: tr("Desconectar o Google Calendar?"), ok: tr("Desconectar"), perigo: true,
      texto: tr("O painel deixa de mandar os seus retornos e de mostrar os seus compromissos. Os eventos que já estão no seu Google ficam lá.") })) return
    setBusy('des')
    try { await api.post('/google/disconnect'); toast(tr("Google Calendar desconectado."), 'ok'); onMudou() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }

  const botaoConectar = <button className="btn primary" disabled={!status.configurado || !!busy} onClick={conectar}
    title={status.configurado ? undefined : (status.motivo || '')}>
    {busy === 'con' ? <Spinner /> : <><Icon name="cal" size={16} /> {status.expirado ? tr("Conectar de novo") : tr("Conectar ao Google Calendar")}</>}
  </button>

  return <section className="card" aria-labelledby="google-cal-h">
    <div className="card-h"><h2 className="h2" id="google-cal-h">{tr("Google Calendar")}</h2></div>
    <div className="card-b stack">
      {status.conectado ? <>
        <div className="small"><b>{tr("Conectado como {0}", status.email || tr("sua conta Google"))}</b></div>
        <div className="small muted">{tr("Os retornos que você marcar vão para o seu Google Calendar e os seus compromissos do Google aparecem aqui, só para leitura.")}
          {status.sincronizado_em ? ` ${tr("Última sincronia: {0}.", fmtDateTime(status.sincronizado_em))}` : ''}</div>
        {status.erro && <Banner tone="warn">{status.erro}</Banner>}
        <div className="row wrap" style={{ gap: 8 }}>
          <button className="btn" disabled={!!busy} onClick={sincronizar}>{busy === 'sync' ? <Spinner /> : tr("Sincronizar agora")}</button>
          <button className="btn ghost" disabled={!!busy} onClick={desconectar}>{busy === 'des' ? <Spinner /> : tr("Desconectar")}</button>
        </div>
      </> : <>
        <div className="small muted">{tr("Entre com a sua conta Google (qualquer conta) para os seus retornos virarem eventos no seu calendário e para ver aqui os seus compromissos.")}</div>
        {status.expirado && <Banner tone="warn">{status.erro || tr("A conexão com o Google expirou: conecte de novo.")}</Banner>}
        {!status.configurado && <Banner tone="info">{status.motivo || tr("O gerente ainda não configurou o acesso ao Google.")}</Banner>}
        <div className="row wrap">{botaoConectar}</div>
      </>}
    </div>
  </section>
}

/** O estado da conexão, com a volta do Google tratada. */
export function useStatusGoogle() {
  const s = useGet<StatusGoogle>('/google/status')
  useVoltaDoGoogle(s.reload)
  return s
}
