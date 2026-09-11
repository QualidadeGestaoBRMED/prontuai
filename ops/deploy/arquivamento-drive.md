# Arquivamento de documentos no Google Drive

Libera o disco da EC2 movendo para o Drive os documentos que já passaram da
janela de consulta **e** já foram checados por humano. Script:
`ops/deploy/archive_documents_to_drive.sh`.

## A regra

Um arquivo só sai do disco se as **duas** condições valerem:

1. tem mais de `ARCHIVE_AFTER_DAYS` dias (**20**, padrão);
2. o documento correspondente no banco já passou pela checagem humana.

Quem não passou pela checagem **fica no disco**, por mais velho que seja — a
tela de revisão lê o arquivo do disco, e arquivar por idade sozinha esvaziaria
a fila de checagem por baixo do revisor.

### O que conta como "checado por humano"

`documents.reviewed_by` preenchido. **Não** use `validation_status`:
`v1_brmed.py:215` marca `validated` sozinho quando a IA não encontra exame
faltante, antes de qualquer humano abrir o documento — e a fila de CHECAGEM do
produto (`api/v1/documents.py:199`) trata justamente esses como pendentes.
`reviewed_by` só é gravado para ADMIN, CHECKER ou MANAGER.

Dois portões, via `ARCHIVE_GATE`:

| `ARCHIVE_GATE` | Sai do disco | Fica no disco |
|---|---|---|
| `decidido` (padrão) | qualquer coisa com revisor humano (aprovado **ou** rejeitado) | pendente, `validated` só pela IA e `rejected` só pela IA |
| `aprovado` | `validated` **com** revisor humano | o mesmo, e também o **rejeitado por humano** |

O padrão é `decidido`: toda decisão humana libera o arquivo, seja aprovação ou
rejeição. As duas gravam o revisor — na aprovação o back preenche
`reviewed_by`; na rejeição o front envia o e-mail da sessão
(`front-end/app/checagem/page.tsx`). A rejeição **automática** da IA não tem
revisor e continua no disco, porque ainda está na fila de checagem. Se o
rejeitado por humano precisar continuar reabrível, use `ARCHIVE_GATE=aprovado`.

### Os três baldes do relatório

Todo run classifica os candidatos por idade em três listas, gravadas em
`$ARCHIVE_WORK_DIR`:

- `lista-enviar.txt` — liberados pelo portão. Sobem, são verificados, e só então apagados.
- `relatorio-retidos.txt` — têm linha em `documents`, mas sem checagem humana. **Ficam.**
- `relatorio-orfaos.txt` — **nenhuma** linha em `documents`. Ficam, por padrão.

Órfão é registro antigo com `file_path` NULL ou sobra de upload que morreu no
meio. Revise a lista antes de liberar; se forem descartáveis,
`ARCHIVE_ORPHAN_MODE=archive` os envia e apaga junto.

O casamento disco↔banco é por **basename**, não por caminho: `file_path` guarda
o caminho de dentro do container (`/app/data/uploads/x.pdf`, pelo volume
`./data/uploads:/app/data/uploads`), que nunca bate com o caminho do host.

Se dois registros de `documents` apontarem para o mesmo basename, o arquivo só
é liberado quando **todas** as linhas estiverem decididas (`bool_and` no
`GROUP BY`). Hoje isso não deveria ocorrer — os dois caminhos de upload passam
prefixo único (`uuid4()` em `v1_brmed.py:156`, `job_id` em `:617`) — mas a
helper ainda aceita `prefix=None` e registros antigos podem preceder o
prefixo. O delete é irreversível; a consulta conservadora não custa nada.

## 1. Configurar o rclone na VPS

A VPS é headless, então o OAuth interativo do `rclone config` não funciona lá
direto. Dois caminhos.

### Opção A — reusar a service account do backend (recomendado)

O backend já fala com o Drive por service account
(`GOOGLE_DRIVE_CREDENTIALS_FILE` / `GOOGLE_DRIVE_CREDENTIALS_JSON`). Não exige
navegador nenhum.

```bash
# na VPS, com o JSON da service account em /home/ec2-user/prontuai-db/gdrive-sa.json
mkdir -p ~/.config/rclone
cat >> ~/.config/rclone/rclone.conf <<'EOF'
[gdrive]
type = drive
scope = drive
service_account_file = /home/ec2-user/prontuai-db/gdrive-sa.json
team_drive =
root_folder_id =
EOF
chmod 600 ~/.config/rclone/rclone.conf
```

Preencha **um** dos dois:

- `team_drive` = ID do Shared Drive, se o arquivo vai para um drive compartilhado;
- `root_folder_id` = ID da pasta compartilhada com a service account.

Um dos dois é **obrigatório**: service account não tem Drive próprio nem cota.
Sem isso o upload falha com `storageQuotaExceeded`. O
`GOOGLE_DRIVE_SUPPORTS_ALL_DRIVES=true` do backend sugere que já existe um
Shared Drive em uso — reaproveite o mesmo, numa subpasta dedicada.

Confirme o acesso e o espaço antes de enviar 30 GB:

```bash
rclone lsd gdrive:
rclone about gdrive:            # cota; em Shared Drive costuma vir ilimitado
```

### Opção B — OAuth na sua conta

Exige autorizar no notebook e colar o token na VPS. Os GB contam na cota
pessoal da conta.

```bash
# 1) NO NOTEBOOK (tem navegador):
rclone authorize "drive"
#    → abre o navegador, e no fim imprime um JSON entre chaves. Copie-o.

# 2) NA VPS:
rclone config
#    n) novo remote  → nome: gdrive  → storage: drive
#    client_id/secret: em branco
#    scope: 1 (full access)
#    "Use auto config?" → N   ← essencial, senão tenta abrir navegador na VPS
#    cole o JSON do passo 1
```

### Armadilha comum

`rclone` lê `~/.config/rclone/rclone.conf` **do usuário que roda o comando**. Se
você configurar com `sudo`, o arquivo vai para `/root/` e o systemd unit
(que roda como `ec2-user`) não encontra o remote. Configure **sem** `sudo`, e
confirme com:

```bash
sudo -u ec2-user rclone listremotes
```

## 2. Instalar o script na VPS

```bash
# do repo, no notebook:
scp ops/deploy/archive_documents_to_drive.sh ops/deploy/lib.sh \
    ec2-user@$DEPLOY_HOST:/home/ec2-user/prontuai-db/script/
```

Acrescente ao `.env` do banco (`/home/ec2-user/prontuai-db/.env`), que o unit
já carrega via `EnvironmentFile`:

```
ARCHIVE_RCLONE_REMOTE=gdrive:prontuai/arquivo
```

O script precisa do `POSTGRES_USER`/`POSTGRES_DB` que já estão nesse `.env`:
ele consulta o banco para saber o que passou pela checagem humana, e **se
recusa a rodar** com o container `prontuai-db` fora do ar — sem o banco, apagar
por idade sozinha removeria documentos da fila de revisão.

## Testando em staging — atenção ao banco

Staging roda em **outra máquina** (Ubuntu, usuário `ubuntu`, pasta
`/home/ubuntu/prontuai-staging` — ver `DEPLOY_ENV=staging` em
`ops/deploy/deploy_vps.sh`), com o banco no container `prontuai-db-stg`. Os
padrões do script são de produção, então lá tudo precisa ser explícito:

```bash
ARCHIVE_DB_CONTAINER=prontuai-db-stg \
ARCHIVE_SOURCE_DIR=/home/ubuntu/prontuai-staging/data/uploads \
POSTGRES_USER=<usuario de staging> POSTGRES_DB=<banco de staging> \
ARCHIVE_RCLONE_REMOTE=gdrive:prontuai/arquivo-staging \
ARCHIVE_DRY_RUN=true ./archive_documents_to_drive.sh
```

`POSTGRES_USER`/`POSTGRES_DB` explícitos porque o script, na falta deles, lê o
`.env` de `/home/ec2-user/prontuai-db`, que não existe na máquina de staging. O
rclone também precisa estar configurado lá. Use um remote separado para o
teste não misturar arquivos no Drive de produção, e confira a linha `Banco:` no
início do log antes de rodar sem dry-run.

## 3. Primeiro run (o acervo acumulado)

**Não** dispare pelo systemd: são ~30 GB, e o `TimeoutStartSec` mata no meio.
Rode a mão, dentro de um `tmux`, para a sessão sobreviver a queda de SSH.

```bash
ssh ec2-user@$DEPLOY_HOST
tmux new -s arquivo

cd /home/ec2-user/prontuai-db/script

# 3.1 — SEMPRE primeiro: dry-run. Não envia e não apaga nada; só classifica
#       e imprime os três baldes com contagem e MB.
ARCHIVE_DRY_RUN=true ./archive_documents_to_drive.sh

# 3.2 — leia os relatórios antes de aplicar:
wc -l /home/ec2-user/prontuai/data/arquivo-tmp/relatorio-*.txt
head -20 /home/ec2-user/prontuai/data/arquivo-tmp/relatorio-orfaos.txt

# 3.3 — aplica. Lote a lote: copy → check → apaga só o que casou por checksum.
#       Pode interromper com Ctrl-C a qualquer momento: o que já foi verificado
#       já saiu do disco, e rodar de novo continua de onde parou.
./archive_documents_to_drive.sh
```

Confira o alívio: `df -h /` e `du -sh /home/ec2-user/prontuai/data/uploads`.

Se o dry-run mostrar **muito** em "retidos", o gargalo não é disco: é fila de
checagem parada. Nenhum script resolve isso — os documentos têm de ser
revisados. Se mostrar muito em "órfãos", revise a lista: pode ser sobra de
upload interrompido, que é lixo puro.

## 3.1 Ensaio graduado (`ARCHIVE_MAX_FILES`)

Numa base de dezenas de GB, a primeira execução real não deveria ser "tudo".
`ARCHIVE_MAX_FILES` põe teto na execução, e rodar de novo continua de onde
parou (o que já foi arquivado sai da lista porque o arquivo não está mais no
disco):

```bash
# arquiva 20, para, e deixa o resto para depois
ARCHIVE_MAX_FILES=20 ./archive_documents_to_drive.sh

# confirme o ciclo completo antes de soltar o resto:
#  - os 20 estão no Drive?            rclone ls $ARCHIVE_RCLONE_REMOTE | head -20
#  - saíram do disco?                 df -h /
#  - foram marcados no banco?         SELECT count(*) FROM documents WHERE archived_at IS NOT NULL;
#  - abrir um deles na tela mostra a mensagem de recuperação (não erro genérico)?

./archive_documents_to_drive.sh          # agora sem teto
```

Esse é o ensaio que vale: ele exercita copy → check → marcação → delete → 410
→ mensagem no front, de ponta a ponta, arriscando 20 arquivos em vez de
milhares.

## 4. Habilitar o timer semanal

Só depois do primeiro run manual ter concluído.

```bash
sudo cp ops/deploy/systemd/prontuai-archive-drive.service /etc/systemd/system/
sudo cp ops/deploy/systemd/prontuai-archive-drive.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now prontuai-archive-drive.timer

systemctl list-timers prontuai-archive-drive.timer
journalctl -u prontuai-archive-drive.service -n 50 --no-pager
```

Segunda 04:30, depois do backup das 03:15. Backup, purga e arquivamento
compartilham o `flock` de `db_maintenance_lock`: se o backup ainda estiver
rodando, o arquivamento **espera** até 30 min e depois **pula** — perder uma
execução semanal não tem consequência, perder um backup tem.

## O que o usuário vê depois do arquivamento

Documento arquivado **não abre mais no app** — não existe fallback para o
Drive, nem no back-end nem no front. O Drive é arquivo morto: recuperar é
manual.

Para isso não virar erro genérico, o job marca `documents.archived_at`
(migration 007) **antes** de remover o arquivo, e o endpoint de visualização
passa a responder **410 Gone** com um corpo estruturado:

```json
{"detail": {"code": "documento_arquivado", "message": "...",
            "archived_at": "2026-08-12T04:31:00", "filename": "exame.pdf",
            "contact": "o administrador do ProntuAI"}}
```

O front (`front-end/lib/document-archive.ts`) traduz isso numa mensagem
orientando a pedir a recuperação ao responsável, em `checagem`, `pendentes`,
`historico` e `anexar-prontuario`. Configure o contato exibido com
`DOCUMENT_ARCHIVE_CONTACT` no `.env` do **backend** (não no do banco).

A distinção importa: **410 é arquivado** (esperado, com caminho de
recuperação); **404 continua sendo defeito** (o arquivo deveria estar lá e não
está). Se o arquivamento respondesse 404 para os dois casos, perderíamos o
sinal de arquivo perdido por bug.

Por que marcar antes do `rm`: se a marcação vale e o `rm` falha, o arquivo
segue no disco e é servido normalmente — o endpoint resolve o arquivo primeiro
e só olha `archived_at` quando não acha nada. Na ordem inversa, um `rm` seguido
de falha na marcação deixaria o usuário com erro genérico. Se a marcação
falhar, o job **não apaga** aquele lote (a cópia no Drive já existe; o próximo
run re-verifica e tenta marcar de novo).

### Um bug que o arquivamento tornaria alcançável

O endpoint tinha um fallback que varria a pasta de uploads procurando qualquer
arquivo terminado em `_<nome_original>`. Enquanto nada era apagado ele nunca
era alcançado — o arquivo verdadeiro sempre existia e ganhava. Depois do
arquivamento, abrir um documento cujo nome original era `exame.pdf` acharia o
`<outro_job>_exame.pdf` de **outro paciente** e serviria aquele PDF; pior, o
`update` seguinte gravaria o caminho errado no `file_path`, tornando a troca
permanente. Nomes originais repetem muito neste domínio.

Agora esse fallback só roda quando `file_path` é nulo — o caso de registro
antigo para o qual ele foi escrito. Com `file_path` gravado e arquivo ausente,
a resposta é 410 ou 404, nunca o documento de outra pessoa.

## Segurança do delete

Ordem, por lote: `rclone copy` → `rclone check` → `rm`. Nada é apagado antes de
a cópia ser verificada por checksum no destino. São prontuários: um upload
truncado que passe despercebido é perda definitiva.

Duas defesas contra o arquivo mudar debaixo do script (upload truncado, ou
reescrita durante o run):

1. `rclone check --match` — só a lista do que casou por checksum é apagada. O
   que divergiu fica no disco, entra em `relatorio-nao-verificados.txt`, e o
   run **continua**. Um arquivo divergente não bloqueia a liberação dos outros
   30 GB, que é o que importa com o disco cheio.
2. Recheck de `mtime` imediatamente antes do `rm` — pega a sobrescrita que caia
   na janela entre o check e o delete.

O script sai com **código 1** se algo ficou para trás sem verificação, mas só
**depois** de ter liberado tudo o que era seguro liberar: a falha precisa
disparar o alerta sem custar o alívio de disco.

## Por que arquivo por arquivo, e não zip

A primeira versão zipava por semana/mês. Duas razões para não zipar:

1. **Disco cheio.** Zipar exige espaço livre igual ao tamanho do balde *antes*
   de liberar qualquer coisa — exatamente o que não existe quando o disco
   estourou, que é o momento em que o script mais precisa rodar.
2. **O portão de aprovação quebra o zip por período.** O zip era nomeado pelo
   período (`prontuai-documentos-2026-W32.zip`), com um guard que só arquivava
   o período quando *todos* os arquivos dele tinham saído da janela — para o
   nome não ser gerado duas vezes e o `rclone copy` sobrescrever o zip
   anterior. Com o portão, um único documento retido por falta de checagem
   mantém o período aberto para sempre; quando ele é finalmente aprovado, o zip
   é regerado com o **mesmo nome**. Ou nada nunca é arquivado, ou o zip
   anterior é sobrescrito em silêncio.

Arquivo por arquivo não tem nome colidindo nem período para fechar: cada
documento sobe assim que fica elegível, e a árvore no Drive espelha a local.

## Sobreposição com o `drive_service`

O backend já sobe cada documento ao Drive no momento da aprovação
(`app/services/drive_service.py`, chamado no PATCH de revisão). Este script
**não** assume que aquele upload aconteceu: o de lá é best-effort, roda em
`BackgroundTask` e apenas loga em caso de falha. Aqui a cópia é verificada por
checksum antes do delete — prova, não suposição.

Consequência: um documento aprovado pode chegar ao Drive duas vezes, por
caminhos diferentes. Se isso incomodar, aponte `ARCHIVE_RCLONE_REMOTE` para um
prefixo próprio (ex.: `gdrive:prontuai/arquivo`, separado da pasta de
`GOOGLE_DRIVE_FOLDER_ID`).

## Monitoramento

`track_job "arquivamento-drive"` reporta o resultado ao coletor OTel na saída.
O alerta correspondente já existe em
`otel/grafana/provisioning/alerting/alerts.yml`
(`prontuai-job-arquivamento-atrasado`): dispara se o job não conclui há mais de
10 dias. O alerta é sobre a **idade** do último sucesso, não sobre erro — é o
que pega timer que nunca disparou, script travado e máquina desligada.
