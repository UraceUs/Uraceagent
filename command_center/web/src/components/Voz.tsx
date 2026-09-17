/* Voz no painel (dono, 17/09): "para a gente não ficar precisando digitar".
 *
 * Ditado: reconhecimento de fala do próprio navegador (Chrome, Edge, Safari 14.5+).
 * Não sai do aparelho para nenhum servidor nosso e não precisa de chave nova.
 * Fala: a resposta da IA pode ser lida em voz alta (o mesmo motor do navegador).
 *
 * Onde o navegador não tem o recurso, o botão não aparece — nada quebra.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Icon } from './Icon'

type Rec = {
  lang: string; continuous: boolean; interimResults: boolean
  start: () => void; stop: () => void; abort: () => void
  onresult: ((e: { resultIndex: number; results: { length: number;[i: number]: { isFinal: boolean;[j: number]: { transcript: string } } } }) => void) | null
  onerror: ((e: { error?: string }) => void) | null
  onend: (() => void) | null
}
type ComRec = { SpeechRecognition?: new () => Rec; webkitSpeechRecognition?: new () => Rec }

function Motor(): (new () => Rec) | null {
  const w = window as unknown as ComRec
  return w.SpeechRecognition || w.webkitSpeechRecognition || null
}
export const temDitado = () => !!Motor()
export const temFala = () => typeof window !== 'undefined' && 'speechSynthesis' in window

/** Lê um texto em voz alta (pt-BR quando houver voz instalada). Chamar de novo troca a fala. */
export function falar(texto: string) {
  if (!temFala() || !texto.trim()) return
  const s = window.speechSynthesis
  s.cancel()
  const f = new SpeechSynthesisUtterance(texto.replace(/\s+/g, ' ').slice(0, 4000))
  const vozes = s.getVoices()
  const pt = vozes.find(v => /pt.?BR/i.test(v.lang)) || vozes.find(v => /^pt/i.test(v.lang))
  if (pt) f.voice = pt
  f.lang = pt?.lang || 'pt-BR'
  f.rate = 1.03
  s.speak(f)
}
export const calar = () => { if (temFala()) window.speechSynthesis.cancel() }

/** Ditado: devolve o que já foi reconhecido (parcial e final) enquanto o microfone está ligado. */
export function useDitado(aoFinal?: (texto: string) => void) {
  const [ligado, setLigado] = useState(false)
  const [parcial, setParcial] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  const rec = useRef<Rec | null>(null)
  const cb = useRef(aoFinal)
  useEffect(() => { cb.current = aoFinal }, [aoFinal])

  const parar = useCallback(() => { try { rec.current?.stop() } catch { /* já parado */ } setLigado(false) }, [])

  const ligar = useCallback(() => {
    const M = Motor()
    if (!M) { setErro('Este navegador não tem ditado. No celular use o microfone do teclado; no computador, o Chrome.'); return }
    setErro(null)
    const r = new M()
    r.lang = 'pt-BR'
    r.continuous = true
    r.interimResults = true
    r.onresult = e => {
      let fim = '', meio = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript
        if (e.results[i].isFinal) fim += t
        else meio += t
      }
      if (meio) setParcial(meio)
      if (fim.trim()) { setParcial(''); cb.current?.(fim.trim()) }
    }
    r.onerror = e => {
      const k = e?.error || ''
      setErro(k === 'not-allowed' || k === 'service-not-allowed'
        ? 'O navegador bloqueou o microfone. Libere o microfone para este site e tente de novo.'
        : k === 'no-speech' ? null : `Ditado parou (${k || 'erro'}).`)
      setLigado(false)
    }
    r.onend = () => { setLigado(false); setParcial('') }
    rec.current = r
    try { r.start(); setLigado(true) } catch { setLigado(false) }
  }, [])

  useEffect(() => () => { try { rec.current?.abort() } catch { /* nada */ } }, [])
  return { ligado, parcial, erro, ligar, parar, alternar: () => (ligado ? parar() : ligar()), disponivel: temDitado() }
}

/** Botão de microfone: cola o que for falado no fim do texto que já está no campo. */
export function Mic({ valor, onTexto, titulo, className }: { valor: string; onTexto: (t: string) => void; titulo?: string; className?: string }) {
  const base = useRef(valor)
  const d = useDitado(t => { base.current = (base.current ? base.current.replace(/\s*$/, ' ') : '') + t; onTexto(base.current) })
  useEffect(() => { if (!d.ligado) base.current = valor }, [valor, d.ligado])
  if (!d.disponivel) return null
  return <button type="button" className={`mic${d.ligado ? ' on' : ''}${className ? ' ' + className : ''}`} onClick={d.alternar}
    title={d.erro || titulo || (d.ligado ? 'Parar de ditar' : 'Ditar (falar em vez de digitar)')}
    aria-label={d.ligado ? 'Parar de ditar' : 'Ditar'} aria-pressed={d.ligado}>
    <Icon name="mic" size={16} />{d.ligado && <i className="onda" aria-hidden="true"><i /><i /><i /></i>}
  </button>
}

/** Campo de texto com microfone embutido: é o que usamos em todo lugar que se digita muito. */
export function TextoComVoz({ valor, onChange, linhas = 3, placeholder, disabled, onEnter, autoFocus, id }: {
  valor: string; onChange: (t: string) => void; linhas?: number; placeholder?: string
  disabled?: boolean; onEnter?: () => void; autoFocus?: boolean; id?: string
}) {
  const d = useDitado(t => onChange((valor ? valor.replace(/\s*$/, ' ') : '') + t))
  return <div className={`vozwrap${d.ligado ? ' ditando' : ''}`}>
    <textarea id={id} className="input" rows={linhas} value={valor + (d.parcial ? (valor ? ' ' : '') + d.parcial : '')}
      placeholder={placeholder} disabled={disabled} autoFocus={autoFocus}
      onChange={e => onChange(e.target.value)}
      onKeyDown={e => { if (onEnter && e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); onEnter() } }} />
    {d.disponivel && <button type="button" className={`mic dentro${d.ligado ? ' on' : ''}`} onClick={d.alternar} disabled={disabled}
      title={d.erro || (d.ligado ? 'Parar de ditar' : 'Ditar')} aria-label="Ditar" aria-pressed={d.ligado}>
      <Icon name="mic" size={16} />{d.ligado && <i className="onda" aria-hidden="true"><i /><i /><i /></i>}
    </button>}
    {d.erro && <div className="small" style={{ color: 'var(--warn)', marginTop: 4 }}>{d.erro}</div>}
  </div>
}

/** Botão "ouvir": lê um texto em voz alta e para quando clicado de novo. */
export function Ouvir({ texto, titulo }: { texto: string; titulo?: string }) {
  const [falando, setFalando] = useState(false)
  useEffect(() => {
    if (!temFala()) return
    const t = setInterval(() => setFalando(window.speechSynthesis.speaking), 500)
    return () => clearInterval(t)
  }, [])
  if (!temFala() || !texto.trim()) return null
  return <button type="button" className={`mic sm${falando ? ' on' : ''}`} title={titulo || 'Ouvir em voz alta'} aria-label="Ouvir"
    onClick={() => { if (window.speechSynthesis.speaking) { calar(); setFalando(false) } else { falar(texto); setFalando(true) } }}>
    <Icon name={falando ? 'x' : 'som'} size={15} />
  </button>
}
