# Prompt da extensão — fechar o acesso público aos backups do site (issue #47)

Cole isto na extensão do navegador, com o hPanel da Hostinger aberto. **Esta é uma mudança
no servidor**: quem cola o prompt é o dono, e isso é a autorização.

**O problema.** O levantamento de 01/10 achou o backup completo do urace.us (`.wpress`, 1,8
GB, com o banco inteiro: clientes, pedidos e senhas com hash). Ele pode ser baixado por
qualquer pessoa que saiba o nome do arquivo. O objetivo aqui é **bloquear o download sem
apagar nem mover nenhum backup**.

---

Regras:

- **Não apague, não mova e não renomeie nenhum arquivo.**
- **Não** restaure backup.
- **Não** mexa no plugin All-in-One WP Migration.
- **Não** copie o nome dos arquivos `.wpress` para o relatório. Escreva só "arquivo 1, 2…",
  com a data e o tamanho de cada um.
- Se uma tela pedir confirmação de algo que não está nesta lista, **cancele**.

## Passos

1. Abra hPanel › Sites › urace.us › **Gerenciador de arquivos**.
2. Vá até `public_html/wp-content/ai1wm-backups/`.
3. Anote quantos `.wpress` existem, com a data e o tamanho de cada um.
4. Veja se existe um arquivo chamado `.htaccess` nessa pasta. Ative "mostrar arquivos
   ocultos", se precisar.
   - **Se existir**: abra-o só para ler e copie o conteúdo para o relatório. **Não edite.**
     Pare aqui e entregue o relatório: o bloqueio precisa ser outro, e o Claude decide qual.
   - **Se não existir**: crie um arquivo novo `.htaccess` **nessa pasta** (não na raiz do
     site), com exatamente este conteúdo:

     ```
     # bloqueio de download dos backups (issue #47)
     <IfModule mod_authz_core.c>
       Require all denied
     </IfModule>
     <IfModule !mod_authz_core.c>
       Order allow,deny
       Deny from all
     </IfModule>
     ```

5. Teste o bloqueio:
   - numa aba anônima, abra `https://urace.us/wp-content/ai1wm-backups/` e anote o
     código ou a mensagem;
   - abra também o endereço de **um** dos `.wpress`, montado com o nome que você viu, sem
     colar o nome no relatório. **Não deixe o download continuar**: se começar, cancele.

   O esperado é 403 (Forbidden) nos dois.
6. Confirme que o site continua no ar: a home e uma página de produto abrem normalmente.

## Como entregar

- quantos backups existem, com data e tamanho;
- se o `.htaccess` já existia, e o conteúdo, se existia;
- o resultado dos testes do passo 5;
- se o site continua no ar.

Termine com a linha: **"Nenhum arquivo foi apagado, movido ou renomeado."**
