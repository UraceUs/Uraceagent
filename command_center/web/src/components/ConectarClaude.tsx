/* Conectar o Claude ao Command Center (#73, #77). Dono, 02/10: os vendedores usam o Claude nas
 * máquinas deles, e o conector tem de estar à vista de quem trabalha aqui. O endereço vem do
 * servidor (o mesmo do login), e cada pessoa entra com o próprio usuário: o Claude dela opera
 * com o papel dela, e a auditoria fica com o nome dela. */
import { useState } from 'react'
import { useGet } from '../api/hooks'
import { Section } from './ui'
import { useToast } from './Toast'

interface Conector { url: string; papel: string; pode_operar: boolean; terminal: string }

function Copiar({ texto, rotulo }: { texto: string; rotulo: string }) {
  const toast = useToast()
  return <div className="row" style={{ gap: 8, alignItems: 'center', minWidth: 0 }}>
    <code className="mono small" style={{ flex: 1, minWidth: 0, overflowWrap: 'anywhere', padding: '8px 10px', borderRadius: 8, background: 'var(--glass-2)' }}>{texto}</code>
    <button type="button" className="btn sm" onClick={async () => {
      try { await navigator.clipboard.writeText(texto); toast(`${rotulo} copiado.`, 'ok') }
      catch { toast('Não deu para copiar: selecione e copie à mão.', 'warn') }
    }}>Copiar</button>
  </div>
}

export function ConectarClaude() {
  const d = useGet<Conector>('/equipe/conector-claude')
  const [aberto, setAberto] = useState(false)
  if (!d.data) return null
  const c = d.data
  return <Section title="Conectar o Claude" right={<button type="button" className="btn sm ghost" aria-expanded={aberto}
    onClick={() => setAberto(a => !a)}>{aberto ? 'Fechar' : 'Como conectar'}</button>}>
    <p className="small" style={{ margin: 0 }}>
      O seu Claude pode {c.pode_operar ? <b>consultar e operar</b> : <b>consultar</b>} o Command Center como <b>você</b> ({c.papel}): agendar,
      criar cliente, fechar venda, mandar invoice e waiver — só o que o seu papel já faz aqui. O que vai para o cliente ou cobra pede a sua
      confirmação antes, e tudo fica na auditoria com o seu nome.</p>
    {aberto && <div className="stack" style={{ gap: 14, marginTop: 12 }}>
      <div className="stack" style={{ gap: 6 }}>
        <h3 className="h3">No app do Claude (celular, computador ou claude.ai)</h3>
        <ol className="small" style={{ margin: 0, paddingLeft: 18 }}>
          <li>Configurações › <b>Conectores</b> › <b>Adicionar conector personalizado</b>.</li>
          <li>Nome: <b>URACE Command Center</b>. URL: cole <b>só</b> este endereço:</li>
        </ol>
        <Copiar texto={c.url} rotulo="Endereço" />
        <ol className="small" start={3} style={{ margin: 0, paddingLeft: 18 }}>
          <li><b>Conectar</b> e entre com o <b>seu</b> usuário do Command Center.</li>
          <li>{c.pode_operar ? <>Deixe marcado <b>"Também operar o painel como você"</b> e clique em <b>Autorizar</b>.</>
            : <>Clique em <b>Autorizar</b>. Pelo seu papel, o acesso é só de leitura.</>}</li>
        </ol>
      </div>
      <div className="stack" style={{ gap: 6 }}>
        <h3 className="h3">No terminal (Claude Code)</h3>
        <Copiar texto={c.terminal} rotulo="Comando" />
        <p className="small muted" style={{ margin: 0 }}>Depois, dentro do Claude Code: <code>/mcp</code> › <b>urace</b> › <b>Authenticate</b>, e os mesmos passos 3 e 4.</p>
      </div>
      <p className="small muted" style={{ margin: 0 }}>Nunca cole senha ou chave no chat: o login é pelo navegador. Para desligar, remova o conector no Claude.</p>
    </div>}
  </Section>
}
