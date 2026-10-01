/* O lado da pista do login (redesenho aprovado em 17/09). O mesmo desenho serve à equipe
 * (Command Center) e ao cliente (área do cliente): dono, 01/10 — "mesmo desenho, mesmo layout". */
import { useState } from 'react'

/** O lado da pista: a foto quando existe; um fundo de asfalto quando ainda não foi colocada. */
export function Pista() {
  const [semFoto, setSemFoto] = useState(false)
  return <div className="pista" aria-hidden="true">
    {/* issue #21: WebP de 1600 px (142 KB, 60% menor que o JPG de 363 KB); o JPG fica para navegador antigo.
        É a maior imagem da tela de login — o LCP dela —, então vai com prioridade alta. */}
    {!semFoto && <picture>
      <source srcSet={`${import.meta.env.BASE_URL}pista.webp`} type="image/webp" />
      <img className="foto-pista" src={`${import.meta.env.BASE_URL}pista.jpg`} alt="" width={1600} height={1070}
        fetchPriority="high" decoding="async" onError={() => setSemFoto(true)} />
    </picture>}
    {semFoto && <div className="tk"><i className="asf" /><i className="def" /></div>}
    <i className="veu" /><i className="brasa" /><i className="grao" />
  </div>
}

