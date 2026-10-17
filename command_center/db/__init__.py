"""Acesso ao banco do Command Center. SQLite, sem ORM.

Uma conexão por requisição (FastAPI injeta via `get_db`), `Row` como
dict, `foreign_keys` ligado. O esquema é aplicado em toda subida — cada
bloco de schema.sql é idempotente.

O arquivo do banco fica FORA do repositório, em ~/.urace/ por padrão,
ao lado dos outros segredos (permissão 600).
"""
import json
import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(AQUI, "schema.sql")
URACE_DIR = os.environ.get("URACE_DIR", os.path.expanduser("~/.urace"))
def db_path():
    """Lido a cada chamada: testes e serviços trocam pelo ambiente."""
    return os.environ.get("CC_DB_PATH", os.path.join(
        os.environ.get("URACE_DIR", os.path.expanduser("~/.urace")), "command-center.sqlite"))


def agora():
    """ISO-8601 em UTC com milissegundos — o mesmo formato do schema."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
        f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"


def conectar(caminho=None):
    caminho = caminho or db_path()
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    novo = not os.path.exists(caminho)
    # check_same_thread=False: o FastAPI abre a dependência num thread do pool
    # e roda o endpoint em outro. A conexão é de UMA requisição, nunca é
    # compartilhada entre duas ao mesmo tempo, então é seguro.
    con = sqlite3.connect(caminho, timeout=10, isolation_level=None,  # autocommit
                          check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 10000")
    # Revisão do #328: sem isto, o INSERT OR REPLACE apaga a linha em conflito SEM disparar o trigger de DELETE, e
    # passa por cima das tabelas append-only (audit_logs, waiver_voids, waiver_template_versions…). Ligado, o REPLACE
    # nelas é recusado. Todo trigger do schema só faz RAISE (não há recursão), nenhuma FK tem CASCADE/SET NULL, e
    # as tabelas onde o código usa REPLACE (vault_unlocks, qbo_items, action_policies) não têm trigger de DELETE.
    con.execute("PRAGMA recursive_triggers = ON")
    # Em TESTE, o banco é descartável: gravar com segurança de queda de energia não
    # protege nada e custa caro. Medido na VPS em 21/09: cada fixture levava ~2 s só
    # criando a schema (o disco é volume de rede, e cada CREATE TABLE sincroniza), o que
    # colocava 170 s no deploy e fazia o terminal do dono cair antes do fim.
    #
    # Em produção NADA muda — e a trava é a mesma do custo da senha: isto só vale com o
    # pytest carregado no processo. Não há variável de ambiente que desligue a durabilidade
    # do banco de verdade, nem por engano nem de propósito.
    # Só `synchronous`: trocar `journal_mode` pede lock exclusivo e falha quando outra
    # conexão está com o banco aberto — um teste pegou isso na hora (21/09). O ganho está
    # no fsync mesmo; o journal em memória acrescentava pouco e trazia essa fragilidade.
    if "pytest" in sys.modules:
        con.execute("PRAGMA synchronous = OFF")
    if novo:
        try:
            os.chmod(caminho, 0o600)
        except OSError:
            pass
    return con


def conectar_somente_leitura(caminho=None):
    """Conexão que o SQLite **recusa** usar para escrever (`mode=ro`).

    Existe para o MCP: JSON-RPC manda leitura por POST, então a trava de "chave só de
    leitura" — que olha o método HTTP — não serve ali. Em vez de abrir uma exceção
    baseada em confiança, a rota abre o banco num modo em que escrever é impossível.
    Promessa vira garantia: se um dia alguém acrescentar por engano uma ferramenta que
    escreve, ela falha em vez de gravar.
    """
    caminho = caminho or db_path()
    con = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True, timeout=10,
                          check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout = 10000")
    return con


# Colunas acrescentadas depois do primeiro deploy: CREATE TABLE IF NOT EXISTS
# não as adiciona em banco existente; cada linha aqui é idempotente.
MIGRACOES = [
    ("tasks", "fields", "TEXT"),          # campos personalizados do Asana (json)
    ("tasks", "section_gid", "TEXT"),
    ("emails", "snippet", "TEXT"),
    ("emails", "is_inbox", "INTEGER NOT NULL DEFAULT 1"),
    ("emails", "messages", "INTEGER"),
    ("emails", "suggested_label", "TEXT"),   # sugestão da IA/regras: para onde mover
    ("emails", "suggested_reason", "TEXT"),
    ("emails", "suggested_by", "TEXT"),      # rules | ia | label (já tinha marcador)
    ("emails", "suggested_at", "TEXT"),
    ("emails", "triaged_at", "TEXT"),        # triagem automática da IA (manhã/tarde/noite)
    ("emails", "triage_reason", "TEXT"),
    ("emails", "needs_human", "INTEGER NOT NULL DEFAULT 0"),  # movido pela IA, mas pede resposta humana
    ("automation_rules", "schedule", "TEXT"),      # json: ["07:00","13:00","21:00"] hora local (Orlando)
    ("automation_rules", "last_run_at", "TEXT"),   # chave do último horário rodado: "2026-09-09 07:00"
    ("automation_rules", "last_result", "TEXT"),
    ("races", "task_id", "INTEGER"),
    ("clients", "email_alt", "TEXT"),
    ("ai_commands", "prompt", "TEXT"),              # o que foi ao agente (texto do dono + contexto); `text` é só o que o dono escreveu              # segundo e-mail da descrição (o principal fica limpo)               # tarefa da coluna RACES (calendário = o que está no Asana)
    ("gmail_labels", "mailboxes", "TEXT"),         # json: em que caixas o marcador existe, ex. ["urace","support"]
    ("gmail_labels", "origin", "TEXT"),            # caixa | ia (marcador que a IA propôs, ainda não existe no Gmail)
    ("gmail_labels", "proposed_reason", "TEXT"),   # o e-mail que motivou a proposta
    ("waivers", "hidden", "INTEGER NOT NULL DEFAULT 0"),   # lixeira do painel (restaurável)
    ("waivers", "minor_name", "TEXT"),                     # nome do menor (parental), do form data
    ("waivers", "link_reason", "TEXT"),                    # por que está ligada a este cliente
    ("waivers", "link_by", "TEXT"),                        # sync | human
    ("clients", "status_locked", "INTEGER NOT NULL DEFAULT 0"),  # status mudado à mão não é recalculado
    ("clients", "last_service_at", "TEXT"),
    ("clients", "scanned_at", "TEXT"),                     # última varredura Gmail/DocuSign deste cliente
    ("emails", "handled_by", "TEXT"),                      # user:<id> | auto
    ("emails", "handled_reason", "TEXT"),
    ("clients", "monthly_plan", "TEXT"),                  # ex.: "Academy 4 stroke" — gera a invoice do dia 1
    ("clients", "monthly_note", "TEXT"),                  # ajustes do plano (extra, desconto de contrato)
    ("clients", "plan_type", "TEXT"),                     # monthly | daily
    ("clients", "pro_driver", "INTEGER NOT NULL DEFAULT 0"),  # estrela: pronto para competir
    ("clients", "chassis_id", "INTEGER"),
    ("clients", "engine_id", "INTEGER"),
    ("clients", "equipment_notes", "TEXT"),
    ("invoices", "memo", "TEXT"),                         # ex.: "Urace Academy Training Program + Tuner [August, 2026]"
    ("invoices", "customer_email", "TEXT"),
    ("invoices", "customer_ref", "TEXT"),                 # id do cliente no QBO (a IA usa direto na próxima invoice)
    ("waivers", "pdf_path", "TEXT"),                      # PDF assinado guardado em ~/.urace/waivers (card e anexo usam)
    ("waivers", "subject", "TEXT"),                       # assunto do envelope: é o que identifica um documento interno
    ("waivers", "internal", "INTEGER NOT NULL DEFAULT 0"), # 1 = documento da empresa (support@ assina); não é waiver de cliente
    # #85: waiver assinada no próprio sistema (sem DocuSign), na mesma tabela das do DocuSign
    ("waivers", "source", "TEXT"),                        # urace = assinada aqui; NULL = DocuSign (espelho)
    ("waivers", "pilot_id", "INTEGER"),                   # piloto da área do cliente a que ela vale
    ("waivers", "doc_sha256", "TEXT"),                    # hash do PDF final (prova de que não mudou)
    ("waivers", "audit", "TEXT"),                         # json: quem, quando, IP, aparelho, consentimentos, hashes
    ("booking_config", "waiver_native", "INTEGER NOT NULL DEFAULT 0"),   # 0: desligada até o ADMIN ligar
    ("portal_accounts", "email_verified_at", "TEXT"),       # #108: o e-mail da conta confirmado por código
    ("tasks", "waiver_id", "INTEGER"),                    # waiver que já foi anexada nesta tarefa (não anexa duas vezes)
    ("crm_messages", "status", "TEXT"),                   # saída: queued | sent | failed (entrada fica NULL)
    ("crm_messages", "error", "TEXT"),
    ("crm_leads", "return_url", "TEXT"),                  # continuação do Salesbot em aberto (efêmera)
    ("crm_leads", "return_token", "TEXT"),
    ("crm_leads", "return_at", "TEXT"),
    ("crm_leads", "last_hook_at", "TEXT"),                # última vez que o bot falou com o painel por este lead
    ("crm_leads", "link_by", "TEXT"),
    ("crm_leads", "detail", "TEXT"),                      # retrato completo do lead no Kommo (json de kommo_lead_completo)
    ("crm_leads", "detail_at", "TEXT"),
    ("crm_leads", "starred", "INTEGER"),                   # conversa favorita (estrela na lista do chat)
    ("crm_messages", "starred", "INTEGER"),                # mensagem favorita dentro da conversa
    ("crm_leads", "contact_avatar", "TEXT"),               # foto do perfil que o Kommo manda no webhook (author.avatar_url)
    ("crm_leads", "profiles", "TEXT"),                     # json {instagram: "@usuario", facebook: "url"} informado no painel                     # human = vínculo com o cliente feito à mão (a sincronia não mexe)
    # 21/09: entregar uma vez e torcer não é entregar. A fila agora insiste sozinha e a
    # entrega só é dada por certa quando o próprio Kommo devolve a mensagem.
    ("crm_messages", "tentativas", "INTEGER NOT NULL DEFAULT 0"),
    ("crm_messages", "ultima_tentativa", "TEXT"),
    ("crm_messages", "confirmado_em", "TEXT"),             # o Kommo devolveu esta mensagem: chegou mesmo
    ("api_keys", "read_only", "INTEGER NOT NULL DEFAULT 1"),   # chave que lê e não mexe (padrão)
    # 21/09, o dono explicando a intenção do chat interno: falar com uma pessoa em um
    # clique, montar grupo com nome e foto, e poder silenciar os dois.
    ("team_channels", "icon", "TEXT"),        # emoji do grupo (o barato: não precisa de upload)
    ("team_channels", "image_path", "TEXT"),  # foto do grupo, guardada fora do repositório
    # conversa direta entre duas pessoas: "menor-maior" dos ids. O UNIQUE é o que impede
    # duas conversas paralelas entre as mesmas pessoas — cada uma com metade do histórico.
    ("team_channels", "dm_key", "TEXT"),
    # 22/09 — dono: "pode só separar". Card que é corrida/tarefa não é apagado: sai da
    # lista de clientes com kind='separado', e continua consultável.
    ("clients", "kind", "TEXT NOT NULL DEFAULT 'cliente'"),
    # 22/09 — dono: "o princípio para cruzar e confirmar é usar o nome do responsável e
    # informações de contato" — e "aplique como base de agora para frente". A sincronia
    # já lia isso da descrição da tarefa e jogava fora; agora fica na tarefa, para a
    # atribuição decidir por contato antes de olhar o título.
    ("tasks", "resp_name", "TEXT"),
    ("tasks", "resp_email", "TEXT"),
    ("tasks", "resp_phone", "TEXT"),
    ("tasks", "desc_read_at", "TEXT"),
    # 22/09 — o dono CONFIRMOU de quem é o serviço. A varredura nunca mexe nisso de novo:
    # "está certo hoje" não basta, porque um homônimo novo no cadastro faria o serviço sair.
    ("tasks", "client_by", "TEXT"),        # sync | human
    ("tasks", "client_at", "TEXT"),   # quando a descrição foi lida — mesmo que não tivesse contato nenhum
    # Foto da peça, tirada pelo mecânico no celular (dono, 23/09). Só o nome do arquivo:
    # a imagem mora em ~/.urace/estoque, fora do banco e fora do repositório.
    ("stock_items", "image_path", "TEXT"),
    # 29/09 — dono: estoque em fileiras de categoria (pneus, motores, peças de motor,
    # hardware… vestuário por último), subcategoria (marca do pneu, família do motor) e
    # medida; e o preço: quanto pagamos, a margem (campo livre: "15%" ou "20") e o valor
    # final que vai para a invoice do cliente. Prateleira é onde aparece; o `kind` não muda.
    ("stock_items", "category", "TEXT"),
    ("stock_items", "subcategory", "TEXT"),
    ("stock_items", "size", "TEXT"),
    ("stock_items", "cost", "REAL"),
    ("stock_items", "markup", "TEXT"),
    ("stock_items", "price", "REAL"),
    # 29/09 — dono: o valor da mensalidade é do cliente, não só da tabela ("às vezes um
    # deal diferente"). É ele que vai na invoice do dia 1 e na recorrência do QuickBooks.
    ("clients", "monthly_amount", "REAL"),
    ("clients", "monthly_item_id", "TEXT"),        # item do catálogo do QuickBooks da mensalidade
    # 29/09 — dono: "é para ser uma recorrência só, vinculada uma à outra". painel = criada
    # por aqui; qbo = já existia no QuickBooks e foi VINCULADA ao card (não criada de novo).
    ("monthly_recurring", "source", "TEXT NOT NULL DEFAULT 'painel'"),
    # 30/09 — ponte do chat da equipe com o WhatsApp: o que aconteceu com a mensagem lá fora
    # (enviado, entregue, lido, falhou, fora da janela de 24 h, simulação) e o porquê.
    ("team_messages", "wa_status", "TEXT"),
    ("team_messages", "wa_error", "TEXT"),
    # 30/09 — dono: "todo email relacionado a compra que chegar no urace@ se torne um item de
    # compra, e toda atualização de envio / pagamento / entregue atualize". O andamento da
    # ENTREGA (e-mail) é separado do status do ESTOQUE: "entregue" pela transportadora não é
    # "recebida" — alguém ainda conta o que chegou e dá entrada.
    ("purchase_orders", "source", "TEXT NOT NULL DEFAULT 'painel'"),   # painel | email
    ("purchase_orders", "order_number", "TEXT"),     # nº do pedido na loja, lido do e-mail
    ("purchase_orders", "tracking", "TEXT"),         # rastreio(s), separados por espaço
    ("purchase_orders", "carrier", "TEXT"),          # UPS, FedEx, USPS, DHL, Amazon
    ("purchase_orders", "ship_status", "TEXT"),      # pedido | pago | enviado | entregue | cancelado
    ("purchase_orders", "paid_at", "TEXT"),
    ("purchase_orders", "shipped_at", "TEXT"),
    ("purchase_orders", "delivered_at", "TEXT"),
    ("purchase_orders", "email_total", "REAL"),      # total que a loja disse no e-mail
    ("purchase_orders", "items_hint", "TEXT"),       # o que a loja disse que foi (assunto)
    # 06/10 — dono: "chegou uma fatura daquele pedido. Ah, está pendente o pagamento" e "tem que
    # abrir o link". Fatura do fornecedor, pagamento pendente/pago, link do pedido e o espelho
    # da compra no quadro Shipping Orders do Asana.
    ("purchase_orders", "invoice_number", "TEXT"),   # nº da fatura do fornecedor (INV-116671, 1678)
    ("purchase_orders", "payment_status", "TEXT"),   # pendente | pago
    ("purchase_orders", "amount_due", "REAL"),       # quanto a fatura pede
    ("purchase_orders", "order_url", "TEXT"),        # página do pedido / rastreio que veio no e-mail
    ("purchase_orders", "asana_gid", "TEXT"),        # tarefa no Shipping Orders
    ("purchase_orders", "asana_synced_at", "TEXT"),
    ("purchase_orders", "asana_error", "TEXT"),
    ("purchase_events", "stage", "TEXT"),            # pagamento_pendente, em_transito, saiu_para_entrega…
    ("purchase_events", "url", "TEXT"),              # link de rastreio/pedido do e-mail (ou a página lida)
    ("purchase_events", "invoice_number", "TEXT"),
    # 01/10 — dono: o preço é editável; o agendamento guarda o serviço e o valor do dia.
    ("bookings", "service_id", "INTEGER"),
    ("bookings", "service_name", "TEXT"),
    ("bookings", "price", "REAL"),
    # 01/10 — dono (#54): cliente de outro país (telefone com código) e rede social do piloto.
    ("portal_accounts", "phone_country", "TEXT NOT NULL DEFAULT '+1'"),
    ("portal_pilots", "social", "TEXT"),
    # 01/10 — dono (#52): "toda segunda fica bloqueado para não ter nenhuma aula". Bloqueio
    # recorrente: vale só naquele dia da semana, dentro do intervalo (fim aberto = 9999-12-31).
    ("booking_blocks", "weekday", "INTEGER"),
    # 01/10 — dono (#61): o item do serviço pode ser um texto livre (vai na linha da invoice),
    # e o contrato mensal diz quantas sessões cabem no mês.
    ("booking_services", "invoice_text", "TEXT"),
    ("clients", "monthly_sessions", "INTEGER"),
    # 01/10 — dono (#65): "um client id para cada driver". Cada piloto da conta liga ao SEU
    # card do site interno; a conta (o responsável) continua com o card principal.
    ("portal_pilots", "client_id", "INTEGER REFERENCES clients(id)"),
    ("portal_pilots", "linked_by", "INTEGER REFERENCES users(id)"),
    ("portal_pilots", "linked_at", "TEXT"),
    # 08/10 — dono (#158): "Todo lugar que a gente for fazer inserção manual, sempre coloque um para
    # vincular com o cliente". O lead de macacão também liga ao card.
    ("suit_leads", "client_id", "INTEGER REFERENCES clients(id)"),
    # 13/10 — dono (#195): "nenhum desse aí foi e-mail de suit … limpa esses daí". O pedido que não é
    # de macacão é DESCARTADO (some das listas, a ponte ignora), nunca apagado: dá para restaurar.
    ("suit_orders", "discarded_at", "TEXT"),
    ("suit_orders", "discard_reason", "TEXT"),
    ("suit_orders", "discarded_by", "INTEGER REFERENCES users(id)"),
    # 13/10 — dono (#198): "um switch para poder ligar e desligar IA naquele pedido". 1 = a IA age no pedido.
    ("suit_orders", "ia_ligada", "INTEGER NOT NULL DEFAULT 1"),
    # 13/10 — dono (#206): "Escaneou, selecionou o cliente, já finaliza. Não tem essa de ter que confirmar
    # depois". A leitura do celular vai direto para a OS; só o que não pode ir fica pendente, com o motivo.
    ("counter_pending", "motivo", "TEXT"),
    # 13/10 — dono (#219): "ela exclui, deixa de ser mostrada, mas lá no histórico de serviço ela continua
    # sendo armazenada como uma tarefa excluída". Nada sai do banco nem do Asana; só deixa de aparecer.
    ("tasks", "deleted_at", "TEXT"),
    ("tasks", "deleted_by", "INTEGER"),
    ("tasks", "deleted_reason", "TEXT"),
    # 01/10 — dono (#67): "todo agendamento... vira uma tarefa no asana".
    ("bookings", "asana_gid", "TEXT"),
    ("bookings", "asana_status", "TEXT"),        # a última situação levada ao Asana
    ("bookings", "asana_error", "TEXT"),
    ("bookings", "asana_attempts", "INTEGER NOT NULL DEFAULT 0"),
    # #50 PR B (dono, 06/10): aceitar a vaga cobra e pede a waiver; confirma sozinha com pago + waiver
    ("bookings", "accepted_at", "TEXT"),
    ("bookings", "accepted_by", "INTEGER"),
    ("bookings", "charge_kind", "TEXT"),                # contrato | invoice
    ("bookings", "qbo_invoice_id", "TEXT"),
    ("bookings", "invoice_doc", "TEXT"),
    ("bookings", "invoice_total", "REAL"),
    ("bookings", "invoice_link", "TEXT"),
    ("bookings", "invoice_sent_to", "TEXT"),
    ("bookings", "charge_error", "TEXT"),
    ("bookings", "charge_attempts", "INTEGER NOT NULL DEFAULT 0"),
    ("bookings", "waiver_ref", "INTEGER"),               # waivers.id do envelope mandado ao aceitar
    ("bookings", "waiver_error", "TEXT"),
    ("bookings", "reminded_3d_at", "TEXT"),
    ("bookings", "reminded_1d_at", "TEXT"),
    ("bookings", "reminder_error", "TEXT"),
    # #164 (dono, 08/10): "um site totalmente automático que venda sozinho, sem precisar de um humano"
    ("booking_config", "auto_sell", "INTEGER NOT NULL DEFAULT 0"),   # 0: a equipe aceita cada pedido (como antes)
    ("bookings", "pay_link", "TEXT"),             # link de pagamento do CLIENTE (InvoiceLink do QuickBooks)
    ("bookings", "paid_at", "TEXT"),              # o QuickBooks disse que a invoice está paga (conferência direta)
    ("bookings", "pay_checked_at", "TEXT"),       # última conferência direta (no máximo 1 por minuto)
    ("bookings", "origin", "TEXT"),               # site | portal
    ("bookings", "utm", "TEXT"),                  # json: de onde veio a venda (utm_source, utm_campaign…)
    ("bookings", "card_note", "TEXT"),            # o que a venda automática fez com o card (criado, ligado, possível duplicado)
    ("bookings", "notified_received_at", "TEXT"),
    ("bookings", "notified_confirmed_at", "TEXT"),
    ("booking_services", "deposit", "REAL"),             # depósito por sessão (Arrive and Drive: 400)
    # #169: plano mensal vendido pelo site (Academy, Boost): preço por mês, meses do compromisso, sessões por mês
    ("booking_services", "kind", "TEXT NOT NULL DEFAULT 'session'"),
    ("booking_services", "months", "INTEGER"),
    ("booking_services", "sessions_month", "INTEGER"),
    # #263 (dono, 15/10): a chave do kart do site que este serviço vende (`vitrine.conteudo.KARTS`).
    # O site casa serviço e kart por ela, igual e exata — nunca mais por "o nome contém o do kart".
    ("booking_services", "site_kart", "TEXT"),
    # #297 (dono, 16/10): o cartão do kart no site sai do painel — nome no site, linha de baixo, aviso no
    # cartão e "o cliente traz o kart" (vazio/NULL = o texto de sempre de `vitrine.conteudo.KARTS`)
    ("booking_services", "site_title", "TEXT"),
    ("booking_services", "site_subtitle", "TEXT"),
    ("booking_services", "site_note", "TEXT"),
    ("booking_services", "own_kart", "INTEGER"),
    # 05/10 — dono (#87): balcão com leitor. Cada card tem um QR próprio (código opaco, não
    # o id); cada peça pode ter o item dela no QuickBooks, criado quando o código é cadastrado.
    ("clients", "scan_code", "TEXT"),
    ("stock_items", "qbo_item_id", "TEXT"),
    ("stock_items", "qbo_item_name", "TEXT"),
    # a peça cobrada pelo balcão entra na invoice de peças do dia daquele cliente
    ("stock_charges", "parts_invoice_id", "INTEGER REFERENCES parts_invoices(id)"),
    # 06/10 — cartão no Balcão (QuickBooks GoPayment): quando a invoice de peças foi paga.
    ("parts_invoices", "paid_at", "TEXT"),
    ("parts_invoices", "paid_amount", "REAL"),
    # 05/10 — dono (#92): cargo de quem trabalha no box. O papel continua OPERATOR (é o que
    # libera lançar peça, contar estoque…); o cargo RESTRINGE: o mecânico e o coach só alcançam
    # as rotas da lista aprovada (auth.ROTAS_DO_CARGO). NULL = sem restrição de cargo.
    ("users", "cargo", "TEXT"),
    # 14/10 — dono (#204): o item do catálogo do QuickBooks da venda (o preço da tabela vem dele,
    # não do valor da venda) e o card de irmão criado à mão (mesmo responsável, e-mail e telefone;
    # piloto diferente). `sibling_of` aponta o card de onde a família começou: os dois nunca se unem.
    ("opportunities", "qbo_item_id", "TEXT"),
    ("clients", "sibling_of", "INTEGER REFERENCES clients(id)"),
    # 14/10 — dono (#236): carrinho do site. Um pedido do Stripe com várias linhas (produtos e sessões
    # da agenda); as linhas ficam em store_order_items. O pedido de um produto só (#174) continua igual.
    ("store_orders", "kind", "TEXT NOT NULL DEFAULT 'produto'"),      # produto (#174) | carrinho (#236)
    ("store_orders", "account_id", "INTEGER REFERENCES portal_accounts(id)"),   # a conta do site que comprou
    ("store_orders", "attention", "TEXT"),        # o que a equipe precisa resolver (ex.: a vaga sumiu antes do pagamento)
    ("bookings", "store_order_id", "INTEGER REFERENCES store_orders(id)"),      # sessão paga no carrinho do site
    # 14/10 — dono (#245): "monte páginas para cada um no site" (os 4 eventos do Stripe). O resultado que
    # o webhook trouxe (falhou | expirado), para quem vai o aviso e quando saiu (um aviso por pedido), e o
    # pedido de onde este saiu ("Try again" / "Restore cart").
    ("store_orders", "outcome", "TEXT"),
    ("store_orders", "outcome_email", "TEXT"),
    ("store_orders", "outcome_notified_at", "TEXT"),
    ("store_orders", "outcome_notify_error", "TEXT"),
    ("store_orders", "retry_of", "INTEGER REFERENCES store_orders(id)"),
    # 14/10 — dono (#248): "switch para mudar de português para inglês". O idioma em que a pessoa
    # comprou (en | pt): os e-mails do pagamento saem nele.
    ("store_orders", "lang", "TEXT"),
    # 15/10 — dono (#260): medição de campanha no site. De onde o contato veio (json com utm_source,
    # utm_medium, utm_campaign, utm_term, utm_content, gclid, fbclid, fbp, fbc, campaign_id, adset_id).
    # Só campanha: nenhum dado da pessoa entra aqui.
    ("opportunities", "campaign", "TEXT"),
    # 16/10 — dono (#298): "nos produtos da loja, colocar o valor de envio, o shipping … o valor do Security
    # Deposit". O frete cobrado com "Ship to me" (o do pedido e o de cada linha) e o depósito do pedido de um
    # produto só ("Buy now"). NULL nos pedidos de antes: o frete era combinado à parte.
    ("store_orders", "shipping_fee", "REAL"),
    ("store_orders", "deposit", "REAL"),
    ("store_order_items", "shipping", "REAL"),
    # 16/10 — dono (#305): "toda vez que criar a conta, a pessoa recebe o um e-mail com a nossa identidade";
    # o piloto da sessão paga pode completar o cadastro depois, "com lembretes pelo email ate completar".
    ("portal_accounts", "welcome_sent_at", "TEXT"),      # o e-mail de boas-vindas saiu (só essas contas recebem os avisos)
    ("portal_accounts", "welcome_error", "TEXT"),
    ("portal_accounts", "welcome_lang", "TEXT"),         # en | pt: o idioma dos avisos seguintes
    ("portal_accounts", "client_id_sent_at", "TEXT"),    # o número do card ligado à CONTA (compra só de produto) saiu
    ("portal_accounts", "client_id_sent", "INTEGER"),    # qual número foi (a equipe uniu ou religou: manda o certo)
    ("portal_pilots", "client_id_sent", "INTEGER"),
    ("portal_pilots", "client_id_sent_at", "TEXT"),      # o e-mail com o número de cliente (o card) saiu
    ("portal_pilots", "remind_at", "TEXT"),              # o último lembrete de completar o piloto
    ("portal_pilots", "remind_n", "INTEGER"),
    ("bookings", "pilot_pending", "INTEGER NOT NULL DEFAULT 0"),   # paga com o piloto incompleto: lembrar até completar
    # 16/10 — dono (#306): o painel do site diz de onde veio cada venda; o pedido do carrinho e do Buy now guarda a campanha
    ("store_orders", "utm", "TEXT"),
    # 16/10 — dono (#311): a sessão do parts.urace.us nasce de uma sessão do painel; sair do painel derruba as duas
    ("sessions", "parent_id", "TEXT"),
    # 16/10 — dono (#317): Site › Security deposit. Quanto o pagamento já teve devolvido no Stripe (lido no "Conferir"),
    # e o serviço cujo depósito é obrigatório ("o serviço que eu coloquei no checkout ia permitir … sem o security deposit")
    ("store_orders", "stripe_refunded", "REAL"),
    ("booking_services", "deposit_required", "INTEGER"),   # NULL = de antes da caixa: a pós-migração decide uma vez
    # 16/10 — dono (#309): "a gente seleciona o que que é dropshipping e o que que a gente tem em estoque … não precisa
    # ficar aparente … para os clientes". O marcador interno de cada produto (dropshipping: nada muda no site no dia do
    # deploy) e a baixa do estoque na venda paga: o movimento (idempotência) e o que a equipe precisa resolver.
    ("store_products", "fulfillment", "TEXT NOT NULL DEFAULT 'dropshipping' CHECK (fulfillment IN ('dropshipping','estoque'))"),
    ("store_orders", "stock_move_id", "INTEGER REFERENCES stock_moves(id)"),
    ("store_orders", "stock_note", "TEXT"),
    ("store_order_items", "stock_move_id", "INTEGER REFERENCES stock_moves(id)"),
    ("store_order_items", "stock_note", "TEXT"),
    # revisão do #309: o "Resolver: sem estoque" que a equipe já resolveu (botão Resolvido em Pedidos do site) sai do
    # "Resolver" do pedido e do "Pagos sem estoque" do Painel do site; a frase fica na linha e no histórico
    ("store_orders", "stock_resolved_at", "TEXT"),
    ("store_orders", "stock_resolved_by", "INTEGER REFERENCES users(id)"),
    ("store_order_items", "stock_resolved_at", "TEXT"),
    ("store_order_items", "stock_resolved_by", "INTEGER REFERENCES users(id)"),
    # 16/10 — dono (#314): "se ele já tiver usado as sessões daquele pacote dele mensal, aí ele paga uma sessão
    # adicional … o valor do mensal dele dividido para duas ou quatro sessões … ou então usa aqueles valores".
    # O valor e o item do QuickBooks da sessão extra: no card (o combinado com o cliente, vence) e no plano do site.
    ("clients", "extra_session_price", "REAL"),
    ("clients", "extra_item_id", "TEXT"),
    ("booking_services", "extra_price", "REAL"),
    ("booking_services", "extra_item_id", "TEXT"),
    # A sessão do aluno recorrente: `plano` (dentro do pacote do mês, sem custo) ou `extra` (cobrada pela invoice);
    # NULL = avulsa ou de antes. `price` passa a ser o que é cobrado (0 no plano); `list_price` guarda o da tabela.
    ("bookings", "coverage", "TEXT"),
    ("bookings", "list_price", "REAL"),
    # #314: o pedido de vários dias de onde a sessão saiu (as extras do pedido saem numa invoice só)
    ("bookings", "group_id", "INTEGER REFERENCES booking_groups(id)"),
    # 16/10 — dono (#315): o editor do site "como um Canva". Cada rascunho salvo soma 1: dois gerentes na mesma página
    # não apagam o que o outro fez, e o Publicar só põe no ar o que a tela mostra
    ("site_pages", "rev", "INTEGER NOT NULL DEFAULT 0"),
    # #116: o ponteiro da versão atual de cada modelo da waiver nativa (as versões ficam em waiver_template_versions)
    ("waiver_templates", "version_id", "INTEGER REFERENCES waiver_template_versions(id)"),
]
INDICES_EXTRA = [
    "CREATE UNIQUE INDEX IF NOT EXISTS clients_scan_code ON clients(scan_code) WHERE scan_code IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS portal_pilots_client ON portal_pilots(client_id) WHERE client_id IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS team_channels_dm ON team_channels(dm_key) WHERE dm_key IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS bookings_pedido ON bookings(store_order_id) WHERE store_order_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS bookings_grupo ON bookings(group_id) WHERE group_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS store_orders_refeito ON store_orders(retry_of) WHERE retry_of IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS sessions_pai ON sessions(parent_id) WHERE parent_id IS NOT NULL",
]


# #109 (dono, 06/10: "nunca apagar"; issue: "ficam livres só hidden e client_id"): a linha da waiver
# assinada no próprio sistema não muda e não sai do banco. Livres ficam o vínculo com o card (unir,
# soltar e vincular à mão escrevem os três juntos) e a lixeira do painel, que a rota e a IA já recusam
# para a nativa assinada. O resto é prova. O que vem depois de assinar (anulação, e-mail, conferência
# no balcão) vai para tabela própria (`waiver_voids`…), nunca para esta linha nem para `audit`.
# Coluna nova em `waivers` tem de entrar numa das duas listas (test_waiver_imutavel.py trava).
WAIVER_LIVRES = ("client_id", "link_by", "link_reason", "hidden")
WAIVER_TRAVADAS = ("id", "signer_name", "signer_email", "template", "status", "sent_at", "completed_at", "expires_at",
                   "synced_at", "minor_name", "pdf_path", "subject", "internal", "source", "pilot_id", "doc_sha256", "audit")


def waiver_anulada(alias="waivers"):
    """SQL: a waiver `alias` foi anulada (#109). A linha dela continua `completed`; quem vale é `waiver_voids`."""
    return f"EXISTS (SELECT 1 FROM waiver_voids v WHERE v.waiver_id = {alias}.id)"


def status_da_waiver(alias="waivers"):
    """SQL: o status que a tela e a IA leem — a anulada aparece como `voided`, como a anulada do DocuSign."""
    return f"CASE WHEN {waiver_anulada(alias)} THEN 'voided' ELSE {alias}.status END"


# Tabelas de prova da waiver que só recebem INSERT: o banco recusa UPDATE e DELETE, como no `audit_logs`.
# #116: as versões dos modelos; #111: a trilha de eventos. A trava é criada (ou trocada, se o texto mudou) a cada
# subida, com as da waiver.
WAIVER_SO_INSERT = ("waiver_template_versions", "waiver_events")
# #112: a revisão antes do clique final só aceita marcar `used_at`, uma vez (na transação da assinatura); o resto é
# prova e não muda, e nada sai. Coluna nova em `waiver_reviews` tem de entrar aqui (test_waiver_revisao.py trava).
REVISAO_TRAVADAS = ("id", "created_at", "expires_at", "flow", "account_id", "invite_id", "pilot_id", "client_id", "kind",
                    "template_version_id", "template_sha256", "content_sha256", "typed_name", "name_on_file", "name_matches",
                    "signer_relationship", "ip", "user_agent")


def _so_insert(tabela):
    return {f"{tabela}_no_{op.lower()}": (f"CREATE TRIGGER {tabela}_no_{op.lower()} BEFORE {op} ON {tabela}\n"
                                         f"BEGIN SELECT RAISE(ABORT, '{tabela} is append-only'); END")
            for op in ("UPDATE", "DELETE")}


def _travas_da_waiver():
    mudou = " OR ".join(f"NEW.{c} IS NOT OLD.{c}" for c in WAIVER_TRAVADAS)
    return {
        **{nome: sql for t in WAIVER_SO_INSERT for nome, sql in _so_insert(t).items()},
        "waivers_nativa_imutavel": (
            "CREATE TRIGGER waivers_nativa_imutavel BEFORE UPDATE ON waivers\n"
            f"WHEN (OLD.source IS 'urace' AND ({mudou})) OR (NEW.source IS 'urace' AND OLD.source IS NOT 'urace')\n"
            "BEGIN SELECT RAISE(ABORT, 'signed native waiver is immutable (#109)'); END"),
        "waivers_nativa_sem_apagar": (
            "CREATE TRIGGER waivers_nativa_sem_apagar BEFORE DELETE ON waivers\n"
            "WHEN OLD.source IS 'urace'\n"
            "BEGIN SELECT RAISE(ABORT, 'signed native waiver is never deleted (#109)'); END"),
        "waiver_reviews_so_usar": (
            "CREATE TRIGGER waiver_reviews_so_usar BEFORE UPDATE ON waiver_reviews\n"
            "WHEN OLD.used_at IS NOT NULL OR NEW.used_at IS NULL OR "
            + " OR ".join(f"NEW.{c} IS NOT OLD.{c}" for c in REVISAO_TRAVADAS) + "\n"
            "BEGIN SELECT RAISE(ABORT, 'waiver_reviews: only used_at, once (#112)'); END"),
        "waiver_reviews_no_delete": (
            "CREATE TRIGGER waiver_reviews_no_delete BEFORE DELETE ON waiver_reviews\n"
            "BEGIN SELECT RAISE(ABORT, 'waiver_reviews is append-only (#112)'); END"),
    }


def _travar_waivers(con):
    """Cria as travas a cada subida e troca a que mudou de texto (coluna nova na lista), numa transação:
    não há instante em que a waiver fique sem trava. Igual ao que já está no banco, não mexe."""
    for nome, sql in _travas_da_waiver().items():
        atual = con.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (nome,)).fetchone()
        if atual and atual[0].strip() == sql:
            continue
        dentro = con.in_transaction
        if not dentro:
            con.execute("BEGIN IMMEDIATE")
        try:
            con.execute(f"DROP TRIGGER IF EXISTS {nome}")
            con.execute(sql)
            if not dentro:
                con.execute("COMMIT")
        except Exception:
            if not dentro:
                con.execute("ROLLBACK")
            raise


def _versionar_modelos(con):
    """#116: o modelo da waiver nativa importado antes das versões entra como a versão dele, uma vez, e o
    ponteiro passa a apontar para ela. Nada é reescrito: a versão é a cópia do que já estava no ponteiro."""
    for kind, sha, name, path, pages, text, source, at, by in con.execute(
            """SELECT kind, sha256, name, pdf_path, pages, text, source, imported_at, imported_by
                 FROM waiver_templates WHERE version_id IS NULL""").fetchall():
        con.execute("""INSERT OR IGNORE INTO waiver_template_versions (kind, sha256, name, pdf_path, pages, text, source,
                       imported_at, imported_by) VALUES (?,?,?,?,?,?,?,?,?)""", (kind, sha, name, path, pages, text, source, at, by))
        vid = con.execute("SELECT id FROM waiver_template_versions WHERE kind=? AND sha256=?", (kind, sha)).fetchone()[0]
        con.execute("UPDATE waiver_templates SET version_id=? WHERE kind=?", (vid, kind))


def aplicar_schema(con):
    with open(SCHEMA, encoding="utf-8") as f:
        con.executescript(f.read())
    for tabela, coluna, tipo in MIGRACOES:
        existentes = {r[1] for r in con.execute(f"PRAGMA table_info({tabela})")}
        if coluna not in existentes:
            con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
    for sql in INDICES_EXTRA:        # índices de colunas que só existem depois da migração
        con.execute(sql)
    _travar_waivers(con)             # #109: depois das migrações, porque as colunas de prova vêm delas
    _versionar_modelos(con)          # #116: o modelo importado antes das versões vira a versão dele
    _migrar_papeis(con)             # o papel CLOSER foi desfeito: quem tiver vira OPERATOR
    _herdar_card_do_piloto(con)      # #65: conta já vinculada → o piloto daquele card herda o card
    _semear_marcadores(con)          # depois das migrações: a semente escreve `mailboxes`
    for sql in POS_MIGRACAO:
        con.execute(sql)
    _importar_produtos(con)          # #298: os produtos do WooCommerce entram no banco uma vez
    _importar_posts(con)             # #172: os 7 artigos do WordPress, uma vez, com o HTML como está


PRODUTOS_WOO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vitrine", "dados", "produtos.json")
POSTS_WP = os.path.join(os.path.dirname(PRODUTOS_WOO), "posts.json")


def _importar_posts(con):
    """#172 (dono, 16/10: *"editor do blog, pode seguir"*): os 7 artigos de `posts.json` passam para `blog_posts`
    **uma vez**, como estão (id do WordPress, data, capa e o HTML cru). Só roda com a tabela vazia: o que a equipe
    escrever, mudar ou tirar do ar depois nunca volta."""
    from command_center.providers import blog
    blog.importar(con, POSTS_WP)


def _importar_produtos(con):
    """#298 (dono, 16/10: *"nos produtos da loja … que eu consiga alterar"*): os 70 produtos copiados do WooCommerce
    passam para `store_products` **uma vez**, como estão (id, ordem, fotos, variações): a loja não muda nada no
    dia da troca. Só roda com a tabela vazia, então o que a equipe mudar ou esconder depois nunca volta."""
    if con.execute("SELECT 1 FROM store_products LIMIT 1").fetchone():
        return
    try:
        with open(PRODUTOS_WOO, encoding="utf-8") as f:
            produtos = json.load(f)["produtos"]
    except (OSError, ValueError, KeyError):
        return
    j = lambda v: json.dumps(v or [], ensure_ascii=False)  # noqa: E731
    con.executemany(
        """INSERT OR IGNORE INTO store_products (id, slug, name, kind, price, regular, on_sale, price_min, price_max, short,
                  description, images, categories, tags, attributes, variations, in_stock, sku, sort, origin)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'woocommerce')""",
        [(p["id"], p["slug"], p["name"], "variable" if p.get("type") == "variable" else "simple", p.get("price") or 0,
          p.get("regular") or 0, 1 if p.get("on_sale") else 0, p.get("price_min"), p.get("price_max"), p.get("short") or "",
          p.get("description") or "", j(p.get("images")), j(p.get("categories")), j(p.get("tags")), j(p.get("attributes")),
          j(p.get("variations")), 1 if p.get("in_stock", True) else 0, p.get("sku") or None, (i + 1) * 10)
         for i, p in enumerate(produtos)])


def _herdar_card_do_piloto(con):
    """#65: antes, a conta inteira ligava a um card. O card é de UM piloto (`pilot_name`):
    esse piloto herda o card — o que tem o mesmo nome, ou o único piloto da conta. Os outros
    pilotos ficam sem card até a equipe vincular ou criar. Só preenche o que está vazio;
    nunca troca um vínculo feito por uma pessoa."""
    from command_center.providers.vinculo_site import herdar_card
    for a in con.execute("SELECT id FROM portal_accounts WHERE client_id IS NOT NULL").fetchall():
        herdar_card(con, a[0])


def _migrar_papeis(con):
    """O papel CLOSER existiu por algumas horas em 17/09 e foi desfeito na mesma tarde
    ("vendas e operador devem ser a mesma coisa, com os acessos de operador"). Quem tiver
    ficado com ele vira OPERATOR — o CHECK antigo do banco aceita os dois, então não é
    preciso recriar a tabela."""
    con.execute("UPDATE users SET role='OPERATOR' WHERE role='CLOSER'")


def _semear_marcadores(con):
    """Manual dos marcadores do Gmail. O dono confirmou os 145 em 11/09 (marcador por
    marcador): a semente traz esse estado para quem ainda está `pendente`. Nunca
    desfaz o que ele mudar depois no painel — só promove pendente → confirmado."""
    from command_center.providers.taxonomia_gmail import MANUAL, MANUAL_SUPPORT, CONFIRMADO_POR
    livros = (("urace", MANUAL), ("support", MANUAL_SUPPORT))
    for caixa, nome, familia, o_que, threads, estado in (
            (c, *linha) for c, livro in livros for linha in livro):
        con.execute("""INSERT INTO gmail_labels (name, family, what, threads, status, mailboxes, confirmed_by, confirmed_at)
                       VALUES (?,?,?,?,?,?,
                               CASE WHEN ?='confirmado' THEN ? END,
                               CASE WHEN ?='confirmado' THEN strftime('%Y-%m-%dT%H:%M:%fZ','now') END)
                       ON CONFLICT(name) DO UPDATE SET
                         family=excluded.family,
                         mailboxes=COALESCE(gmail_labels.mailboxes, excluded.mailboxes),
                         what=CASE WHEN gmail_labels.status='pendente' THEN excluded.what ELSE gmail_labels.what END,
                         threads=COALESCE(gmail_labels.threads, excluded.threads),
                         status=CASE WHEN gmail_labels.status='pendente' THEN excluded.status ELSE gmail_labels.status END,
                         confirmed_by=CASE WHEN gmail_labels.status='pendente' AND excluded.status='confirmado'
                                           THEN ? ELSE gmail_labels.confirmed_by END,
                         confirmed_at=CASE WHEN gmail_labels.status='pendente' AND excluded.status='confirmado'
                                           THEN strftime('%Y-%m-%dT%H:%M:%fZ','now') ELSE gmail_labels.confirmed_at END""",
                    (nome, familia, o_que, threads, estado, json.dumps([caixa]),
                     estado, CONFIRMADO_POR, estado, CONFIRMADO_POR))


# Sementes que dependem de coluna criada por migração (rodam depois dela).
# Horários em hora local de Orlando; quem lê é command_center/api/agenda.py.
# --------------------------------------------------------- portão do APLICAR, revisado
# O dono respondeu as 42 ações uma a uma em 21/09 (página editável). Cada linha abaixo só
# troca a política SE ela ainda for a que estava valendo — o que ele mudar depois no painel
# fica. Isso é o que torna a revisão idempotente e não atropela decisão posterior.
#
# 22/09, segunda rodada: perguntei as seis que tinha segurado e ele respondeu uma a uma.
#   · apagar_cliente e qbo_apagar: MANTER em "nunca" — ele confirmou o que eu tinha
#     segurado. Cliente e contabilidade não se apagam, ponto.
#   · apagar_qualquer_coisa: ele ABRIU para aprovação. É a regra guarda-chuva — e abrir só
#     faz sentido se ela de fato guardar alguma coisa, o que até ontem não acontecia (ver
#     `piso_de_apagar` em api/ia.py).
#   · docusign_send_reminder e gmail_rotular: ele escolheu a REGRA, não só o portão. A
#     política abre, e a condição virou trava no servidor — é lá que ela protege.
#   · venda_tarefa: era toque errado mesmo. Continua fazendo sozinha.
REVISAO_21_09 = [
    # afrouxaram (decisão dele)
    ("docusign_enviar_waiver", "REQUIRES_APPROVAL", "SAFE"),
    ("docusign_reenviar_waiver", "REQUIRES_APPROVAL", "SAFE"),
    ("docusign_anular_envelope", "REQUIRES_APPROVAL", "REQUIRES_CONFIRMATION"),
    ("venda_enviar_waiver", "REQUIRES_CONFIRMATION", "SAFE"),
    ("venda_enviar_invoice", "REQUIRES_APPROVAL", "REQUIRES_CONFIRMATION"),
    ("qbo_criar_invoice", "REQUIRES_CONFIRMATION", "SAFE"),
    ("qbo_enviar_invoice", "REQUIRES_APPROVAL", "REQUIRES_CONFIRMATION"),
    ("gmail_enviar", "BLOCKED", "REQUIRES_APPROVAL"),
    # apertou (decisão dele)
    ("venda_mover_etapa", "SAFE", "REQUIRES_CONFIRMATION"),
    # 22/09, com a regra escrita no servidor junto (sem a trava, isto seria perigoso)
    ("apagar_qualquer_coisa", "BLOCKED", "REQUIRES_APPROVAL"),
    ("gmail_rotular", "REQUIRES_CONFIRMATION", "SAFE"),
    ("docusign_send_reminder", "BLOCKED", "SAFE"),
]

# ------------------------------------------------------------ os quatro karts do site (#263)
# Dono, 15/10: *"esses serviços já estão sendo mostrados no site… o mais lógico é ir com o produto
# que foi selecionado na mesma página que selecionou a data e daí clicar no add to cart"*.
#
# A página do Arrive and Drive mostra os quatro karts com preço (`vitrine.conteudo.KARTS`, os preços
# da Rate Card ditada pelo dono em 09/09), mas só dava para comprar quando a equipe tinha cadastrado
# à mão um serviço com o nome do kart. Agora os quatro nascem da migração, ligados ao kart pela
# chave (`site_kart`), e o painel continua dono do preço (#50).
#
# NADA É DESTRUÍDO: primeiro liga o que a equipe já criou para aquele kart, e só cria linha nova
# quando nenhuma linha é daquele kart. Preço, nome, descrição, depósito, item do QuickBooks e o
# estado (ativo/inativo) de linha que já existe não são tocados em nenhum dos dois caminhos.
#
# O depósito nasce 400 porque é o que o próprio site publica nos termos desta página
# ("a $400 deposit will be charged in advance", `vitrine.conteudo.TERMOS`); o gerente muda no painel
# (0 = sem depósito) e a subida seguinte não desfaz. O item do QuickBooks nasce vazio de propósito:
# o site cobra pelo Stripe (#262), e a invoice da equipe segue existindo à parte.
def _servicos_dos_karts():
    """Os SQL de cada kart do site, na ordem da página: ligar pelo nome do padrão, ligar o que a
    equipe criou para aquele kart, e só então criar a linha que falta."""
    from command_center.vitrine.conteudo import KARTS          # só dados, sem import de volta
    for i, k in enumerate(KARTS, start=1):
        chave = k["nome"].replace("'", "''")
        nome = f"Arrive and Drive {k['nome']}".replace("'", "''")
        ja_e_do_kart = (f"EXISTS (SELECT 1 FROM booking_services b "
                        f"WHERE LOWER(COALESCE(b.site_kart,''))=LOWER('{chave}'))")
        # 1 · já existe a linha com o nome do padrão (a equipe criou, ou é de uma subida antiga, de
        # antes da coluna): liga essa, sem mexer em mais nada. Uma linha só, sempre a mesma.
        yield f"""UPDATE booking_services SET site_kart='{chave}'
                   WHERE id = (SELECT id FROM booking_services
                                WHERE site_kart IS NULL AND LOWER(name)=LOWER('{nome}')
                                ORDER BY active DESC, id LIMIT 1)
                     AND NOT {ja_e_do_kart}"""
        # 2 · a equipe criou com outro nome, mas claramente para este kart (o nome do kart está no
        # nome) e é um só: liga esse. Dois candidatos é ambíguo — a migração não escolhe por ninguém.
        yield f"""UPDATE booking_services SET site_kart='{chave}'
                   WHERE site_kart IS NULL AND COALESCE(kind,'session')='session'
                     AND INSTR(LOWER(name), LOWER('{chave}')) > 0
                     AND NOT {ja_e_do_kart}
                     AND (SELECT COUNT(*) FROM booking_services c
                            WHERE c.site_kart IS NULL AND COALESCE(c.kind,'session')='session'
                              AND INSTR(LOWER(c.name), LOWER('{chave}')) > 0) = 1"""
        # 3 · nenhuma linha é deste kart: nasce a do site, com o preço da Rate Card
        yield f"""INSERT INTO booking_services
                    (name, price, deposit, kind, site_kart, sort, active, created_at)
                  SELECT '{nome}', {float(k["preco"])}, {float(k.get("deposito", 400))}, 'session', '{chave}', {i}, 1,
                         strftime('%Y-%m-%dT%H:%M:%fZ','now')
                   WHERE NOT {ja_e_do_kart}
                     AND NOT EXISTS (SELECT 1 FROM booking_services d WHERE LOWER(d.name)=LOWER('{nome}'))"""


def _cartoes_dos_karts():
    """#297: o texto que o cartão de cada kart já mostra no site entra no serviço do painel, para a equipe ver e
    mudar ali. Só preenche o campo VAZIO (NULL): o que alguém escreveu no painel nunca é sobrescrito."""
    from command_center.vitrine.conteudo import KARTS, LEAD_AND_FOLLOW as LF

    def q(t):
        return "NULL" if t is None else "'" + str(t).replace("'", "''") + "'"
    for k in KARTS:
        yield f"""UPDATE booking_services SET site_title=COALESCE(site_title, {q(k["nome"])}),
                         site_subtitle=COALESCE(site_subtitle, {q(k["idade"])}),
                         site_note=COALESCE(site_note, {q(k.get("aviso"))}),
                         own_kart=COALESCE(own_kart, {1 if k.get("proprio") else 0})
                   WHERE LOWER(COALESCE(site_kart,''))=LOWER({q(k["nome"])}) AND COALESCE(kind,'session')='session'"""
    yield f"""UPDATE booking_services SET description=COALESCE(description, {q(LF["texto"])})
               WHERE kind='addon' AND LOWER(COALESCE(site_kart,''))=LOWER({q(LF["chave"])})"""


def _cartoes_das_paginas():
    """#297, parte 2: os cartões de preço das páginas (planilha da Academy, opções do Pro Team, próximos passos do
    For Beginners) entram em `site_offers` **uma vez**, pela `seed_key` única (INSERT OR IGNORE): esconder ou
    mudar no painel nunca recria nem sobrescreve. O preço do kart e dos planos do painel vai como marca
    (`{kart}`, `{academy}`, `{boost}`) e vira valor ao vivo na página."""
    from urllib.parse import quote

    from command_center.vitrine import conteudo_paginas as P   # só dados, sem import de volta

    def q(v):
        return "NULL" if v is None else "'" + str(v).replace("'", "''") + "'"
    linhas = []
    for gi, (grupo, cards) in enumerate(P.ACADEMY["planos_grupos"]):
        for ci, (n, s, t, pr, por) in enumerate(cards):
            linhas.append((f"academy:{gi}:{ci}", "academy", grupo, n, s, t, pr, por,
                           f"/contact/?assunto=academy&produto={quote(grupo.split(' · ')[0] + ' — ' + n)}", "Choose",
                           gi * 100 + ci * 10))
    for i, (n, s, t, pr, por, h) in enumerate(P.PRO_TEAM["opcoes"]):
        linhas.append((f"pro-team:{i}", "pro-team", None, n, s, t, {"academy": "{academy}", "boost": "{boost}"}.get(pr, pr),
                       por, h, "Choose", i * 10))
    for i, (n, s, t, pr, h, b) in enumerate(P.BEGINNERS["proximo"]):
        linhas.append((f"for-beginners:{i}", "for-beginners", None, n, s, t, "{kart}" if pr == "kart" else (pr or None),
                       "Starting at" if pr == "kart" else None, h, b, i * 10))
    for chave, pagina, grp, t, s, b, pr, por, link, botao, ordem in linhas:
        yield (f"""INSERT OR IGNORE INTO site_offers (seed_key, page, grp, title, subtitle, body, price, per, link, button, sort, active, created_at)
                   VALUES ({q(chave)}, {q(pagina)}, {q(grp)}, {q(t)}, {q(s)}, {q(b)}, {q(pr)}, {q(por)}, {q(link)}, {q(botao)}, {ordem}, 1,
                           strftime('%Y-%m-%dT%H:%M:%fZ','now'))""")


# ------------------------------------------------------------ o Lead and Follow do site (#279)
# Dono, 15/10: "o lead and follow é um add on que pode ser adicionado no dia de treino seja arrive and drive ou
# no academy … somente o de 769 por dia de treino". Nasce como serviço do painel de tipo 'addon', ligado pela
# chave, com o mesmo cuidado dos karts: liga a linha de mesmo nome que a equipe já tenha; só cria se não houver
# nenhuma; e nunca mexe em preço, nome ou estado de linha que já existe.
def _servico_do_lead_and_follow():
    from command_center.vitrine.conteudo import LEAD_AND_FOLLOW as LF
    chave, nome = LF["chave"].replace("'", "''"), LF["nome"].replace("'", "''")
    ja = f"EXISTS (SELECT 1 FROM booking_services b WHERE LOWER(COALESCE(b.site_kart,''))=LOWER('{chave}'))"
    yield f"""UPDATE booking_services SET site_kart='{chave}'
               WHERE id = (SELECT id FROM booking_services WHERE site_kart IS NULL AND kind='addon'
                            AND LOWER(name)=LOWER('{nome}') ORDER BY active DESC, id LIMIT 1)
                 AND NOT {ja}"""
    yield f"""INSERT INTO booking_services (name, price, deposit, kind, site_kart, sort, active, created_at)
              SELECT '{nome}', {float(LF["preco"])}, 0, 'addon', '{chave}', 50, 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')
               WHERE NOT {ja}
                 AND NOT EXISTS (SELECT 1 FROM booking_services d WHERE LOWER(d.name)=LOWER('{nome}') AND d.kind='addon')"""


POS_MIGRACAO = [
    # 06/10 (#50): o contrato da Academy (§2.3) pede depósito de US$ 400 no Arrive and Drive. Só preenche
    # quem ainda não tem valor: o gerente pode mudar (0 = sem depósito) e a próxima subida não desfaz.
    """UPDATE booking_services SET deposit=400 WHERE deposit IS NULL
         AND LOWER(name) LIKE '%arrive%' AND LOWER(name) LIKE '%drive%'""",
    # 29/09 — dono: os locais são "galpão, trailer de corrida e pista (OKC)". O código
    # continua 'sede' (é ele que o razão guarda); só o nome que aparece muda — e só se
    # ainda for o que eu escrevi, para não desfazer um nome que alguém tenha trocado.
    "UPDATE stock_locations SET name='Galpão' WHERE code='sede' AND name='Sede'",
    # 16/09: o dono ditou a regra Docusign x Waivers depois de já ter confirmado os dois.
    # Troca o texto só se ainda for o que eu escrevi em 14/09 — o que ele editar fica.
    """UPDATE gmail_labels SET what='TODO e-mail do DocuSign, sem exceção (regra do dono, 16/09): enviado, visualizado, concluído, anulado, aviso da conta. Se for waiver enviada ou assinada, leva TAMBÉM o marcador ''Waivers''.'
       WHERE name='Softwares|Apps/Docusign' AND what LIKE 'DocuSign, TODO o tráfego de envelope%'""",
    """UPDATE gmail_labels SET what='WAIVER do DocuSign ENVIADA ao cliente ou RECEBIDA ASSINADA (regra do dono, 16/09). Vai SEMPRE junto com ''Softwares|Apps/Docusign'', nunca sozinho. Aviso de ''visualizou'' e ''anulada'' NÃO entra aqui. Ao marcar, a IA identifica de quem é, guarda o PDF no card do cliente e fecha a subtarefa da waiver nas tarefas dele.'
       WHERE name='Waivers' AND what LIKE 'WAIVER de responsabilidade no DocuSign: enviada, vista%'""",
    # o manual nasceu lendo só a urace@ (11/09). Quem não tem caixa é de lá.
    """UPDATE gmail_labels SET mailboxes='["urace"]' WHERE mailboxes IS NULL OR mailboxes=''""",
    """INSERT OR IGNORE INTO automation_rules (name, enabled, trigger, conditions, actions) VALUES
       ('gmail_triagem', 1, '{"schedule":true}', NULL,
        '{"ia":"ler cada e-mail da inbox, aplicar os marcadores e mover para o marcador principal"}')""",
    """INSERT OR IGNORE INTO automation_rules (name, enabled, trigger, conditions, actions) VALUES
       ('sondagem_integracoes', 1, '{"schedule":true}', NULL,
        '{"sistema":"sondar cada integração com uma chamada real; fora do horário, só se uma falhar"}')""",
    """UPDATE automation_rules SET schedule='["07:00","13:00","21:00"]' WHERE name='gmail_triagem' AND schedule IS NULL""",
    """UPDATE automation_rules SET schedule='["07:00","22:00"]' WHERE name='sondagem_integracoes' AND schedule IS NULL""",
    """INSERT OR IGNORE INTO automation_rules (name, enabled, trigger, conditions, actions) VALUES
       ('lembrete_invoice', 1, '{"schedule":true}', NULL,
        '{"sistema":"mandar o lembrete (reenvio da invoice pelo QuickBooks) de cada invoice em aberto com lembrete ligado e dia chegado"}')""",
    """UPDATE automation_rules SET schedule='["09:00"]' WHERE name='lembrete_invoice' AND schedule IS NULL""",
    """INSERT OR IGNORE INTO automation_rules (name, enabled, trigger, conditions, actions) VALUES
       ('varredura_clientes', 1, '{"schedule":true}', NULL,
        '{"sistema":"varrer o Gmail (as duas caixas) e o DocuSign de cada cliente ativo e ligar o que achar ao card"}')""",
    """UPDATE automation_rules SET schedule='["06:00"]' WHERE name='varredura_clientes' AND schedule IS NULL""",
    """INSERT OR IGNORE INTO automation_rules (name, enabled, trigger, conditions, actions) VALUES
       ('ratecard_semanal', 1, '{"schedule":true}', NULL,
        '{"sistema":"ler a URACE RATE CARD 2026 no Drive e aplicar os preços no QuickBooks, pelo mapa revisado"}')""",
    """UPDATE automation_rules SET schedule='["07:30"]' WHERE name='ratecard_semanal' AND schedule IS NULL""",
    # dono, 21/09: "preciso garantir que todas cheguem". Confere o chat contra o Kommo todo dia.
    """INSERT OR IGNORE INTO automation_rules (name, enabled, trigger, conditions, actions) VALUES
       ('conferir_chat', 1, '{"schedule":true}', NULL,
        '{"sistema":"conferir a conversa de cada lead no Kommo contra a do painel e avisar o que o painel nao recebeu"}')""",
    """UPDATE automation_rules SET schedule='["08:10"]' WHERE name='conferir_chat' AND schedule IS NULL""",
    """INSERT OR IGNORE INTO action_policies (action, policy, note) VALUES
       ('docusign_reenviar_waiver','REQUIRES_APPROVAL','reenvia/corrige e-mail do signatário: sai da empresa (dono, 17/09)'),
       ('docusign_anular_envelope','REQUIRES_APPROVAL','anula envelope em aberto; assinado nunca (dono, 17/09)'),
       ('docusign_renomear_modelo','REQUIRES_CONFIRMATION','só o nome do modelo (dono, 17/09)'),
       ('docusign_substituir_documento_modelo','REQUIRES_APPROVAL','troca o PDF do modelo com cópia do antigo (dono, 17/09)'),
       ('asana_criar_corrida','SAFE','corrida pelo modelo New Race, na coluna RACES (dono, 17/09)'),
       ('qbo_lembrete_invoice','SAFE','lembrete de invoice: o gerente escolhe quais, o disparo é da IA (dono, 17/09)'),
       ('venda_registrar_ligacao','SAFE','registro do closer na oportunidade, ditado ou digitado (dono, 17/09)'),
       ('venda_agendar_retorno','SAFE','retorno na agenda de vendas; nada sai para o cliente (dono, 17/09)'),
       ('venda_anotar','SAFE','anotação interna na oportunidade (dono, 17/09)'),
       ('venda_mover_etapa','SAFE','move a oportunidade no quadro de vendas (dono, 17/09)'),
       ('venda_tarefa','SAFE','tarefa/lembrete do fechamento: painel ou Asana (dono, 17/09)'),
       ('venda_enviar_waiver','REQUIRES_CONFIRMATION','waiver do serviço combinado, pelo modelo do DocuSign (dono, 17/09)'),
       ('venda_enviar_invoice','REQUIRES_APPROVAL','invoice fora da tabela de preços só com o dono (dono, 17/09)'),
       ('venda_fechar','REQUIRES_CONFIRMATION','fecha a venda e dispara cliente, QuickBooks, waiver, Asana e Kommo (dono, 17/09)'),
       ('painel_unir_clientes','SAFE','só com mesmo e-mail, telefone ou responsável; fora disso a ação recusa (dono, 17/09)'),
       ('painel_varrer_cliente','SAFE','Gmail + DocuSign do cliente: só leitura e espelho (dono, 17/09)'),
       ('painel_waiver_lixeira','REQUIRES_CONFIRMATION','tira do painel; em aberto anula no DocuSign (dono, 17/09)'),
       ('dialpad_ligar','REQUIRES_CONFIRMATION','discar pelo Dialpad: só a pedido de uma pessoa, nunca por conta da IA (dono, 18/09)'),
       ('qbo_atualizar_preco','SAFE','preço do catálogo vindo da Rate Card do Drive: o dono dispensou aprovação quando o valor é o dela (18/09); peça nunca muda')""",
    """INSERT OR IGNORE INTO automation_rules (name, enabled, trigger, conditions, actions) VALUES
       ('waiver_na_tarefa', 1, '{"event":"task.created","por":"sistema"}', NULL,
        '{"sistema":"anexar a waiver assinada do piloto na tarefa do Asana e guardar o PDF no card do cliente"}')""",
    # dono, 12/10 (#185): "vai dando rodada de aviso até o usuário completar essas informações faltantes"
    """INSERT OR IGNORE INTO automation_rules (name, enabled, trigger, conditions, actions) VALUES
       ('pendencias_aviso', 1, '{"schedule":true}', NULL,
        '{"sistema":"conferir as pendências da IA e avisar cada pessoa do que ela ainda precisa completar"}')""",
    """UPDATE automation_rules SET schedule='["09:00","16:00"]' WHERE name='pendencias_aviso' AND schedule IS NULL""",
    # #135 (dono, 14/10): o convite da waiver por e-mail. Pela pessoa no painel é o clique dela;
    # pela IA sai para o cliente, então espera o aprovar.
    """INSERT OR IGNORE INTO action_policies (action, policy, note) VALUES
       ('painel_waiver_convite','REQUIRES_APPROVAL','convite por e-mail para assinar a waiver nativa; sai para o cliente (#135, dono 14/10)')""",
    # Por último, de propósito: os UPDATE abaixo só encontram a linha depois dos
    # INSERT OR IGNORE acima. Tentei colocá-los no topo e, em banco novo, metade não
    # pegou — a linha ainda não existia.
    *[f"""UPDATE action_policies SET policy='{depois}',
             note=COALESCE(note,'') || ' · revisto pelo dono em 21/09 ({antes} -> {depois})'
           WHERE action='{acao}' AND policy='{antes}'"""
      for acao, antes, depois in REVISAO_21_09],
    # #263: os quatro karts do site, por último — depois de tudo o que mexe em booking_services
    *_servicos_dos_karts(),
    *_servico_do_lead_and_follow(),
    *_cartoes_dos_karts(),
    *_cartoes_das_paginas(),
    # #317: a caixa "Security deposit obrigatório" nasce marcada em toda sessão que já cobra depósito (os karts do
    # site, com US$ 400). Só toca quem ainda não decidiu (NULL): o que o gerente desmarcar continua desmarcado.
    """UPDATE booking_services SET deposit_required =
         CASE WHEN COALESCE(deposit, 0) > 0 AND COALESCE(kind, 'session') = 'session' THEN 1 ELSE 0 END
       WHERE deposit_required IS NULL""",
]


@contextmanager
def transacao(con, imediata=False):
    """BEGIN/COMMIT explícitos; rollback em exceção. `imediata` pega a trava de escrita já no começo
    (BEGIN IMMEDIATE): o que se lê dentro dela não muda até o COMMIT (ler, mudar e gravar, #310)."""
    con.execute("BEGIN IMMEDIATE" if imediata else "BEGIN")
    try:
        yield con
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


# ------------------------------------------------------------ helpers
def um(con, sql, params=()):
    r = con.execute(sql, params).fetchone()
    return dict(r) if r else None


def todos(con, sql, params=()):
    return [dict(r) for r in con.execute(sql, params).fetchall()]


def inserir(con, tabela, **campos):
    cols = ", ".join(campos)
    marks = ", ".join("?" for _ in campos)
    cur = con.execute(f"INSERT INTO {tabela} ({cols}) VALUES ({marks})",
                      tuple(campos.values()))
    return cur.lastrowid


def atualizar(con, tabela, id_, **campos):
    sets = ", ".join(f"{k} = ?" for k in campos)
    con.execute(f"UPDATE {tabela} SET {sets} WHERE id = ?",
                (*campos.values(), id_))


def auditar(con, event, actor, user_id=None, entity_type=None, entity_id=None,
            detail=None, ip=None):
    """Grava no audit_logs. `detail` vira JSON; nunca passe segredo aqui."""
    inserir(con, "audit_logs", event=event, actor=actor, user_id=user_id,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            detail=json.dumps(detail, ensure_ascii=False) if detail is not None else None,
            ip=ip)


# ------------------------------------------------------------ FastAPI
def get_db():
    con = conectar()
    try:
        yield con
    finally:
        con.close()
