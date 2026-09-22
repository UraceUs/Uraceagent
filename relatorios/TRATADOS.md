# Relatórios já tratados pelo Claude

A rotina horária lê `relatorios/vps-*.md` e age no que estiver em **Precisa do Claude**.
Esta lista é a memória dela entre sessões: relatório que está aqui não se retrabalha.

| Relatório | Tratado em | O que saiu dele |
|---|---|---|
| `vps-20260922T180854Z.md` | 22/09 19:0x | Os 3 achados já estavam consertados quando ele chegou (o push estava bloqueado pelo 403, então ele ficou preso na máquina enquanto o dono relatava por chat). Ver `3e7abdf` (CLI de sincronia + `%%20` + carimbo de saída nas unidades), `cd6392d` (venv + instalador de unidades). As decisões de "Precisa do dono" o dono já respondeu: sim para Savage, sim para Alex, sim para as cinco uniões — viraram `ccf2022` (carimbo `client_by='human'`). |
| `vps-20260922T192440Z.md` | 22/09 19:4x | `garantir_venv` não trocava de interpretador: o `bin/python` de um venv é **symlink** para o Python do sistema, e a guarda anti-laço comparava `realpath` — os dois lados davam o mesmo caminho. Corrigido para caminho absoluto + marca de ambiente; 5 testes, e um deles varre todas as ferramentas. O pid pendurado virou T-004. A recusa da T-001 estava certa: refiz o desenho da autorização. |

## Como a rotina usa isto

1. Lê os `vps-*.md` que **não** estão na tabela.
2. Age no que for dela; junta o que for do dono em `brain/04_PROJETOS/Command Center - Proximos passos.md`.
3. Acrescenta uma linha aqui, com o commit que saiu.
