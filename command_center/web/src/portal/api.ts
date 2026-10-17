/* Cliente HTTP da área do cliente (#40). Separado do cliente da equipe (api/client.ts):
 * outra base (/ops/api/portal), outro cookie de CSRF (cp_csrf). Sessão em cookie HttpOnly. */
const BASE = '/ops/api/portal'

export class PortalError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

function csrf() {
  const m = document.cookie.match(/(?:^|;\s*)cp_csrf=([^;]+)/)
  return m ? decodeURIComponent(m[1]) : ''
}

export async function papi<T>(method: 'GET' | 'POST' | 'PATCH', path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (method !== 'GET') headers['X-CSRF'] = csrf()
  let res: Response
  try {
    res = await fetch(BASE + path, { method, headers, credentials: 'same-origin', body: body === undefined ? undefined : JSON.stringify(body) })
  } catch { throw new PortalError(0, 'No connection. Check your internet and try again.') }
  if (!res.ok) {
    let msg = `Something went wrong (${res.status}).`
    try {
      const j = await res.json()
      if (typeof j?.detail === 'string') msg = j.detail
      else if (Array.isArray(j?.detail) && j.detail[0]?.msg) msg = String(j.detail[0].msg)
    } catch { /* corpo não-JSON */ }
    throw new PortalError(res.status, msg)
  }
  return res.json() as Promise<T>
}

export type SituacaoMedidas = 'ok' | 'aviso' | 'vencida' | 'faltando'
export interface Driver { id: number; name: string; birth_date: string | null; is_self: boolean; email: string | null; phone: string | null
  measures: Record<string, number | string>; measures_updated_at: string | null; notes: string | null; social: string | null; age: number | null
  missing: string[]; measures_status: SituacaoMedidas; measures_days: number | null
  last_session: string | null; days_since_last_session: number | null
  /** o card do driver na URACE (#65); vazio até a equipe ligar */
  client_id: number | null }
export interface Account { id: number; email: string; name: string; birth_date: string; phone_country: string; phone: string | null
  address_line1: string | null; address_line2: string | null; city: string | null; state: string | null; zip: string | null; country: string
  linked: boolean; missing: string[]; drivers: Driver[] }

export interface Periodo { open: boolean; spots: number }
export interface Dia { date: string; weekday: number; any_open: boolean; periods: { manha: Periodo; tarde: Periodo; dia: Periodo } }
export interface AgendaCfg { morning_start: string; morning_end: string; afternoon_start: string; afternoon_end: string
  horizon_days: number; min_notice_hours: number; auto_confirm: number }
// #263: `site_kart` é a chave do kart do site que este serviço vende (vazio = não é do site)
export interface Servico { id: number; name: string; description: string | null; price: number; deposit?: number
  site_kart?: string | null }
/** #164: as etapas de um pedido, como o servidor resume para o cliente. */
export interface Checkout { id: number; status: 'pendente' | 'confirmada' | 'recusada' | 'cancelada'; date: string; period: 'manha' | 'tarde' | 'dia'
  service: string | null; price: number | null; driver: string | null; aceita: boolean; confirmada: boolean
  pagamento: { estado: 'pagar' | 'pago' | 'contrato' | 'preparando' | 'equipe'; link: string | null; invoice: string | null; total: number | null; para: string | null }
  waiver: { estado: 'ok' | 'email' | 'assinar_aqui' | 'preparando' | 'equipe'; link: string | null; para?: string | null }
  coverage?: Cobertura }
/** #169: um plano mensal que o site vende (Academy, Boost). */
export interface Plano { id: number; name: string; description: string | null; price: number; months: number; sessions_month: number; total: number }
/** #169: as etapas do plano, como o servidor resume para o cliente. */
export interface CheckoutPlano { id: number; status: 'pendente' | 'ativa' | 'cancelada'; plan: string; price: number; months: number
  sessions_month: number | null; total: number; driver: string | null; start_month: string; next_months: string[]; aceita: boolean; ativo: boolean
  pagamento: Checkout['pagamento']; waiver: Checkout['waiver'] }
export interface Booking { id: number; date: string; period: 'manha' | 'tarde' | 'dia'; status: 'pendente' | 'confirmada' | 'recusada' | 'cancelada'
  notes: string | null; decision_note: string | null; driver: string | null; created_at: string; service: string | null; price: number | null
  /** #50: aceita pela equipe — falta pagar a invoice e/ou assinar a waiver */
  accepted?: string | null; charge_kind?: 'contrato' | 'invoice' | null; invoice_doc?: string | null; invoice_link?: string | null
  invoice_sent?: number; waiver_sent?: number
  /** #314: aluno recorrente — "plano" (incluída no plano) ou "extra" (sessão extra, pela invoice) */
  coverage?: Cobertura; group_id?: number | null }
/** #314: a sessão do aluno recorrente. O cliente vê só "Included in your plan" ou "Extra session · $X". */
export type Cobertura = 'plano' | 'extra' | null
export const rotuloCobertura = (c: Cobertura | undefined, preco: number | null | undefined) =>
  c === 'plano' ? 'Included in your plan' : c === 'extra' ? `Extra session${preco != null ? ` · ${usd(preco)}` : ''}` : null

export const usd = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })

export interface Painel { account: Account; next_session: Booking | null; upcoming: number; last_session: string | null
  days_since_last_session: number | null; linked: boolean; measures_warn_days: number; measures_limit_days: number }

/** "today", "1 day ago", "23 days ago" */
export const haDias = (n: number | null) => n == null ? null : n === 0 ? 'today' : n === 1 ? '1 day ago' : `${n} days ago`

/** Waiver assinada aqui (#85): por piloto, qual vale (menor → parental) e se já está assinada. */
export interface WaiverPiloto { driver_id: number; driver: string; kind: 'adult' | 'parental' | null; status: 'signed' | 'none'
  /** #104: piloto adulto que não é o titular assina a própria waiver */
  own_signature_required: boolean
  /** #106: faz 18 nos próximos 30 dias: a parental vence na véspera e ele assina a adult */
  turns_18_on: string | null
  waiver_id: number | null; signed_at: string | null; valid_until: string | null }
export interface Waivers { enabled: boolean; drivers: WaiverPiloto[]
  /** #108: o e-mail da conta e se já foi confirmado por código */
  email: string | null; email_verified: boolean }
export interface WaiverModelo { kind: 'adult' | 'parental'; name: string; pages: number; text: string
  /** #105: a declaração do pai ou da mãe, com {minor} no lugar do nome */
  declaration: string | null }
/** #112: o resumo que o servidor devolve no passo 1 (revisão) — é exatamente o que o clique final assina. */
export interface RevisaoWaiver { review_id: number; review_expires_at: string; document: string; pages: number; kind: 'adult' | 'parental'
  driver: string; driver_birth_date: string | null; signing_as: string; relationship: string | null; guardian_declaration: string | null
  typed_name: string; name_on_file: string; name_matches: boolean; signature_sha256: string; valid_until: string; valid_until_reason: string
  /** C-4: a frase de efeito legal, mostrada ao lado do botão final, e o texto do botão */
  legal_effect: string; button: string }
/** #135: o convite da waiver por e-mail, como o link mostra (sem conta). O card e o piloto vêm do convite. */
export interface ConviteWaiver { kind: 'adult' | 'parental'; driver: string; signer_name: string; email: string; expires_at: string
  model: { name: string; pages: number; text: string; declaration: string | null } }

/** #314: o piloto é aluno recorrente (plano mensal vigente)? Nunca o contador do pacote (dono, 01/10). */
export interface PlanoPiloto { driver_id: number; recurring: boolean; plan: string | null; extra_price: number | null
  /** #314, parte 3: como paga a sessão — do plano (QuickBooks), carrinho (Stripe) ou invoice */
  payment?: 'plano' | 'stripe' | 'invoice' }
export type Turno = 'manha' | 'tarde' | 'dia'
/** #314: um dia do pedido, como o servidor vê: aberto ou não, e do plano ou extra. */
export interface DiaCotado { date: string; period: Turno; ok: boolean; reason: string | null; message: string | null
  coverage: Cobertura; price: number | null; label: string | null }
export interface Cotacao { slots: DiaCotado[]; included: number; extras: number; extras_total: number; extra_price_missing: boolean
  service: string; hash: string }
/** #314: as etapas do pedido de vários dias. */
export interface CheckoutGrupo { id: number; service: string | null; driver: string | null; status: 'pendente' | 'confirmada' | 'cancelada'
  sessions: { id: number; date: string; period: Turno; status: Booking['status']; coverage: Cobertura; price: number | null; label: string | null }[]
  included: number; extras: number; extras_total: number; aceita: boolean; confirmada: boolean
  pagamento: Checkout['pagamento']; waiver: Checkout['waiver'] }
