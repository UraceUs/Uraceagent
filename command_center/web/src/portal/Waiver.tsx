/* Assinar a waiver na área do cliente (#85), sem DocuSign. Carregada só nesta rota.
 *
 * O texto é o do PDF do DocuSign, importado como veio; o original abre em PDF. Para assinar:
 * ler, marcar as duas caixas (concordo / assino eletronicamente), digitar o nome completo e
 * desenhar a assinatura. Quem assina é o responsável logado; o servidor decide o modelo pela
 * idade do piloto e guarda a prova (hora, IP, aparelho, hashes). A adult só o próprio piloto
 * assina (#104): para um adulto que não é o titular, a tela explica em vez de assinar. */
import { useEffect, useRef, useState, type FormEvent, type PointerEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { papi, PortalError, type Account, type WaiverModelo, type Waivers } from './api'

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
  const [f, setF] = useState({ typed_name: '', signature: '', read_and_agree: false, consent_esign: false, relationship: '', guardian_declaration: false })
  const [erro, setErro] = useState<string | null>(null)
  const [indo, setIndo] = useState(false)
  const [feita, setFeita] = useState<{ waiver_id: number; valid_until: string } | null>(null)
  const meu = sit?.drivers.find(d => d.driver_id === pid)

  useEffect(() => { papi<Waivers>('GET', '/waivers').then(setSit).catch(e => setErro((e as PortalError).message)) }, [])
  useEffect(() => {
    if (sit?.enabled && meu?.kind) papi<WaiverModelo>('GET', `/waivers/model/${meu.kind}`).then(setModelo).catch(e => setErro((e as PortalError).message))
  }, [sit, meu?.kind])

  async function assinar(e: FormEvent) {
    e.preventDefault(); setErro(null); setIndo(true)
    try { setFeita(await papi('POST', `/drivers/${pid}/waiver`, f)) }
    catch (ex) { setErro((ex as PortalError).message) } finally { setIndo(false) }
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
      ? <>You sign as the <b>parent or legal guardian</b> of {piloto.name}.</>
      : 'You sign for yourself.'} Valid for one year.</p>
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
        <a className="btn sm" href={`${BASE}/waivers/model/${meu.kind}/pdf`} target="_blank" rel="noreferrer">Open the PDF</a></div>
      <div className="card card-b portal-waiver-texto" tabIndex={0} aria-label="Waiver text">{modelo ? modelo.text || 'Open the PDF to read the document.' : <span className="spin" />}</div>
    </section>
    <section className="stack" aria-labelledby="w-ass" style={{ gap: 10 }}>
      <h2 className="h2" id="w-ass">Sign</h2>
      <label className="check"><input type="checkbox" checked={f.read_and_agree} onChange={e => setF({ ...f, read_and_agree: e.target.checked })} />
        I have read this waiver, I understand it gives up legal rights, and I agree to it{menor ? ` on behalf of ${piloto.name}` : ''}.</label>
      <label className="check"><input type="checkbox" checked={f.consent_esign} onChange={e => setF({ ...f, consent_esign: e.target.checked })} />
        I agree to sign electronically. My electronic signature is legally binding, the same as a handwritten one.</label>
      <label className="fld"><span>Your full name<b className="portal-obr" aria-hidden="true"> *</b><i> · typed, as your signature</i></span>
        <input autoComplete="name" value={f.typed_name} onChange={e => setF({ ...f, typed_name: e.target.value })} required /></label>
      <Quadro onMuda={png => setF(x => ({ ...x, signature: png }))} />
      <button className="btn primary block" disabled={indo || !modelo || naoOnline}>{indo ? 'Signing…' : 'Sign the waiver'}</button>
      <p className="small muted" style={{ margin: 0 }}>We record the date and time, your IP address and device with your signature. You get the signed PDF right after.</p>
    </section>
  </form>
}
