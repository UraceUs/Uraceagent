/* Cofre de logins e senhas (#162).
 *
 * Dono, 08/10: "somente no acesso livre crie uma sessão de logins e senhas de onde fiquem seguras e
 * consigam ser armazenadas por lá". Só a conta de acesso livre entra; a senha fica cifrada no
 * servidor e só aparece depois de confirmar a senha de login (vale 10 minutos). A senha mostrada
 * some sozinha depois de 30 s e nunca é guardada no navegador.
 */
import { useEffect, useId, useState } from 'react'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, PageHeader, Scrim, Section } from '../components/ui'
import { useToast } from '../components/Toast'
import { tr, LOCALE } from '../i18n'

interface Item { id: number; name: string; url: string | null; username: string | null; tem_senha: number; tem_nota: number
  archived: number; updated_at: string; revealed_at: string | null; outra_chave: boolean }
interface Lista { ligado: boolean; motivo: string | null; impressao: string | null; desbloqueado_ate: string | null; itens: Item[] }
interface Aberto { senha: string | null; nota: string | null }

const hora = (iso: string) => new Date(iso).toLocaleTimeString(LOCALE(), { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit' })
const dia = (iso: string) => new Date(iso).toLocaleDateString(LOCALE(), { timeZone: 'America/New_York', day: '2-digit', month: '2-digit', year: '2-digit' })

function gerarSenha(n = 20) {
  const abc = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%&*-_+='
  const v = new Uint32Array(n)
  crypto.getRandomValues(v)
  return Array.from(v, x => abc[x % abc.length]).join('')
}

async function copiar(texto: string, toast: ReturnType<typeof useToast>, oque: string) {
  try { await navigator.clipboard.writeText(texto); toast(tr("{0} copiado.", oque), 'ok') } catch { toast(tr("Não deu para copiar neste navegador."), 'warn') }
}

export function Cofre() {
  const { livre } = useAuth()
  const toast = useToast()
  const [arquivados, setArquivados] = useState(false)
  const l = useGet<Lista>(livre ? `/cofre${arquivados ? '?arquivados=true' : ''}` : null)
  const [senha, setSenha] = useState('')
  const [indo, setIndo] = useState(false)
  const [busca, setBusca] = useState('')
  const [editar, setEditar] = useState<Item | 'novo' | null>(null)
  const [abertos, setAbertos] = useState<Record<number, Aberto>>({})

  // a senha mostrada some sozinha: 30 s na tela, no máximo
  useEffect(() => {
    if (!Object.keys(abertos).length) return
    const t = window.setTimeout(() => setAbertos({}), 30000)
    return () => window.clearTimeout(t)
  }, [abertos])

  if (!livre) return <><PageHeader title={tr("Cofre")} />
    <div className="card"><Empty title={tr("Esta área não é do seu acesso")}>{tr("O cofre é só da conta de acesso livre.")}</Empty></div></>

  const d = l.data
  const aberto = !!d?.desbloqueado_ate
  async function desbloquear(e: React.FormEvent) {
    e.preventDefault()
    setIndo(true)
    try { await api.post('/cofre/desbloquear', { senha }); setSenha(''); l.reload() }
    catch (err) { toast((err as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  async function travar() { await api.post('/cofre/travar', {}); setAbertos({}); l.reload() }
  async function ver(it: Item) {
    if (abertos[it.id]) { setAbertos(a => { const b = { ...a }; delete b[it.id]; return b }); return }
    try { const r = await api.post<Aberto>(`/cofre/${it.id}/revelar`, {}); setAbertos(a => ({ ...a, [it.id]: r })) }
    catch (err) { toast((err as ApiError).message, 'crit'); if ((err as ApiError).status === 423) l.reload() }
  }
  async function arquivar(it: Item) {
    try { await api.post(`/cofre/${it.id}/${it.archived ? 'restaurar' : 'arquivar'}`, {}); toast(it.archived ? tr("Restaurado.") : tr("Arquivado. Fica em “Arquivados”."), 'ok'); l.reload() }
    catch (err) { toast((err as ApiError).message, 'crit') }
  }
  const itens = (d?.itens || []).filter(i => !busca.trim() || `${i.name} ${i.username || ''} ${i.url || ''}`.toLowerCase().includes(busca.trim().toLowerCase()))

  return <>
    <PageHeader title={tr("Cofre")} help={tr("Logins e senhas da URACE. Só a conta de acesso livre entra; a senha fica cifrada no servidor e só aparece depois de confirmar a sua senha de login. A IA não tem acesso.")} />
    {l.error ? <ErrorState error={l.error} retry={l.reload} /> : !d ? <Loading /> : <>
      {!d.ligado && <Banner tone="warn">{d.motivo} {tr("Rode o bloco de deploy do cofre no VPS.")}</Banner>}
      {d.ligado && (aberto
        ? <div className="cofre-estado card"><Chip tone="ok" dot>{tr("Aberto até")} {hora(d.desbloqueado_ate!)}</Chip><span className="small muted">{tr("chave")} {d.impressao}</span>
            <button className="btn sm" onClick={travar}>{tr("Trancar agora")}</button></div>
        : <form className="cofre-estado card" onSubmit={desbloquear}>
            <label className="fld grow"><span>{tr("Confirme a sua senha de login para abrir")}</span>
              <input type="password" autoComplete="current-password" value={senha} onChange={e => setSenha(e.target.value)} required /></label>
            <button className="btn primary" disabled={indo || !senha}>{tr("Abrir o cofre")}</button>
          </form>)}
      <Section title={arquivados ? tr("Arquivados") : tr("Logins")} count={d.itens.length}
        right={<div className="row wrap gap">
          <button className="btn sm ghost" onClick={() => { setArquivados(a => !a); setAbertos({}) }}>{arquivados ? tr("Ver os ativos") : tr("Arquivados")}</button>
          {d.ligado && aberto && !arquivados && <button className="btn sm primary" onClick={() => setEditar('novo')}>{tr("Novo login")}</button>}
        </div>}>
        {d.itens.length > 4 && <label className="fld"><span>{tr("Buscar")}</span><input type="search" value={busca} onChange={e => setBusca(e.target.value)} placeholder={tr("serviço, usuário ou endereço")} /></label>}
        {!itens.length ? <Empty title={arquivados ? tr("Nada arquivado") : tr("Nenhum login guardado")}>{arquivados ? '' : aberto ? tr("Use “Novo login”.") : tr("Abra o cofre para guardar o primeiro.")}</Empty> :
          <ul className="cofre-lista">
            {itens.map(it => {
              const a = abertos[it.id]
              return <li key={it.id} className="cofre-item">
                <div className="cofre-topo">
                  <h3>{it.name}</h3>
                  {it.outra_chave && <Chip tone="warn" title={tr("Guardado com outra chave do cofre")}>{tr("outra chave")}</Chip>}
                </div>
                {it.url && <a className="small truncate" href={it.url} target="_blank" rel="noopener noreferrer">{it.url}</a>}
                {it.username && <div className="cofre-linha"><span className="small muted">{tr("Usuário")}</span><b className="truncate">{it.username}</b>
                  <button className="btn sm ghost" onClick={() => copiar(it.username!, toast, 'Usuário')}>{tr("Copiar")}</button></div>}
                {a && <div className="cofre-linha cofre-segredo"><span className="small muted">{tr("Senha")}</span><code className="truncate">{a.senha || tr("(sem senha)")}</code>
                  {a.senha && <button className="btn sm ghost" onClick={() => copiar(a.senha!, toast, 'Senha')}>{tr("Copiar")}</button>}</div>}
                {a?.nota && <p className="small cofre-nota">{a.nota}</p>}
                <div className="cofre-acoes">
                  {aberto && (it.tem_senha || it.tem_nota) ? <button className="btn sm" onClick={() => ver(it)}>{a ? tr("Esconder") : tr("Ver senha")}</button> : null}
                  {aberto && !it.archived && <button className="btn sm ghost" onClick={() => setEditar(it)}>{tr("Editar")}</button>}
                  <button className="btn sm ghost" onClick={() => arquivar(it)}>{it.archived ? tr("Restaurar") : tr("Arquivar")}</button>
                  <span className="small muted">{tr("mudou em")} {dia(it.updated_at)}</span>
                </div>
              </li>
            })}
          </ul>}
      </Section>
    </>}
    {editar && <Editar item={editar === 'novo' ? null : editar} onClose={() => setEditar(null)} onDone={() => { setAbertos({}); l.reload() }} />}
  </>
}

function Editar({ item, onClose, onDone }: { item: Item | null; onClose: () => void; onDone: () => void }) {
  const toast = useToast()
  const [f, setF] = useState({ name: item?.name || '', url: item?.url || '', username: item?.username || '', senha: '', nota: '' })
  const [trocar, setTrocar] = useState(!item)
  const [mostrar, setMostrar] = useState(false)
  const [indo, setIndo] = useState(false)
  const idSenha = useId()
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF(x => ({ ...x, [k]: e.target.value }))
  async function salvar(e: React.FormEvent) {
    e.preventDefault()
    setIndo(true)
    const corpo: Record<string, string> = { name: f.name, url: f.url, username: f.username }
    if (trocar) { corpo.senha = f.senha; corpo.nota = f.nota }
    try {
      if (item) await api.patch(`/cofre/${item.id}`, corpo); else await api.post('/cofre', corpo)
      toast(item ? tr("Login atualizado.") : tr("Login guardado."), 'ok'); onDone(); onClose()
    } catch (err) { toast((err as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  const titulo = item ? `Editar ${item.name}` : 'Novo login'
  return <Scrim onMouseDown={onClose}><form className="modal" style={{ maxWidth: 520 }} onMouseDown={e => e.stopPropagation()} onSubmit={salvar}
    role="dialog" aria-modal="true" aria-label={titulo}>
    <button type="button" className="btn ghost sm close" onClick={onClose} aria-label={tr("Fechar")}>✕</button>
    <h3>{titulo}</h3>
    <label className="fld"><span>{tr("Serviço")}</span><input value={f.name} onChange={set('name')} placeholder={tr("ex.: WordPress urace.us")} required /></label>
    <label className="fld"><span>{tr("Endereço")}</span><input type="url" value={f.url} onChange={set('url')} placeholder={tr("https://")} /></label>
    <label className="fld"><span>{tr("Usuário ou e-mail")}</span><input value={f.username} onChange={set('username')} autoComplete="off" /></label>
    {item && <label className="check"><input type="checkbox" checked={trocar} onChange={e => setTrocar(e.target.checked)} /> {tr("Trocar a senha e a observação")}</label>}
    {trocar && <>
      <div className="fld"><label htmlFor={idSenha}>{tr("Senha")}</label>
        <span className="row gap"><input id={idSenha} className="inp grow" type={mostrar ? 'text' : 'password'} value={f.senha} onChange={set('senha')} autoComplete="new-password" />
          <button type="button" className="btn sm ghost" onClick={() => setMostrar(m => !m)}>{mostrar ? tr("Ocultar") : tr("Mostrar")}</button>
          <button type="button" className="btn sm ghost" onClick={() => { setF(x => ({ ...x, senha: gerarSenha() })); setMostrar(true) }}>{tr("Gerar")}</button></span></div>
      <label className="fld"><span>{tr("Observação (fica cifrada)")}</span><textarea value={f.nota} onChange={set('nota')} placeholder={tr("pergunta de segurança, PIN do 2FA de reserva…")} /></label>
    </>}
    <div className="row" style={{ justifyContent: 'flex-end' }}><button type="button" className="btn" onClick={onClose}>{tr("Cancelar")}</button>
      <button className="btn primary" disabled={indo}>{item ? tr("Salvar") : tr("Guardar")}</button></div>
  </form></Scrim>
}
