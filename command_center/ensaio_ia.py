"""Ensaio do motor da IA no VPS (#185): `python -m command_center.ensaio_ia`.

Dono, 12/10: *"um bloco pra jogar na VPS pra testar o motor da IA, conferir que tá tudo
funcionando"* — e que, com informação faltando, ela *"coloca a tarefa com as informações que
tem"* e avisa o que falta, em vez de travar.

1. Ambiente: SDK, credencial da Anthropic, servidores (QuickBooks, Asana, Gmail, DocuSign,
   Kommo), cérebro e banco.
2. Uma resposta curta do modelo, sem ferramentas.
3. Pedidos incompletos, como a equipe escreve, em MODO ENSAIO: a IA lê os dados de verdade e
   NADA é gravado nem enviado. Para cada um, confere que ela criou mesmo com dado faltando,
   anotou a pendência, avisou na resposta e não inventou e-mail nem telefone.

Sai com código 1 se algo falhar. O relatório (tem nomes de clientes) fica em ~/.urace, nunca
no repositório.
"""
import json
import os
import re
import sys
from datetime import datetime

from command_center.api import agente_sdk
from command_center.db import conectar_somente_leitura, todos

RX_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
RX_FONE = re.compile(r"\+?\d[\d\s().-]{8,}\d")
LIMITE_CENARIO = float(os.environ.get("CC_ENSAIO_LIMITE_USD", "1.5"))


def _digitos(s):
    return re.sub(r"\D", "", s or "")


def inventados(tentou, fontes):
    """E-mails e telefones que aparecem no que a IA tentou gravar e em nenhum lugar que ela leu."""
    base = "\n".join(fontes).lower()
    base_dig = _digitos(base)
    fora = []
    for t in tentou:
        texto = json.dumps(t.get("args") or {}, ensure_ascii=False)
        for e in RX_EMAIL.findall(texto):
            if e.lower() not in base:
                fora.append(e)
        for f in RX_FONE.findall(texto):
            d = _digitos(f)
            if len(d) >= 10 and d[-10:] not in base_dig:
                fora.append(f.strip())
    return sorted(set(fora))


def avaliar(cenario, res, tentou, lido):
    """[(passou, frase)] de um cenário. Função pura: é o que os testes conferem."""
    out = [(bool(res.ok), "a IA respondeu" if res.ok else f"a IA falhou: {res.erro}")]
    criou = [t for t in tentou if not t["ferramenta"].startswith("pendencia")]
    out.append((bool(criou), "criou com o que tinha: " + ", ".join(sorted({t["ferramenta"] for t in criou}))
                if criou else "não criou nada (travou por falta de informação)"))
    pend = [t for t in tentou if t["ferramenta"] == "pendencia_registrar"]
    falta = []
    for t in pend:
        a = t.get("args") or {}
        falta += [str(x) for x in (a.get("faltando") or [])] + [str(x) for x in (a.get("campos") or [])]
    out.append((bool(falta), "anotou a pendência: falta " + ", ".join(falta) if falta
                else "não anotou o que falta (pendencia_registrar)"))
    texto = (res.texto or "").lower()
    out.append(("falta" in texto or "faltando" in texto, "avisou na resposta o que falta"
                if ("falta" in texto or "faltando" in texto) else "a resposta não diz o que falta"))
    fora = inventados(tentou, [cenario["pedido"], *lido])
    out.append((not fora, "nenhum e-mail ou telefone inventado" if not fora else "INVENTOU: " + ", ".join(fora)))
    for nao in cenario.get("nao_pode_faltar", []):
        achou = any(nao in f.lower() for f in falta)
        out.append((not achou, f"achou sozinho o {nao} que já estava no cadastro" if not achou
                    else f"pediu o {nao}, que já estava no cadastro"))
    return out


def cenarios(con):
    """Pedidos como a equipe escreve. O cliente real é só lido (para ver se a IA acha o que já existe)."""
    lista = [{"nome": "piloto desconhecido, sem contato nem horário",
              "pedido": "agenda uma aula de kart pro Rafael Quintanilha Borges semana que vem"}]
    c = todos(con, """SELECT id, name, pilot_name, email FROM clients
                       WHERE status='ACTIVE' AND email IS NOT NULL AND email<>'' ORDER BY updated_at DESC LIMIT 1""")
    if c:
        nome = c[0]["pilot_name"] or c[0]["name"]
        lista.append({"nome": "cliente do cadastro, sem data", "pedido": f"cria uma tarefa pro {nome}: troca de pneus do kart, ainda sem data",
                      "nao_pode_faltar": ["e-mail", "email"]})
        lista.append({"nome": "macacão sem medidas", "pedido": f"pedido de macacão pro {nome}, azul e branco"})
    return lista


def prompt_do_painel(pedido):
    """O mesmo prompt que o AI Command monta (pedido + contexto do painel), lido sem gravar."""
    from command_center.api import ia
    con = conectar_somente_leitura()
    try:
        return ia.montar_prompt(con, pedido, None)
    except Exception:                       # alguma parte do contexto quis gravar: vai o pedido puro
        return pedido
    finally:
        con.close()


def ambiente():
    linhas = []
    try:
        import claude_agent_sdk
        linhas.append((True, f"SDK do agente instalado ({getattr(claude_agent_sdk, '__version__', '?')})"))
    except ImportError:
        linhas.append((False, "SDK do agente NÃO instalado (pip install claude-agent-sdk no cc-venv)"))
    cred = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))
    linhas.append((cred, "credencial da Anthropic no ambiente" if cred else "falta ANTHROPIC_API_KEY no adminai.env"))
    serv = sorted(agente_sdk.servidores_mcp())
    faltam = sorted(set(agente_sdk.SERVIDORES) - set(serv))
    linhas.append((bool(serv), "sistemas ligados: " + ", ".join(serv) + (f" · sem credencial: {', '.join(faltam)}" if faltam else "")))
    cer = os.path.isfile(os.path.join(agente_sdk.CEREBRO, "URACE.md"))
    linhas.append((cer, "cérebro legível" if cer else f"cérebro não achado em {agente_sdk.CEREBRO}"))
    linhas.append((True, f"modelo {agente_sdk.MODELO} · e-mail {agente_sdk.MODELO_EMAIL}"))
    return linhas


def main(argv=None):
    so_ambiente = "--so-ambiente" in (argv or sys.argv[1:])
    relatorio = [f"# Ensaio do motor da IA · {datetime.now(agente_sdk.FUSO):%Y-%m-%d %H:%M} (Flórida)", ""]
    falhas = 0

    def mostra(ok, frase, recuo="  "):
        nonlocal falhas
        falhas += 0 if ok else 1
        linha = f"{recuo}{'✓' if ok else '✗'} {frase}"
        print(linha)
        relatorio.append(linha)

    print("── 1. ambiente")
    for ok, frase in ambiente():
        mostra(ok, frase)
    if falhas or so_ambiente:
        return _fim(relatorio, falhas)

    print("── 2. o modelo responde")
    r = agente_sdk.rodar("Responda só com a palavra OK.", None, ferramentas=False, max_turnos=2, limite=0.2)
    mostra(r.ok and "ok" in (r.texto or "").lower(), f"resposta: {(r.texto or r.erro or '')[:80]!r}"
           + (f" · US$ {r.custo:.3f}" if r.custo else ""))
    if falhas:
        return _fim(relatorio, falhas)

    print("── 3. pedidos incompletos (modo ensaio: lê de verdade, não grava nada)")
    con = conectar_somente_leitura()
    try:
        lista = cenarios(con)
    finally:
        con.close()
    custo = 0.0
    for c in lista:
        print(f"\n  ▸ {c['nome']}: “{c['pedido']}”")
        relatorio += ["", f"## {c['nome']}", f"Pedido: {c['pedido']}"]
        portao = agente_sdk.Portao(None, True, None, ensaio=True)
        res = agente_sdk.rodar(prompt_do_painel(c["pedido"]), None, portao=portao, limite=LIMITE_CENARIO, max_turnos=40)
        custo += res.custo or 0
        for ok, frase in avaliar(c, res, portao.tentou, portao.lido):
            mostra(ok, frase, "    ")
        resposta = (res.texto or res.erro or "").strip()
        print("    resposta: " + resposta[:500].replace("\n", "\n              "))
        relatorio += ["", "Tentou (não gravado):"] + [f"- {t['ferramenta']}: {json.dumps(t['args'], ensure_ascii=False)[:400]}"
                                                      for t in portao.tentou] + ["", "Resposta:", resposta]
    print(f"\n  custo do ensaio: US$ {custo:.2f}")
    relatorio.append(f"\nCusto: US$ {custo:.2f}")
    return _fim(relatorio, falhas)


def _fim(relatorio, falhas):
    pasta = os.environ.get("URACE_DIR", os.path.expanduser("~/.urace"))
    try:
        os.makedirs(pasta, exist_ok=True)
        caminho = os.path.join(pasta, f"ensaio-ia-{datetime.now():%Y%m%dT%H%M}.md")
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("\n".join(relatorio) + "\n")
        print(f"\nrelatório: {caminho}")
    except OSError:
        pass
    print("RESULTADO: " + ("tudo certo ✓" if not falhas else f"{falhas} problema(s) ✗"))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
