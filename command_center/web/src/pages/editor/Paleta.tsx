/* Editor do site como o Canva (#315): o que dá para pôr na página. No computador, arraste uma peça até a prévia
 * (a linha azul mostra onde cai) ou clique para pôr depois do que está selecionado. No celular, toque na peça e
 * depois toque na prévia onde quer pôr. */
import type { PointerEvent as PE } from 'react'
import { tr } from '../../i18n'
import { nomeDaPeca, PALETA, type Peca } from './modelo'

export function Paleta({ aoEscolher, aoArrastar, estreito }: { aoEscolher: (p: Peca) => void; aoArrastar: (p: Peca, e: PE<HTMLButtonElement>) => void; estreito: boolean }) {
  const botao = (p: Peca) => <button key={p} type="button" className="btn ed-peca" onPointerDown={e => aoArrastar(p, e)} onClick={() => aoEscolher(p)}>
    {nomeDaPeca(p)}</button>
  return <div className="stack" style={{ gap: 10 }}>
    <p className="small muted" style={{ margin: 0 }}>{estreito ? tr("Toque numa peça e depois toque na página onde quer pôr.")
      : tr("Arraste uma peça até a página (a linha azul mostra onde cai), ou clique para pôr depois do que está selecionado.")}</p>
    <div className="ed-paleta-grade">{PALETA.map(botao)}</div>
    <h3 className="h3" style={{ margin: 0 }}>{tr("Seções")}</h3>
    <div className="ed-paleta-grade">{(['secao1', 'secao2', 'secao3'] as Peca[]).map(botao)}</div>
    <p className="small muted" style={{ margin: 0 }}>{tr("Fotos: solte um arquivo do computador direto na página, ou numa imagem para trocar a foto dela.")}</p>
  </div>
}
