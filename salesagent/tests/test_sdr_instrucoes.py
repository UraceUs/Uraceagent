#!/usr/bin/env python3
"""Robô SDR (12/10): as instruções do comercial, escritas na página /sdr do painel, entram no
bloco [SYSTEM] de cada turno do agente — e só quando o arquivo existe e tem conteúdo.

Sem rede: o agente é um stub que guarda o que recebeu.

Uso:
    python3 salesagent/tests/test_sdr_instrucoes.py
"""
import os
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
SALESAGENT = HERE.parent
_TMP = tempfile.mkdtemp(prefix="urace-sdr-instr-")
os.environ["URACE_DIR"] = _TMP
os.environ.setdefault("SDR_MODO", "atender")
sys.path.insert(0, str(SALESAGENT))
sys.path.insert(0, str(SALESAGENT / "bridge"))

FALHAS = []


def check(rotulo, cond, detalhe=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {rotulo}" + ("" if cond else f"  {detalhe}"))
    if not cond:
        FALHAS.append(rotulo)


def main():
    import app
    import state
    recebido = []
    app._call_agent = lambda lead_id, msg: (recebido.append(msg) or ("Olá! Qual a idade do piloto?", []))
    arquivo = Path(_TMP) / "sdr_instrucoes.md"
    TRECHO = "Instruções do comercial (valem acima da persona, exceto preço, que vem da tabela, e as travas de segurança):"

    print("\n1. Sem o arquivo: nada entra")
    app.BRAIN_RETRIEVAL = "off"
    app.run_agent(11, "oi, quanto custa?")
    check("o turno vai sem bloco de instruções", recebido and TRECHO not in recebido[-1], recebido[-1][:120] if recebido else "")
    check("a mensagem do lead chega inteira", recebido and recebido[-1].endswith("oi, quanto custa?"))

    print("\n2. Arquivo vazio: nada entra")
    arquivo.write_text("", encoding="utf-8")
    app.run_agent(11, "oi")
    check("arquivo vazio não vira bloco", TRECHO not in recebido[-1])

    print("\n3. Com instruções: entram no [SYSTEM], antes da mensagem do lead")
    arquivo.write_text("- [tom] Responda curto e em português.\n- [horário] Fora do horário, diga que a equipe responde no dia seguinte.\n",
                       encoding="utf-8")
    app.run_agent(11, "bom dia")
    m = recebido[-1]
    check("o trecho entra", TRECHO in m, m[:200])
    check("as duas linhas entram", "[tom] Responda curto" in m and "[horário] Fora do horário" in m)
    check("dentro de [SYSTEM] … [FIM DO SYSTEM]", m.index("[SYSTEM]") < m.index(TRECHO) < m.index("[FIM DO SYSTEM]"))
    check("a mensagem do lead vem depois", m.index("[FIM DO SYSTEM]") < m.index("Mensagem do lead: bom dia"))

    print("\n4. Com o Sales Brain ligado: entra antes de 'Memória do lead:'")
    falso_kb = types.ModuleType("brain_kb")
    falso_kb.search = lambda lead_id, q, top_docs=3: []
    falso_kb.format_for_context = lambda hits: ""
    sys.modules["brain_kb"] = falso_kb
    app.confidence.assess = lambda hits: {"level": "none", "reason": "teste"}
    app.confidence.system_note = lambda v: ""
    app._memory_context = lambda lead_id, conv: "primeiro contato"
    app.BRAIN_RETRIEVAL = "on"
    app.run_agent(11, "oi de novo")
    m = recebido[-1]
    check("o trecho entra no bloco do Brain", TRECHO in m, m[:200])
    check("antes de 'Memória do lead:'", m.index(TRECHO) < m.index("Memória do lead: primeiro contato"))
    check("é lido a cada turno: apagar o arquivo tira o bloco", (arquivo.unlink() or app.run_agent(11, "x") or True)
          and TRECHO not in recebido[-1])

    print("\n5. Falha na leitura: segue sem ele e registra")
    arquivo.mkdir()                                            # um diretório no lugar do arquivo: a leitura falha
    app.run_agent(11, "oi")
    check("o turno sai mesmo assim", recebido[-1].endswith("Mensagem do lead: oi") and TRECHO not in recebido[-1])
    with state.db() as conn:
        erro = conn.execute("SELECT detail FROM audit WHERE kind='error' AND detail LIKE 'sdr_instrucoes:%' ORDER BY id DESC LIMIT 1").fetchone()
    check("state.log('error', …, 'sdr_instrucoes: …')", bool(erro), "sem registro")

    print()
    if FALHAS:
        print(f"{len(FALHAS)} falha(s): " + "; ".join(FALHAS))
        sys.exit(1)
    print("tudo certo")


if __name__ == "__main__":
    main()
