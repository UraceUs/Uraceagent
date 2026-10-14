/* Assinar a waiver pelo convite do e-mail (#135), sem conta e sem login. Carregada só nesta rota.
 *
 * Dono, 14/10: "vai ser por e-mail para o adulto ou para o responsável assinar aquela waiver".
 * O link é pessoal, vale uma vez e vence; o card, o piloto e o modelo vêm do convite (nada aqui
 * escolhe card). O resto é a mesma assinatura da área do cliente (#85): o PDF de verdade, lido
 * página por página (#107), as caixas, o nome, a assinatura desenhada e o código de 6 dígitos que
 * chega no mesmo e-mail (#108). Pelo menor, só pai ou mãe, com a declaração (#105). */
import { useEffect, useState, type FormEvent } from 'react'
import { papi, PortalError, type ConviteWaiver } from './api'
import { VisorPdf } from './VisorPdf'
import { Quadro } from './Waiver'

const BASE = '/ops/api/portal'
const TIPO = { adult: 'Adult release and waiver', parental: 'Parental consent and waiver (minor)' }
const PARENTESCO: [string, string][] = [['mother', 'Mother'], ['father', 'Father'], ['legal_guardian', 'Court-appointed legal guardian'],
  ['other', 'Other (grandparent, step-parent, relative, coach…)']]
const dataUS = (iso: string) => new Date(iso.length === 10 ? iso + 'T12:00:00' : iso)
  .toLocaleDateString('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric', year: 'numeric' })

export function ConviteWaiverPagina({ token }: { token: string }) {
  const caminho = `/invite/${encodeURIComponent(token)}`
  const [c, setC] = useState<ConviteWaiver | null>(null)
  const [fora, setFora] = useState<string | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [f, setF] = useState({ typed_name: '', signature: '', read_and_agree: false, consent_esign: false, english_understood: false, relationship: '', guardian_declaration: false })
  const [lido, setLido] = useState<{ em: string; modo: 'pdf_viewer' | 'pdf_opened_and_text' } | null>(null)
  const [semVisor, setSemVisor] = useState(false)
  const [abriuPdf, setAbriuPdf] = useState(false)
  const [codigo, setCodigo] = useState('')
  const [enviado, setEnviado] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)
  const [indo, setIndo] = useState(false)
  const [feita, setFeita] = useState<{ valid_until: string } | null>(null)

  useEffect(() => {
    papi<ConviteWaiver>('GET', caminho).then(setC).catch(e => setFora((e as PortalError).message))
  }, [caminho])

  async function mandarCodigo() {
    setErro(null); setOcupado(true)
    try { setEnviado((await papi<{ sent_to: string }>('POST', `${caminho}/code`)).sent_to) }
    catch (ex) { setErro((ex as PortalError).message) } finally { setOcupado(false) }
  }
  async function assinar(e: FormEvent) {
    e.preventDefault(); setErro(null); setIndo(true)
    try { setFeita(await papi('POST', `${caminho}/sign`, { ...f, document_read_at: lido?.em ?? null, document_read_mode: lido?.modo ?? null, sign_code: codigo })) }
    catch (ex) { const p = ex as PortalError; if (p.status === 410 || p.status === 404) setFora(p.message); else setErro(p.message) }
    finally { setIndo(false) }
  }

  const topo = <div><h1 className="h1">Sign the waiver</h1>
    {c && <p className="muted" style={{ margin: '4px 0 0' }}>Driver: <b>{c.driver}</b></p>}</div>
  if (feita && c) return <div className="stack" style={{ gap: 18 }}>
    {topo}
    <div className="banner ok" role="status"><span className="bi" aria-hidden="true">✓</span><div className="grow">
      Signed. The waiver for {c.driver} is valid until <b>{dataUS(feita.valid_until)}</b>. URACE already has it on file.</div></div>
    <div className="row wrap" style={{ gap: 8 }}><a className="btn primary" href={`${BASE}${caminho}/signed.pdf`}>Download the signed PDF</a></div>
  </div>
  if (fora) return <div className="stack" style={{ gap: 12 }}>
    <h1 className="h1">Waiver invitation</h1>
    <div className="banner warn" role="alert"><span className="bi" aria-hidden="true">▲</span><div className="grow">{fora}</div></div>
    <p className="small muted" style={{ margin: 0 }}>You can also sign in person at the track.</p>
  </div>
  if (!c) return <div className="stack">{topo}<div className="state"><span className="spin" /></div></div>

  const menor = c.kind === 'parental'
  const naoOnline = menor && (f.relationship === 'legal_guardian' || f.relationship === 'other')
  const pdf = `${BASE}${caminho}/pdf`
  return <form className="stack" style={{ gap: 18 }} onSubmit={assinar} noValidate>
    {topo}
    <p className="muted" style={{ margin: 0 }}>{TIPO[c.kind]}. {menor
      ? <>You sign as the <b>parent</b> of {c.driver}. Valid for one year, or until the day before {c.driver} turns 18, whichever comes first.</>
      : <>You sign for yourself, {c.signer_name}. Valid for one year.</>} This personal link works once, until {dataUS(c.expires_at)}.</p>
    {menor && <section className="stack" aria-labelledby="c-par" style={{ gap: 8 }}>
      <h2 className="h2" id="c-par">Who is signing</h2>
      <fieldset className="stack portal-parentesco" style={{ gap: 6 }}>
        <legend>Your relationship to {c.driver}<b className="portal-obr" aria-hidden="true"> *</b></legend>
        {PARENTESCO.map(([v, rotulo]) => <label key={v} className="check"><input type="radio" name="relationship" value={v}
          checked={f.relationship === v} onChange={() => setF({ ...f, relationship: v })} /> {rotulo}</label>)}
      </fieldset>
      {f.relationship === 'legal_guardian' && <div className="banner warn" role="status"><span className="bi" aria-hidden="true">▲</span><div className="grow">
        A court-appointed legal guardian signs <b>in person at the track</b>, with a copy of the court order.</div></div>}
      {f.relationship === 'other' && <div className="banner warn" role="status"><span className="bi" aria-hidden="true">▲</span><div className="grow">
        Only a parent (mother or father) can sign the waiver for a minor. Ask {c.driver}'s mother or father to sign it, or come to the track together.</div></div>}
      {!naoOnline && c.model.declaration && <label className="check"><input type="checkbox" checked={f.guardian_declaration}
        onChange={e => setF({ ...f, guardian_declaration: e.target.checked })} /> {c.model.declaration.replace('{minor}', c.driver)}</label>}
    </section>}
    {erro && <div className="banner crit" role="alert"><span className="bi" aria-hidden="true">✕</span><div className="grow">{erro}</div></div>}
    <section className="stack" aria-labelledby="c-doc" style={{ gap: 8 }}>
      <div className="row"><h2 className="h2 grow" id="c-doc">Read the document</h2>
        <a className="btn sm" href={pdf} target="_blank" rel="noreferrer" onClick={() => setAbriuPdf(true)}>Open the PDF</a></div>
      {!semVisor ? <VisorPdf url={pdf} onLido={em => setLido({ em, modo: 'pdf_viewer' })} onFalha={() => setSemVisor(true)} />
        : <>
          <div className="banner warn" role="status"><span className="bi" aria-hidden="true">▲</span><div className="grow">
            This browser could not show the document here. Tap <b>Open the PDF</b>, read it, then read the text below to the end.</div></div>
          <div className="card card-b portal-waiver-texto" tabIndex={0} aria-label="Waiver text"
            onScroll={e => { const t = e.currentTarget; if (abriuPdf && t.scrollTop + t.clientHeight >= t.scrollHeight - 8 && !lido) setLido({ em: new Date().toISOString(), modo: 'pdf_opened_and_text' }) }}>
            {c.model.text || 'Open the PDF to read the document.'}</div>
          {abriuPdf && !lido && <button type="button" className="btn sm ghost" onClick={() => setLido({ em: new Date().toISOString(), modo: 'pdf_opened_and_text' })}>I have read the whole PDF</button>}
        </>}
      {!semVisor && c.model.text && <details className="small"><summary>Text version (for screen readers)</summary>
        <div className="portal-waiver-texto" aria-label="Waiver text">{c.model.text}</div></details>}
    </section>
    <section className="stack" aria-labelledby="c-ass" style={{ gap: 10 }}>
      <h2 className="h2" id="c-ass">Sign</h2>
      {!lido && <p className="small muted" style={{ margin: 0 }}>Read the whole document above to unlock the boxes.</p>}
      <label className="check"><input type="checkbox" disabled={!lido} checked={f.english_understood} onChange={e => setF({ ...f, english_understood: e.target.checked })} /> I read and understand English, or I had this document translated before signing.</label>
      <label className="check"><input type="checkbox" disabled={!lido} checked={f.read_and_agree} onChange={e => setF({ ...f, read_and_agree: e.target.checked })} />
        I have read this waiver, I understand it gives up legal rights, and I agree to it{menor ? ` on behalf of ${c.driver}` : ''}.</label>
      <label className="check"><input type="checkbox" disabled={!lido} checked={f.consent_esign} onChange={e => setF({ ...f, consent_esign: e.target.checked })} />
        I agree to sign electronically. My electronic signature is legally binding, the same as a handwritten one.</label>
      <label className="fld"><span>Your full name<b className="portal-obr" aria-hidden="true"> *</b><i> · typed, as your signature</i></span>
        <input autoComplete="name" value={f.typed_name} onChange={e => setF({ ...f, typed_name: e.target.value })} required /></label>
      <Quadro onMuda={png => setF(x => ({ ...x, signature: png }))} />
      <div className="card card-b stack portal-codigo" style={{ gap: 8 }}>
        <p className="small muted" style={{ margin: 0 }}>To sign, enter the code we send to <b>{c.email}</b> now. It shows that it is really you.</p>
        {!enviado ? <button type="button" className="btn" disabled={ocupado || !lido} onClick={mandarCodigo}>Send me the signing code</button>
          : <>
            <label className="fld"><span>Signing code sent to {enviado}</span>
              <input inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={codigo} onChange={e => setCodigo(e.target.value.replace(/\D/g, ''))} /></label>
            <button type="button" className="btn ghost sm" disabled={ocupado} onClick={mandarCodigo}>Send a new code</button>
          </>}
      </div>
      <button className="btn primary block" disabled={indo || naoOnline || !lido || codigo.length !== 6}>{indo ? 'Signing…' : 'Sign the waiver'}</button>
      <p className="small muted" style={{ margin: 0 }}>We record the date and time, your IP address, device and the email code with your signature. You get the signed PDF right after.</p>
    </section>
  </form>
}
