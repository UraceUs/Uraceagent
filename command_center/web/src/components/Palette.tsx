import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, qs } from '../api/client'
import type { SearchResult } from '../api/types'
import { Chip } from './ui'
import { fmtDate } from './fmt'

interface Item { group: string; label: string; hint?: string; go: () => void; tone?: 'ok' | 'warn' | 'crit' | 'neutral' | 'info' }

export function Palette({ open, onClose, ask }: { open: boolean; onClose: () => void; ask: (text: string) => void }) {
  const nav = useNavigate()
  const [q, setQ] = useState('')
  const [res, setRes] = useState<SearchResult | null>(null)
  const [sel, setSel] = useState(0)
  const [busy, setBusy] = useState(false)
  const inp = useRef<HTMLInputElement>(null)

  useEffect(() => { if (open) { setQ(''); setRes(null); setSel(0); setTimeout(() => inp.current?.focus(), 10) } }, [open])
  useEffect(() => {
    if (!open) return
    const s = q.trim()
    if (s.length < 2) { setRes(null); return }
    setBusy(true)
    const t = setTimeout(() => {
      api.get<SearchResult>('/search' + qs({ q: s })).then(setRes).catch(() => setRes(null)).finally(() => setBusy(false))
    }, 180)
    return () => clearTimeout(t)
  }, [q, open])

  const items = useMemo<Item[]>(() => {
    const out: Item[] = []
    const go = (p: string) => () => { onClose(); nav(p) }
    const s = q.trim()
    if (res) {
      res.clients.forEach(c => out.push({ group: 'Clientes', label: c.name + (c.pilot_name ? ` · piloto ${c.pilot_name}` : ''), hint: c.email || '', go: go(`/clients/${c.id}`), tone: c.vip ? 'warn' : undefined }))
      res.tasks.forEach(t => out.push({ group: 'Serviços', label: t.title, hint: `${t.section || ''} ${fmtDate(t.due_on)}`, go: go(t.client_id ? `/clients/${t.client_id}` : '/asana') }))
      res.waivers.forEach(w => out.push({ group: 'Waivers', label: `${w.signer_name || w.signer_email} · ${w.status}`, hint: 'expira ' + fmtDate(w.expires_at), go: go(w.client_id ? `/clients/${w.client_id}` : '/docusign') }))
      res.emails.forEach(e => out.push({ group: 'E-mails', label: e.subject || '(sem assunto)', hint: `${e.mailbox}@ · ${e.sender || ''}`, go: go(e.client_id ? `/clients/${e.client_id}` : '/gmail') }))
      res.commands.forEach(c => out.push({ group: 'Comandos', label: c.text, hint: c.status, go: go(`/ai/${c.id}`) }))
    }
    if (s.length >= 2) out.push({ group: 'IA', label: `Perguntar à IA: "${s}"`, hint: 'Enter', go: () => { onClose(); ask(s) } })
    const pages: [string, string][] = [['Dashboard', '/'], ['Precisa de atenção', '/attention'], ['Clientes', '/clients'], ['AI Command', '/ai'],
      ['Aprovações', '/approvals'], ['Asana', '/asana'], ['DocuSign', '/docusign'], ['Gmail', '/gmail'], ['QuickBooks', '/quickbooks'], ['Integrações', '/integrations'], ['Automação e memória', '/automation'], ['Atividade da IA', '/activity'], ['Políticas', '/policies'], ['Auditoria', '/audit'], ['Usuários', '/users']]
    pages.filter(([n]) => !s || n.toLowerCase().includes(s.toLowerCase())).forEach(([n, p]) => out.push({ group: 'Ir para', label: n, go: go(p) }))
    return out
  }, [res, q, nav, onClose, ask])

  useEffect(() => { setSel(0) }, [items.length])
  useEffect(() => {
    if (!open) return
    const h = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); onClose() }
      else if (e.key === 'ArrowDown') { e.preventDefault(); setSel(s => Math.min(items.length - 1, s + 1)) }
      else if (e.key === 'ArrowUp') { e.preventDefault(); setSel(s => Math.max(0, s - 1)) }
      else if (e.key === 'Enter') { e.preventDefault(); items[sel]?.go() }
    }
    window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h)
  }, [open, items, sel, onClose])

  if (!open) return null
  let lastGroup = ''
  return <div className="pal-scrim" onMouseDown={onClose}>
    <div className="pal" role="dialog" aria-label="Busca" onMouseDown={e => e.stopPropagation()}>
      <input ref={inp} value={q} onChange={e => setQ(e.target.value)} placeholder="Buscar cliente, piloto, e-mail, serviço… ou perguntar à IA" aria-label="Buscar" />
      <div className="res">
        {items.length === 0 && <div className="state"><p>{busy ? 'Buscando…' : 'Digite ao menos 2 letras.'}</p></div>}
        {items.map((it, i) => {
          const head = it.group !== lastGroup ? <div className="grp" key={'g' + i}>{it.group}</div> : null
          lastGroup = it.group
          return <div key={i}>{head}
            <div className={`it${i === sel ? ' sel' : ''}`} onMouseEnter={() => setSel(i)} onClick={it.go}>
              <span className="truncate">{it.label}</span>
              {it.tone && <Chip tone={it.tone}>VIP</Chip>}
              {it.hint && <span className="k truncate" style={{ maxWidth: 220 }}>{it.hint}</span>}
            </div></div>
        })}
      </div>
      <div className="ft"><span><kbd className="k">↑↓</kbd> navegar</span><span><kbd className="k">↵</kbd> abrir</span><span><kbd className="k">esc</kbd> fechar</span>{busy && <span className="spin" style={{ marginLeft: 'auto', width: 12, height: 12 }} />}</div>
    </div>
  </div>
}
