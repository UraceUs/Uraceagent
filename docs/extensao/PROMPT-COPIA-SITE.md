# Prompt das extensões — copiar o site urace.us para a VPS

Dono, 07/10: *"de o prompt para a extensão copiar todo o site atual da urace, quero criar
uma copia na nossa vps"*.

**O que sai daqui:** uma cópia fiel do WordPress do urace.us (arquivos + banco) guardada na
VPS, em `/home/ubuntu/site-urace/`. **Não sai** um site no ar: subir a cópia é o passo
seguinte, com as travas do fim deste arquivo.

**Por que são três colagens.** A extensão do navegador entra no hPanel, mas não consegue
levar 4 GB até a VPS. Quem copia é a extensão da VPS, por SSH; a do navegador só abre a
porta e, no fim, fecha. Quem cola cada parte é o dono, e isso é a autorização de cada uma.

| Ordem | Onde colar | O que faz |
|---|---|---|
| 1 | extensão da **VPS** | cria uma chave SSH só para esta cópia e mostra a parte **pública** |
| 2 | extensão do **navegador** (hPanel aberto) | liga o SSH da hospedagem e cadastra essa chave pública |
| 3 | extensão da **VPS** | copia arquivos e banco, confere e faz o relatório |
| 4 | extensão do **navegador** | desliga o SSH e tira a chave (volta como estava) |

**O que a cópia carrega, e por isso nunca vai para o GitHub:** dados de clientes e
pedidos, senhas com hash, e as chaves do Stripe, do Kommo, do RD Station e do Meta que
estão no banco e no `wp-config.php`. A pasta fica só na VPS, com permissão 700.

**Como foi em 07/10.** A extensão do navegador **recusou** a Parte 2 (ligar SSH e cadastrar
chave é mudança de segurança): o dono fez à mão no hPanel. A cópia saiu completa: 34.429
arquivos dos dois lados (1,7 GB) e o banco com 112 tabelas (13 MB comprimido), pelo
mysqldump. O dono decidiu **manter o SSH ligado** com essa chave, para o Claude consultar o
site pela VPS; o uso é só de leitura, e qualquer mudança no site precisa do sim dele.

---

## Parte 1 — extensão da VPS: criar a chave

```
Tarefa do dono, 07/10: preparar a cópia do site urace.us. Nesta parte você só cria uma
chave SSH e me mostra a parte PÚBLICA. Não conecte em nada ainda.

1. Confira o espaço: rode `df -h /home/ubuntu`. Se houver MENOS de 10 GB livres, pare e
   me diga quanto há; não apague nada para abrir espaço.
2. Crie a chave só desta tarefa (se já existir, não sobrescreva; use a que existe):
     test -f ~/.ssh/hostinger_copia || ssh-keygen -t ed25519 -N "" -C "vps-copia-urace" -f ~/.ssh/hostinger_copia
     chmod 600 ~/.ssh/hostinger_copia
3. Mostre só a pública: `cat ~/.ssh/hostinger_copia.pub`
   NUNCA mostre, copie ou commite o arquivo sem ".pub".
4. Responda com: o espaço livre e a linha inteira da chave pública (começa com ssh-ed25519).
```

## Parte 2 — extensão do navegador: abrir o SSH da hospedagem

Cole junto a linha `ssh-ed25519 …` que a Parte 1 devolveu, no lugar indicado.

```
Tarefa do dono, 07/10: liberar acesso SSH da hospedagem urace.us para a VPS da URACE,
SÓ por chave. Esta é uma mudança no servidor e eu, dono, autorizo.

Chave pública da VPS (não é segredo):
<COLE AQUI A LINHA ssh-ed25519 ... DA PARTE 1>

Regras:
- Não troque nenhuma senha (nem da hospedagem, nem do FTP, nem do WordPress).
- Não crie conta FTP, não mexa em arquivos, banco, plugins, DNS ou backups.
- Se uma tela pedir confirmação de algo fora destes passos, cancele.

Passos:
1. hPanel › Sites › urace.us › Avançado › Acesso SSH.
2. Se o status estiver INACTIVE, ative o SSH.
3. Em "Chaves SSH", adicione uma chave com o nome "vps-copia-urace" e o conteúdo acima.
4. Na mesma tela, anote: IP, porta e usuário que o hPanel mostra para o SSH
   (o levantamento de 01/10 achou porta 65002 e usuário u762058566 — confira).
   NÃO anote senha nenhuma.

Entregue: IP, porta, usuário, se o SSH já estava ativo antes, e se a chave foi aceita.
Termine com: "Nenhuma senha foi trocada e nenhum arquivo foi alterado."
```

## Parte 3 — extensão da VPS: copiar

Troque `<IP>`, `<PORTA>` e `<USUARIO>` pelo que a Parte 2 devolveu.

```
Tarefa do dono, 07/10: copiar o site urace.us (arquivos + banco) para esta VPS. É só
LEITURA na Hostinger: você não escreve, não apaga e não muda nada lá. Eu, dono, autorizo
esta cópia.

Dados da conexão: host <IP>, porta <PORTA>, usuário <USUARIO>, chave ~/.ssh/hostinger_copia.

Regras:
- Na Hostinger, só comandos de leitura: ls, du, cat, wp … list, mysqldump, rsync
  (sentido Hostinger → VPS). Nunca rm, mv, wp plugin, wp option update, nada que escreva.
- Nunca imprima, copie para o relatório ou commite: senhas, conteúdo do wp-config.php,
  chaves de API, nem o dump. O relatório leva só tamanhos, contagens e versões.
- A cópia fica FORA do repositório, em /home/ubuntu/site-urace/. Nada dela vai para o git.
- Não suba a cópia: nada de nginx, php-fpm, banco local ou DNS nesta tarefa.

Passos:
1. Prepare a pasta e o atalho de conexão:
     mkdir -p /home/ubuntu/site-urace && chmod 700 /home/ubuntu/site-urace
     S="ssh -i ~/.ssh/hostinger_copia -p <PORTA> -o StrictHostKeyChecking=accept-new -o BatchMode=yes <USUARIO>@<IP>"
     $S 'echo conectado; pwd; ls'
2. Ache a pasta do site: normalmente ~/domains/urace.us/public_html. Confirme que ela
   tem wp-config.php e wp-content/. Se não achar, pare e reporte o que o `ls` mostrou.
   Guarde o caminho em R (ex.: R=domains/urace.us/public_html).
3. Meça antes de copiar (para o relatório):
     $S "du -sh $R; du -sh $R/wp-content/uploads $R/wp-content/ai1wm-backups $R/lp 2>/dev/null"
4. Banco (o ativo é o u762058566_db_urace_2026). Use o mysqldump da Hostinger: em 07/10
   o `wp db export` por SSH devolveu um arquivo vazio. A senha do banco é lida do
   wp-config.php e usada lá dentro; não aparece na tela nem chega à VPS:
     B=/home/ubuntu/site-urace/banco-$(date -u +%Y%m%dT%H%MZ).sql.gz
     ssh -i ~/.ssh/hostinger_copia -p <PORTA> -o BatchMode=yes <USUARIO>@<IP> bash -s <<'REMOTO' 2>/home/ubuntu/site-urace/banco-erros.txt | gzip > "$B"
     cd domains/urace.us/public_html || exit 1
     c(){ sed -n "s/^[[:space:]]*define([[:space:]]*['\"]$1['\"][[:space:]]*,[[:space:]]*['\"]\(.*\)['\"][[:space:]]*);.*/\1/p" wp-config.php | head -1; }
     DBN=$(c DB_NAME); DBU=$(c DB_USER); DBH=$(c DB_HOST); export MYSQL_PWD="$(c DB_PASSWORD)"
     [ "$DBN" = u762058566_db_urace_2026 ] || { echo "banco inesperado: $DBN" >&2; exit 1; }
     mysqldump -h "${DBH:-localhost}" -u "$DBU" --single-transaction --quick --default-character-set=utf8mb4 --no-tablespaces "$DBN"
     REMOTO
   Confira: `zcat "$B" | grep -c '^CREATE TABLE'` (em 07/10 eram 112), a última linha
   de `zcat "$B" | tail -n 1` é "-- Dump completed on …" e banco-erros.txt está vazio.
   Se der "banco inesperado", pare e reporte (não tente outro banco por conta).
5. Arquivos, sem os backups antigos (12 GB de .wpress que já são cópias), sem cache e sem
   o WordPress velho do lp (outro site, com plugins vulneráveis):
     rsync -a --info=stats2 -e "ssh -i ~/.ssh/hostinger_copia -p <PORTA> -o BatchMode=yes" \
       --exclude 'wp-content/ai1wm-backups/' --exclude 'wp-content/cache/' \
       --exclude 'wp-content/litespeed/' --exclude 'lp/' \
       <USUARIO>@<IP>:$R/ /home/ubuntu/site-urace/arquivos/
   Se cair no meio, rode o mesmo comando de novo: o rsync continua de onde parou.
6. Confira a cópia:
     ls /home/ubuntu/site-urace/arquivos/wp-config.php
     du -sh /home/ubuntu/site-urace/arquivos /home/ubuntu/site-urace/arquivos/wp-content/uploads
     find /home/ubuntu/site-urace/arquivos -type f | wc -l
     $S "find $R -type f -not -path '*/ai1wm-backups/*' -not -path '*/cache/*' -not -path '*/litespeed/*' -not -path '$R/lp/*' | wc -l"
   As duas contagens de arquivos têm de bater (diferença de poucos arquivos de cache é
   normal; diga quantos).
7. Anote as versões, sem segredo:
     $S "cd $R && wp core version && wp plugin list --status=active --fields=name,version --format=csv && wp theme list --status=active --fields=name,version --format=csv"
8. Feche a pasta: chmod -R go-rwx /home/ubuntu/site-urace

Relatório (relatorios/vps-<data>.md, como de costume): tamanho na Hostinger e na cópia,
tamanho do banco .gz, as duas contagens de arquivos, versões do WordPress, do tema e dos
plugins ativos, quanto tempo levou, e qualquer erro. Em "Precisa do dono" escreva:
"Desligar o SSH da hospedagem (Parte 4 do PROMPT-COPIA-SITE)".
Termine com: "Nada foi escrito, apagado ou alterado na Hostinger."
```

## Parte 4 — extensão do navegador: fechar a porta

```
Tarefa do dono, 07/10: a cópia do site terminou. Volte o SSH da hospedagem urace.us como
estava antes. Eu, dono, autorizo.

1. hPanel › Sites › urace.us › Avançado › Acesso SSH.
2. Em "Chaves SSH", remova SÓ a chave "vps-copia-urace". Não remova nenhuma outra.
3. Se o SSH estava INACTIVE antes da Parte 2, desative de novo. Se já estava ativo, deixe.

Entregue: a lista de chaves que sobrou (só os nomes) e o status final do SSH.
```

---

## Depois: subir a cópia (não é desta tarefa)

A cópia é de um WordPress **em produção**. Se ela subir do jeito que veio, ela age como o
site de verdade. Antes de qualquer `nginx` apontar para ela, o Claude prepara um passo com
estas travas:

- **Stripe:** a cópia tem as chaves *live*. Ou o gateway fica desligado, ou passa para as
  chaves de teste. Senão, um teste na cópia cobra cartão de verdade.
- **E-mail:** o WooCommerce e o Contact Form 7 mandam e-mail a clientes e à equipe. A cópia
  sobe com o envio desligado (um plugin de "não enviar" ou SMTP para lugar nenhum).
- **WP-Cron e integrações:** `DISABLE_WP_CRON`, e Kommo, RD Station e o catálogo do Meta
  desligados, para não duplicar lead, pedido ou produto.
- **Endereço e busca:** a cópia roda num endereço próprio (ex.: `copia.urace.us`), com
  `noindex` e login na frente, até a decisão de virar o site principal. O DNS de `urace.us`
  não muda nesta fase.
- **Licenças:** o Elementor Pro está com a licença cancelada e ligada à Colina Tech
  (levantamento de 01/10). A cópia funciona, mas não recebe atualização.
