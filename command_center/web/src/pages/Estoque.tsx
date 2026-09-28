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
import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
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
  contado: boolean; ultima_contagem: string | null
}
interface Repor { id: number; name: string; unit: string; falta: number; sku: string | null; supplier_url: string | null }
interface Local { id: number; code: string; name: string }
interface Lista { itens: ItemEstoque[]; locais: Local[]; repor: Repor[]; divergencias: unknown[]; a_contar: number[] }
interface Movimento { id: number; kind: string; qty: number; qty_before: number | null; qty_after: number | null
  reason: string | null; notes: string | null; at: string; quem: string | null; de_nome: string | null; para_nome: string | null }
interface Ficha { item: ItemEstoque & { supplier: string | null }; total: number; nosso: number
  saldos: { local: string; qty: number; cliente: string | null }[]; movimentos: Movimento[] }
interface Sugestao { sku: string; name: string; url: string | null; price: number | null; brand: string | null; score: number }

const MOV_ROTULO: Record<string, string> = { entrada: 'entrada', saida: 'saída', ajuste: 'ajuste', transferencia: 'transferência', contagem: 'contagem' }

function quando(iso: string | null) {
  if (!iso) return '—'
  return `${iso.slice(8, 10)}/${iso.slice(5, 7)} ${iso.slice(11, 16)}`
}

/** Contar a prateleira — o que tira o estoque do zero.
 *  Em branco é "não contei" e fica como está; zero é "contei e não tem". A gravação é tudo
 *  ou nada: se uma linha não serve, nenhuma entra e a mensagem diz qual. */
function Contar({ d, onClose, reload }: { d: Lista; onClose: () => void; reload: () => void }) {
  const toast = useToast()
  const [local, setLocal] = useState(d.locais[0]?.code || 'sede')
  const [so, setSo] = useState(d.a_contar.length > 0)
  const [busca, setBusca] = useState('')
  const [qtd, setQtd] = useState<Record<number, string>>({})
  const [salvando, setSalvando] = useState(false)
  const nunca = useMemo(() => new Set(d.a_contar), [d])
  const lista = d.itens.filter(i => i.tracking === 'quantidade')
    .filter(i => !so || nunca.has(i.id))
    .filter(i => !busca.trim() || i.name.toLowerCase().includes(busca.trim().toLowerCase()))
  const preenchidas = Object.entries(qtd).filter(([, v]) => v.trim() !== '')

  async function salvar() {
    const itens = preenchidas.map(([id, v]) => ({ item_id: Number(id), qty: Number(v.replace(',', '.')) }))
    if (itens.some(i => Number.isNaN(i.qty) || i.qty < 0)) { toast('Quantidade precisa ser um número, zero ou mais.', 'warn'); return }
    setSalvando(true)
    try {
      const r = await api.post<{ contados: number; com_diferenca: { name: string; antes: number; depois: number }[] }>(
        '/estoque/contagem', { local, itens })
      const dif = r.com_diferenca.length
      toast(`${r.contados} contagem(ns) gravada(s)` + (dif ? ` · ${dif} com diferença do que o painel tinha` : ''), 'ok')
      reload(); onClose()
    } catch (e) {
      toast((e as ApiError).message, 'crit')
    } finally { setSalvando(false) }
  }

  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 620 }} onMouseDown={e => e.stopPropagation()}>
    <h3>Contar prateleira</h3>
    <p className="small muted">Digite quanto tem de cada peça. <b>Em branco fica como está</b>; zero quer dizer
      "contei e não tem". Nada é gravado até você salvar.</p>
    <div className="row gap wrap">
      {d.locais.length > 1 && <label className="fld grow"><span>Onde você está contando</span>
        <select value={local} onChange={e => setLocal(e.target.value)}>
          {d.locais.map(l => <option key={l.code} value={l.code}>{l.name}</option>)}
        </select></label>}
      <label className="fld grow"><span>Buscar</span>
        <input value={busca} onChange={e => setBusca(e.target.value)} placeholder="nome da peça" /></label>
    </div>
    {!!d.a_contar.length && <label className="check small"><input type="checkbox" checked={so} onChange={e => setSo(e.target.checked)} />
      só as {d.a_contar.length} que nunca foram contadas</label>}
    <div className="tbl" style={{ maxHeight: '52vh', overflow: 'auto' }}>
      {!lista.length && <Empty title="Nada para contar aqui" />}
      {lista.map(i => <label className="tr" key={i.id} style={{ cursor: 'text' }}>
        <div className="grow"><b>{i.name}</b>
          <div className="small muted">{nunca.has(i.id) ? 'nunca contada' : `painel diz ${i.nosso} ${i.unit}`}{i.min_qty ? ` · mín ${i.min_qty}` : ''}</div></div>
        <input className="inp sm" style={{ width: 90, textAlign: 'right' }} type="number" inputMode="decimal" min={0}
               value={qtd[i.id] ?? ''} placeholder={i.unit} aria-label={`quantidade de ${i.name}`}
               onChange={e => setQtd(q => ({ ...q, [i.id]: e.target.value }))} />
      </label>)}
    </div>
    <div className="modal-foot">
      <span className="small muted grow">{preenchidas.length ? `${preenchidas.length} preenchida(s)` : 'nenhuma preenchida'}</span>
      <button className="btn ghost" onClick={onClose}>Cancelar</button>
      <button className="btn" disabled={salvando || !preenchidas.length} onClick={salvar}>
        {salvando ? 'Salvando…' : `Salvar contagem`}</button>
    </div>
  </div></Scrim>
}

/** Mexer numa peça: chegou, usei, levei para o trailer. Cada botão é um movimento no razão. */
function Mover({ ficha, locais, onDone }: { ficha: Ficha; locais: Local[]; onDone: () => void }) {
  const toast = useToast()
  const [tipo, setTipo] = useState<'entrada' | 'saida' | 'transferir'>('saida')
  const [qtd, setQtd] = useState('')
  const [de, setDe] = useState(locais[0]?.code || 'sede')
  const [para, setPara] = useState(locais[1]?.code || 'trailer')
  const [nota, setNota] = useState('')
  const [indo, setIndo] = useState(false)
  if (ficha.item.tracking !== 'quantidade') return <p className="small muted">Motor e chassi andam por unidade (número de série).</p>

  async function enviar() {
    const q = Number(qtd.replace(',', '.'))
    if (!q || q <= 0) { toast('Informe a quantidade.', 'warn'); return }
    setIndo(true)
    try {
      const corpo = { item_id: ficha.item.id, qty: q, local: de, para, nota: nota.trim() || null,
                      motivo: tipo === 'entrada' ? 'compra' : tipo === 'saida' ? 'uso em serviço' : null }
      await api.post(`/estoque/${tipo}`, corpo)
      toast(tipo === 'entrada' ? 'Entrada registrada.' : tipo === 'saida' ? 'Saída registrada.' : 'Transferência registrada.', 'ok')
      setQtd(''); setNota(''); onDone()
    } catch (e) {
      toast((e as ApiError).message, 'crit')
    } finally { setIndo(false) }
  }

  return <div>
    <div className="row gap wrap">
      {(['saida', 'entrada', 'transferir'] as const).map(t => <button key={t} className={`btn sm${tipo === t ? '' : ' ghost'}`} onClick={() => setTipo(t)}>
        {t === 'saida' ? 'Usei em serviço' : t === 'entrada' ? 'Chegou (compra)' : 'Levar para outro local'}</button>)}
    </div>
    <div className="row gap wrap">
      <label className="fld grow"><span>Quantidade</span>
        <input type="number" inputMode="decimal" min={0} value={qtd} onChange={e => setQtd(e.target.value)} placeholder={ficha.item.unit} /></label>
      {locais.length > 1 && <label className="fld grow"><span>{tipo === 'entrada' ? 'Para' : 'De'}</span>
        <select value={de} onChange={e => setDe(e.target.value)}>{locais.map(l => <option key={l.code} value={l.code}>{l.name}</option>)}</select></label>}
      {tipo === 'transferir' && <label className="fld grow"><span>Para</span>
        <select value={para} onChange={e => setPara(e.target.value)}>{locais.map(l => <option key={l.code} value={l.code}>{l.name}</option>)}</select></label>}
    </div>
    <label className="fld"><span>Nota <i className="muted">(qual kart, qual cliente, nota fiscal)</i></span>
      <input value={nota} onChange={e => setNota(e.target.value)} /></label>
    <button className="btn" disabled={indo || !qtd} onClick={enviar}>{indo ? 'Registrando…' : 'Registrar'}</button>
  </div>
}

/** Ligar a peça ao catálogo da Comet: a máquina sugere, gente escolhe (SKU é o que compras vai pedir). */
function LigarSku({ ficha, onDone }: { ficha: Ficha; onDone: () => void }) {
  const { can } = useAuth()
  const toast = useToast()
  const sug = useGet<{ tem_catalogo: boolean; sugestoes: Sugestao[] }>(`/estoque/item/${ficha.item.id}/sku-sugestoes`)
  const [indo, setIndo] = useState<string | null>(null)
  async function ligar(sku: string) {
    setIndo(sku)
    try {
      await api.post(`/estoque/item/${ficha.item.id}/sku`, { sku })
      toast(`Ligada ao SKU ${sku}.`, 'ok'); onDone()
    } catch (e) {
      toast((e as ApiError).message, 'crit')
    } finally { setIndo(null) }
  }
  if (sug.loading && !sug.data) return <Loading rows={2} />
  if (sug.error) return <ErrorState error={sug.error} retry={sug.reload} />
  if (!sug.data?.tem_catalogo) return <p className="small muted">O catálogo do fornecedor ainda não foi importado neste painel.</p>
  if (!sug.data.sugestoes.length) return <p className="small muted">Nenhum produto do catálogo parece com o nome desta peça.</p>
  return <div className="tbl">
    {sug.data.sugestoes.map(x => <div className="tr" key={x.sku}>
      <div className="grow"><b>{x.name}</b>
        <div className="small muted">SKU {x.sku}{x.brand ? ` · ${x.brand}` : ''}{x.price ? ` · $${x.price.toFixed(2)}` : ''} · {Math.round(x.score * 100)}% das palavras</div></div>
      {x.url && <a className="btn ghost sm" href={x.url} target="_blank" rel="noreferrer">ver</a>}
      {ficha.item.sku === x.sku ? <Chip tone="ok">ligada</Chip>
        : can('MANAGER') && <button className="btn sm" disabled={!!indo} onClick={() => ligar(x.sku)}>{indo === x.sku ? '…' : 'É este'}</button>}
    </div>)}
    {!can('MANAGER') && <p className="small muted">Quem liga ao SKU é o gerente — o SKU decide o que se compra.</p>}
  </div>
}

function FichaPeca({ id, locais, onClose, reload }: { id: number; locais: Local[]; onClose: () => void; reload: () => void }) {
  const { can } = useAuth()
  const f = useGet<Ficha>(`/estoque/${id}`)
  const [aba, setAba] = useState<'historico' | 'mover' | 'sku'>('historico')
  const recarregar = () => { f.reload(); reload() }
  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 620 }} onMouseDown={e => e.stopPropagation()}>
    {f.error && <ErrorState error={f.error} retry={f.reload} />}
    {f.loading && !f.data && <Loading />}
    {f.data && <>
      <h3>{f.data.item.name}</h3>
      <p className="small muted">{TIPO_ROTULO[f.data.item.kind] || f.data.item.kind}
        {f.data.item.sku ? <> · SKU {f.data.item.sku}</> : ' · sem SKU'}
        {f.data.item.min_qty ? <> · mínimo {f.data.item.min_qty} {f.data.item.unit}</> : null}</p>
      <div className="row gap wrap">
        <Chip tone="neutral">nosso: {f.data.nosso} {f.data.item.unit}</Chip>
        {f.data.total !== f.data.nosso && <Chip tone="info">de clientes: {f.data.total - f.data.nosso}</Chip>}
        {f.data.saldos.map(sd => <Chip key={sd.local + (sd.cliente || '')} tone="outline">{sd.local}{sd.cliente ? ` (${sd.cliente})` : ''}: {sd.qty}</Chip>)}
      </div>
      <div className="row gap wrap" style={{ margin: '10px 0' }}>
        <button className={`btn sm${aba === 'historico' ? '' : ' ghost'}`} onClick={() => setAba('historico')}>Histórico</button>
        {can('OPERATOR') && <button className={`btn sm${aba === 'mover' ? '' : ' ghost'}`} onClick={() => setAba('mover')}>Movimentar</button>}
        <button className={`btn sm${aba === 'sku' ? '' : ' ghost'}`} onClick={() => setAba('sku')}>Catálogo da Comet</button>
      </div>
      {aba === 'historico' && (f.data.movimentos.length
        ? <div className="tbl" style={{ maxHeight: '40vh', overflow: 'auto' }}>
          {f.data.movimentos.map(m => <div className="tr" key={m.id}>
            <div className="grow"><b>{MOV_ROTULO[m.kind] || m.kind}</b> {m.qty} {f.data!.item.unit}
              {m.para_nome && m.de_nome ? ` · ${m.de_nome} → ${m.para_nome}` : m.para_nome ? ` · ${m.para_nome}` : m.de_nome ? ` · ${m.de_nome}` : ''}
              <div className="small muted">{quando(m.at)} · {m.quem || 'sistema'}{m.reason ? ` · ${m.reason}` : ''}{m.notes ? ` · ${m.notes}` : ''}</div></div>
            {m.qty_before !== null && m.qty_after !== null && <span className="small muted">{m.qty_before} → {m.qty_after}</span>}
          </div>)}
        </div>
        : <Empty title="Nunca foi contada">O zero desta peça é "ninguém contou", não "acabou".</Empty>)}
      {aba === 'mover' && <Mover ficha={f.data} locais={locais} onDone={recarregar} />}
      {aba === 'sku' && <LigarSku ficha={f.data} onDone={recarregar} />}
      <div className="modal-foot"><button className="btn ghost" onClick={onClose}>Fechar</button></div>
    </>}
  </div></Scrim>
}

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
  const [sp, setSp] = useSearchParams()
  const [contar, setContar] = useState(sp.get('contar') === '1')
  const [ficha, setFicha] = useState<number | null>(null)
  const [busca, setBusca] = useState('')
  const d = lista.data
  useEffect(() => { if (sp.get('contar') === '1') { sp.delete('contar'); setSp(sp, { replace: true }) } }, [sp, setSp])

  const itens = useMemo(() => {
    const t = busca.trim().toLowerCase()
    return (d?.itens || []).filter(i => !t || i.name.toLowerCase().includes(t) || (i.sku || '').toLowerCase().includes(t))
  }, [d, busca])

  const deClientes = (d?.itens || []).filter(i => i.de_clientes > 0)

  return <>
    <PageHeader title="Estoque" help="O que existe, onde está e de quem é. Peça de cliente nunca sai para outro.">
      {can('OPERATOR') && <button className="btn ghost" onClick={() => setContar(true)}>Contar prateleira</button>}
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
        <Kpi label="Nunca contadas" value={d.a_contar.length} tone={d.a_contar.length ? 'warn' : undefined}
             foot={d.a_contar.length ? 'zero aqui é "ninguém contou"' : 'todas já contadas'}
             onClick={d.a_contar.length && can('OPERATOR') ? () => setContar(true) : undefined} />
        <Kpi label="De clientes, com a gente" value={deClientes.length}
             foot={deClientes.length ? 'não é nosso para vender' : undefined} />
      </div>

      {!!d.a_contar.length && <Banner tone="warn">
        {d.a_contar.length} peça(s) nunca foram contadas. O zero delas é "ninguém contou", não "acabou" —
        por isso a lista "Precisa comprar" só vale depois da contagem.
        {can('OPERATOR') && <> <button className="btn sm" onClick={() => setContar(true)}>Contar agora</button></>}</Banner>}

      {!!d.divergencias.length && <Banner tone="crit">
        {d.divergencias.length} saldo(s) não batem com o histórico de movimentos. Alguém mexeu
        no banco por fora, ou há defeito. Vale conferir antes de confiar nos números.</Banner>}

      {!!d.repor.length && <Section title="Precisa comprar" count={d.repor.length}>
        <div className="tbl">
          {d.repor.map(r => <div className="tr" key={r.id}>
            <div className="grow"><b>{r.name}</b>{r.sku && <span className="small muted"> · SKU {r.sku}</span>}
              {d.a_contar.includes(r.id) && <span className="small muted"> · nunca contada</span>}</div>
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
            {itens.map(i => <div className="tr" key={i.id} role="button" tabIndex={0} style={{ cursor: 'pointer' }}
                                 onClick={() => setFicha(i.id)} onKeyDown={e => { if (e.key === 'Enter') setFicha(i.id) }}>
              {i.tem_foto
                ? <img src={`/ops/api/estoque/item/${i.id}/foto`} alt="" style={{ width: 40, height: 40, objectFit: 'cover', borderRadius: 8 }} />
                : <span className="avatar sq" aria-hidden="true"><Icon name="box" size={18} /></span>}
              <div className="grow">
                <b>{i.name}</b> <span className="small muted">{TIPO_ROTULO[i.kind] || i.kind}</span>
                {i.notes && <div className="small muted truncate">{i.notes}</div>}
              </div>
              {i.de_clientes > 0 && <Chip tone="info" title="peça de cliente guardada com a gente">
                {i.de_clientes} de cliente</Chip>}
              {!i.contado && i.tracking === 'quantidade'
                ? <Chip tone="neutral" title="nenhum movimento registrado: ninguém contou ainda">não contada</Chip>
                : <Chip tone={i.abaixo ? 'warn' : i.nosso > 0 ? 'ok' : 'neutral'}>
                  {i.nosso} {i.unit}{i.min_qty ? ` · mín ${i.min_qty}` : ''}</Chip>}
            </div>)}
          </div>}
      </Section>
    </>}

    {abrir && d && <Adicionar locais={d.locais} onClose={() => setAbrir(false)} reload={lista.reload} />}
    {contar && d && <Contar d={d} onClose={() => setContar(false)} reload={lista.reload} />}
    {ficha !== null && d && <FichaPeca id={ficha} locais={d.locais} onClose={() => setFicha(null)} reload={lista.reload} />}
  </>
}
