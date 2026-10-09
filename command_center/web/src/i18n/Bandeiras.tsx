/* O seletor de idioma (#177): bandeira do Brasil (português) e dos Estados Unidos (inglês), no
 * topo de toda página. Bandeiras em SVG próprio: emoji de bandeira vira "BR"/"US" no Windows. */
import { idioma, mudarIdioma, type Idioma } from '.'

function Brasil() {
  return <svg viewBox="0 0 28 20" width="24" height="17" aria-hidden="true">
    <rect width="28" height="20" rx="2" fill="#009c3b" />
    <path d="M14 2.6 25.2 10 14 17.4 2.8 10Z" fill="#ffdf00" />
    <circle cx="14" cy="10" r="4.4" fill="#002776" />
    <path d="M9.8 9.1c2.8-.6 5.9-.2 8.3 1.3" stroke="#fff" strokeWidth=".9" fill="none" />
  </svg>
}

function EstadosUnidos() {
  const listras = Array.from({ length: 7 }, (_, i) => <rect key={i} y={i * 20 / 6.5} width="28" height={20 / 13} fill="#b22234" />)
  return <svg viewBox="0 0 28 20" width="24" height="17" aria-hidden="true">
    <rect width="28" height="20" rx="2" fill="#fff" />
    {listras}
    <rect width="12" height={20 * 7 / 13} fill="#3c3b6e" />
    {Array.from({ length: 12 }, (_, i) => <circle key={i} cx={1.6 + (i % 4) * 2.9} cy={1.8 + Math.floor(i / 4) * 3.4} r=".55" fill="#fff" />)}
  </svg>
}

const OPCOES: { id: Idioma; nome: string; Bandeira: () => React.JSX.Element }[] = [
  { id: 'pt', nome: 'Português', Bandeira: Brasil },
  { id: 'en', nome: 'English', Bandeira: EstadosUnidos },
]

export function Bandeiras({ className = '' }: { className?: string }) {
  const atual = idioma()
  return <div className={`bandeiras ${className}`} role="group" aria-label={atual === 'en' ? 'Language' : 'Idioma'}>
    {OPCOES.map(({ id, nome, Bandeira }) =>
      <button key={id} type="button" className="bandeira" aria-pressed={atual === id} aria-label={nome} title={nome}
        onClick={() => mudarIdioma(id)}><Bandeira /></button>)}
  </div>
}
