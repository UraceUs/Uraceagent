/* Balcão no celular, com uma mão (#180).
 *
 * Dono, 09/10: "escaneou a peça, identificou ali, isso o sistema faz sozinho … já abre um
 * pop-up para selecionar os pilotos que estão no dia … quando ele clicar no cliente, já
 * registra aquela peça" — e "ele não vai ter tempo para digitar, não vai ter tempo para ficar
 * revisando nada".
 *
 * Metade de cima: a câmera, sempre lendo. Metade de baixo: a peça lida e os pilotos do dia em
 * botões grandes, ao alcance do polegar. Um toque registra (pendente: o gerente confirma na
 * Revisão do balcão) e a câmera volta a ler sozinha. Em balcao.urace.us esta é a única tela. */
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, qs } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { useLeitor, vibrar } from '../components/Leitor'
import { LOCALE, tr } from '../i18n'

interface Piloto { chave: string; client_id: number | null; pilot_id: number | null; nome: string; origens: string[]; pecas: number }
interface Pendente { id: number; code: string; peca: string | null; pilot_name: string | null; client_id: number | null }
interface Dia { data: string; hoje: string; pilotos: Piloto[]; minhas: Pendente[] }
interface Item { id: number; name: string }
type Lido = { codigo: string; carregando: true } | { codigo: string; carregando: false; item: Item | null }

const ESPERA_MESMO_CODIGO = 3500        // ms: a mesma peça ainda na frente da câmera não abre de novo
const ORIGEM: Record<string, string> = { 'sessão': tr("sessão"), corrida: tr("corrida"), 'serviço': tr("serviço") }

function somaDias(iso: string, n: number) {
  const d = new Date(iso + 'T12:00:00')
  d.setDate(d.getDate() + n)
  return d.toISOString().slice(0, 10)
}
const rotuloDia = (iso: string) => new Date(iso + 'T12:00:00').toLocaleDateString(LOCALE(), { weekday: 'short', day: '2-digit', month: '2-digit' })

export function BalcaoRapido() {
  const { user, logout } = useAuth()
  const video = useRef<HTMLVideoElement>(null)
  const [dia, setDia] = useState<Dia | null>(null)
  const [data, setData] = useState<string | null>(null)
  const [lido, setLido] = useState<Lido | null>(null)
  const [feito, setFeito] = useState<{ id: number; texto: string } | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [indo, setIndo] = useState(false)
  const [digitar, setDigitar] = useState(false)
  const [texto, setTexto] = useState('')
  const ultimo = useRef<{ codigo: string; em: number }>({ codigo: '', em: 0 })

  const carregar = useCallback((d?: string | null) => {
    api.get<Dia>(`/balcao/rapido${qs({ data: d || undefined })}`).then(r => { setDia(r); setData(r.data) })
      .catch(e => setErro((e as ApiError).message))
  }, [])
  useEffect(() => { carregar(data) }, [carregar, data])
  useEffect(() => {                                   // o aviso de "registrado" some sozinho
    if (!feito) return
    const t = setTimeout(() => setFeito(null), 6000)
    return () => clearTimeout(t)
  }, [feito])

  const ler = useCallback(async (bruto: string) => {
    const codigo = bruto.trim()
    if (!codigo) return
    const agora = Date.now()
    if (codigo === ultimo.current.codigo && agora - ultimo.current.em < ESPERA_MESMO_CODIGO) return
    ultimo.current = { codigo, em: agora }
    vibrar(40)
    setErro(null); setFeito(null); setLido({ codigo, carregando: true })
    try {
      const r = await api.get<{ tipo: string; codigo?: string; item?: Item }>(`/balcao/ler${qs({ codigo })}`)
      if (r.tipo === 'cliente') { setLido(null); vibrar(250); setErro(tr("Este é o QR de um cliente. Aqui o primeiro passo é a peça.")); return }
      setLido({ codigo: r.codigo || codigo, carregando: false, item: r.tipo === 'peca' && r.item ? r.item : null })
    } catch (e) { setLido(null); vibrar(250); setErro((e as ApiError).message) }
  }, [])

  const ativo = !lido && !indo && !digitar
  const { erro: erroCamera, pronto } = useLeitor(video, ativo, ler)

  async function registrar(p: Piloto | null) {
    if (!lido || lido.carregando || indo) return
    setIndo(true)
    try {
      const r = await api.post<Pendente>('/balcao/rapido', { codigo: lido.codigo, data, client_id: p?.client_id ?? null, pilot_id: p?.pilot_id ?? null })
      vibrar([30, 40, 30])
      const peca = lido.item?.name || tr("Código {0}", lido.codigo)
      setFeito({ id: r.id, texto: p ? `${peca} → ${p.nome}` : tr("{0} → decidir depois", peca) })
      ultimo.current = { codigo: lido.codigo, em: Date.now() }
      setLido(null)
      carregar(data)
    } catch (e) { vibrar(250); setErro((e as ApiError).message) } finally { setIndo(false) }
  }

  function cancelar() {
    if (lido) ultimo.current = { codigo: lido.codigo, em: Date.now() }
    setLido(null)
  }

  async function desfazer() {
    if (!feito) return
    try { await api.post(`/balcao/rapido/${feito.id}/desfazer`); setFeito(null); vibrar(40); carregar(data) }
    catch (e) { setErro((e as ApiError).message) }
  }

  function enviarDigitado(e: FormEvent) {
    e.preventDefault()
    const t = texto
    setTexto(''); setDigitar(false)
    ultimo.current = { codigo: '', em: 0 }
    ler(t)
  }

  const hoje = dia?.hoje
  const dias = hoje ? [[somaDias(hoje, -1), tr("Ontem")], [hoje, tr("Hoje")], [somaDias(hoje, 1), tr("Amanhã")]] : []
  const soBalcao = !!user?.so_balcao
  return <div className="br">
    <h1 className="sr-only">{tr("Balcão")}</h1>
    <section className="br-camera" aria-label={tr("Câmera")}>
      <video ref={video} muted playsInline aria-label={tr("Imagem da câmera")} />
      <div className="br-topo">
        <div className="br-dias" role="radiogroup" aria-label={tr("Dia das peças")}>
          {dias.map(([d, r]) => <button key={d} role="radio" aria-checked={d === data} onClick={() => setData(d)}>{r}</button>)}
        </div>
        {soBalcao ? <button className="br-sair" onClick={() => logout()}>{tr("Sair")}</button>
          : <Link className="br-sair" to="/balcao">{tr("Painel")}</Link>}
      </div>
      {!erroCamera && <div className={`br-mira${lido ? ' pausa' : ''}`} aria-hidden="true" />}
      <p className="br-status" role="status">
        {erroCamera || (lido ? tr("Lido. Escolha o piloto embaixo.") : pronto ? tr("Aponte para o código da peça") : tr("Abrindo a câmera…"))}
      </p>
    </section>

    <section className="br-painel" aria-label={tr("Peça e pilotos")}>
      {erro && <p className="br-erro" role="alert">{erro}</p>}
      {feito && <div className="br-feito" role="status">
        <span>✓ {feito.texto}</span>
        <button className="btn" onClick={desfazer}>{tr("Desfazer")}</button>
      </div>}

      {lido ? <>
        <div className="br-peca">
          {lido.carregando ? <span className="spin" /> : lido.item
            ? <><h2>{lido.item.name}</h2><span className="mono small muted">{lido.codigo}</span></>
            : <><h2>{tr("Código novo")}</h2><span className="small muted">{tr("O gerente diz que peça é na revisão.")} <span className="mono">{lido.codigo}</span></span></>}
        </div>
        <h3 className="br-quem">{tr("De quem é? {0}", dia ? rotuloDia(dia.data) : '')}</h3>
        <div className="br-pilotos">
          {(dia?.pilotos || []).map(p => <button key={p.chave} className="br-piloto" disabled={indo || lido.carregando} onClick={() => registrar(p)}>
            <b>{p.nome}</b><small>{p.origens.map(o => ORIGEM[o] || o).join(' · ')}{p.pecas ? ` · ${tr("{0} peça(s)", p.pecas)}` : ''}</small>
          </button>)}
          {dia && !dia.pilotos.length && <p className="small muted">{tr("Ninguém marcado neste dia.")}</p>}
        </div>
        <div className="br-acoes">
          <button className="btn" disabled={indo || lido.carregando} onClick={() => registrar(null)}>{tr("Decidir depois")}</button>
          <button className="btn ghost" disabled={indo} onClick={cancelar}>{tr("Ler outra")}</button>
        </div>
      </> : <>
        <div className="br-dica">
          <h2>{tr("Leia a peça")}</h2>
          <p className="small muted">{dia ? tr("{0} piloto(s) em {1}. Depois de ler, um toque no piloto registra.", dia.pilotos.length, rotuloDia(dia.data)) : ''}</p>
        </div>
        {!!dia?.minhas.length && <ul className="br-minhas" aria-label={tr("Suas últimas leituras")}>
          {dia.minhas.map(m => <li key={m.id}><span className="truncate">{m.peca || m.code}</span><span className="muted">{m.pilot_name || tr("decidir depois")}</span></li>)}
        </ul>}
        {digitar ? <form className="br-digitar" onSubmit={enviarDigitado}>
          <input autoFocus value={texto} onChange={e => setTexto(e.target.value)} aria-label={tr("Código da peça")} autoComplete="off"
            autoCapitalize="off" spellCheck={false} enterKeyHint="go" />
          <button className="btn primary">{tr("Ler")}</button>
          <button type="button" className="btn ghost" onClick={() => setDigitar(false)}>{tr("Fechar")}</button>
        </form> : <button className="btn ghost br-teclado" onClick={() => setDigitar(true)}>{tr("Código apagado? Digitar")}</button>}
      </>}
    </section>
  </div>
}
