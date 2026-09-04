export type Role = 'ADMIN' | 'MANAGER' | 'OPERATOR' | 'VIEWER'
export const ROLES: Role[] = ['VIEWER', 'OPERATOR', 'MANAGER', 'ADMIN']
export type Level = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
export type Policy = 'SAFE' | 'REQUIRES_CONFIRMATION' | 'REQUIRES_APPROVAL' | 'BLOCKED'

export interface User { id: number; email: string; name: string; role: Role }

export interface Integration {
  system: string; status: 'CONNECTED' | 'SYNCING' | 'DEGRADED' | 'ERROR' | 'DISCONNECTED'
  last_success_at: string | null; last_attempt_at: string | null; error_count: number
  last_error: string | null; detail: string | null
}

export interface Attention {
  key: string; level: Level; title: string; why: string
  dismissed: null | { by: string | null; at: string; reason: string | null }
  entity: { type: string; id: number | string | null }
  client_id: number | null; link: string | null; action: string
}

export interface Dashboard {
  active_clients: number; tasks_due_today: number; overdue_tasks: number; upcoming_7d: number
  waivers_open: number; waivers_bounced: number; emails_attention: number
  ai_actions_today: number; ai_pending_approval: number
  open_invoices: null | { count: number; total: number; overdue: number; connected: boolean }
  integrations: Pick<Integration, 'system' | 'status' | 'last_success_at'>[]
  needs_attention: Attention[]; needs_attention_total: number
  last_sync: { system: string; at: string | null; ok: number | null; message: string | null }[]
}

export interface Link { system: string; external_id: string; deep_link: string | null }

export interface Client {
  id: number; name: string; company: string | null; email: string | null; phone: string | null
  pilot_name: string | null; pilot_dob: string | null; vip: number; status: string
  stage_code: string | null; stage?: string | null; source: string | null; notes: string | null
  status_locked?: number; last_service_at?: string | null; scanned_at?: string | null
  created_at: string; updated_at: string
  open_tasks?: number; done_tasks?: number; last_service?: string | null
  next_service?: string | null; waiver_status?: string | null
  emails_open?: number; last_activity?: string | null
}

export interface Task {
  id: number; client_id: number | null; title: string; project: string | null; section: string | null
  status: string | null; due_on: string | null; assignee: string | null
  subtasks_total: number | null; subtasks_done: number | null; synced_at: string
  fields?: string | null; section_gid?: string | null
  client_name?: string | null; links?: Link[]
}

export interface Waiver {
  id: number; client_id: number | null; signer_name: string | null; signer_email: string | null
  template: string | null; status: string | null; sent_at: string | null; completed_at: string | null
  expires_at: string | null; hidden?: number; minor_name?: string | null; link_reason?: string | null; link_by?: 'sync' | 'human' | null
  client_name?: string | null; client_pilot?: string | null; links?: Link[]
}

export interface Email {
  id: number; client_id: number | null; mailbox: string; subject: string | null; sender: string | null
  last_at: string | null; labels: string | null; priority: string | null; intent: string | null
  handled: number; snippet?: string | null; is_inbox?: number; messages?: number | null
  suggested_label?: string | null; suggested_reason?: string | null; suggested_by?: 'rules' | 'ia' | 'label' | null; suggested_at?: string | null
  client_name?: string | null; links?: Link[]
}

export interface Invoice {
  id: number; client_id: number | null; number: string | null; amount: number | null
  balance: number | null; status: string | null; issued_on: string | null; due_on: string | null
}

export interface TimelineEvent {
  at: string; kind: 'SERVICE' | 'WAIVER_SENT' | 'WAIVER_SIGNED' | 'EMAIL' | 'AI_ACTION'
  title: string; status: string; entity: { type: string; id: number }
}

export interface Client360 {
  client: Client; links: Link[]; tasks: Task[]; waivers: Waiver[]; emails: Email[]
  invoices: Invoice[] | null; ai_actions: AiAction[]; timeline: TimelineEvent[]
  stages: { code: string; label: string }[]
}

export interface AiCommand {
  id: number; user_id: number; text: string; status: 'QUEUED' | 'RUNNING' | 'DONE' | 'FAILED' | 'CANCELLED'
  created_at: string; started_at: string | null; finished_at: string | null
  output?: string | null; error: string | null; actions?: AiAction[]
}

export interface AiAction {
  id: number; command_id: number | null; workflow_id: number | null; action: string
  system: string | null; policy: Policy
  status: 'PROPOSED' | 'APPROVED' | 'REJECTED' | 'RUNNING' | 'DONE' | 'FAILED' | 'BLOCKED'
  payload: string | null; result: string | null; reason: string | null
  created_at: string; finished_at: string | null
}

export interface AuditRow {
  id?: number; at: string; actor: string; event: string; entity_type: string | null
  entity_id: string | null; detail: string | null; ip?: string | null; user_id?: number | null
}

export interface ActionPolicy {
  action: string; system: string | null; policy: Policy; note: string | null
  updated_by: number | null; updated_at: string | null
}

export interface SearchResult {
  clients: Pick<Client, 'id' | 'name' | 'pilot_name' | 'email' | 'status' | 'vip'>[]
  tasks: Pick<Task, 'id' | 'title' | 'due_on' | 'section' | 'status' | 'client_id'>[]
  waivers: Pick<Waiver, 'id' | 'signer_name' | 'signer_email' | 'status' | 'expires_at' | 'client_id'>[]
  emails: Pick<Email, 'id' | 'subject' | 'sender' | 'mailbox' | 'last_at' | 'client_id'>[]
  commands: Pick<AiCommand, 'id' | 'text' | 'status' | 'created_at'>[]
}

export interface SyncStatus {
  running: boolean; started_at: string | null; finished_at: string | null
  result: Record<string, { ok: boolean; motivo?: string; tarefas?: number; clientes_novos?: number }> | null
  logs: { id: number; system: string; started_at: string; finished_at: string; ok: number; items: number; message: string }[]
}

export interface GmailLabel { name: string; id: string | null; type: string | null; inbox_count: number }
export interface GmailMessage {
  message_id: string; de: string | null; para: string | null; data: string | null; assunto: string | null
  marcadores: string[] | null; snippet: string | null; corpo?: string; anexos?: { nome: string; mime: string; attachment_id: string | null; bytes: number | null }[] | null
}
