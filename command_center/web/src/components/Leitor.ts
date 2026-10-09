/* O leitor de código pela câmera (#87, #180): o nativo do Chrome (BarcodeDetector) ou, no
 * iPhone, o ZXing em JavaScript puro — carregado só quando a câmera abre. Usado pelo Balcão do
 * painel e pelo balcão do celular. */
import { useEffect, useRef, useState, type RefObject } from 'react'
import { tr } from '../i18n'

export type Detector = { detect: (v: HTMLVideoElement) => Promise<{ rawValue: string }[]> }
const BD = typeof window === 'undefined' ? undefined
  : (window as unknown as { BarcodeDetector?: new (o: { formats: string[] }) => Detector }).BarcodeDetector
/** Em http (sem TLS) o navegador nem oferece a câmera: mediaDevices some. */
export const temCamera = () => typeof navigator !== 'undefined' && 'mediaDevices' in navigator && typeof navigator.mediaDevices.getUserMedia === 'function'
const FORMATOS = ['qr_code', 'ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128', 'code_39', 'itf']
export const vibrar = (ms: number | number[]) => { try { navigator.vibrate?.(ms) } catch { /* sem vibração */ } }

async function detectorZxing(): Promise<Detector> {
  const [{ BrowserMultiFormatReader }, { BarcodeFormat, DecodeHintType }] = await Promise.all([import('@zxing/browser'), import('@zxing/library')])
  const hints = new Map([[DecodeHintType.POSSIBLE_FORMATS, [BarcodeFormat.QR_CODE, BarcodeFormat.EAN_13, BarcodeFormat.EAN_8,
    BarcodeFormat.UPC_A, BarcodeFormat.UPC_E, BarcodeFormat.CODE_128, BarcodeFormat.CODE_39, BarcodeFormat.ITF]]])
  const leitor = new BrowserMultiFormatReader(hints)
  const tela = document.createElement('canvas')
  return {
    async detect(v) {
      if (!v.videoWidth) return []
      tela.width = v.videoWidth; tela.height = v.videoHeight
      tela.getContext('2d', { willReadFrequently: true })?.drawImage(v, 0, 0)
      try { return [{ rawValue: leitor.decodeFromCanvas(tela).getText() }] } catch { return [] }   // quadro sem código
    },
  }
}

export function novoDetector(): Promise<Detector> {
  return BD ? Promise.resolve(new BD({ formats: FORMATOS })) : detectorZxing()
}

/** A câmera de trás ligada no `video` enquanto o componente existir; lê só quando `ativo`.
 *  Cada código lido chama `onLer` (uma vez por leitura; quem chama decide se pausa). */
export function useLeitor(video: RefObject<HTMLVideoElement | null>, ativo: boolean, onLer: (t: string) => void) {
  const [erro, setErro] = useState<string | null>(temCamera() ? null
    : tr("Este navegador não abre a câmera aqui. Abra o painel pelo endereço https e permita a câmera."))
  const [pronto, setPronto] = useState(false)
  const ativoRef = useRef(ativo)
  const lerRef = useRef(onLer)
  useEffect(() => { ativoRef.current = ativo }, [ativo])
  useEffect(() => { lerRef.current = onLer }, [onLer])
  useEffect(() => {
    let parar = false, stream: MediaStream | null = null
    if (!temCamera()) return
    ;(async () => {
      try {
        const [det, s] = await Promise.all([novoDetector(), navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })])
        stream = s
        if (parar || !video.current) { s.getTracks().forEach(t => t.stop()); return }
        video.current.srcObject = s; await video.current.play(); setPronto(true)
        while (!parar) {
          if (ativoRef.current && video.current) {
            try { const r = await det.detect(video.current); if (r[0]?.rawValue && ativoRef.current) lerRef.current(r[0].rawValue) } catch { /* quadro ruim */ }
          }
          await new Promise(ok => setTimeout(ok, 150))
        }
      } catch (e) {
        if (!parar) setErro((e as Error)?.name === 'NotAllowedError'
          ? tr("A câmera foi negada. Libere a câmera para este site nas configurações do navegador e tente de novo.")
          : tr("Não deu para abrir a câmera."))
      }
    })()
    return () => { parar = true; stream?.getTracks().forEach(t => t.stop()) }
  }, [video])
  return { erro, pronto }
}
