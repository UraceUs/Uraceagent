# Ligando o circuito completo Kommo ⇄ ponte ⇄ Chase

> Guia de implantação (21/08). Três blocos: **A** — ponte como serviço 24/7;
> **B** — HTTPS público; **C** — Salesbot no Kommo. A e B são comandos no
> VPS; C é na interface do Kommo (Italo na tela, este guia do lado).

## Visão do circuito pronto

```
lead escreve no chat (Kommo)
  → Salesbot dispara (gatilho: mensagem recebida no funil do Chase)
  → bloco do widget "Chase" POSTa pra https://bridge.urace.us/kommo/hook?key=...
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

1. **DNS** (no gerenciador do domínio urace.us): registro **A**,
   `bridge.urace.us` → IP estático do Lightsail.
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
curl https://bridge.urace.us/health
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
> `https://bridge.urace.us/kommo/hook?key=COLE_A_CHAVE_AQUI`

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

## O que continua pendente depois disso

- Agendador de follow-up real (hoje `[[followup]]` vira task no Kommo).
- Alarme de escalação C2 (re-alerta 10–30min, 9h–18h Orlando).
- Sync do snapshot do Rate Card com a planilha.
