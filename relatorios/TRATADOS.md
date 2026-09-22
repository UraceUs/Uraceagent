# Relatórios já tratados pelo Claude

A rotina horária lê `relatorios/vps-*.md` e age no que estiver em **Precisa do Claude**.
Esta lista é a memória dela entre sessões: relatório que está aqui não se retrabalha.

| Relatório | Tratado em | O que saiu dele |
|---|---|---|
| `vps-20260922T180854Z.md` | 22/09 19:0x | Os 3 achados já estavam consertados quando ele chegou (o push estava bloqueado pelo 403, então ele ficou preso na máquina enquanto o dono relatava por chat). Ver `3e7abdf` (CLI de sincronia + `%%20` + carimbo de saída nas unidades), `cd6392d` (venv + instalador de unidades). As decisões de "Precisa do dono" o dono já respondeu: sim para Savage, sim para Alex, sim para as cinco uniões — viraram `ccf2022` (carimbo `client_by='human'`). |
| `vps-20260922T192440Z.md` | 22/09 19:4x | `garantir_venv` não trocava de interpretador: o `bin/python` de um venv é **symlink** para o Python do sistema, e a guarda anti-laço comparava `realpath` — os dois lados davam o mesmo caminho. Corrigido para caminho absoluto + marca de ambiente; 5 testes, e um deles varre todas as ferramentas. O pid pendurado virou T-004. A recusa da T-001 estava certa: refiz o desenho da autorização. |
| `vps-20260922T194036Z.md` (T-002) | 22/09 | Três defeitos nas ferramentas: carimbo sem filtro (ia carimbar 70 em vez de 20, incluindo uma corrida), união que só olhava o responsável (não achava o Luciano, que é piloto no card do pai), plano que parava no primeiro erro. Corrigidos em `cb07856`. |
| `vps-20260922T...` (T-003 + varredura) | 22/09 | A união do Martin seria desfeita pela varredura: uma tarefa truncada fazia o ramo `truncados` pular a checagem da união do dono. **Decisão do dono agora vem antes de qualquer heurística.** |
| `vps-20260922T194631Z.md` | 22/09 20:0x | Os 3 pedidos dela já estavam feitos em `cb07856` (filtro `--nome`, união pelo piloto, plano que não para). A T-005 que ela pediu também já estava na fila. |
| `vps-20260922T195050Z.md` | 22/09 20:0x | **O defeito do Martin**, corrigido em `5dee9d4`: a decisão do dono passou a vir antes de qualquer heurística. A pergunta dela — "o mesmo pode acontecer com Mikey/Sanghera/Luciano/Mauricio?" — está respondida: a checagem é por `drop_name` e vale para os cinco. Também tirei o `DeprecationWarning` do `utcnow()` que sujava o relatório de waivers. |

## Como a rotina usa isto

1. Lê os `vps-*.md` que **não** estão na tabela.
2. Age no que for dela; junta o que for do dono em `brain/04_PROJETOS/Command Center - Proximos passos.md`.
3. Acrescenta uma linha aqui, com o commit que saiu.
