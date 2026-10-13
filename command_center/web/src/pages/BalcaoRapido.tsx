/* Balcão no celular, com uma mão (#180).
 *
 * Dono, 09/10: "escaneou a peça, identificou ali, isso o sistema faz sozinho … já abre um
 * pop-up para selecionar os pilotos que estão no dia … quando ele clicar no cliente, já
 * registra aquela peça" — e "ele não vai ter tempo para digitar, não vai ter tempo para ficar
 * revisando nada".
 *
 * Metade de cima: a câmera, sempre lendo. Metade de baixo: a peça lida e os pilotos do dia em
 * botões grandes, ao alcance do polegar. Um toque registra (pendente: o gerente confirma na
 * Revisão do balcão) e a câmera volta a ler sozinha. Em parts.urace.us esta é a única tela. */
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, qs } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { useLeitor, vibrar } from '../components/Leitor'
import { LOCALE, tr } from '../i18n'

interface Piloto { chave: string; client_id: number | null; pilot_id: number | null; nome: string; origens: string[]; pecas: number }
/** #206: `lancada` foi direto para a OS do cliente; `pendente` ficou para o gerente (com o motivo). */
interface Pendente { id: number; tipo: 'lancada' | 'pendente'; code: string; peca: string | null; pilot_name: string | null
  client_id: number | null; motivo?: string | null }
/** A operação de um piloto: lê as peças dele, uma atrás da outra, e encerra. */
interface Alvo { client_id: number | null; pilot_id: number | null; nome: string }
interface Dia { data: string; hoje: string; pilotos: Piloto[]; minhas: Pendente[] }
interface Item { id: number; name: string }
interface Achado { client_id: number; nome: string; responsavel: string | null }
interface Lanc { origem: 'celular' | 'balcão'; id: number; at: string; por: string | null; peca: string | null; codigo: string | null; para: string | null; qtd: number; situacao: string; revisado_por: string | null; modo: string | null }
interface Auditoria { data: string; itens: Lanc[]; total: number; pessoas: string[] }
type Lido = { codigo: string; carregando: true } | { codigo: string; carregando: false; item: Item | null }

const ESPERA_MESMO_CODIGO = 3500        // ms: a mesma peça ainda na frente da câmera não abre de novo
const ORIGEM: Record<string, string> = { 'sessão': tr("sessão"), corrida: tr("corrida"), 'serviço': tr("serviço") }

function somaDias(iso: string, n: number) {
  const d = new Date(iso + 'T12:00:00')
  d.setDate(d.getDate() + n)
  return d.toISOString().slice(0, 10)
}
const rotuloDia = (iso: string) => new Date(iso + 'T12:00:00').toLocaleDateString(LOCALE(), { weekday: 'short', day: '2-digit', month: '2-digit' })
const diaLongo = (iso: string) => new Date(iso + 'T12:00:00').toLocaleDateString(LOCALE(), { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' })
const horaFl = (iso: string) => new Date(iso).toLocaleTimeString(LOCALE(), { hour: '2-digit', minute: '2-digit', timeZone: 'America/New_York' })
const SITUACAO: Record<string, string> = { pendente: tr("pendente"), confirmada: tr("confirmada"), descartada: tr("descartada"), 'lançada': tr("lançada"), desfeita: tr("desfeita") }

/** #189: o gerente e o acesso livre veem tudo o que foi lançado naquele dia, por quem. */
function AuditoriaDia({ data }: { data: string }) {
  const [a, setA] = useState<Auditoria | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [quem, setQuem] = useState('')
  useEffect(() => { setA(null); setErro(null); api.get<Auditoria>(`/balcao/rapido/auditoria${qs({ data })}`).then(setA).catch(e => setErro((e as ApiError).message)) }, [data])
  const itens = (a?.itens || []).filter(x => !quem || x.por === quem)
  return <section className="br-aud" aria-labelledby="br-aud-h">
    <h2 id="br-aud-h" className="h3">{tr("Auditoria · {0}", diaLongo(data))}</h2>
    {erro ? <p className="br-erro" role="alert">{erro}</p> : !a ? <span className="spin" /> : !a.total ? <p className="small muted">{tr("Nada lançado neste dia.")}</p> : <>
      {a.pessoas.length > 1 && <select value={quem} onChange={e => setQuem(e.target.value)} aria-label={tr("Quem lançou")}>
        <option value="">{tr("Todos ({0})", a.total)}</option>{a.pessoas.map(p => <option key={p} value={p}>{p}</option>)}</select>}
      <ul className="br-aud-l">{itens.map(x => <li key={x.origem + x.id}>
        <span className="mono small">{horaFl(x.at)}</span>
        <span className="grow"><b>{x.peca || tr("Código {0}", x.codigo || '')}</b>{x.qtd !== 1 ? ` ×${x.qtd}` : ''} → {x.para || tr("decidir depois")}
          <span className="small muted"> · {x.por || '—'} · {x.origem === 'celular' ? tr("celular") : tr("balcão")}{x.revisado_por ? ` · ${x.revisado_por}` : ''}</span></span>
        <span className={`br-sit ${x.situacao}`}>{SITUACAO[x.situacao] || x.situacao}</span>
      </li>)}</ul>
    </>}
  </section>
}

/** #189: o piloto não está no calendário do dia — busca pelo nome entre os clientes. */
function OutroCliente({ desativado, onEscolher }: { desativado: boolean; onEscolher: (c: Achado) => void }) {
  const [q, setQ] = useState('')
  const [lista, setLista] = useState<Achado[] | null>(null)
  useEffect(() => {
    const t = q.trim(); if (t.length < 2) { setLista(null); return }
    const h = setTimeout(() => { api.get<Achado[]>(`/balcao/rapido/clientes${qs({ q: t })}`).then(setLista).catch(() => setLista([])) }, 250)
    return () => clearTimeout(h)
  }, [q])
  return <div className="br-outro">
    <input value={q} onChange={e => setQ(e.target.value)} placeholder={tr("Outro cliente: digite o nome")} aria-label={tr("Buscar cliente pelo nome")} autoComplete="off" />
    {lista && (lista.length ? <div className="br-pilotos">{lista.map(c => <button key={c.client_id} className="br-piloto" disabled={desativado} onClick={() => onEscolher(c)}>
      <b>{c.nome}</b>{c.responsavel && <small>{tr("resp. {0}", c.responsavel)}</small>}</button>)}</div>
      : <p className="small muted">{tr("Nenhum cliente com esse nome.")}</p>)}
  </div>
}

export function BalcaoRapido() {
  const { user, logout, livre, can } = useAuth()
  const video = useRef<HTMLVideoElement>(null)
  const [dia, setDia] = useState<Dia | null>(null)
  const [data, setData] = useState<string | null>(null)
  const [lido, setLido] = useState<Lido | null>(null)
  const [feito, setFeito] = useState<{ id: number; tipo: Pendente['tipo']; texto: string; motivo?: string | null } | null>(null)
  // #206 (dono, 13/10): "escaneia ... fecha a operação, passa para o próximo cliente". Com um piloto
  // escolhido, cada peça lida já vai para ele, sem tocar de novo; "Encerrar" fecha e mostra o resumo.
  const [alvo, setAlvo] = useState<Alvo | null>(null)
  const alvoRef = useRef<Alvo | null>(null)
  const [sessao, setSessao] = useState<Pendente[]>([])
  const [resumo, setResumo] = useState<{ nome: string; itens: Pendente[] } | null>(null)
  const [local, setLocal] = useState(() => { try { return localStorage.getItem('balcao.local') || 'sede' } catch { return 'sede' } })
  const [erro, setErro] = useState<string | null>(null)
  const [indo, setIndo] = useState(false)
  const [digitar, setDigitar] = useState(false)
  const [texto, setTexto] = useState('')
  const ultimo = useRef<{ codigo: string; em: number }>({ codigo: '', em: 0 })
  const gerente = livre || can('MANAGER')
  const [auditar, setAuditar] = useState(false)

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

  useEffect(() => { alvoRef.current = alvo }, [alvo])

  const lancar = useCallback(async (codigo: string, item: Item | null, p: Alvo | Piloto | Achado | null) => {
    setIndo(true)
    try {
      const r = await api.post<Pendente>('/balcao/rapido', { codigo, data, local, client_id: p?.client_id ?? null,
        pilot_id: p && 'pilot_id' in p ? p.pilot_id : null })
      vibrar(r.tipo === 'lancada' ? [30, 40, 30] : [80, 60, 80])
      const peca = r.peca || item?.name || tr("Código {0}", codigo)
      const quem = p ? p.nome : tr("decidir depois")
      setFeito({ id: r.id, tipo: r.tipo, motivo: r.motivo, texto: `${peca} → ${quem}` })
      if (p) {
        const novo: Alvo = { client_id: p.client_id, pilot_id: 'pilot_id' in p ? p.pilot_id : null, nome: p.nome }
        if (!alvoRef.current) { setAlvo(novo); setSessao([]) }
        setSessao(s => [...s, { ...r, peca }])
      }
      ultimo.current = { codigo, em: Date.now() }
      setLido(null)
      carregar(data)
    } catch (e) { vibrar(250); setErro((e as ApiError).message) } finally { setIndo(false) }
  }, [data, local, carregar])

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
      const item = r.tipo === 'peca' && r.item ? r.item : null
      if (alvoRef.current) { await lancar(r.codigo || codigo, item, alvoRef.current); return }   // operação aberta: vai direto
      setLido({ codigo: r.codigo || codigo, carregando: false, item })
    } catch (e) { setLido(null); vibrar(250); setErro((e as ApiError).message) }
  }, [lancar])

  const ativo = !lido && !indo && !digitar
  const { erro: erroCamera, pronto } = useLeitor(video, ativo, ler)

  async function registrar(p: Piloto | Achado | null) {
    if (!lido || lido.carregando || indo) return
    await lancar(lido.codigo, lido.item, p)
  }

  function escolherAntes(p: Piloto | Achado) {          // começar pelo piloto, antes da primeira peça
    setResumo(null); setFeito(null); setErro(null)
    setAlvo({ client_id: p.client_id, pilot_id: 'pilot_id' in p ? p.pilot_id : null, nome: p.nome }); setSessao([])
  }

  function encerrar() {
    if (alvo) setResumo({ nome: alvo.nome, itens: sessao })
    setAlvo(null); setSessao([]); setFeito(null)
  }

  function mudarLocal(v: string) { setLocal(v); try { localStorage.setItem('balcao.local', v) } catch { /* sem armazenamento */ } }

  function cancelar() {
    if (lido) ultimo.current = { codigo: lido.codigo, em: Date.now() }
    setLido(null)
  }

  // #206: a própria leitura se desfaz a qualquer hora — a que foi para a OS (enquanto a OS não foi
  // enviada nem paga) e a que ficou pendente (enquanto o gerente não revisou)
  async function desfazerLeitura(id: number, tipo: Pendente['tipo']) {
    try {
      await api.post(tipo === 'lancada' ? `/balcao/rapido/lancada/${id}/desfazer` : `/balcao/rapido/${id}/desfazer`)
      vibrar(40); if (feito?.id === id && feito.tipo === tipo) setFeito(null)
      setSessao(s => s.filter(x => !(x.id === id && x.tipo === tipo))); carregar(data)
    } catch (e) { setErro((e as ApiError).message) }
  }

  async function desfazer() { if (feito) await desfazerLeitura(feito.id, feito.tipo) }

  function enviarDigitado(e: FormEvent) {
    e.preventDefault()
    const t = texto
    setTexto(''); setDigitar(false)
    ultimo.current = { codigo: '', em: 0 }
    ler(t)
  }

  const hoje = dia?.hoje
  const ultima = sessao.length ? sessao[sessao.length - 1] : null
  const dias = hoje ? [[somaDias(hoje, -1), tr("Ontem")], [hoje, tr("Hoje")], [somaDias(hoje, 1), tr("Amanhã")]] : []
  const soBalcao = !!user?.so_balcao
  return <div className="br">
    <h1 className="sr-only">{tr("Balcão")}</h1>
    <section className="br-camera" aria-label={tr("Câmera")}>
      <video ref={video} muted playsInline aria-label={tr("Imagem da câmera")} />
      <div className="br-topo">
        <div className="br-dias" role="radiogroup" aria-label={tr("Dia das peças")}>
          {dias.map(([d, r]) => <button key={d} role="radio" aria-checked={d === data} onClick={() => setData(d)}>{r}</button>)}
          {gerente && <label className={`br-outro-dia${data && !dias.some(([d]) => d === data) ? ' on' : ''}`}>
            <span>{data && !dias.some(([d]) => d === data) ? rotuloDia(data) : tr("Outro dia")}</span>
            <input type="date" value={data || ''} onChange={e => e.target.value && setData(e.target.value)} aria-label={tr("Escolher o dia")} />
          </label>}
        </div>
        {soBalcao ? <button className="br-sair" onClick={() => logout()}>{tr("Sair")}</button>
          : <Link className="br-sair" to="/balcao">{tr("Painel")}</Link>}
      </div>
      {!erroCamera && <div className={`br-mira${lido ? ' pausa' : ''}`} aria-hidden="true" />}
      <p className="br-status" role="status">
        {erroCamera || (lido ? tr("Lido. Escolha o piloto embaixo.") : !pronto ? tr("Abrindo a câmera…")
          : alvo ? tr("Peças de {0}: leia a próxima", alvo.nome) : tr("Aponte para o código da peça"))}
      </p>
    </section>

    <section className="br-painel" aria-label={tr("Peça e pilotos")}>
      {erro && <p className="br-erro" role="alert">{erro}</p>}
      {/* #215 (dono, 13/10): "o nome do cliente fica como a maior coisa ali, e o nome da peça quase
          não dá para ver". Com a operação aberta, o cliente vai para a faixa de cima, pequeno; a
          última peça lida fica num cartão grande e fixo, com a confirmação de que entrou para ele. */}
      {alvo && <div className="br-sessao" role="group" aria-label={tr("Operação aberta")}>
        <div className="grow"><small>{tr("Peças de")}</small><span className="br-sessao-nome">{alvo.nome}</span></div>
        <select value={local} onChange={e => mudarLocal(e.target.value)} aria-label={tr("A peça sai de")}>
          <option value="sede">{tr("Galpão")}</option><option value="trailer">{tr("Trailer")}</option><option value="pista">{tr("Pista")}</option></select>
        <button className="btn primary" onClick={encerrar}>{tr("Encerrar")}</button>
      </div>}
      {alvo && ultima && <div key={ultima.tipo + ultima.id} className={`br-add${ultima.tipo === 'pendente' ? ' pend' : ''}`} role="status">
        <span className="br-add-selo">{ultima.tipo === 'lancada' ? tr("✓ Peça adicionada") : tr("⏳ Ficou para o gerente")}</span>
        <h2 className="br-add-peca">{ultima.peca || ultima.code}</h2>
        <p className="br-add-para">{ultima.tipo === 'lancada' ? tr("Já está na invoice de {0}, {1}.", alvo.nome, dia ? rotuloDia(dia.data) : '')
          : (ultima.motivo || tr("O gerente confere na revisão."))}</p>
        <button className="btn" onClick={() => desfazerLeitura(ultima.id, ultima.tipo)}>{tr("Desfazer")}</button>
      </div>}
      {!alvo && feito && <div className={`br-feito${feito.tipo === 'pendente' ? ' pend' : ''}`} role="status">
        <span>{feito.tipo === 'lancada' ? `✓ ${feito.texto} · ${tr("na OS")}` : `⏳ ${feito.texto} · ${tr("ficou para o gerente")}`}
          {feito.motivo && <small className="br-motivo">{feito.motivo}</small>}</span>
        <button className="btn" onClick={desfazer}>{tr("Desfazer")}</button>
      </div>}
      {resumo && !alvo && <div className="br-resumo" role="status">
        <h2>{tr("Operação encerrada")}</h2>
        <p>{tr("{0} peça(s) para {1}", resumo.itens.length, resumo.nome)}</p>
        {resumo.itens.length > 0 && <ul>{resumo.itens.map(x => <li key={x.tipo + x.id}>{x.tipo === 'lancada' ? '✓' : '⏳'} <b>{x.peca || x.code}</b>
          <small className="muted"> · {x.tipo === 'lancada' ? tr("na invoice") : tr("ficou para o gerente")}</small></li>)}</ul>}
        <button className="btn primary" onClick={() => setResumo(null)}>{tr("Próximo piloto")}</button>
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
          {dia && !dia.pilotos.length && <p className="small muted">{tr("Ninguém marcado neste dia no Asana, nas sessões do site ou nas corridas. Busque o cliente pelo nome abaixo.")}</p>}
        </div>
        <OutroCliente desativado={indo || lido.carregando} onEscolher={c => registrar(c)} />
        <p className="small muted" style={{ margin: 0 }}>{tr("Depois do toque, as próximas peças lidas já vão para o mesmo piloto, até você tocar em Encerrar.")}</p>
        <div className="br-acoes">
          <button className="btn" disabled={indo || lido.carregando} onClick={() => registrar(null)}>{tr("Decidir depois")}</button>
          <button className="btn ghost" disabled={indo} onClick={cancelar}>{tr("Ler outra")}</button>
        </div>
      </> : <>
        <div className="br-dica">
          <h2>{alvo ? tr("Leia a próxima peça") : tr("Leia a peça")}</h2>
          <p className="small muted">{alvo ? tr("Cada peça lida já entra na invoice de {0}. Era só essa? Toque em Encerrar.", alvo.nome)
            : tr("Leia a peça e toque no piloto, ou toque no piloto primeiro.")}</p>
        </div>
        {!alvo && !resumo && dia && <section className="br-antes" aria-labelledby="br-dia-h">
          {/* dono, 13/10: "não tá aparecendo nenhum cliente nos dias que tiveram clientes" — a lista
              ficava fechada, e só abria depois de a câmera ler uma peça */}
          <h2 id="br-dia-h" className="h3">{tr("Pilotos de {0}", rotuloDia(dia.data))}</h2>
          {dia.pilotos.length ? <div className="br-pilotos">{dia.pilotos.map(p => <button key={p.chave} className="br-piloto" onClick={() => escolherAntes(p)}>
            <b>{p.nome}</b><small>{p.origens.map(o => ORIGEM[o] || o).join(' · ')}{p.pecas ? ` · ${tr("{0} peça(s)", p.pecas)}` : ''}</small></button>)}</div>
            : <p className="small muted">{tr("Ninguém marcado neste dia no Asana, nas sessões do site ou nas corridas. Busque o cliente pelo nome abaixo.")}</p>}
          <p className="small muted" style={{ margin: 0 }}>{tr("Toque no piloto e leia as peças dele. O que é marcado no Asana aparece aqui em até 15 minutos.")}</p>
          <OutroCliente desativado={false} onEscolher={c => escolherAntes(c)} />
        </section>}
        {alvo && sessao.length > 0 && <section className="br-op" aria-labelledby="br-op-h">
          <h2 id="br-op-h" className="h3">{tr("Nesta operação · {0}", sessao.length)}</h2>
          <ul className="br-op-l">{[...sessao].reverse().map(x => <li key={x.tipo + x.id} className={x.tipo === 'pendente' ? 'pend' : ''}>
            <span className="br-op-icone" aria-hidden="true">{x.tipo === 'lancada' ? '✓' : '⏳'}</span>
            <span className="grow"><b>{x.peca || x.code}</b><small>{x.tipo === 'lancada' ? tr("na invoice") : tr("ficou para o gerente")}</small></span>
            <button className="btn sm ghost" onClick={() => desfazerLeitura(x.id, x.tipo)} aria-label={tr("Desfazer {0}", x.peca || x.code)}>{tr("Desfazer")}</button></li>)}</ul>
        </section>}
        {!alvo && !!dia?.minhas.length && <ul className="br-minhas" aria-label={tr("Suas últimas leituras")}>
          {dia.minhas.map(m => <li key={m.tipo + m.id}><span className="truncate">{m.tipo === 'lancada' ? '✓ ' : '⏳ '}{m.peca || m.code}</span>
            <span className="muted">{m.pilot_name || tr("decidir depois")}</span>
            <button className="btn sm ghost" onClick={() => desfazerLeitura(m.id, m.tipo)} aria-label={tr("Desfazer {0}", m.peca || m.code)}>{tr("Desfazer")}</button></li>)}
        </ul>}
        {gerente && dia && <button className="btn ghost br-teclado" aria-expanded={auditar} onClick={() => setAuditar(v => !v)}>{auditar ? tr("Fechar a auditoria") : tr("Auditoria do dia: quem lançou o quê")}</button>}
        {gerente && auditar && dia && <AuditoriaDia data={dia.data} />}
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
