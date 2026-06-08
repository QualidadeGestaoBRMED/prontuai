# Relatorio OWASP - ProntuAI

Data da analise: 2026-06-08

Escopo: auditoria estatica do repositorio local, configuracoes de deploy/CI, dependencias e testes locais. Nao foi executado pentest dinamico contra producao.

Referencias usadas:

- OWASP Top 10 2025: https://owasp.org/Top10/2025/
- OWASP API Security Top 10 2023: https://owasp.org/API-Security/editions/2023/en/0x11-t10/
- OWASP ASVS 5.0.0: https://owasp.org/www-project-application-security-verification-standard/

## Resumo executivo

O sistema ja possui controles importantes: autenticacao Google com validacao criptografica do `id_token`, JWT com `issuer`/`audience`, bloqueio de `DEV_AUTH_BYPASS` fora de ambiente nao produtivo, CORS configurado, headers de seguranca no Next, rate limit basico e algumas rotas com RBAC.

Mesmo assim, o estado atual nao deve ser considerado seguro para producao ate corrigir os pontos criticos abaixo. Os riscos mais relevantes sao: dados sensiveis/segredos versionados, falha de autorizacao em atualizacao de documentos, upload de arquivos sem limite real antes da leitura em memoria, dependencias frontend vulneraveis e CI insuficiente para evitar regressao de seguranca.

## Criticos

### 1. Segredos, logs, backups e documentos sensiveis versionados

Categoria OWASP: A02 Security Misconfiguration, A03 Software Supply Chain Failures, A04 Cryptographic Failures, A09 Security Logging and Alerting Failures; API8 Security Misconfiguration.

Evidencia:

- `back-end/cloudflared/83000be2-edf2-4446-a62e-93d2101d853b.json` esta versionado e contem credencial de tunnel.
- `back-end/cloudflared/config.yml` esta versionado.
- `back-end/logs/app.log` esta versionado e contem dados pessoais e rastros operacionais.
- `back-end/backups/reset_20260209_113140/*.json` esta versionado.
- `back-end/data/users.json` esta versionado.
- `back-end/auditoria_validacao/*.json` esta versionado.
- `pasta_teste/**/*.pdf` contem PDFs com nomes de pacientes em nomes de arquivo.
- `.gitignore` e `back-end/.gitignore` ignoram alguns caminhos, mas os arquivos ja estao no indice Git.

Impacto:

- A credencial do tunnel deve ser tratada como comprometida.
- Dados pessoais e medicos podem ter sido expostos para qualquer pessoa com acesso ao repositorio, clones, backups ou forks.
- Mesmo removendo arquivos em commit futuro, o historico Git continua contendo os dados.

Correcao:

- Rotacionar imediatamente a credencial do Cloudflare Tunnel e qualquer segredo relacionado.
- Remover esses arquivos do indice Git com `git rm --cached` e reforcar `.gitignore`.
- Se o repositorio ja foi compartilhado fora do ambiente controlado, executar resposta a incidente: limpeza de historico com `git filter-repo`/BFG, invalidacao de clones antigos quando possivel, revisao LGPD e notificacao conforme politica juridica.
- Substituir logs/auditoria por armazenamento seguro, minimizado, com retencao definida e sem CPF em nome de arquivo.

### 2. SENDER consegue atualizar campos de validacao de documentos da propria clinica

Categoria OWASP: A01 Broken Access Control, A06 Insecure Design; API1 Broken Object Level Authorization, API3 Broken Object Property Level Authorization, API5 Broken Function Level Authorization.

Evidencia:

- `back-end/app/api/v1/documents.py:540` define `PATCH /{document_id}` com `get_current_user`.
- `back-end/app/api/v1/documents.py:559` a `563` restringe `SENDER` apenas por `clinic_id`.
- `back-end/app/api/v1/documents.py:608` a `622` persiste `validation_status`, `result_payload`, OCR, exames e motivos.
- `back-end/app/api/v1/documents.py:590` a `644` usa `is_human_reviewer` para upload no Drive, mas nao bloqueia a mutacao dos campos de validacao por `SENDER`.

Impacto:

- Um usuario `SENDER` autenticado pode manipular o status ou payload de validacao de documentos da propria clinica, potencialmente burlando o fluxo de conferencia.
- A rota tem risco de autorizacao por propriedade: nem todo campo aceito por `DocumentUpdate` deve ser editavel por todos os papeis.

Correcao:

- Separar DTOs/endpoints por papel. Exemplo: `SENDER` somente cria/envia e talvez atualize metadados permitidos; `CHECKER`/`ADMIN` altera status, resultado de validacao, revisao e motivos.
- Adicionar teste negativo garantindo que `SENDER` nao consegue enviar `validation_status`, `result_payload`, `ocr_markdown`, `exams_*`, `reviewed_*`.
- Padronizar leitura/edicao: se `view_document` limita `SENDER` ao proprio documento, `update_document` tambem nao deve ser mais permissivo sem justificativa formal.

### 3. Dependencias frontend com vulnerabilidades conhecidas

Categoria OWASP: A03 Software Supply Chain Failures, A08 Software or Data Integrity Failures.

Evidencia:

- `front-end/package.json:34` usa `jspdf` `^4.0.0`.
- `front-end/package.json:36` usa `next` `15.5.7`.
- `npm audit --json` apontou 11 vulnerabilidades: 1 critica, 4 altas e 6 moderadas.
- O audit indicou correcao disponivel para `next` em `15.5.19` e correcoes para `jspdf`.

Impacto:

- Vulnerabilidades em Next podem afetar proxy/middleware/cache/SSRF/DoS dependendo da rota e configuracao.
- Vulnerabilidades em jsPDF podem permitir injecao em PDF/HTML e DoS em cenarios de geracao/visualizacao.

Correcao:

- Atualizar `next` para a versao corrigida indicada pelo audit.
- Atualizar `jspdf` para versao corrigida.
- Rodar `npm audit`, `npm run build` e testes de fluxo critico apos atualizacao.
- Tratar `next-auth`/`uuid` manualmente, porque o fix automatico sugerido pelo npm pode ser inadequado.

## Altos

### 4. Upload sem limite real de tamanho/tipo antes de ler em memoria

Categoria OWASP: A06 Insecure Design, A10 Mishandling of Exceptional Conditions; API4 Unrestricted Resource Consumption, API6 Unrestricted Access to Sensitive Business Flows.

Evidencia:

- `back-end/app/api/v1_brmed.py:138` le todo o arquivo em memoria na rota sincrona.
- `back-end/app/api/v1_brmed.py:390` le todo o arquivo em memoria na rota async.
- `back-end/app/api/v1_brmed.py:562` a `566` grava temporario com sufixo `.pdf` sem validacao forte de conteudo.
- `back-end/app/services/ocr_service.py:1246` a `1248` tambem le todo o `UploadFile` em memoria.
- `ops/deploy/nginx/api.prontuai.grupobrmed.com.br.conf:5` permite `100M`, mas a aplicacao nao tem limite equivalente antes de `read()`.

Impacto:

- DoS por memoria/CPU/disco e aumento de custo em OCR, OpenAI, Textract ou APIs externas.
- Risco de aceitar conteudo nao PDF com extensao falsa.

Correcao:

- Rejeitar por `Content-Length` antes da leitura.
- Implementar leitura em chunks com limite maximo.
- Validar MIME, extensao, assinatura `%PDF`, numero de paginas e tamanho final.
- Definir limites coerentes entre Nginx, FastAPI e OCR.

### 5. Refresh token sem revogacao, rotacao persistida ou deteccao de reutilizacao

Categoria OWASP: A07 Authentication Failures; API2 Broken Authentication.

Evidencia:

- `back-end/app/api/v1/auth.py:128` a `169` aceita refresh token JWT valido e emite novo par.
- `back-end/app/core/auth.py:105` a `110` gera refresh token de longa duracao com `scope=refresh`.
- O `jti` existe, mas nao ha armazenamento para revogar ou detectar reuse.

Impacto:

- Se um refresh token vazar, ele permanece utilizavel ate expirar.
- Nao ha logout global, revogacao por usuario, session version ou bloqueio por reutilizacao.

Correcao:

- Persistir refresh tokens por `jti`, usuario, data, device e status.
- Rotacionar refresh token a cada uso e invalidar o anterior.
- Detectar reutilizacao e revogar a familia de tokens.
- Invalidar sessoes quando usuario for desativado, tiver papel alterado ou segredo for rotacionado.

### 6. Auditoria e logs gravam PII/CPF em disco sem minimizacao

Categoria OWASP: A04 Cryptographic Failures, A09 Security Logging and Alerting Failures.

Evidencia:

- `back-end/app/services/validacao_service.py:349` a `360` grava CPF em arquivo JSON e no nome do arquivo.
- `back-end/logs/app.log` esta versionado e contem dados pessoais, nomes, emails, IPs e URLs de API externa com identificadores.

Impacto:

- Exposicao de dados pessoais e medicos.
- Retencao indefinida e dificil apagamento.
- Risco LGPD/compliance.

Correcao:

- Remover CPF de nomes de arquivo.
- Registrar somente identificadores tecnicos ou hashes com salt quando necessario.
- Redigir logs antes de persistir.
- Definir retencao, criptografia em repouso e controle de acesso para trilhas de auditoria.

### 7. Deploy/container com hardening incompleto

Categoria OWASP: A02 Security Misconfiguration.

Evidencia:

- `back-end/Dockerfile:2` usa imagem Python slim, mas nao define usuario nao-root.
- `back-end/Dockerfile:48` copia aplicacao com dono `root:root`.
- `back-end/docker-compose.yml:50` a `59` executa `cloudflared` como `user: "0:0"` e monta `./cloudflared`.
- `ops/deploy/nginx/api.prontuai.grupobrmed.com.br.conf:2` escuta HTTP 80; TLS pode estar externo, mas nao esta garantido nesse arquivo.

Impacto:

- Se houver RCE, o impacto dentro do container e maior.
- Credenciais montadas no container aumentam impacto de comprometimento.
- TLS/HSTS dependem de configuracao fora do artefato versionado.

Correcao:

- Criar usuario sem privilegio no Dockerfile e usar `USER`.
- Montar segredos via secret manager, nao via arquivo versionado.
- Documentar/enforcar TLS no ponto de entrada real e HSTS no dominio publico.
- Evitar `latest` para imagens externas sensiveis quando possivel.

### 8. Bypass de autenticacao no frontend por variavel publica e protecao parcial de rotas

Categoria OWASP: A01 Broken Access Control, A02 Security Misconfiguration; API5 Broken Function Level Authorization.

Evidencia:

- `front-end/middleware.ts:5` usa `NEXT_PUBLIC_DEV_AUTH_BYPASS`.
- `front-end/middleware.ts:20` a `21` protege apenas rotas listadas, nao inclui `/admin/*`.
- `front-end/components/require-role.tsx:47` a `54` renderiza children em bypass e durante `loading`.
- `front-end/app/api/proxy/[...path]/route.ts:71` a `79` tambem aceita bypass.

Impacto:

- Se a variavel publica for habilitada por erro em ambiente hospedado, a camada frontend/proxy deixa de exigir sessao.
- Conteudo de paginas pode aparecer antes de confirmacao de permissao. APIs backend continuam sendo a fonte de verdade, mas o frontend nao deve depender de guard client-side para paginas administrativas.

Correcao:

- Remover `NEXT_PUBLIC_DEV_AUTH_BYPASS` de builds que nao sejam locais e falhar build se estiver ativo em producao/staging.
- Proteger `/admin/:path*` no middleware.
- Nao renderizar children enquanto `status === "loading"` em paginas sensiveis.
- Manter checagem de permissao no backend para todas as APIs administrativas.

## Medios

### 9. Restricao de dominio Google nao e controle explicito

Categoria OWASP: A07 Authentication Failures; API2 Broken Authentication.

Evidencia:

- `back-end/app/api/v1/auth.py:61` a `86` valida `id_token`, email verificado e usuario existente, mas nao valida dominio.
- `front-end/app/api/auth/[...nextauth]/route.ts:40` a `59` envia email/id_token ao backend sem checagem de dominio.

Impacto:

- Hoje a barreira efetiva e o cadastro previo de usuario ativo. Isso e aceitavel se for decisao consciente, mas contradiz qualquer requisito de dominio corporativo obrigatório.

Correcao:

- Se o requisito for dominio corporativo, validar `hd`/dominio no backend e testar isso.
- Se usuarios externos forem permitidos, documentar explicitamente a regra.

### 10. Token curto de upload aceita token comum

Categoria OWASP: A07 Authentication Failures; API2 Broken Authentication.

Evidencia:

- `back-end/app/core/auth.py:309` a `316` declara que a dependencia valida token curto de upload.
- `back-end/app/core/auth.py:340` a `342` aceita `scope in (None, "upload")`.

Impacto:

- O isolamento de escopo do token de upload e enfraquecido: um access token comum tambem serve para upload direto.

Correcao:

- Exigir `scope == "upload"` nas rotas de upload direto.
- Adicionar teste garantindo rejeicao de access token comum.

### 11. Rate limit em memoria e por processo

Categoria OWASP: A06 Insecure Design; API4 Unrestricted Resource Consumption.

Evidencia:

- `back-end/main.py:96` a `118` guarda contadores em `_RATE_LIMIT_STATE`.
- `back-end/main.py:154` a `170` aplica middleware local.

Impacto:

- Limites resetam em restart e nao sao compartilhados entre workers/instancias.
- Ataques distribuidos ou multi-instancia podem contornar o limite.

Correcao:

- Migrar para Redis/Upstash/NGINX rate limit ou WAF.
- Criar limites especificos para login, upload, OCR, BRMED e comparacao OpenAI.

### 12. Admin padrao criado automaticamente quando banco esta vazio

Categoria OWASP: A02 Security Misconfiguration, A07 Authentication Failures.

Evidencia:

- `back-end/app/core/database_postgres.py:520` a `537` cria usuario admin fixo quando o banco esta vazio.

Impacto:

- Em ambientes novos/recuperados, uma identidade especifica recebe admin automaticamente.
- Como o login exige Google e usuario ativo, nao e senha padrao classica, mas ainda e um bootstrap perigoso.

Correcao:

- Remover criacao automatica em runtime.
- Criar comando/migracao de bootstrap com aprovacao explicita, email via variavel segura e auditoria.

### 13. Configuracao duplicada do Next

Categoria OWASP: A02 Security Misconfiguration.

Evidencia:

- `front-end/next.config.ts:20` a `52` define headers de seguranca.
- `front-end/next.config.mjs:1` a `14` define outro config sem headers.

Impacto:

- Configuracao duplicada aumenta risco de Next carregar o arquivo errado ou de alguem editar o arquivo errado no futuro.

Correcao:

- Manter apenas um arquivo de config.
- Confirmar em build qual config e carregado.

### 14. CSP usa `unsafe-inline`

Categoria OWASP: A02 Security Misconfiguration.

Evidencia:

- `front-end/next.config.ts:12` e `13` permitem `unsafe-inline`.

Impacto:

- CSP perde parte da capacidade de mitigar XSS.

Correcao:

- Migrar para nonce/hash quando viavel.
- Remover `unsafe-inline` pelo menos de `script-src` em producao.

### 15. Python dependencies sem lock reprodutivel

Categoria OWASP: A03 Software Supply Chain Failures.

Evidencia:

- `pip-audit` nao encontrou CVEs conhecidas em `back-end/requirements.txt`, mas o arquivo usa ranges em varias dependencias.

Impacto:

- O que foi auditado hoje pode nao ser o mesmo que sera instalado em deploy futuro.

Correcao:

- Gerar lock/constraints com hashes.
- Auditar o lock real usado em CI e deploy.

### 16. CI cobre pouco e nao bloqueia regressao de seguranca

Categoria OWASP: A03 Software Supply Chain Failures, A09 Security Logging and Alerting Failures.

Evidencia:

- `.github/workflows/backend-ghcr-deploy.yml:51` a `58` executa somente `test_brmed.py`.
- `.github/workflows/backend-ghcr-staging-deploy.yml:51` a `58` tem o mesmo padrao.
- Nao ha scan de segredos, `npm audit`, `pip-audit`, lint/build frontend ou testes de autorizacao no pipeline.

Impacto:

- Vulnerabilidades conhecidas e regressao de autorizacao podem chegar a staging/producao.

Correcao:

- Incluir testes de seguranca backend, build/lint frontend, `npm audit`, `pip-audit` e scan de segredos.
- Bloquear deploy quando critico/alto nao estiver aprovado.

### 17. FAQ com pickle esta desativado, mas e risco futuro

Categoria OWASP: A08 Software or Data Integrity Failures.

Evidencia:

- `back-end/app/services/faq_service.py:3` importa `pickle`.
- `back-end/app/services/faq_service.py:50` a `51` carrega `faq_data.pkl`.
- `back-end/app/api/__init__.py:10` a `11` mostra FAQ desativado por seguranca.

Impacto:

- Se reativado e o arquivo `.pkl` for substituido, `pickle.load` pode executar codigo arbitrario.

Correcao:

- Manter desativado ate migrar para JSON assinado/HMAC ou outro formato seguro.

## Matriz OWASP resumida

| OWASP | Achados principais |
| --- | --- |
| A01 Broken Access Control | `SENDER` consegue atualizar validacao; frontend com guard parcial; upload token com escopo frouxo |
| A02 Security Misconfiguration | Segredos/dados versionados; Docker root; TLS nao garantido no config; config Next duplicada |
| A03 Software Supply Chain Failures | `next`/`jspdf` vulneraveis; Python sem lock; CI sem audit |
| A04 Cryptographic Failures | Segredos versionados; dados sensiveis sem minimizacao/criptografia clara |
| A05 Injection | Sem evidencia forte de SQL injection no app principal; manter ORM/allowlist e revisar integrações IA |
| A06 Insecure Design | Fluxo de validacao permite mutacao indevida; upload/IA sem limites de negocio suficientes |
| A07 Authentication Failures | Refresh token sem revogacao; dominio Google nao explicito; token upload aceita access token comum |
| A08 Software or Data Integrity Failures | FAQ com pickle se reativado; dependencia vulneravel; build args de clone remoto no Dockerfile |
| A09 Security Logging and Alerting Failures | Logs com PII; auditoria com CPF; falta de scan/alerta em CI |
| A10 Mishandling of Exceptional Conditions | Upload e processamento podem falhar por consumo excessivo; excecoes amplas em leitura de arquivo |
| API1 BOLA | Acesso a documentos por ID precisa politica consistente por dono/clinica/papel |
| API2 Broken Authentication | Refresh token e upload token |
| API3 Object Property Authorization | Campos de `DocumentUpdate` editaveis por papel indevido |
| API4 Resource Consumption | Upload/OCR/OpenAI/BRMED sem limites distribuidos fortes |
| API5 Function Level Authorization | Rotas administrativas dependem corretamente do backend, mas frontend nao protege todo `/admin` |
| API6 Sensitive Business Flows | Upload e comparacao podem ser automatizados com custo operacional |
| API8 Security Misconfiguration | Deploy, logs, tunnel, CI |
| API9 Improper Inventory | Rotas/arquivos legados e configs duplicadas |
| API10 Unsafe Consumption of APIs | BRMED/OpenAI/Textract exigem validacao, timeout, retries e minimizacao de dados |

## Acoes imediatas 0-48h

1. Rotacionar credencial do Cloudflare Tunnel e remover arquivos sensiveis do indice Git.
2. Tratar logs, backups, PDFs e auditorias versionados como incidente de exposicao de dados.
3. Corrigir `PATCH /v1/documents/{document_id}` para bloquear mutacoes de validacao por `SENDER`.
4. Atualizar `next` e `jspdf`; rodar build e `npm audit`.
5. Implementar limite de upload antes de `await arquivo.read()`.
6. Adicionar CI com testes de autorizacao, `npm audit`, `pip-audit` e scan de segredos.

## Plano 7-30 dias

1. Implementar refresh token persistido com rotacao/revogacao.
2. Mover auditoria/logs para armazenamento seguro com redacao, retencao e criptografia.
3. Migrar rate limit para Redis/WAF e criar limites por rota cara.
4. Rodar containers como usuario nao-root e revisar secrets no deploy.
5. Consolidar `next.config` e endurecer CSP.
6. Criar lock reprodutivel para Python e auditar o lock.
7. Definir politica formal de acesso por papel e transformar em testes.
8. Adicionar gitleaks/trufflehog ou equivalente no pre-commit e no CI.

## Verificacoes executadas

- `PYTHONPATH=back-end .venv/bin/python -m pytest back-end/tests/test_auth_security.py -q --noconftest`: 6 testes passaram.
- `npm audit --json` em `front-end`: 11 vulnerabilidades reportadas, incluindo 1 critica e 4 altas.
- `pip-audit -r back-end/requirements.txt`: nenhuma vulnerabilidade conhecida reportada no conjunto resolvido durante a analise.
- Busca estatica por rotas, dependencias, logs, arquivos versionados, bypass, pickle, rate limit e configuracoes de deploy.

