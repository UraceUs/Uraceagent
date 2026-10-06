/* Assinar a waiver na área do cliente (#85), sem DocuSign. Carregada só nesta rota.
 *
 * O documento é o PDF do DocuSign, importado como veio, mostrado página por página (#107); as
 * caixas só se liberam depois de todas as páginas passarem pela tela. O e-mail da conta é
 * confirmado por código (uma vez) e cada assinatura pede um código novo nesse e-mail (#108).
 * Para assinar: ler, marcar as duas caixas (concordo / assino eletronicamente), digitar o nome completo e
 * desenhar a assinatura. Quem assina é o responsável logado; o servidor decide o modelo pela
 * idade do piloto e guarda a prova (hora, IP, aparelho, hashes). A adult só o próprio piloto
 * assina (#104): para um adulto que não é o titular, a tela explica em vez de assinar. */
import { useEffect, useRef, useState, type FormEvent, type PointerEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { papi, PortalError, type Account, type WaiverModelo, type Waivers } from './api'
import { VisorPdf } from './VisorPdf'

const BASE = '/ops/api/portal'
const TIPO = { adult: 'Adult release and waiver', parental: 'Parental consent and waiver (minor)' }
/** #105: pelo menor, online, só pai ou mãe (Fla. Stat. §744.301(3)). Tutor nomeado por juiz e outros: no balcão. */
const PARENTESCO: [string, string][] = [['mother', 'Mother'], ['father', 'Father'], ['legal_guardian', 'Court-appointed legal guardian'],
  ['other', 'Other (grandparent, step-parent, relative, coach…)']]

/** O quadro da assinatura: dedo, caneta ou mouse. Devolve o PNG (ou '' se vazio). */
function Quadro({ onMuda }: { onMuda: (png: string) => void }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const ultimo = useRef<{ x: number; y: number } | null>(null)
  const tinta = useRef(0)
  useEffect(() => {
    const c = ref.current!
    const r = window.devicePixelRatio || 1
    c.width = c.clientWidth * r; c.height = c.clientHeight * r
    const g = c.getContext('2d')!
    g.scale(r, r); g.lineWidth = 2.6; g.lineCap = 'round'; g.lineJoin = 'round'; g.strokeStyle = '#111'
  }, [])
  const ponto = (e: PointerEvent<HTMLCanvasElement>) => { const b = e.currentTarget.getBoundingClientRect(); return { x: e.clientX - b.left, y: e.clientY - b.top } }
  function desce(e: PointerEvent<HTMLCanvasElement>) { e.currentTarget.setPointerCapture(e.pointerId); ultimo.current = ponto(e) }
  function move(e: PointerEvent<HTMLCanvasElement>) {
    if (!ultimo.current) return
    const p = ponto(e), g = e.currentTarget.getContext('2d')!
    g.beginPath(); g.moveTo(ultimo.current.x, ultimo.current.y); g.lineTo(p.x, p.y); g.stroke()
    tinta.current += Math.hypot(p.x - ultimo.current.x, p.y - ultimo.current.y)
    ultimo.current = p
  }
  function sobe() {
    if (!ultimo.current) return
    ultimo.current = null
    onMuda(tinta.current > 40 ? ref.current!.toDataURL('image/png') : '')
  }
  function limpar() {
    const c = ref.current!
    c.getContext('2d')!.clearRect(0, 0, c.width, c.height); tinta.current = 0; onMuda('')
  }
  return <div className="stack" style={{ gap: 6 }}>
    <canvas ref={ref} className="portal-assinatura" aria-label="Signature pad: draw your signature here" role="img"
      onPointerDown={desce} onPointerMove={move} onPointerUp={sobe} onPointerCancel={sobe} onPointerLeave={sobe} />
    <div className="row"><span className="small muted grow">Draw your signature with your finger or mouse.</span>
      <button type="button" className="btn sm ghost" onClick={limpar}>Clear</button></div>
  </div>
}

export function AssinarWaiver({ conta }: { conta: Account }) {
  const pid = Number(useParams().pid)
  const nav = useNavigate()
  const piloto = conta.drivers.find(p => p.id === pid)
  const [sit, setSit] = useState<Waivers | null>(null)
  const [modelo, setModelo] = useState<WaiverModelo | null>(null)
  const [f, setF] = useState({ typed_name: '', signature: '', read_and_agree: false, consent_esign: false, english_understood: false, relationship: '', guardian_declaration: false })
  const [erro, setErro] = useState<string | null>(null)
  const [indo, setIndo] = useState(false)
  const [feita, setFeita] = useState<{ waiver_id: number; valid_until: string } | null>(null)
  // #107: as caixas só se liberam depois de o documento inteiro passar pela tela
  const [lido, setLido] = useState<{ em: string; modo: 'pdf_viewer' | 'pdf_opened_and_text' } | null>(null)
  const [semVisor, setSemVisor] = useState(false)
  // #108: e-mail confirmado (uma vez por conta) e o código de uma vez para assinar
  const [cod, setCod] = useState({ email: '', assinar: '' })
  const [enviado, setEnviado] = useState<{ email?: string; assinar?: string }>({})
  const [ocupado, setOcupado] = useState(false)
  const [abriuPdf, setAbriuPdf] = useState(false)
  const meu = sit?.drivers.find(d => d.driver_id === pid)

  useEffect(() => { papi<Waivers>('GET', '/waivers').then(setSit).catch(e => setErro((e as PortalError).message)) }, [])
  useEffect(() => {
    if (sit?.enabled && meu?.kind) papi<WaiverModelo>('GET', `/waivers/model/${meu.kind}`).then(setModelo).catch(e => setErro((e as PortalError).message))
  }, [sit, meu?.kind])

  async function assinar(e: FormEvent) {
    e.preventDefault(); setErro(null); setIndo(true)
    try { setFeita(await papi('POST', `/drivers/${pid}/waiver`, { ...f, document_read_at: lido?.em ?? null, document_read_mode: lido?.modo ?? null, sign_code: cod.assinar })) }
    catch (ex) { setErro((ex as PortalError).message) } finally { setIndo(false) }
  }

  async function mandarCodigo(qual: 'email' | 'assinar') {
    setErro(null); setOcupado(true)
    try {
      const r = await papi<{ sent_to?: string; verified?: boolean }>('POST', qual === 'email' ? '/email/verify/send' : '/waivers/code')
      if (r.verified) setSit(await papi<Waivers>('GET', '/waivers'))
      else setEnviado(x => ({ ...x, [qual]: r.sent_to }))
    } catch (ex) { setErro((ex as PortalError).message) } finally { setOcupado(false) }
  }
  async function confirmarEmail() {
    setErro(null); setOcupado(true)
    try { await papi('POST', '/email/verify', { code: cod.email }); setSit(await papi<Waivers>('GET', '/waivers')) }
    catch (ex) { setErro((ex as PortalError).message) } finally { setOcupado(false) }
  }

  if (!piloto) return <div className="stack"><h1 className="h1">Waiver</h1><p className="muted">Driver not found. <Link to="/portal/drivers">Back to Drivers</Link></p></div>
  const topo = <div><h1 className="h1">Sign the waiver</h1><p className="muted" style={{ margin: '4px 0 0' }}>Driver: <b>{piloto.name}</b></p></div>
  if (feita) return <div className="stack" style={{ gap: 18 }}>
    {topo}
    <div className="banner ok" role="status"><span className="bi" aria-hidden="true">✓</span><div className="grow">
      Signed. The waiver for {piloto.name} is valid until <b>{new Date(feita.valid_until + 'T12:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</b>.</div></div>
    <div className="row wrap" style={{ gap: 8 }}>
      <a className="btn primary" href={`${BASE}/waivers/${feita.waiver_id}/pdf`}>Download the signed PDF</a>
      <button className="btn" onClick={() => nav('/portal/drivers')}>Back to Drivers</button></div>
  </div>
  if (!sit) return <div className="stack">{topo}{erro ? <div className="banner crit" role="alert">{erro}</div> : <div className="state"><span className="spin" /></div>}</div>
  if (!sit.enabled) return <div className="stack">{topo}<p className="muted">Online signing is not available yet. Our team will email you the waiver.</p>
    <Link to="/portal/drivers">Back to Drivers</Link></div>
  if (meu?.status === 'signed') return <div className="stack">{topo}<p>This driver already has a valid waiver.</p>
    <div className="row wrap" style={{ gap: 8 }}><a className="btn" href={`${BASE}/waivers/${meu.waiver_id}/pdf`}>Download the signed PDF</a><Link className="btn ghost" to="/portal/drivers">Back to Drivers</Link></div></div>
  if (!meu?.kind) return <div className="stack">{topo}<p className="muted">Add {piloto.name}'s date of birth first: it decides which waiver applies.</p>
    <Link to="/portal/drivers">Back to Drivers</Link></div>
  if (meu.own_signature_required) return <div className="stack">{topo}
    <div className="banner warn" role="status"><span className="bi" aria-hidden="true">▲</span><div className="grow">
      <b>{piloto.name} is an adult and must sign their own waiver.</b> Only the driver can give up their own rights, so the account holder
      can't sign for them. {piloto.name} can create their own account and sign it there, or sign in person at the track.</div></div>
    <Link to="/portal/drivers">Back to Drivers</Link></div>

  const menor = meu.kind === 'parental'
  const naoOnline = menor && (f.relationship === 'legal_guardian' || f.relationship === 'other')
  return <form className="stack" style={{ gap: 18 }} onSubmit={assinar} noValidate>
    {topo}
    <p className="muted" style={{ margin: 0 }}>{TIPO[meu.kind]}. {menor
      ? <>You sign as the <b>parent</b> of {piloto.name}.</>
      : 'You sign for yourself.'} {menor ? <>Valid for one year, or until the day before {piloto.name} turns 18, whichever comes first.</> : 'Valid for one year.'}</p>
    {menor && <section className="stack" aria-labelledby="w-par" style={{ gap: 8 }}>
      <h2 className="h2" id="w-par">Who is signing</h2>
      <fieldset className="stack portal-parentesco" style={{ gap: 6 }}>
        <legend>Your relationship to {piloto.name}<b className="portal-obr" aria-hidden="true"> *</b></legend>
        {PARENTESCO.map(([v, rotulo]) => <label key={v} className="check"><input type="radio" name="relationship" value={v}
          checked={f.relationship === v} onChange={() => setF({ ...f, relationship: v })} /> {rotulo}</label>)}
      </fieldset>
      {f.relationship === 'legal_guardian' && <div className="banner warn" role="status"><span className="bi" aria-hidden="true">▲</span><div className="grow">
        A court-appointed legal guardian signs <b>in person at the track</b>, with a copy of the court order.</div></div>}
      {f.relationship === 'other' && <div className="banner warn" role="status"><span className="bi" aria-hidden="true">▲</span><div className="grow">
        Only a parent (mother or father) can sign the waiver for a minor. Ask {piloto.name}'s mother or father to sign it, or come to the track together.</div></div>}
      {!naoOnline && modelo?.declaration && <label className="check"><input type="checkbox" checked={f.guardian_declaration}
        onChange={e => setF({ ...f, guardian_declaration: e.target.checked })} /> {modelo.declaration.replace('{minor}', piloto.name)}</label>}
    </section>}
    {erro && <div className="banner crit" role="alert"><span className="bi" aria-hidden="true">✕</span><div className="grow">{erro}</div></div>}
    <section className="stack" aria-labelledby="w-doc" style={{ gap: 8 }}>
      <div className="row"><h2 className="h2 grow" id="w-doc">Read the document</h2>
        <a className="btn sm" href={`${BASE}/waivers/model/${meu.kind}/pdf`} target="_blank" rel="noreferrer" onClick={() => setAbriuPdf(true)}>Open the PDF</a></div>
      {!semVisor ? <VisorPdf url={`${BASE}/waivers/model/${meu.kind}/pdf`} onLido={em => setLido({ em, modo: 'pdf_viewer' })} onFalha={() => setSemVisor(true)} />
        : <>
          <div className="banner warn" role="status"><span className="bi" aria-hidden="true">▲</span><div className="grow">
            This browser could not show the document here. Tap <b>Open the PDF</b>, read it, then read the text below to the end.</div></div>
          <div className="card card-b portal-waiver-texto" tabIndex={0} aria-label="Waiver text"
            onScroll={e => { const t = e.currentTarget; if (abriuPdf && t.scrollTop + t.clientHeight >= t.scrollHeight - 8 && !lido) setLido({ em: new Date().toISOString(), modo: 'pdf_opened_and_text' }) }}>
            {modelo ? modelo.text || 'Open the PDF to read the document.' : <span className="spin" />}</div>
          {abriuPdf && !lido && <button type="button" className="btn sm ghost" onClick={() => setLido({ em: new Date().toISOString(), modo: 'pdf_opened_and_text' })}>I have read the whole PDF</button>}
        </>}
      {!semVisor && modelo?.text && <details className="small"><summary>Text version (for screen readers)</summary>
        <div className="portal-waiver-texto" aria-label="Waiver text">{modelo.text}</div></details>}
    </section>
    <section className="stack" aria-labelledby="w-ass" style={{ gap: 10 }}>
      <h2 className="h2" id="w-ass">Sign</h2>
      {!lido && <p className="small muted" style={{ margin: 0 }}>Read the whole document above to unlock the boxes.</p>}
      <label className="check"><input type="checkbox" disabled={!lido} checked={f.english_understood} onChange={e => setF({ ...f, english_understood: e.target.checked })} /> I read and understand English, or I had this document translated before signing.</label>
      <label className="check"><input type="checkbox" disabled={!lido} checked={f.read_and_agree} onChange={e => setF({ ...f, read_and_agree: e.target.checked })} />
        I have read this waiver, I understand it gives up legal rights, and I agree to it{menor ? ` on behalf of ${piloto.name}` : ''}.</label>
      <label className="check"><input type="checkbox" disabled={!lido} checked={f.consent_esign} onChange={e => setF({ ...f, consent_esign: e.target.checked })} />
        I agree to sign electronically. My electronic signature is legally binding, the same as a handwritten one.</label>
      <label className="fld"><span>Your full name<b className="portal-obr" aria-hidden="true"> *</b><i> · typed, as your signature</i></span>
        <input autoComplete="name" value={f.typed_name} onChange={e => setF({ ...f, typed_name: e.target.value })} required /></label>
      <Quadro onMuda={png => setF(x => ({ ...x, signature: png }))} />
      {!sit.email_verified ? <div className="card card-b stack portal-codigo" style={{ gap: 8 }}>
        <h3 className="h3" style={{ margin: 0 }}>Confirm your email</h3>
        <p className="small muted" style={{ margin: 0 }}>Before you sign, we confirm that <b>{sit.email}</b> is yours with a 6-digit code. You do this once.</p>
        {!enviado.email ? <button type="button" className="btn" disabled={ocupado} onClick={() => mandarCodigo('email')}>Send the code to my email</button>
          : <>
            <label className="fld"><span>Code sent to {enviado.email}</span>
              <input inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={cod.email} onChange={e => setCod({ ...cod, email: e.target.value.replace(/\D/g, '') })} /></label>
            <div className="row wrap" style={{ gap: 8 }}>
              <button type="button" className="btn" disabled={ocupado || cod.email.length !== 6} onClick={confirmarEmail}>Confirm email</button>
              <button type="button" className="btn ghost sm" disabled={ocupado} onClick={() => mandarCodigo('email')}>Send a new code</button></div>
          </>}
      </div> : <div className="card card-b stack portal-codigo" style={{ gap: 8 }}>
        <p className="small muted" style={{ margin: 0 }}>To sign, enter the code we send to <b>{sit.email}</b> now. It shows that it is really you.</p>
        {!enviado.assinar ? <button type="button" className="btn" disabled={ocupado || !lido} onClick={() => mandarCodigo('assinar')}>Send me the signing code</button>
          : <>
            <label className="fld"><span>Signing code sent to {enviado.assinar}</span>
              <input inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={cod.assinar} onChange={e => setCod({ ...cod, assinar: e.target.value.replace(/\D/g, '') })} /></label>
            <button type="button" className="btn ghost sm" disabled={ocupado} onClick={() => mandarCodigo('assinar')}>Send a new code</button>
          </>}
      </div>}
      <button className="btn primary block" disabled={indo || !modelo || naoOnline || !lido || !sit.email_verified || cod.assinar.length !== 6}>{indo ? 'Signing…' : 'Sign the waiver'}</button>
      <p className="small muted" style={{ margin: 0 }}>We record the date and time, your IP address, device and the email code with your signature. You get the signed PDF right after.</p>
    </section>
  </form>
}
