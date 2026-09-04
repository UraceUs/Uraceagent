#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera o Pit Wall — o painel de monitoramento do Administrative AI.

Lê o estado real da máquina e escreve uma página HTML autossuficiente.

De onde vem cada número:
  rotinas      systemctl show (próxima execução, última, resultado)
  sincronia    o LOG da última execução — não refaz o trabalho, não
               chama a API do Asana. Painel observa, não trabalha.
  cérebro      brain_health.py, que é local e barato
  credenciais  só a PRESENÇA da variável no env; o valor nunca é lido,
               nunca é impresso, nunca entra no HTML
  problemas    as notas de brain/13_PROBLEMAS
  em progresso os relatórios que as rotinas gravam no workspace do
               agente (relatorios/<rotina>-AAAA-MM-DD.md). O painel não
               refaz o trabalho: mostra o que o agente escreveu, e diz
               quando aquilo foi escrito.

Uso:
    python3 adminai/painel/gerar_painel.py                 # escreve o padrão
    python3 adminai/painel/gerar_painel.py --saida /x.html # outro destino
"""
import html
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
URACE_DIR = os.environ.get("URACE_DIR", os.path.expanduser("~/.urace"))
LOGS = os.path.join(URACE_DIR, "logs")
ENV_FILE = os.path.join(URACE_DIR, "adminai.env")
SAIDA_PADRAO = os.path.join(URACE_DIR, "painel", "index.html")

ROTINAS = [
    ("urace-asana-sync", "Sincronia do Asana",
     "Status ↔ quadro no Shipping Orders", "asana-sync.log"),
    ("urace-triagem-email", "Triagem de e-mail",
     "Classifica a caixa e prepara rascunhos", "triagem-email.log"),
    ("urace-waivers", "Varredura de waivers",
     "Quem falta assinar, e quanto falta pro prazo", "waivers.log"),
    ("urace-brain-health", "Saúde do cérebro",
     "Mede a forma do grafo de conhecimento", "brain-health.log"),
]

CREDENCIAIS = [
    ("ASANA_TOKEN", "Asana", "Token próprio"),
    ("QBO_REFRESH_TOKEN", "QuickBooks", "Refresh token do app"),
    ("DOCUSIGN_INTEGRATION_KEY", "DocuSign", "Integration key e chave RSA"),
    ("GOOGLE_TOKEN_JSON", "Gmail e Drive", "OAuth e acesso ao support@"),
]


# ------------------------------------------------------------------ util
def sh(cmd):
    """Roda e devolve stdout. Nunca levanta — painel não pode cair."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True,
                           text=True, timeout=45)
        return r.stdout
    except Exception:
        return ""


def quando(us):
    """Microssegundos-desde-epoch do systemd → datetime local, ou None."""
    try:
        n = int(us)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return datetime.fromtimestamp(n / 1_000_000)


def humano(dt, agora):
    """'qua 06:40' + 'em 16h18' — ou '—' quando não há."""
    if not dt:
        return "—", ""
    dias = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
    rotulo = f"{dias[dt.weekday()]} {dt:%H:%M}"
    delta = dt - agora
    seg = abs(delta.total_seconds())
    if seg < 3600:
        rel = f"{int(seg // 60)} min"
    elif seg < 86400:
        rel = f"{int(seg // 3600)}h{int((seg % 3600) // 60):02d}"
    else:
        rel = f"{int(seg // 86400)} dias"
    return rotulo, (f"em {rel}" if delta.total_seconds() > 0 else f"há {rel}")


# -------------------------------------------------------------- coletas
def coleta_rotinas():
    agora = datetime.now()
    linhas = []
    for unit, nome, desc, log in ROTINAS:
        t = sh(f"systemctl show {unit}.timer -p NextElapseUSecRealtime "
               f"-p LastTriggerUSec -p LoadState 2>/dev/null")
        p = dict(l.split("=", 1) for l in t.strip().splitlines() if "=" in l)
        instalado = p.get("LoadState") == "loaded"

        s = sh(f"systemctl show {unit}.service -p Result -p ExecMainStatus "
               f"-p ExecMainExitTimestamp 2>/dev/null")
        ps = dict(l.split("=", 1) for l in s.strip().splitlines() if "=" in l)

        prox, prox_rel = humano(quando(p.get("NextElapseUSecRealtime")), agora)
        ult, ult_rel = humano(quando(p.get("LastTriggerUSec")), agora)

        resultado, classe = "Aguardando", "idle"
        if not instalado:
            resultado, classe = "Não instalada", "warn"
            prox, prox_rel = "—", "sem credencial"
        elif ps.get("Result") == "success" and ps.get("ExecMainStatus") == "0":
            resultado, classe = "OK", "ok"
        elif ps.get("Result") not in ("", "success", None):
            resultado, classe = "Falhou", "crit"
            ult_rel = ps.get("Result", "erro")

        linhas.append(dict(nome=nome, desc=desc, prox=prox, prox_rel=prox_rel,
                           ult=ult, ult_rel=ult_rel, resultado=resultado,
                           classe=classe, log=log))
    return linhas


def coleta_sync():
    """Lê o LOG da sincronia. Não chama a API."""
    caminho = os.path.join(LOGS, "asana-sync.log")
    vazio = dict(ok=0, fora=0, sem_status=0, div=None, modo="—", tem=False)
    if not os.path.exists(caminho):
        return vazio
    try:
        txt = open(caminho, encoding="utf-8", errors="replace").read()
    except OSError:
        return vazio
    # só o último bloco interessa
    blocos = txt.split("== sincronia status x seção")
    if len(blocos) < 2:
        return vazio
    b = blocos[-1]

    def num(padrao):
        m = re.search(padrao, b)
        return int(m.group(1)) if m else 0

    div = None
    if "nenhuma divergência" in b:
        div = 0
    else:
        m = re.search(r"--\s*(\d+)\s*divergência", b)
        if m:
            div = int(m.group(1))

    return dict(
        ok=num(r"--\s*(\d+)\s*tarefa\(s\) já consistentes"),
        fora=num(r"--\s*(\d+)\s*fora do fluxo"),
        sem_status=num(r"--\s*(\d+)\s*SEM status"),
        div=div,
        modo="aplicando" if "APLICANDO" in b else "simulação",
        tem=True,
    )


def coleta_cerebro():
    saida = sh(f"cd {REPO} && python3 adminai/brain_health.py 2>/dev/null")
    def num(p):
        m = re.search(p, saida)
        return m.group(1) if m else "—"
    return dict(
        notas=num(r"notas ativas \.+ (\d+)"),
        links=num(r"ligações \.+ (\d+)"),
        hubs=num(r"hubs \(>=\d+ entradas\) (\d+)"),
        integro="✅" in saida,
        orfas="0" if "ÓRFÃS" not in saida else
              (re.search(r"ÓRFÃS \((\d+)\)", saida) or ["", "?"])[1],
    )


def coleta_credenciais():
    """Só presença. O VALOR nunca é lido nem impresso."""
    presentes = set()
    if os.path.exists(ENV_FILE):
        try:
            for linha in open(ENV_FILE, encoding="utf-8", errors="replace"):
                linha = linha.strip()
                if linha.startswith("#") or "=" not in linha:
                    continue
                chave, valor = linha.split("=", 1)
                if valor.strip():
                    presentes.add(chave.strip())
        except OSError:
            pass
    aplicar = "APLICAR" in presentes and _valor_aplicar()
    return [dict(nome=n, desc=d, ok=(k in presentes))
            for k, n, d in CREDENCIAIS], aplicar


def _valor_aplicar():
    try:
        for linha in open(ENV_FILE, encoding="utf-8", errors="replace"):
            if linha.strip().startswith("APLICAR="):
                return linha.strip().split("=", 1)[1].strip() == "1"
    except OSError:
        pass
    return False


def coleta_problemas():
    pasta = os.path.join(REPO, "brain", "13_PROBLEMAS")
    abertos, destaques = [], []
    if not os.path.isdir(pasta):
        return abertos, destaques
    for arq in sorted(os.listdir(pasta)):
        if not arq.startswith("P-") or not arq.endswith(".md"):
            continue
        try:
            txt = open(os.path.join(pasta, arq), encoding="utf-8").read()
        except OSError:
            continue
        if re.search(r"^status:\s*superado", txt, re.M):
            continue
        pid = arq.split(" - ")[0]
        titulo = re.search(r"^# .*?— (.+)$", txt, re.M)
        titulo = titulo.group(1) if titulo else arq[:-3]
        corpo = re.search(r"## O problema\n(.+?)(?:\n\n|\n##)", txt, re.S)
        corpo = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1",
                       corpo.group(1).strip()) if corpo else ""
        corpo = re.sub(r"\*\*(.+?)\*\*", r"\1", corpo).replace("\n", " ")
        abertos.append(dict(id=pid, titulo=titulo, corpo=corpo[:150]))
    prioridade = ["P-04", "P-07", "P-05"]
    destaques = [p for k in prioridade for p in abertos if p["id"] == k]
    destaques += [p for p in abertos if p not in destaques][:max(0, 3 - len(destaques))]
    return abertos, destaques[:3]


def _agente():
    try:
        for linha in open(ENV_FILE, encoding="utf-8", errors="replace"):
            if linha.strip().startswith("OPENCLAW_AGENT="):
                return linha.strip().split("=", 1)[1].strip() or "urace-admin"
    except OSError:
        pass
    return "urace-admin"


def _md(txt):
    """Markdown mínimo → HTML. Escapa ANTES de transformar."""
    linhas, saida, tabela = txt.split("\n"), [], []

    def fecha_tabela():
        if not tabela:
            return
        cab, corpo = tabela[0], tabela[2:] if len(tabela) > 2 else []
        th = "".join(f"<th>{c}</th>" for c in cab)
        tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in l) + "</tr>"
                     for l in corpo)
        saida.append(f"<table class=rel-tab><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>")
        tabela.clear()

    lista = False
    for bruto in linhas:
        l = e(bruto.rstrip())
        # inline
        l = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", l)
        l = re.sub(r"`([^`]+)`", r"<code>\1</code>", l)
        l = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", l)
        nu = l.strip()
        if nu.startswith("|") and nu.endswith("|"):
            tabela.append([c.strip() for c in nu.strip("|").split("|")])
            continue
        fecha_tabela()
        if not nu:
            if lista:
                saida.append("</ul>"); lista = False
            continue
        if nu.startswith("#"):
            if lista:
                saida.append("</ul>"); lista = False
            saida.append(f"<h4>{nu.lstrip('#').strip()}</h4>")
        elif re.match(r"^([-*•]|\d+\.)\s", nu):
            if not lista:
                saida.append("<ul>"); lista = True
            item = re.sub(r"^([-*\u2022]|\d+\.)\s+", "", nu)
            saida.append(f"<li>{item}</li>")
        else:
            if lista:
                saida.append("</ul>"); lista = False
            saida.append(f"<p>{nu}</p>")
    if lista:
        saida.append("</ul>")
    fecha_tabela()
    return "\n".join(saida)


def coleta_relatorios(agora):
    """O último relatório de cada rotina, com a idade dele."""
    pasta = os.path.join(os.path.expanduser("~"), ".openclaw", "workspace",
                         _agente(), "relatorios")
    fontes = [("waivers", "Varredura de waivers"), ("triagem", "Triagem de e-mail")]
    saida = []
    for prefixo, titulo in fontes:
        arqs = []
        if os.path.isdir(pasta):
            arqs = sorted(a for a in os.listdir(pasta)
                          if a.startswith(prefixo + "-") and a.endswith(".md"))
        if not arqs:
            saida.append(dict(titulo=titulo, vazio=True, classe="warn",
                              idade="sem relatório ainda",
                              corpo="<p>Esta rotina ainda não gravou relatório. "
                                    "Ela grava um por execução, em "
                                    "<code>relatorios/</code>.</p>"))
            continue
        arq = arqs[-1]
        caminho = os.path.join(pasta, arq)
        try:
            txt = open(caminho, encoding="utf-8", errors="replace").read()
        except OSError:
            txt = ""
        dias = (agora.date() - datetime.fromtimestamp(os.path.getmtime(caminho)).date()).days
        if dias <= 0:
            idade, classe = "de hoje", "ok"
        elif dias == 1:
            idade, classe = "de ontem", "ok"
        else:
            idade, classe = f"de {dias} dias atrás", "warn"
        saida.append(dict(titulo=titulo, vazio=False, classe=classe,
                          arquivo=arq, idade=idade, corpo=_md(txt.strip())))
    return saida


def coleta_alertas(rotinas, creds, aplicar, sync, relatorios=None):
    a = []
    falhas = [r for r in rotinas if r["classe"] == "crit"]
    if falhas:
        a.append(("crit", "Erro",
                  f"{len(falhas)} rotina(s) falharam na última execução: "
                  + ", ".join(r["nome"] for r in falhas)
                  + ". O motivo está em <code>~/.urace/logs/</code>."))
    faltando = [c["nome"] for c in creds if not c["ok"]]
    if faltando:
        a.append(("warn", "Acesso",
                  "Sem credencial de " + ", ".join(faltando)
                  + ". As rotinas que dependem delas registram o erro e param aí — não quebram nada."))
    a.append(("info", "Modo",
              "<code>APLICAR=1</code> — a sincronia escreve no Asana de verdade."
              if aplicar else
              "<code>APLICAR=0</code> — simulação. A sincronia calcula o que faria e "
              "escreve no log, sem tocar nas tarefas."))
    velhos = [r["titulo"] for r in (relatorios or []) if r["classe"] == "warn"]
    if velhos:
        a.append(("warn", "Relatório",
                  "Sem relatório recente de " + ", ".join(velhos)
                  + ". O que está em progresso abaixo pode estar desatualizado."))
    if sync["tem"] and sync["sem_status"]:
        a.append(("warn", "Dados",
                  f"{sync['sem_status']} tarefa(s) sem status preenchido no "
                  "Shipping Orders. A sincronia não age nelas — precisa de humano."))
    return a


# --------------------------------------------------------------- render
def e(x):
    return html.escape(str(x), quote=False)


def render(rotinas, sync, cerebro, creds, aplicar, alertas, abertos, destaques,
           relatorios):
    agora = datetime.now()
    host = sh("hostname").strip() or "vps"
    tz = sh("timedatectl show -p Timezone --value").strip() or "—"

    ok_rot = sum(1 for r in rotinas if r["classe"] in ("ok", "idle"))
    if any(r["classe"] == "crit" for r in rotinas):
        vclasse, vtexto = "crit", "Com erro"
    elif ok_rot < len(rotinas):
        vclasse, vtexto = "warn", "Parcial"
    else:
        vclasse, vtexto = "ok", "No ar"

    linhas_rot = "\n".join(f"""        <tr>
          <td><span class="rot-nome">{e(r['nome'])}</span>
              <span class="rot-desc">{e(r['desc'])}</span></td>
          <td class="t"><b>{e(r['prox'])}</b><small>{e(r['prox_rel'])}</small></td>
          <td class="t"><b>{e(r['ult'])}</b><small>{e(r['ult_rel'])}</small></td>
          <td><span class="chip {r['classe']}">{e(r['resultado'])}</span></td>
        </tr>""" for r in rotinas)

    blocos_rel = "\n".join(f"""      <div class="card rel">
        <div class="rel-head">
          <h3>{e(r['titulo'])}</h3>
          <span class="chip {r['classe']}">{e(r['idade'])}</span>
        </div>
        <div class="rel-corpo">{r['corpo']}</div>
      </div>""" for r in relatorios)

    if sync["tem"]:
        total = sync["ok"] + sync["fora"] or 1
        div_txt = ("<b>divergências.</b> Campo de status e quadro contam a mesma "
                   "história em todas as tarefas do Shipping Orders."
                   if sync["div"] == 0 else
                   "<b>divergência(s).</b> Campo de status e quadro discordam — "
                   "a última alteração vence.")
        num = sync["div"] if sync["div"] is not None else "—"
        cor = "var(--ok)" if sync["div"] == 0 else "var(--warn)"
        bloco_sync = f"""
        <div class="sync-head">
          <div class="sync-num" style="color:{cor}">{e(num)}</div>
          <p>{div_txt}</p>
        </div>
        <div class="bar">
          <i style="background:var(--ok); flex:{sync['ok'] or 1}"></i>
          <i style="background:var(--muted); opacity:.45; flex:{sync['fora']}"></i>
        </div>
        <div class="legend">
          <span><i style="background:var(--ok)"></i> {sync['ok']} consistentes</span>
          <span><i style="background:var(--muted); opacity:.45"></i> {sync['fora']} fora do fluxo</span>
        </div>
        <div class="rows" style="margin-top:14px">
          <div class="row"><div class="lbl">Fora do fluxo<small>Seção é categoria, não estado — puladas de propósito</small></div><div class="t"><b>{sync['fora']}</b></div></div>
          <div class="row"><div class="lbl">Tarefas lidas<small>Projeto Shipping Orders · {e(sync['modo'])}</small></div><div class="t"><b>{total}</b></div></div>
        </div>"""
    else:
        bloco_sync = ('<p style="margin:0; color:var(--muted)">A sincronia ainda '
                      'não rodou. O painel mostra os números assim que houver '
                      'a primeira execução.</p>')

    linhas_cred = "\n".join(f"""          <div class="row">
            <div class="lbl">{e(c['nome'])}<small>{e(c['desc'])}</small></div>
            <span class="chip {'ok' if c['ok'] else 'warn'}">{'Ativo' if c['ok'] else 'Pendente'}</span>
          </div>""" for c in creds)

    linhas_alerta = "\n".join(f"""  <div class="alert {'info' if k == 'info' else ''}"
       style="border-left-color:var(--{'accent' if k == 'info' else k})">
    <div class="ico" style="color:var(--{'accent' if k == 'info' else k})">{e(rot)}</div>
    <div><p>{txt}</p></div>
  </div>""" for k, rot, txt in alertas)

    linhas_prob = "\n".join(f"""    <div class="prob">
      <div class="id">{e(p['id'])}</div>
      <h4>{e(p['titulo'])}</h4>
      <p>{e(p['corpo'])}</p>
    </div>""" for p in destaques)

    return TEMPLATE.format(
        css=CSS, blocos_rel=blocos_rel,
        vclasse=vclasse, vtexto=e(vtexto),
        n_rot=len(rotinas), n_skills=len(os.listdir(os.path.join(REPO, "skills"))) - 1,
        modo=("escrevendo nos sistemas" if aplicar else
              "<b>Modo simulação</b> — nada está sendo escrito nos sistemas"),
        stamp=f"{agora:%d/%m/%Y · %H:%M}", host=e(host), tz=e(tz),
        linhas_rot=linhas_rot, bloco_sync=bloco_sync, linhas_cred=linhas_cred,
        notas=e(cerebro["notas"]), links=e(cerebro["links"]),
        hubs=e(cerebro["hubs"]), orfas=e(cerebro["orfas"]),
        n_alertas=len(alertas), linhas_alerta=linhas_alerta,
        n_abertos=len(abertos), linhas_prob=linhas_prob,
    )


CSS = r"""
:root{--paper:#F6F3EF;--surface:#FFFFFF;--surface-2:#EFEBE5;--ink:#191714;--ink-2:#4A443C;--muted:#7A7168;--rule:#DED8D0;--rule-strong:#C7BFB5;--accent:#1F5F63;--accent-ink:#12494C;--ok:#2C7A54;--ok-wash:#E3F1E9;--warn:#9C6B12;--warn-wash:#F6ECD9;--crit:#A8352A;--crit-wash:#F7E4E1;--brand:#C4321F;--shadow:0 1px 2px rgba(25,23,20,.06),0 8px 24px -16px rgba(25,23,20,.30)}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#131211;--surface:#1C1A18;--surface-2:#242120;--ink:#EFEBE5;--ink-2:#C4BDB4;--muted:#948B81;--rule:#2E2A27;--rule-strong:#403A35;--accent:#5DAFB2;--accent-ink:#8ACBCD;--ok:#57B387;--ok-wash:#13271E;--warn:#D2A24A;--warn-wash:#2A2113;--crit:#E0705F;--crit-wash:#2E1815;--brand:#E8563E;--shadow:0 1px 2px rgba(0,0,0,.5),0 10px 28px -18px rgba(0,0,0,.9)}
[data-theme="dark"]{--paper:#131211;--surface:#1C1A18;--surface-2:#242120;--ink:#EFEBE5;--ink-2:#C4BDB4;--muted:#948B81;--rule:#2E2A27;--rule-strong:#403A35;--accent:#5DAFB2;--accent-ink:#8ACBCD;--ok:#57B387;--ok-wash:#13271E;--warn:#D2A24A;--warn-wash:#2A2113;--crit:#E0705F;--crit-wash:#2E1815;--brand:#E8563E;--shadow:0 1px 2px rgba(0,0,0,.5),0 10px 28px -18px rgba(0,0,0,.9)}
*{box-sizing:border-box}
body{background:var(--paper);color:var(--ink);font-family:"Barlow",system-ui,-apple-system,"Segoe UI",sans-serif;font-size:15px;line-height:1.5;margin:0;-webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto;padding:28px 20px 72px}
.top{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;flex-wrap:wrap;margin-bottom:18px}
.mark{display:flex;align-items:baseline;gap:10px}
.mark b{font-family:"Barlow Condensed",Impact,sans-serif;font-weight:700;font-size:30px;letter-spacing:.02em;color:var(--brand);text-transform:uppercase}
.mark span{font-family:"Barlow Condensed",sans-serif;font-weight:600;font-size:30px;text-transform:uppercase;letter-spacing:.04em;color:var(--ink)}
.stamp{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px;color:var(--muted);text-align:right;font-variant-numeric:tabular-nums}
.stamp em{display:block;font-style:normal;color:var(--ink-2);font-weight:500}
.verdict{display:flex;align-items:center;gap:16px;flex-wrap:wrap;background:var(--surface);border:1px solid var(--rule);border-left:4px solid var(--{vclasse});border-radius:3px;padding:14px 18px;box-shadow:var(--shadow);margin-bottom:26px}
.verdict .big{font-family:"Barlow Condensed",sans-serif;font-weight:700;font-size:23px;text-transform:uppercase;letter-spacing:.03em;color:var(--{vclasse})}
.verdict p{margin:0;color:var(--ink-2);font-size:14.5px;max-width:62ch}
.verdict .sep{width:1px;align-self:stretch;background:var(--rule)}
h2{font-family:"Barlow Condensed",sans-serif;font-weight:700;font-size:15px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted);margin:0 0 10px;display:flex;align-items:center;gap:10px}
h2::after{content:"";flex:1;height:1px;background:var(--rule)}
h2 .count{font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:0;color:var(--ink-2);background:var(--surface-2);padding:1px 7px;border-radius:2px}
.board{background:var(--surface);border:1px solid var(--rule);border-radius:3px;box-shadow:var(--shadow);overflow-x:auto;margin-bottom:30px}
table{border-collapse:collapse;width:100%;min-width:660px}
thead th{font-family:"Barlow Condensed",sans-serif;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);text-align:left;padding:11px 16px;border-bottom:1px solid var(--rule-strong);background:var(--surface-2);white-space:nowrap}
tbody td{padding:13px 16px;border-bottom:1px solid var(--rule);vertical-align:top}
tbody tr:last-child td{border-bottom:0}
.rot-nome{font-weight:600;color:var(--ink);display:block}
.rot-desc{color:var(--muted);font-size:13px}
.t{font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums;font-size:13.5px;white-space:nowrap}
.t b{font-weight:600;color:var(--ink)}
.t small{display:block;color:var(--muted);font-size:11.5px;letter-spacing:.02em}
.chip{display:inline-flex;align-items:center;gap:6px;white-space:nowrap;font-family:"Barlow Condensed",sans-serif;font-weight:700;font-size:12.5px;text-transform:uppercase;letter-spacing:.07em;padding:3px 9px;border-radius:2px;border:1px solid transparent}
.chip::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.chip.ok{color:var(--ok);background:var(--ok-wash)}
.chip.warn{color:var(--warn);background:var(--warn-wash)}
.chip.crit{color:var(--crit);background:var(--crit-wash)}
.chip.idle{color:var(--muted);background:var(--surface-2);border-color:var(--rule)}
.cols{display:grid;grid-template-columns:1.15fr 1fr;gap:26px;margin-bottom:30px}
@media(max-width:820px){.cols{grid-template-columns:1fr}}
.card{background:var(--surface);border:1px solid var(--rule);border-radius:3px;box-shadow:var(--shadow);padding:16px 18px}
.rel{margin-bottom:14px}
.rel-head{display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid var(--rule);padding-bottom:9px;margin-bottom:11px}
.rel-head h3{margin:0;font-size:15px;letter-spacing:.01em}
.rel-corpo{font-size:13.5px;line-height:1.62;max-height:340px;overflow-y:auto}
.rel-corpo h4{margin:15px 0 5px;font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.rel-corpo h4:first-child{margin-top:0}
.rel-corpo p{margin:0 0 7px}
.rel-corpo ul{margin:0 0 9px;padding-left:19px}
.rel-corpo li{margin-bottom:3px}
.rel-corpo code{font-family:"IBM Plex Mono",monospace;font-size:12px;background:var(--rule);padding:1px 4px;border-radius:2px}
.rel-tab{width:100%;border-collapse:collapse;margin:4px 0 10px;font-size:12.5px}
.rel-tab th,.rel-tab td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--rule);vertical-align:top}
.rel-tab th{color:var(--muted);font-weight:600;text-transform:uppercase;font-size:11px;letter-spacing:.05em}
.sync-num{font-family:"Barlow Condensed",sans-serif;font-weight:700;font-size:44px;line-height:1;font-variant-numeric:tabular-nums}
.sync-head{display:flex;align-items:baseline;gap:12px;margin-bottom:14px}
.sync-head p{margin:0;color:var(--ink-2);font-size:14px}
.bar{display:flex;height:9px;border-radius:2px;overflow:hidden;background:var(--surface-2);margin-bottom:10px}
.bar i{display:block}
.legend{display:flex;gap:18px;flex-wrap:wrap;font-size:13px;color:var(--ink-2)}
.legend span{display:flex;align-items:center;gap:7px}
.legend i{width:9px;height:9px;border-radius:2px;display:block}
.rows{display:flex;flex-direction:column}
.row{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:9px 0;border-bottom:1px solid var(--rule)}
.row:last-child{border-bottom:0}
.row .lbl{font-weight:500}
.row .lbl small{display:block;color:var(--muted);font-weight:400;font-size:12.5px}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--rule);border:1px solid var(--rule);border-radius:3px;overflow:hidden}
.metrics div{background:var(--surface);padding:12px 10px;text-align:center}
.metrics b{display:block;font-family:"IBM Plex Mono",monospace;font-weight:600;font-size:21px;color:var(--ink);font-variant-numeric:tabular-nums;line-height:1.2}
.metrics small{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
.alert{display:flex;gap:14px;padding:13px 16px;border:1px solid var(--rule);border-left:3px solid var(--warn);background:var(--surface);border-radius:3px;margin-bottom:10px;box-shadow:var(--shadow)}
.alert p{margin:0;color:var(--ink-2);font-size:14px;max-width:78ch}
.alert code{font-family:"IBM Plex Mono",monospace;font-size:12.5px;background:var(--surface-2);padding:1px 5px;border-radius:2px;color:var(--accent-ink)}
.alert .ico{font-family:"Barlow Condensed",sans-serif;font-weight:700;font-size:11px;text-transform:uppercase;letter-spacing:.08em;padding-top:2px;white-space:nowrap}
.probs{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
@media(max-width:820px){.probs{grid-template-columns:1fr}}
.prob{background:var(--surface);border:1px solid var(--rule);border-radius:3px;padding:14px 16px;box-shadow:var(--shadow);border-top:3px solid var(--crit)}
.prob .id{font-family:"IBM Plex Mono",monospace;font-size:11.5px;font-weight:600;color:var(--crit);letter-spacing:.04em}
.prob h4{margin:4px 0 5px;font-size:15px;font-weight:600}
.prob p{margin:0;font-size:13.5px;color:var(--ink-2)}
footer{margin-top:34px;padding-top:16px;border-top:1px solid var(--rule);color:var(--muted);font-size:13px;display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}
footer code{font-family:"IBM Plex Mono",monospace;font-size:12.5px}
"""

TEMPLATE = r"""<!doctype html>
<html lang="pt-BR"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pit Wall URACE</title>
<meta http-equiv="refresh" content="300">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=Barlow:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>{css}</style></head><body>
<div class="wrap">
  <div class="top">
    <div class="mark"><b>U·RACE</b><span>Pit Wall</span></div>
    <div class="stamp"><em>atualizado {stamp}</em>{host} · {tz}</div>
  </div>

  <div class="verdict">
    <div class="big">{vtexto}</div><div class="sep"></div>
    <p>{n_rot} rotinas agendadas, {n_skills} skills carregadas. {modo}.</p>
  </div>

  <h2>Rotinas <span class="count">{n_rot}</span></h2>
  <div class="board"><table>
    <thead><tr><th style="width:38%">Rotina</th><th>Próxima</th><th>Última</th><th>Resultado</th></tr></thead>
    <tbody>
{linhas_rot}
    </tbody>
  </table></div>

  <h2 style="margin-top:28px">Em progresso <span class="count">o que cada rotina relatou</span></h2>
{blocos_rel}

  <div class="cols">
    <div>
      <h2>Última sincronia do Asana</h2>
      <div class="card">{bloco_sync}</div>
    </div>
    <div>
      <h2>Acessos</h2>
      <div class="card"><div class="rows">
{linhas_cred}
      </div></div>
      <h2 style="margin-top:22px">Segundo cérebro</h2>
      <div class="metrics">
        <div><b>{notas}</b><small>notas</small></div>
        <div><b>{links}</b><small>ligações</small></div>
        <div><b>{hubs}</b><small>hubs</small></div>
        <div><b>{orfas}</b><small>órfãs</small></div>
      </div>
    </div>
  </div>

  <h2>Precisa de atenção <span class="count">{n_alertas}</span></h2>
{linhas_alerta}

  <h2 style="margin-top:28px">Problemas da operação <span class="count">{n_abertos} abertos</span></h2>
  <div class="probs">
{linhas_prob}
  </div>

  <footer>
    <span>Gerado por <code>adminai/painel/gerar_painel.py</code> · recarrega sozinho a cada 5 min</span>
    <span>Nenhuma credencial é lida ou exibida — só a presença dela</span>
  </footer>
</div></body></html>"""


def main():
    saida = SAIDA_PADRAO
    if "--saida" in sys.argv:
        saida = sys.argv[sys.argv.index("--saida") + 1]

    rotinas = coleta_rotinas()
    sync = coleta_sync()
    cerebro = coleta_cerebro()
    creds, aplicar = coleta_credenciais()
    abertos, destaques = coleta_problemas()
    relatorios = coleta_relatorios(datetime.now())
    alertas = coleta_alertas(rotinas, creds, aplicar, sync, relatorios)

    pagina = render(rotinas, sync, cerebro, creds, aplicar,
                    alertas, abertos, destaques, relatorios)

    os.makedirs(os.path.dirname(saida), exist_ok=True)
    with open(saida, "w", encoding="utf-8") as f:
        f.write(pagina)
    print(f"painel escrito em {saida} ({len(pagina)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
