/* Estoque — o que existe, onde está e de quem é.
 *
 * Duas decisões do dono mandam nesta tela:
 *   22/09: chassi e motor têm ficha com número de série; pneu e peça são quantidade.
 *   23/09: "o acesso de mecânico consiga, ao clicar em estoque, ter um botão de
 *          adicionar; aí ele consegue colocar foto, descrição, nome e quantidade".
 *
 * Por isso o botão Adicionar é a primeira coisa da página, e não um item escondido num
 * menu de três pontinhos: quem está na prateleira com o celular na mão é quem cadastra.
 */
import { useMemo, useRef, useState } from 'react'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Kpi, Loading, PageHeader, Scrim, Section } from '../components/ui'
import { Icon } from '../components/Icon'
import { useToast } from '../components/Toast'

interface ItemEstoque {
  id: number; name: string; kind: string; tracking: string; unit: string
  min_qty: number | null; sku: string | null; supplier_url: string | null
  notes: string | null; tem_foto: boolean
  total: number; nosso: number; de_clientes: number; abaixo: boolean
}
interface Repor { id: number; name: string; unit: string; falta: number; sku: string | null; supplier_url: string | null }
interface Local { id: number; code: string; name: string }
interface Lista { itens: ItemEstoque[]; locais: Local[]; repor: Repor[]; divergencias: unknown[] }

const TIPO_ROTULO: Record<string, string> = { peca: 'peça', pneu: 'pneu', motor: 'motor', chassi: 'chassi' }

/** O formulário que o dono pediu: nome, descrição, quantidade e foto. Nada além. */
function Adicionar({ locais, onClose, reload }: { locais: Local[]; onClose: () => void; reload: () => void }) {
  const toast = useToast()
  const [nome, setNome] = useState('')
  const [tipo, setTipo] = useState('peca')
  const [unidade, setUnidade] = useState('un')
  const [descricao, setDescricao] = useState('')
  const [qtd, setQtd] = useState('')
  const [minimo, setMinimo] = useState('')
  const [local, setLocal] = useState(locais[0]?.code || 'sede')
  const [foto, setFoto] = useState<File | null>(null)
  const [previa, setPrevia] = useState<string | null>(null)
  const [salvando, setSalvando] = useState(false)
  const arquivo = useRef<HTMLInputElement>(null)
  const serie = tipo === 'motor' || tipo === 'chassi'

  function escolher(f: File | null) {
    setFoto(f)
    setPrevia(p => { if (p) URL.revokeObjectURL(p); return f ? URL.createObjectURL(f) : null })
  }

  async function salvar() {
    if (!nome.trim()) { toast('A peça precisa de um nome.', 'warn'); return }
    setSalvando(true)
    try {
      const fd = new FormData()
      fd.append('name', nome.trim())
      fd.append('kind', tipo)
      fd.append('unit', unidade)
      fd.append('local', local)
      if (descricao.trim()) fd.append('notes', descricao.trim())
      if (qtd.trim() && !serie) fd.append('qty', qtd.trim())
      if (minimo.trim() && !serie) fd.append('min_qty', minimo.trim())
      if (foto) fd.append('foto', foto)
      const res = await api.postForm<{ id: number; aviso: string | null }>('/estoque/item', fd)
      toast(res.aviso || `${nome.trim()} cadastrado.`, res.aviso ? 'warn' : 'ok')
      reload(); onClose()
    } catch (e) {
      toast((e as ApiError).message, 'crit')
    } finally { setSalvando(false) }
  }

  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 560 }} onMouseDown={e => e.stopPropagation()}>
    <h3>Adicionar ao estoque</h3>
    <p className="small muted">O que está na prateleira agora. A quantidade entra como contagem —
      você está dizendo quanto tem hoje, não registrando uma compra.</p>

    <label className="fld"><span>Nome da peça</span>
      <input value={nome} onChange={e => setNome(e.target.value)} placeholder="Pastilha de freio Tonykart" autoFocus /></label>

    <label className="fld"><span>Descrição <i className="muted">(onde fica, para que serve, qual kart)</i></span>
      <textarea value={descricao} onChange={e => setDescricao(e.target.value)} rows={2}
                placeholder="Prateleira A. Serve no OTK do Savage e no Parolin." /></label>

    <div className="row gap">
      <label className="fld grow"><span>Tipo</span>
        <select value={tipo} onChange={e => { setTipo(e.target.value); setUnidade(e.target.value === 'pneu' ? 'jogo' : 'un') }}>
          <option value="peca">peça</option><option value="pneu">pneu</option>
          <option value="motor">motor</option><option value="chassi">chassi</option>
        </select></label>
      <label className="fld grow"><span>Unidade</span>
        <input value={unidade} onChange={e => setUnidade(e.target.value)} placeholder="un, jogo, litro" /></label>
    </div>

    {serie
      ? <Banner tone="info">Motor e chassi têm ficha individual, com número de série — um por um,
        para você saber qual está no trailer. Cadastre aqui e depois dê entrada de cada unidade.</Banner>
      : <div className="row gap">
        <label className="fld grow"><span>Quantidade que temos</span>
          <input type="number" inputMode="decimal" value={qtd} onChange={e => setQtd(e.target.value)} placeholder="6" /></label>
        <label className="fld grow"><span>Avisar quando faltar <i className="muted">(mínimo)</i></span>
          <input type="number" inputMode="decimal" value={minimo} onChange={e => setMinimo(e.target.value)} placeholder="4" /></label>
        {locais.length > 1 && <label className="fld grow"><span>Onde</span>
          <select value={local} onChange={e => setLocal(e.target.value)}>
            {locais.map(l => <option key={l.code} value={l.code}>{l.name}</option>)}
          </select></label>}
      </div>}

    <label className="fld"><span>Foto</span>
      <input ref={arquivo} type="file" accept="image/png,image/jpeg,image/webp" capture="environment"
             onChange={e => escolher(e.target.files?.[0] || null)} /></label>
    {previa && <div className="row gap" style={{ alignItems: 'center' }}>
      <img src={previa} alt="prévia da foto" style={{ width: 84, height: 84, objectFit: 'cover', borderRadius: 10 }} />
      <button className="btn ghost" onClick={() => { escolher(null); if (arquivo.current) arquivo.current.value = '' }}>Tirar a foto</button>
    </div>}

    <div className="modal-foot">
      <button className="btn ghost" onClick={onClose}>Cancelar</button>
      <button className="btn" disabled={salvando || !nome.trim()} onClick={salvar}>
        {salvando ? 'Salvando…' : 'Adicionar'}</button>
    </div>
  </div></Scrim>
}

export function Estoque() {
  const { can } = useAuth()
  const lista = useGet<Lista>('/estoque')
  const [abrir, setAbrir] = useState(false)
  const [busca, setBusca] = useState('')
  const d = lista.data

  const itens = useMemo(() => {
    const t = busca.trim().toLowerCase()
    return (d?.itens || []).filter(i => !t || i.name.toLowerCase().includes(t) || (i.sku || '').toLowerCase().includes(t))
  }, [d, busca])

  const deClientes = (d?.itens || []).filter(i => i.de_clientes > 0)

  return <>
    <PageHeader title="Estoque" help="O que existe, onde está e de quem é. Peça de cliente nunca sai para outro.">
      {can('OPERATOR') && <button className="btn" onClick={() => setAbrir(true)}>
        <Icon name="plus" size={16} /> Adicionar</button>}
    </PageHeader>

    {lista.error && <ErrorState error={lista.error} retry={lista.reload} />}
    {lista.loading && !d && <Loading />}

    {d && <>
      <div className="kpis">
        <Kpi label="Itens cadastrados" value={d.itens.length} lead />
        <Kpi label="Precisa repor" value={d.repor.length} tone={d.repor.length ? 'warn' : undefined}
             foot={d.repor.length ? 'abaixo do mínimo' : 'nada faltando'} />
        <Kpi label="De clientes, com a gente" value={deClientes.length}
             foot={deClientes.length ? 'não é nosso para vender' : undefined} />
      </div>

      {!!d.divergencias.length && <Banner tone="crit">
        {d.divergencias.length} saldo(s) não batem com o histórico de movimentos. Alguém mexeu
        no banco por fora, ou há defeito. Vale conferir antes de confiar nos números.</Banner>}

      {!!d.repor.length && <Section title="Precisa comprar" count={d.repor.length}>
        <div className="tbl">
          {d.repor.map(r => <div className="tr" key={r.id}>
            <div className="grow"><b>{r.name}</b>{r.sku && <span className="small muted"> · SKU {r.sku}</span>}</div>
            <Chip tone="warn">faltam {r.falta} {r.unit}</Chip>
            {r.supplier_url && <a className="btn ghost sm" href={r.supplier_url} target="_blank" rel="noreferrer">ver no fornecedor</a>}
          </div>)}
        </div>
      </Section>}

      <Section title="Na prateleira" count={itens.length} right={
        <input className="inp sm" placeholder="Buscar peça ou SKU" value={busca} onChange={e => setBusca(e.target.value)} />}>
        {!itens.length
          ? <Empty title={busca ? 'Nada com esse nome' : 'O estoque está vazio'}>
            {!busca && <>Use <b>Adicionar</b> para cadastrar o que está na prateleira.</>}</Empty>
          : <div className="tbl">
            {itens.map(i => <div className="tr" key={i.id}>
              {i.tem_foto
                ? <img src={`/ops/api/estoque/item/${i.id}/foto`} alt="" style={{ width: 40, height: 40, objectFit: 'cover', borderRadius: 8 }} />
                : <span className="avatar sq" aria-hidden="true"><Icon name="box" size={18} /></span>}
              <div className="grow">
                <b>{i.name}</b> <span className="small muted">{TIPO_ROTULO[i.kind] || i.kind}</span>
                {i.notes && <div className="small muted truncate">{i.notes}</div>}
              </div>
              {i.de_clientes > 0 && <Chip tone="info" title="peça de cliente guardada com a gente">
                {i.de_clientes} de cliente</Chip>}
              <Chip tone={i.abaixo ? 'warn' : i.nosso > 0 ? 'ok' : 'neutral'}>
                {i.nosso} {i.unit}{i.min_qty ? ` · mín ${i.min_qty}` : ''}</Chip>
            </div>)}
          </div>}
      </Section>
    </>}

    {abrir && d && <Adicionar locais={d.locais} onClose={() => setAbrir(false)} reload={lista.reload} />}
  </>
}
