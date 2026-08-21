# Ligando o circuito completo Kommo ⇄ ponte ⇄ Chase

> Guia de implantação (21/08). Três blocos: **A** — ponte como serviço 24/7;
> **B** — HTTPS público; **C** — Salesbot no Kommo. A e B são comandos no
> VPS; C é na interface do Kommo (Italo na tela, este guia do lado).

## Visão do circuito pronto

```
lead escreve no chat (Kommo)
  → Salesbot dispara (gatilho: mensagem recebida no funil do Chase)
  → passo widget_request POSTa pra https://bridge.urace.us/kommo/hook?key=...
  → ponte ACK <2s, processa em background:
      gatilhos de escalação (B4) → estado (G3) → Chase (OpenClaw)
      → diretivas [[...]] executadas (CRM/qualify/escalate/price)
  → ponte POSTa no return_url do Salesbot → bot mostra a resposta no chat
  → bot volta a esperar a próxima mensagem → repete
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

## Bloco C — Salesbot no Kommo (interface, Italo na tela)

> Pré-requisito: pegar a `AGENT_API_KEY` no VPS:
> `grep AGENT_API_KEY ~/.urace/bridge.env`
> A URL completa do bot será:
> `https://bridge.urace.us/kommo/hook?key=COLE_A_CHAVE_AQUI`

1. **Kommo → Automate (Digital Pipeline) no funil do Chase** (o pipeline
   novo, id `14316000`). No estágio **Incoming leads**, adicionar automação
   **"quando o cliente envia uma mensagem" → executar Salesbot → criar novo
   bot** (nome sugerido: `chase-bridge`).
2. No editor do bot, adicionar o passo **Widget request / solicitação a
   serviço externo** (no editor visual pode aparecer como "Make a request"
   ou dentro de "+ Mais" → integração; se só existir no editor de código,
   usar o bloco `widget_request`). Configurar:
   - **URL**: a URL completa com `?key=` acima.
   - Se houver campo de corpo/dados, incluir o id do lead e o texto da
     mensagem (placeholders do editor, ex. lead id e última mensagem). Se
     não houver, não tem problema: o payload padrão do widget_request já
     carrega o contexto do lead — a ponte lê os dois formatos.
3. Depois do passo de request, **o bot deve parar e aguardar** (a
   continuação vem da ponte via `return_url`). Não adicionar mensagem fixa
   depois do request.
4. **Salvar e ativar** o bot no gatilho de mensagem recebida do estágio
   Incoming leads (e nos demais estágios de conversa ativa do funil do
   Chase, se quiser cobertura nos estágios seguintes).

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
