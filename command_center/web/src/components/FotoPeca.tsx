import { useRef, type ChangeEvent } from 'react'
import { Icon } from './Icon'
import { tr } from '../i18n'

/** Foto da peça pelo celular: tirar na hora (câmera) ou escolher da galeria (dono, 06/10).
 *  `capture` abre direto a câmera e, no Android, esconde a galeria — por isso são dois campos. */
export function FotoPeca({ previa, onFile, rotulo = tr("Foto da peça") }: { previa: string | null; onFile: (f: File | null) => void; rotulo?: string }) {
  const camera = useRef<HTMLInputElement>(null)
  const galeria = useRef<HTMLInputElement>(null)
  const escolheu = (e: ChangeEvent<HTMLInputElement>) => { onFile(e.target.files?.[0] || null); e.target.value = '' }
  return <div className="foto-peca">
    <div className="foto-btn" aria-hidden={!previa}>
      {previa ? <img src={previa} alt={tr("imagem da peça")} /> : <><Icon name="box" size={22} /> {rotulo}</>}
    </div>
    <div className="row" style={{ gap: 8 }}>
      <button type="button" className="btn grow" onClick={() => camera.current?.click()}>{tr("Tirar foto")}</button>
      <button type="button" className="btn ghost grow" onClick={() => galeria.current?.click()}>{tr("Escolher da galeria")}</button>
    </div>
    <input ref={camera} type="file" accept="image/png,image/jpeg,image/webp" capture="environment" hidden aria-label={tr("Tirar foto da peça")} onChange={escolheu} />
    <input ref={galeria} type="file" accept="image/png,image/jpeg,image/webp" hidden aria-label={tr("Escolher foto da galeria")} onChange={escolheu} />
  </div>
}
