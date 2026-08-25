# Ligando o circuito completo Kommo ⇄ ponte ⇄ Chase

> Guia de implantação (21/08). Três blocos: **A** — ponte como serviço 24/7;
> **B** — HTTPS público; **C** — Salesbot no Kommo. A e B são comandos no
> VPS; C é na interface do Kommo (Italo na tela, este guia do lado).

## Visão do circuito pronto

```
lead escreve no chat (Kommo)
  → Salesbot dispara (gatilho: mensagem recebida no funil do Chase)
  → bloco do widget "Chase" POSTa pra https://urace-bridge.duckdns.org/kommo/hook?key=...
  → ponte ACK <2s, processa em background:
      gatilhos de escalação (B4) → estado (G3) → Chase (OpenClaw)
      → diretivas [[...]] executadas (CRM/qualify/escalate/price)
  → ponte POSTa no return_url (Bearer KOMMO_TOKEN, handler show)
  → bot mostra a resposta no chat e TERMINA
  → próxima mensagem do lead dispara o bot de novo (padrão re-trigger)
```

## Bloco A — ponte como serviço systemd (VPS)

```bash
cd ~/Uraceagent && git pull
bash salesagent/deploy/install_bridge_service.sh
```

O instalador é idempotente: cria o venv, instala dependências, gera
`AGENT_API_KEY` em `~/.urace/bridge.env` se não existir, instala a unit e
sobe o serviço. No fim ele mesmo confere o `/health`.

Comandos úteis depois:

```bash
sudo systemctl status sales-bridge      # está no ar?
sudo journalctl -u sales-bridge -f      # logs ao vivo
```

**Depois de todo `git pull` que mudar a ponte**, roda o instalador de novo
(ele reinicia o serviço com o código novo).

## Bloco B — HTTPS público (VPS + DNS)

O Kommo só chama webhook em HTTPS válido. O caminho: subdomínio + Caddy
(certificado automático).

1. **DNS** ✅ (21/08): decidido usar **DuckDNS** em vez de mexer no DNS do
   urace.us (que vive no Google, não na Hostinger — migrar nameservers só
   pra isso seria risco desnecessário pro site/e-mail). Subdomínio criado:
   `urace-bridge.duckdns.org` → `34.230.114.116`. ⚠️ Se o IP do Lightsail
   não for estático (attached static IP), ele muda em stop/start — fixar o
   IP estático no console do Lightsail OU atualizar o IP no painel do
   DuckDNS quando mudar.
2. **Firewall do Lightsail** (console AWS → instância → Networking): abrir
   portas **80** e **443** TCP.
3. **Caddy** no VPS (instalação nos comentários de
   `salesagent/deploy/Caddyfile`), depois:

```bash
sudo cp ~/Uraceagent/salesagent/deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

4. Testar de fora (do seu notebook, não do VPS):

```bash
curl https://urace-bridge.duckdns.org/health
# esperado: {"ok":true,"ts":...}
```

O Caddyfile só expõe `/kommo/hook` e `/health` — as tools do agente e
`/human/reply` continuam acessíveis apenas de dentro do VPS.

## Bloco C — widget + Salesbot no Kommo (interface, Italo na tela)

> Confirmado nas docs oficiais (21/08): o passo `widget_request` **só
> existe dentro de um bloco de widget** — é preciso subir um widget custom
> na conta (plano Advanced ✅). O widget já está pronto no repo:
> `salesagent/kommo-widget/` (bloco "Chase — responder ao lead").
>
> Pré-requisito: pegar a `AGENT_API_KEY` no VPS:
> `grep AGENT_API_KEY ~/.urace/bridge.env`
> A URL completa usada no bloco será:
> `https://urace-bridge.duckdns.org/kommo/hook?key=COLE_A_CHAVE_AQUI`

### C1. Subir o widget (uma vez só)

1. Montar o zip (no VPS):
   `cd ~/Uraceagent/salesagent/kommo-widget && zip -r chase-bridge-widget.zip manifest.json script.js i18n images`
   (baixar o zip pro seu computador com scp/SFTP, ou montar o zip
   localmente clonando o repo).
2. Kommo → **Settings → Integrations → Create integration** (privada) →
   enviar o zip como widget da integração → instalar na conta.
3. Opcional (defesa extra): copiar o **client secret** da aba *Keys and
   scopes* e gravar `KOMMO_BOT_SECRET=...` em `~/.urace/kommo.env` no VPS,
   depois `sudo systemctl restart sales-bridge` — a ponte passa a validar a
   assinatura HS512 do token do Salesbot além do `?key=`.

### C2. Criar o bot

1. Kommo → **Settings → Communication tools → Salesbots → criar bot**
   (nome: `chase-bridge`).
2. No designer, adicionar o bloco do widget **"Chase — responder ao lead"**
   (aparece na lista de blocos, grupo de widgets). No campo URL, colar a
   URL completa com `?key=`.
3. **Nada depois do bloco.** O padrão é "re-trigger": o bot termina depois
   que a ponte responde; a PRÓXIMA mensagem do lead dispara o bot de novo.
   Sem loop interno, sem passo de espera.

### C3. Gatilho — bot roda a cada mensagem recebida

1. Kommo → **Leads → funil do Chase** (id `14316000`) → **Automate
   (Digital Pipeline)**.
2. No estágio **Incoming leads**: **+** → **Salesbot** → gatilho
   **mensagem recebida** (incoming message, todos os canais) → escolher o
   bot `chase-bridge`.
3. Repetir nos demais estágios de conversa ativa do funil (qualquer
   estágio onde o lead ainda conversa com o Chase) — o gatilho é por
   estágio.

### Teste ponta a ponta (primeira vez)

1. Criar um lead de teste no funil do Chase e mandar uma mensagem como
   cliente (ou usar um chat real de teste — WhatsApp/Instagram conectado ao
   Kommo).
2. No VPS, ver o que chegou:

```bash
python3 ~/Uraceagent/salesagent/tools/show_recent_audit.py --kind hook_raw
python3 ~/Uraceagent/salesagent/tools/show_recent_audit.py -n 30
```

3. Três resultados possíveis:
   - **Resposta apareceu no chat do lead** → circuito fechado. 🎉
   - **`hook_raw` chegou mas a resposta virou nota no lead** (kind
     `outbound_fallback` ou `salesbot_continue` com erro) → o formato de
     continuação precisa de ajuste fino; colar a saída do
     `show_recent_audit.py` no chat com o Claude que ele ajusta o parser —
     o payload bruto logado é exatamente o que falta pra calibrar.
   - **Nada chegou (`hook_raw` vazio)** → o bot não disparou ou a URL está
     errada; conferir bloco B (curl de fora) e o gatilho do bloco C.

> A ponte foi desenhada pra esse ajuste ser de UMA rodada: ela loga o
> payload bruto sempre, aceita múltiplos formatos de entrada, e o fallback
> de nota garante que nenhuma resposta se perde enquanto calibramos.

## ✅ Circuito fechado (24/08) + migração para widget v2

O teste ponta a ponta com lead real (Instagram) fechou o circuito às 21h05
UTC de 24/08. Dois achados calibrados ao vivo: o Kommo envia o webhook
como **form-encoded** (não JSON), e o continue valida **80 chars por
handler `show`** (400 TooLong) — a primeira entrega real saiu como
sequência de balões picados.

**Widget v2 + modo `json_reply`** resolvem a formatação: a resposta viaja
inteira em `data.reply` e o próprio bot a exibe via `{{json.reply}}` — uma
única mensagem com quebras de linha, sem limite de 80. Migração:

1. **Re-subir o widget**: Kommo → Settings → Integrations → Chase Bridge
   (URACE) → Edit → **Upload new archive** com o zip v2
   (`zip -r chase-bridge-widget.zip manifest.json script.js i18n images`).
2. **Regenerar o fluxo do bot**: abrir o Salesbot no editor, **remover o
   bloco "Chase — responder ao lead" e adicionar de novo** (garante que o
   fluxo é gerado pelo script novo), colar a URL com `?key=` de novo,
   salvar. (Só re-salvar sem recriar o bloco PODE usar script antigo em
   cache — recriar é o caminho garantido.)
3. **Trocar o modo na ponte**: no VPS,
   `echo 'SALESBOT_DISPLAY=json_reply' >> ~/.urace/bridge.env && sudo systemctl restart sales-bridge`
4. Testar de novo. Se `{{json.reply}}` não interpolar (aparecer literal no
   chat), rollback imediato: remover a linha `SALESBOT_DISPLAY` do
   bridge.env e reiniciar — volta ao modo balões, que funciona.

## O que continua pendente depois disso

- `FOLLOWUP_BOT_ID` no bridge.env (id do Salesbot — está na URL do editor
  do bot) para o follow-up agendado chegar no chat.
- Sync do snapshot do Rate Card com a planilha.
- Rotacionar o client secret da integração (passou pelo chat em 24/08),
  junto com a revisão geral de credenciais pré-lançamento.

## Dados confirmados da conta (25/08, varredura na UI)

| Item | Valor |
|---|---|
| Salesbot do Chase | `Salesbot #9`, **id 162247**, `BOT_TYPE_REGULAR` |
| Onde fica a lista | Communication → Bots (`/chats/tools/bots/`) |
| Fluxo do bot | `Start bot` → passo único "Chase — reply to lead" → widget custom. **Sem condição, sem filtro, sem bloco de entrada.** |
| Gatilhos | 13× "Any new conversation", um por etapa do funil, **cooldown de 5 min por lead** |
| Integração | "Chase Bridge (URACE)" instalada e ativa (privada, sem número de versão na UI) |

Nesta versão do Kommo o **editor do bot abre como modal e a URL não muda** —
não existe `/amo_bots/edit/{id}`. O id sai do DOM da lista
(`<div class="list-row" id="list_item_162247" data-id="162247">`).

### ⚠️ Risco aberto: cooldown de 5 min pode engolir mensagem de lead

Os gatilhos têm "5 mins launch cooldown". Se isso significar que uma
segunda mensagem do mesmo lead dentro de 5 minutos **não dispara o bot**,
a ponte nunca vê essa mensagem — e o lead fica sem resposta por um caminho
que nenhum código nosso alcança (a mensagem não chega até nós).

**Como verificar em 2 minutos**, com um lead de teste:

1. Mandar uma mensagem e esperar a resposta do Chase.
2. Mandar uma segunda mensagem **30 segundos depois**.
3. No VPS: `python3 salesagent/tools/show_recent_audit.py -n 10`

- **Dois `hook_raw`** → o cooldown não bloqueia mensagem dentro da mesma
  conversa. Nada a fazer.
- **Um `hook_raw` só** → confirmado: baixar o cooldown para o mínimo que a
  conta permitir, nos 13 gatilhos.

### Rota de disparo do bot por API — RESOLVIDA (25/08)

`run_bot()` chamava `POST /api/v4/bots/{id}/run` desde que foi escrito, sem
nunca ter sido exercitado (`FOLLOWUP_BOT_ID` sempre vazio, agendador sempre
no fallback de nota). Duas pistas sugeriam que estava errado — o
`return_url` do widget vive em `/api/v4/salesbot/{bot}/continue/{id}`, e o
JWT do widget_request traz `"entity_type":"2"` (numérico).

**As duas pistas apontavam para a rota errada.** O probe mediu contra a
conta:

| Rota | Corpo | Resultado |
|---|---|---|
| `POST /api/v4/bots/{id}/run` | `{"entity_type": "leads"}` | **202 ✅** |
| `POST /api/v4/bots/{id}/run` | `{"entity_type": 2}` | 400 `InvalidType` |
| `POST /api/v4/salesbot/run` | lista | 404 (rota inexistente) |
| `POST /api/v4/salesbot/run` | objeto | 404 |

`entity_type` é **string** nesta rota, apesar do JWT usar numérico noutro
contexto. O código original estava certo; a inferência a partir do
`return_url` não valia. Se a conta mudar, o probe responde de novo:

```bash
python3 salesagent/tools/probe_salesbot_run.py --bot 162247 --lead <LEAD_ID>
```

É seguro: sem `pending_followup_text` para o lead, a ponte não tem nada a
dizer e nenhuma mensagem chega ao cliente.
