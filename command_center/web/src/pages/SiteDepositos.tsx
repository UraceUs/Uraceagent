/* #317 · Site › Security deposit (dono, 16/10): "uma sessão de security deposit, onde a gente consiga ter o controle
 * para fazer o reembolso de cada security deposit e alterar o valor do security deposit para ser cobrado no site …
 * só clicar no botão e fazer o refund do Security Deposit pelo Command Center. Sempre conseguindo alterar o valor
 * que vai ser reembolsado."
 *
 * Em cima, o valor que o site cobra (por serviço, com a caixa "obrigatório", e por produto). Embaixo, cada depósito
 * cobrado, no cartão do padrão D do painel (centrado, com a lista do que já aconteceu): devolver pelo Stripe com o
 * valor escolhido e conferir no Stripe. */
import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { Banner, Empty, ErrorState, Loading, Section } from '../components/ui'
import { usePerguntar } from '../components/Perguntar'
import { Cartao, type TomD } from '../components/Cartao'
import { useToast } from '../components/Toast'
import { fmtDate, fmtDateTime } from '../components/fmt'
import { tr } from '../i18n'

const POR_PAGINA = 20
const usd = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
const numero = (t: string) => Number(t.replace(/[$,\s]/g, ''))

type Devolucao = { id: number; valor: number; estado: 'pendente' | 'feito' | 'falhou'; stripe: string | null; stripe_estado: string | null
  nota: string | null; erro: string | null; por: string | null; em: string }
type Deposito = { order_id: number; item_id: number | null; deposito: number; descricao: string; tipo: string; data: string | null
  turno: string | null; piloto: string | null; client_id: number | null; nome: string | null; email: string | null; pago_em: string | null
  stripe_devolvido: number | null; devolvido: number; reservado: number; retido: number; pode_devolver: boolean; devolucoes: Devolucao[] }
type Lista = { depositos: Deposito[]; total: number; soma_retido: number; soma_devolvido: number; stripe: boolean; modo_teste: boolean }
type ServicoDep = { id: number; name: string; deposit: number; deposit_required: boolean; active: boolean }
type ProdutoDep = { id: number; name: string; slug: string; deposit: number; active: boolean }
type Valores = { servicos: ServicoDep[]; produtos: ProdutoDep[] }

const TURNO: Record<string, string> = { manha: tr("manhã"), tarde: tr("tarde"), dia: tr("dia inteiro") }

export function SiteDepositos() {
  const { can } = useAuth()
  const gerente = can('MANAGER')
  const [estado, setEstado] = useState<'retidos' | 'devolvidos' | 'todos'>('retidos')
  const [texto, setTexto] = useState('')
  const [busca, setBusca] = useState('')
  const [offset, setOffset] = useState(0)
  const l = useGet<Lista>(`/site/depositos?estado=${estado}&limit=${POR_PAGINA}&offset=${offset}${busca ? `&q=${encodeURIComponent(busca)}` : ''}`, 60000)
  // devolveu o último cartão da última página: volta uma página (senão fica "nenhum depósito" sem saída)
  const vazia = !!l.data && !l.data.depositos.length && offset > 0
  useEffect(() => { if (vazia) setOffset(o => Math.max(0, o - POR_PAGINA)) }, [vazia])
  return <div className="stack" style={{ gap: 18 }}>
    {l.data?.modo_teste && <Banner tone="info">{tr("O Stripe está em modo teste: as devoluções daqui não devolvem dinheiro de verdade.")}</Banner>}
    {l.data && !l.data.stripe && <Banner tone="warn">{tr("O Stripe não está ligado neste servidor: dá para ver os depósitos, mas não para devolver por aqui.")}</Banner>}
    <ValoresCobrados gerente={gerente} />
    <Section title={tr("Depósitos cobrados")} count={l.data?.total}>
      <div className="stack" style={{ gap: 12 }}>
        <div className="seg" role="group" aria-label={tr("Quais depósitos")}>
          {([['retidos', tr("Retidos")], ['devolvidos', tr("Devolvidos")], ['todos', tr("Todos")]] as const).map(([k, r]) =>
            <button key={k} type="button" className={`btn sm${estado === k ? '' : ' ghost'}`} aria-pressed={estado === k}
              onClick={() => { setEstado(k); setOffset(0) }}>{r}</button>)}
        </div>
        <form className="row wrap" style={{ gap: 8 }} role="search" onSubmit={e => { e.preventDefault(); setBusca(texto.trim()); setOffset(0) }}>
          <label className="fld grow" style={{ margin: 0 }}><span>{tr("Buscar por nome, e-mail, piloto ou nº do pedido")}</span>
            <input type="search" value={texto} onChange={e => setTexto(e.target.value)} enterKeyHint="search" /></label>
          <button className="btn" style={{ alignSelf: 'flex-end' }}>{tr("Buscar")}</button>
        </form>
        {l.data && <p className="small muted" style={{ margin: 0 }}>{tr("Neste filtro: {0} retido · {1} já devolvido.", usd(l.data.soma_retido), usd(l.data.soma_devolvido))}</p>}
        {l.error && <ErrorState error={l.error} retry={l.reload} />}
        {l.loading && !l.data && <Loading />}
        {l.data && (!l.data.depositos.length
          ? <Empty title={estado === 'retidos' ? tr("Nenhum depósito retido") : tr("Nenhum depósito aqui")}>{tr("Cada depósito de segurança pago no site (carrinho ou Buy now) aparece aqui, com o que já foi devolvido.")}</Empty>
          : <div className="cd-grade">{l.data.depositos.map(d => <CartaoDeposito key={`${d.order_id}-${d.item_id ?? 'p'}`} d={d} gerente={gerente} stripe={l.data!.stripe} recarregar={l.reload} />)}</div>)}
        {l.data && l.data.total > POR_PAGINA && <div className="row" style={{ gap: 8 }}>
          <button className="btn sm ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - POR_PAGINA))}>{tr("Anteriores")}</button>
          <span className="small muted grow" style={{ textAlign: 'center' }}>{offset + 1}–{Math.min(offset + POR_PAGINA, l.data.total)} {tr("de")} {l.data.total}</span>
          <button className="btn sm ghost" disabled={offset + POR_PAGINA >= l.data.total} onClick={() => setOffset(offset + POR_PAGINA)}>{tr("Próximas")}</button></div>}
      </div>
    </Section>
  </div>
}

function CartaoDeposito({ d, gerente, stripe, recarregar }: { d: Deposito; gerente: boolean; stripe: boolean; recarregar: () => void }) {
  const toast = useToast()
  const perguntar = usePerguntar()
  const [valor, setValor] = useState(d.retido > 0 ? d.retido.toFixed(2) : '')
  const [nota, setNota] = useState('')
  const [indo, setIndo] = useState<'' | 'devolver' | 'conferir'>('')
  const nome = d.nome || d.email || tr("Pedido #{0}", d.order_id)
  const situacao: { t: string; c: TomD } = d.reservado > 0 ? { t: tr("Devolução pendente"), c: 'warn' } : d.retido <= 0 ? { t: tr("Devolvido"), c: 'ok' }
    : d.devolvido > 0 ? { t: tr("Devolvido em parte"), c: 'info' } : { t: tr("Retido"), c: 'warn' }
  const quando = d.data ? `${fmtDate(d.data)}${d.turno ? ` · ${TURNO[d.turno] || d.turno}` : ''}` : null

  async function devolver(e: FormEvent) {
    e.preventDefault()
    const v = numero(valor)
    if (!(v > 0)) { toast(tr("Ponha o valor a devolver, como 400 ou 150.50."), 'warn'); return }
    if (Math.round(v * 100) > Math.round(d.retido * 100)) { toast(tr("O máximo que ainda dá para devolver é {0}.", usd(d.retido)), 'warn'); return }
    if (!await perguntar({ titulo: tr("Devolver {0} a {1}?", usd(v), nome), texto: tr("O Stripe devolve no cartão que pagou o pedido #{0}. Não dá para desfazer.", d.order_id), ok: tr("Devolver") })) return
    setIndo('devolver')
    try {
      await api.post(`/site/depositos/${d.order_id}/reembolsar`, { item_id: d.item_id, valor: v, nota: nota.trim() || null })
      toast(tr("Devolvido {0} pelo Stripe.", usd(v)), 'ok'); setNota(''); recarregar()
    } catch (x) { toast((x as ApiError).message, 'crit'); recarregar() } finally { setIndo('') }
  }

  async function conferir() {
    setIndo('conferir')
    try {
      const r = await api.post<{ acertos: number; stripe_devolvido: number }>(`/site/depositos/${d.order_id}/conferir`)
      toast(r.acertos ? tr("Conferido: {0} devolução(ões) acertada(s).", r.acertos) : tr("Conferido: tudo igual ao Stripe."), 'ok'); recarregar()
    } catch (x) { toast((x as ApiError).message, 'crit') } finally { setIndo('') }
  }

  return <Cartao id={`dep-${d.order_id}-${d.item_id ?? 'p'}`} estado={situacao.t} tom={situacao.c} avatar={d.nome || d.email || '#'} nome={nome}
    sub={[d.descricao, d.piloto ? <>{tr("Piloto")}: <b>{d.piloto}</b></> : null]}
    grande={usd(Math.max(0, d.retido))} detalhe={`${tr("retido de {0} · pedido #{1}", usd(d.deposito), d.order_id)}${quando ? ` · ${quando}` : ''}`}>
    <ul className="cd-lista">
      <li><i className="cd-ic ok" aria-hidden="true">✓</i><span className="grow">{tr("Cobrado no Stripe")}</span><span className="muted">{d.pago_em ? fmtDateTime(d.pago_em) : '—'}</span></li>
      {d.devolucoes.map(x => <li key={x.id}>
        <i className={`cd-ic ${x.estado === 'feito' ? 'ok' : x.estado === 'pendente' ? 'warn' : 'crit'}`} aria-hidden="true">{x.estado === 'feito' ? '✓' : x.estado === 'pendente' ? '…' : '!'}</i>
        <span className="grow">{x.estado === 'feito' ? tr("Devolvido {0}", usd(x.valor)) : x.estado === 'pendente' ? tr("Devolvendo {0}: confira no Stripe", usd(x.valor)) : tr("Não devolveu {0}", usd(x.valor))}
          {x.nota ? <span className="muted"> · {x.nota}</span> : null}
          {x.estado === 'falhou' && x.erro ? <span className="cd-erro"> · {x.erro}</span> : null}</span>
        <span className="muted">{x.por ? `${x.por} · ` : ''}{fmtDateTime(x.em)}</span></li>)}
      {d.stripe_devolvido != null && d.stripe_devolvido > 0 && <li><i className="cd-ic info" aria-hidden="true">i</i>
        <span className="grow">{tr("No Stripe, este pagamento já teve {0} devolvido no total (inclui o que foi devolvido direto no Stripe).", usd(d.stripe_devolvido))}</span></li>}
    </ul>
    {gerente && stripe && <form className="cd-form" onSubmit={devolver}>
      {d.pode_devolver && <div className="cd-campos">
        <label className="fld"><span>{tr("Valor a devolver (US$)")}</span>
          <input inputMode="decimal" value={valor} onChange={e => setValor(e.target.value)} disabled={!!indo} aria-describedby={`max-${d.order_id}-${d.item_id ?? 'p'}`} /></label>
        <label className="fld"><span>{tr("Motivo (opcional)")}</span>
          <input value={nota} maxLength={300} onChange={e => setNota(e.target.value)} disabled={!!indo} /></label>
        <span id={`max-${d.order_id}-${d.item_id ?? 'p'}`} className="small muted">{tr("Até {0}. Parcial vale: o resto segue retido.", usd(d.retido))}</span>
      </div>}
      <div className={`cd-acoes${d.pode_devolver ? '' : ' um'}`}>
        <button type="button" className="btn" onClick={conferir} disabled={!!indo}>{indo === 'conferir' ? tr("Conferindo…") : tr("Conferir no Stripe")}</button>
        {d.pode_devolver && <button className="btn primary" disabled={!!indo}>{indo === 'devolver' ? tr("Devolvendo…") : tr("Devolver pelo Stripe")}</button>}
      </div>
    </form>}
  </Cartao>
}

function ValoresCobrados({ gerente }: { gerente: boolean }) {
  const toast = useToast()
  const v = useGet<Valores>('/site/depositos/valores')
  const [ed, setEd] = useState<Record<string, string>>({})
  const [indo, setIndo] = useState('')

  async function salvar(tipo: 'servico' | 'produto', id: number, corpo: { valor?: number; obrigatorio?: boolean }) {
    const k = `${tipo}-${id}`
    setIndo(k)
    try {
      await api.patch<Valores>('/site/depositos/valor', { tipo, id, ...corpo })
      setEd(x => { const y = { ...x }; delete y[k]; return y })
      toast(tr("Salvo. Vale para as próximas compras."), 'ok'); v.reload()
    } catch (x) { toast((x as ApiError).message, 'crit') } finally { setIndo('') }
  }

  function linha(tipo: 'servico' | 'produto', id: number, nome: string, valor: number, ativo: boolean, obrigatorio?: boolean) {
    const k = `${tipo}-${id}`
    const t = ed[k] ?? valor.toFixed(2)
    const mudou = ed[k] !== undefined && numero(ed[k]) !== valor
    return <li key={k} className="dep-valor">
      <span className="dep-valor-nome">{nome}{!ativo && <span className="muted"> · {tr("fora do site")}</span>}</span>
      <label className="dep-valor-campo"><span className="sr-only">{tr("Depósito de {0} (US$)", nome)}</span>
        <span aria-hidden="true">US$</span>
        <input className="inp" inputMode="decimal" value={t} disabled={!gerente || indo === k} onChange={e => setEd(x => ({ ...x, [k]: e.target.value }))} /></label>
      {obrigatorio !== undefined && <label className="check dep-valor-obr">
        <input type="checkbox" checked={obrigatorio} disabled={!gerente || indo === k}
          onChange={e => salvar(tipo, id, { obrigatorio: e.target.checked, ...(mudou ? { valor: numero(t) } : {}) })} />
        {tr("Obrigatório")}</label>}
      {gerente && <button type="button" className="btn sm" disabled={!mudou || indo === k} onClick={() => salvar(tipo, id, { valor: numero(t) })}>{tr("Salvar")}</button>}
    </li>
  }

  return <Section title={tr("Valor cobrado no site")}>
    <p className="small muted" style={{ marginTop: 0 }}>{tr("O depósito de cada sessão e de cada produto nas próximas compras (o pedido já pago fica com o valor do dia). Com \"Obrigatório\" marcado, a sessão nunca sai sem o depósito: nem no checkout, nem na invoice.")}</p>
    {v.error && <ErrorState error={v.error} retry={v.reload} />}
    {v.loading && !v.data && <Loading rows={2} />}
    {v.data && <>
      <h3 className="h3 dep-valor-tit">{tr("Sessões")}</h3>
      {v.data.servicos.length ? <ul className="dep-valores">{v.data.servicos.map(s => linha('servico', s.id, s.name, s.deposit, s.active, s.deposit_required))}</ul>
        : <p className="small muted">{tr("Nenhuma sessão cadastrada em Serviços e preços.")}</p>}
      <h3 className="h3 dep-valor-tit">{tr("Produtos com depósito")}</h3>
      {v.data.produtos.length ? <ul className="dep-valores">{v.data.produtos.map(p => linha('produto', p.id, p.name, p.deposit, p.active))}</ul>
        : <p className="small muted">{tr("Nenhum produto cobra depósito. Para pôr, abra o produto em Produtos da loja.")}</p>}
    </>}
  </Section>
}
