/* Como usar (#223): os guias da plataforma dentro do painel, e o MD para a IA de cada um.
 *
 * Dono, 13/10: "uma seção chamada como usar … o guia de como usar a plataforma, cada função,
 * tudo totalmente descrito … MD para IA também, uma parte onde a pessoa consegue baixar o MD
 * para colocar no chat da IA dela, que já tem o nosso MCP ou a nossa API".
 * Os guias são os arquivos de docs/ (uma fonte só); o servidor entrega o HTML pronto. */
import { useEffect, useRef, type MouseEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useGet } from '../api/hooks'
import { Empty, ErrorState, Loading, PageHeader, Section } from '../components/ui'
import { tr } from '../i18n'

interface Guia { slug: string; titulo: string; para_quem: string; resumo: string; pdf: boolean; linhas?: number }
interface Lido extends Guia { html: string }

const BASE = '/ops/api/guia'

function Baixar({ g }: { g: Guia }) {
  return <div className="row wrap" style={{ gap: 8 }}>
    <a className="btn sm" href={`${BASE}/${g.slug}.md`} download>{tr("Baixar .md")}</a>
    {g.pdf && <a className="btn sm" href={`${BASE}/${g.slug}.pdf`} download>{tr("Baixar PDF")}</a>}
  </div>
}

function ParaIA() {
  return <Section title={tr("MD para a sua IA")}>
    <div className="stack" style={{ gap: 10 }}>
      <p style={{ margin: 0 }}>{tr("Um arquivo só, com as regras e todos os guias, para a sua IA operar o painel pelo MCP ou pela API com o seu usuário.")}</p>
      <ol className="guia-passos">
        <li>{tr("Conecte a IA ao painel: Equipe › Conectar o Claude (ou o guia \"Conectar a sua IA\" abaixo).")}</li>
        <li>{tr("Baixe o arquivo e cole nas instruções de um Projeto do Claude, ou salve como CLAUDE.md na pasta do Claude Code.")}</li>
        <li>{tr("Peça em português o que precisa. A IA pergunta ao painel o que o seu acesso pode fazer e mostra antes o que vai para o cliente ou cobra.")}</li>
      </ol>
      <p className="small muted" style={{ margin: 0 }}>{tr("O arquivo não leva chave, token nem senha. Baixe de novo quando o painel mudar: ele sai sempre dos guias atuais.")}</p>
      <div><a className="btn primary" href={`${BASE}/para-ia.md`} download>{tr("Baixar o MD para a IA")}</a></div>
    </div>
  </Section>
}

function Lista() {
  const d = useGet<{ guias: Guia[] }>('/guia')
  if (d.error && !d.data) return <ErrorState error={d.error} retry={d.reload} />
  if (!d.data) return <Loading />
  return <>
    <Section title={tr("Guias")} count={d.data.guias.length}>
      {!d.data.guias.length ? <Empty title={tr("Nenhum guia no servidor")} /> : <div className="guia-cards">
        {d.data.guias.map(g => <div key={g.slug} className="card card-b stack" style={{ gap: 8 }}>
          <h3 className="h3" style={{ margin: 0 }}><Link to={`/como-usar/${g.slug}`}>{g.titulo}</Link></h3>
          <div className="small muted">{tr("Para: {0}", g.para_quem)}</div>
          <p className="small" style={{ margin: 0 }}>{g.resumo}</p>
          <div className="row wrap" style={{ gap: 8 }}>
            <Link className="btn sm primary" to={`/como-usar/${g.slug}`}>{tr("Ler")}</Link>
            <Baixar g={g} />
          </div>
        </div>)}
      </div>}
    </Section>
    <ParaIA />
  </>
}

function Leitura({ slug }: { slug: string }) {
  const d = useGet<Lido>(`/guia/${slug}`)
  const nav = useNavigate()
  const art = useRef<HTMLElement>(null)
  useEffect(() => {                                   // âncora do sumário ao abrir com #
    if (!d.data || !location.hash) return
    document.getElementById(decodeURIComponent(location.hash.slice(1)))?.scrollIntoView()
  }, [d.data])
  // link para outro guia (/ops/como-usar/…) navega sem recarregar a página
  function clicar(e: MouseEvent) {
    const a = (e.target as HTMLElement).closest('a')
    const href = a?.getAttribute('href') || ''
    if (href.startsWith('/ops/como-usar/')) { e.preventDefault(); nav(href.slice(4)); window.scrollTo({ top: 0 }) }
  }
  if (d.error && !d.data) return <ErrorState error={d.error} retry={d.reload} />
  if (!d.data) return <Loading />
  return <>
    <div className="row wrap" style={{ gap: 8 }}>
      <Link className="btn sm ghost" to="/como-usar">{tr("‹ Todos os guias")}</Link>
      <span className="grow" />
      <Baixar g={d.data} />
    </div>
    {/* o HTML vem dos guias de docs/ (do próprio repositório), convertido no servidor */}
    <article ref={art} className="guia card card-b" onClick={clicar} dangerouslySetInnerHTML={{ __html: d.data.html }} />
  </>
}

export function ComoUsar() {
  const { guia } = useParams()
  return <>
    <PageHeader title={tr("Como usar")} help={tr("Os guias do painel, para ler aqui ou baixar, e o arquivo para a sua IA operar o painel com o seu usuário.")} />
    {guia ? <Leitura key={guia} slug={guia} /> : <Lista />}
  </>
}
