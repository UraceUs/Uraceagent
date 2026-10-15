"""O CI do GitHub já passou neste commit? (#277)

Dono, 15/10: *"a partir de agora você rode os testes ... no seu ambiente virtual, porque os testes
estão demorando de 15 a 20 minutos, isso querendo ou não acarreta tempo na nossa produção"*.

O deploy (`servir_command_center.sh`) pergunta à API pública do GitHub pelos check runs do commit que
vai subir e passa o JSON para cá. Responde `ok` só quando os TRÊS jobs do CI — Python, frontend e
end-to-end — terminaram e passaram. Qualquer outra coisa (algum vermelho, algum ainda rodando, algum
faltando, JSON quebrado, GitHub fora do ar) responde o motivo, e o deploy roda a bateria na VPS como
antes. Nunca sobe código sem prova: a dúvida sempre cai no lado de testar.

Uso:  curl … /commits/<sha>/check-runs | python ci_verde.py
"""
import json
import sys

# o começo do nome de cada job em .github/workflows/ci.yml
JOBS = ("Python", "Frontend", "End-to-end")


def veredito(dados):
    """('ok', '') quando os três jobs passaram; senão ('', motivo)."""
    runs = (dados or {}).get("check_runs") if isinstance(dados, dict) else None
    if not isinstance(runs, list):
        return "", "o GitHub não devolveu os checks deste commit"
    for job in JOBS:
        deste = [r for r in runs if str(r.get("name", "")).startswith(job)]
        if not deste:
            return "", f"o job {job} não rodou neste commit"
        # re-run cria outro check com o mesmo nome: vale o mais recente
        ultimo = max(deste, key=lambda r: str(r.get("started_at") or ""))
        if ultimo.get("status") != "completed":
            return "", f"o job {job} ainda está rodando"
        if ultimo.get("conclusion") != "success":
            return "", f"o job {job} terminou {ultimo.get('conclusion')}"
    return "ok", ""


def main():
    try:
        dados = json.load(sys.stdin)
    except ValueError:
        dados = None
    ok, motivo = veredito(dados)
    print(ok or motivo)


if __name__ == "__main__":
    main()
