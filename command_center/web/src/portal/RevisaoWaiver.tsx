/* Revisar antes do clique final (#112; P-15, lacunas C-2, C-4 e A-5; Fla. Stat. §668.50(10)).
 *
 * O passo 2 das duas telas de assinar (a conta e o convite do e-mail). O servidor já conferiu tudo menos o código
 * e devolveu o resumo: documento, piloto, quem assina, parentesco, nome digitado (e se bate com o da conta),
 * validade e a frase de efeito legal. Aqui a pessoa vê também a assinatura que desenhou e só então confirma, no
 * botão "I agree — sign the waiver", com a frase ao lado. "Go back" volta ao formulário sem perder nada; mudou
 * algo, a revisão é feita de novo (o servidor recusa o clique final com conteúdo diferente do revisado). */
import { useEffect, useRef, type ReactNode } from 'react'
import type { RevisaoWaiver } from './api'

const dataUS = (iso: string) => new Date(iso.length === 10 ? iso + 'T12:00:00' : iso)
  .toLocaleDateString('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric', year: 'numeric' })

export function Revisao({ r, assinatura, nomeConfirmado, onNomeConfirmado, codigo, podeAssinar, indo, erro, onVoltar, onAssinar }: {
  r: RevisaoWaiver; assinatura: string; nomeConfirmado: boolean; onNomeConfirmado: (v: boolean) => void
  codigo: ReactNode; podeAssinar: boolean; indo: boolean; erro: string | null; onVoltar: () => void; onAssinar: () => void
}) {
  const titulo = useRef<HTMLHeadingElement>(null)
  useEffect(() => { titulo.current?.focus() }, [])
  const falta = !r.name_matches && !nomeConfirmado
  return <section className="stack portal-revisao page-in" aria-labelledby="rv-titulo" style={{ gap: 14 }}>
    <h2 className="h2" id="rv-titulo" ref={titulo} tabIndex={-1}>Review and sign</h2>
    <p className="small muted" style={{ margin: 0 }}>Check everything below. Nothing is signed until you tap <b>{r.button}</b>.</p>
    <dl className="dl portal-revisao-dl">
      <dt>Document</dt><dd>{r.document} · {r.pages} {r.pages === 1 ? 'page' : 'pages'}</dd>
      <dt>Driver</dt><dd>{r.driver}{r.kind === 'parental' && r.driver_birth_date ? <> · born {dataUS(r.driver_birth_date)}</> : null}</dd>
      <dt>Signing as</dt><dd>{r.signing_as}</dd>
      {r.relationship && <><dt>Relationship</dt><dd>{r.relationship}</dd></>}
      {r.guardian_declaration && <><dt>Declaration</dt><dd>{r.guardian_declaration}</dd></>}
      <dt>Typed name</dt><dd><b>{r.typed_name}</b></dd>
      <dt>Name on file</dt><dd>{r.name_on_file}</dd>
      <dt>Signature</dt><dd><img className="portal-revisao-assinatura" src={assinatura} alt={`Signature drawn by ${r.typed_name}`} /></dd>
      <dt>Valid until</dt><dd>{dataUS(r.valid_until)} ({r.valid_until_reason})</dd>
    </dl>
    {!r.name_matches && <div className="banner warn" role="status"><span className="bi" aria-hidden="true">▲</span><div className="grow stack" style={{ gap: 6 }}>
      <span>The name you typed (<b>{r.typed_name}</b>) is different from the name on file (<b>{r.name_on_file}</b>).
        If that is a mistake, go back and fix it.</span>
      <label className="check portal-revisao-nome"><input type="checkbox" checked={nomeConfirmado} onChange={e => onNomeConfirmado(e.target.checked)} />
        Yes, sign with the name I typed: {r.typed_name}</label></div></div>}
    {codigo}
    {erro && <div className="banner crit" role="alert"><span className="bi" aria-hidden="true">✕</span><div className="grow">{erro}</div></div>}
    <p className="small" id="rv-efeito" style={{ margin: 0 }}>{r.legal_effect}</p>
    <div className="row wrap portal-revisao-acoes" style={{ gap: 8 }}>
      <button type="button" className="btn ghost" disabled={indo} onClick={onVoltar}>Go back</button>
      <button type="button" className="btn primary grow" aria-describedby="rv-efeito" disabled={indo || falta || !podeAssinar} onClick={onAssinar}>
        {indo ? 'Signing…' : r.button}</button>
    </div>
  </section>
}
