# Push para github.com/UraceUs/Uraceagent

## O que já está feito

Este diretório é um clone real do repositório, com o commit **já criado** em
cima do "Initial commit" existente. Nada foi sobrescrito além do README, que
tinha duas linhas.

    e633b9b  AI Sales Agent: arquitetura, schema, prompts, catálogo, agente e testes
    44f7983  Initial commit

Remote, branch e autor já configurados. Falta apenas autenticar e empurrar.

## O comando

```bash
git push origin main
```

Se o git pedir credencial e não houver nenhuma salva, use o gh CLI:

```bash
gh auth login          # uma vez
git push origin main
```

## Antes de empurrar, confirme

```bash
git ls-files | grep -E '^\.env$' && echo "PARE: .env versionado" || echo "ok"
git log --oneline -3
```

O `.env` está no `.gitignore` e foi verificado como ausente. A checagem acima
existe porque publicar credencial é irreversível — o histórico do git guarda,
mesmo depois de remover o arquivo.

## Se este diretório for aninhado dentro de outro repositório

O git de fora pode tentar tratá-lo como submódulo. Nesse caso, mova-o para
fora antes:

```bash
mv Uraceagent ~/Uraceagent && cd ~/Uraceagent && git push origin main
```

## Depois do push

Os próximos passos estão no README, mas os dois que destravam o resto:

1. Aplicar `db/006_agent_functions.sql` no SQL Editor do Supabase, e
   descomentar o GRANT da última linha.
2. Definir `SUPABASE_URL` e `SUPABASE_SERVICE_KEY` nas variáveis do n8n.

Feito isso:

```bash
python tests/test_gates.py
```

Esse comando prova, contra o Postgres real, que o preço fica retido enquanto a
qualificação não fecha, que uma criança abaixo da idade da pista não consegue
ser agendada nem inserindo direto na tabela, e que uma conversa escalada não
volta a vender. Se algum falhar, é bloqueio — não ajuste.
