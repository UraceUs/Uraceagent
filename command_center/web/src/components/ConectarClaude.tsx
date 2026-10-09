/* Conectar o Claude ao Command Center (#73, #77). Dono, 02/10: os vendedores usam o Claude nas
 * máquinas deles, e o conector tem de estar à vista de quem trabalha aqui. O endereço vem do
 * servidor (o mesmo do login), e cada pessoa entra com o próprio usuário: o Claude dela opera
 * com o papel dela, e a auditoria fica com o nome dela. */
import { useState } from 'react'
import { useGet } from '../api/hooks'
import { Section } from './ui'
import { useToast } from './Toast'
import { tr } from '../i18n'

interface Conector { url: string; papel: string; pode_operar: boolean; terminal: string }

function Copiar({ texto, rotulo }: { texto: string; rotulo: string }) {
  const toast = useToast()
  return <div className="row" style={{ gap: 8, alignItems: 'center', minWidth: 0 }}>
    <code className="mono small" style={{ flex: 1, minWidth: 0, overflowWrap: 'anywhere', padding: '8px 10px', borderRadius: 8, background: 'var(--glass-2)' }}>{texto}</code>
    <button type="button" className="btn sm" onClick={async () => {
      try { await navigator.clipboard.writeText(texto); toast(tr("{0} copiado.", rotulo), 'ok') }
      catch { toast(tr("Não deu para copiar: selecione e copie à mão."), 'warn') }
    }}>{tr("Copiar")}</button>
  </div>
}

export function ConectarClaude() {
  const d = useGet<Conector>('/equipe/conector-claude')
  const [aberto, setAberto] = useState(false)
  if (!d.data) return null
  const c = d.data
  return <Section title={tr("Conectar o Claude")} right={<button type="button" className="btn sm ghost" aria-expanded={aberto}
    onClick={() => setAberto(a => !a)}>{aberto ? tr("Fechar") : tr("Como conectar")}</button>}>
    <p className="small" style={{ margin: 0 }}>
      {tr("O seu Claude pode")} {c.pode_operar ? <b>{tr("consultar e operar")}</b> : <b>{tr("consultar")}</b>} {tr("o Command Center como")} <b>{tr("você")}</b> ({c.papel}{tr("): agendar, criar cliente, fechar venda, mandar invoice e waiver — só o que o seu papel já faz aqui. O que vai para o cliente ou cobra pede a sua confirmação antes, e tudo fica na auditoria com o seu nome.")}</p>
    {aberto && <div className="stack" style={{ gap: 14, marginTop: 12 }}>
      <div className="stack" style={{ gap: 6 }}>
        <h3 className="h3">{tr("No app do Claude (celular, computador ou claude.ai)")}</h3>
        <ol className="small" style={{ margin: 0, paddingLeft: 18 }}>
          <li>{tr("Configurações ›")} <b>{tr("Conectores")}</b> › <b>{tr("Adicionar conector personalizado")}</b>.</li>
          <li>{tr("Nome:")} <b>{tr("URACE Command Center")}</b>{tr(". URL: cole")} <b>{tr("só")}</b> {tr("este endereço:")}</li>
        </ol>
        <Copiar texto={c.url} rotulo={tr("Endereço")} />
        <ol className="small" start={3} style={{ margin: 0, paddingLeft: 18 }}>
          <li><b>{tr("Conectar")}</b> {tr("e entre com o")} <b>{tr("seu")}</b> {tr("usuário do Command Center.")}</li>
          <li>{c.pode_operar ? <>{tr("Deixe marcado")} <b>{tr("\"Também operar o painel como você\"")}</b> {tr("e clique em")} <b>{tr("Autorizar")}</b>.</>
            : <>{tr("Clique em")} <b>{tr("Autorizar")}</b>{tr(". Pelo seu papel, o acesso é só de leitura.")}</>}</li>
        </ol>
      </div>
      <div className="stack" style={{ gap: 6 }}>
        <h3 className="h3">{tr("No terminal (Claude Code)")}</h3>
        <Copiar texto={c.terminal} rotulo={tr("Comando")} />
        <p className="small muted" style={{ margin: 0 }}>{tr("Depois, dentro do Claude Code:")} <code>{tr("/mcp")}</code> › <b>{tr("urace")}</b> › <b>{tr("Authenticate")}</b>{tr(", e os mesmos passos 3 e 4.")}</p>
      </div>
      <p className="small muted" style={{ margin: 0 }}>{tr("Nunca cole senha ou chave no chat: o login é pelo navegador. Para desligar, remova o conector no Claude.")}</p>
    </div>}
  </Section>
}
