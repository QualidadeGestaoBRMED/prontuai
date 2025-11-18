# API de Jobs Assíncronos

## Visão Geral

Para evitar timeouts de workers durante processamento de documentos grandes (especialmente OCR com AWS Textract), implementamos um sistema de jobs assíncronos que permite:

1. **Retornar imediatamente** ao cliente com um `job_id`
2. **Processar em background** sem bloquear o worker
3. **Consultar progresso** em tempo real via polling
4. **Obter resultado** quando processamento completar

## Arquitetura

```
Cliente                    API                     JobManager              Worker Background
   |                        |                           |                          |
   |-- POST /processar ---->|                           |                          |
   |                        |-- create_job() ---------> |                          |
   |                        |                           |                          |
   |<-- 200 {job_id} -------|                           |                          |
   |                        |-- background_task() -----------------> inicia ------->|
   |                        |                           |                          |
   |                        |                           |                          |
   |                        |                           |<-- update_progress() ----|
   |-- GET /jobs/{id} ----->|                           |                          |
   |<-- 200 {progress} -----|-- get_job_status() ------>|                          |
   |                        |                           |                          |
   |   (polling)            |                           |                          |
   |                        |                           |<-- complete_job() -------|
   |-- GET /jobs/{id} ----->|                           |                          |
   |<-- 200 {result} -------|-- get_job_status() ------>|                          |
```

## Endpoints

### 1. Iniciar Processamento Assíncrono

**POST** `/v1/processar-documento-async`

Inicia o processamento em background e retorna `job_id` imediatamente.

**Request:**
```bash
curl -X POST "https://api.prontuai.grupobrmed.com.br/v1/processar-documento-async" \
  -F "arquivo=@documento.pdf" \
  -F 'exames_obrigatorios=["HEMOGRAMA", "GLICEMIA"]'
```

**Response (200):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Documento documento.pdf recebido. Processamento iniciado em background.",
  "poll_url": "/v1/jobs/550e8400-e29b-41d4-a716-446655440000"
}
```

### 2. Consultar Status do Job

**GET** `/v1/jobs/{job_id}`

Retorna o status atual, progresso e resultado (quando completo).

**Request:**
```bash
curl "https://api.prontuai.grupobrmed.com.br/v1/jobs/550e8400-e29b-41d4-a716-446655440000"
```

**Response (durante processamento):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "job_type": "document_processing",
  "status": "in_progress",
  "progress": 45,
  "current_step": "brmed",
  "message": "Consultando exames obrigatórios (CPF: 123***)",
  "created_at": "2025-11-18T14:30:00.000Z",
  "started_at": "2025-11-18T14:30:01.000Z",
  "completed_at": null,
  "result": null,
  "error": null,
  "metadata": {
    "filename": "documento.pdf",
    "file_size": "1.69MB",
    "num_exames_obrigatorios": 2
  }
}
```

**Response (completo):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "job_type": "document_processing",
  "status": "completed",
  "progress": 100,
  "current_step": "concluido",
  "message": "Processamento concluído com sucesso!",
  "created_at": "2025-11-18T14:30:00.000Z",
  "started_at": "2025-11-18T14:30:01.000Z",
  "completed_at": "2025-11-18T14:32:15.000Z",
  "result": {
    "cpf_processado": "12345678901",
    "exames_ocr": "HEMOGRAMA, GLICEMIA",
    "exames_brnet": "HEMOGRAMA, GLICEMIA",
    "decisao_final": "Documento aprovado",
    "tabela_comparacao": [...]
  },
  "error": null,
  "metadata": {...}
}
```

**Response (erro):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "failed",
  "progress": 30,
  "current_step": "ocr",
  "message": "Erro durante processamento OCR",
  "error": "Textract job falhou: Invalid PDF format",
  "completed_at": "2025-11-18T14:30:45.000Z"
}
```

### 3. Listar Jobs

**GET** `/v1/jobs?status_filter={status}&limit={limit}`

Lista jobs, opcionalmente filtrados por status.

**Parâmetros:**
- `status_filter` (opcional): `pending`, `in_progress`, `completed`, `failed`, `cancelled`
- `limit` (opcional, padrão 50): Número máximo de jobs

**Request:**
```bash
curl "https://api.prontuai.grupobrmed.com.br/v1/jobs?status_filter=in_progress&limit=10"
```

**Response:**
```json
{
  "total": 3,
  "jobs": [
    {
      "job_id": "...",
      "status": "in_progress",
      "progress": 65,
      ...
    }
  ]
}
```

### 4. Cancelar Job

**DELETE** `/v1/jobs/{job_id}`

Marca um job como cancelado (processamento continua, mas cliente para de fazer polling).

**Request:**
```bash
curl -X DELETE "https://api.prontuai.grupobrmed.com.br/v1/jobs/550e8400-e29b-41d4-a716-446655440000"
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "cancelled",
  "message": "Job marcado como cancelado"
}
```

## Estados do Job

| Status | Descrição |
|--------|-----------|
| `pending` | Job criado, aguardando início do processamento |
| `in_progress` | Processamento em andamento |
| `completed` | Concluído com sucesso, resultado disponível |
| `failed` | Falhou com erro |
| `cancelled` | Cancelado pelo usuário |

## Etapas do Processamento

Durante o processamento (`status=in_progress`), o campo `current_step` indica a etapa atual:

| Step | Descrição |
|------|-----------|
| `pending` | Aguardando início |
| `ocr` | Processando OCR do documento |
| `brmed` | Consultando sistema BRMED |
| `validacao` | Validando exames com IA |
| `concluido` | Processamento finalizado |
| `erro` | Erro durante processamento |

## Implementação no Frontend

### Exemplo React/TypeScript

```typescript
interface JobStatus {
  job_id: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  current_step: string;
  message: string;
  result?: any;
  error?: string;
}

async function processarDocumentoAsync(arquivo: File, exames: string[]): Promise<string> {
  const formData = new FormData();
  formData.append('arquivo', arquivo);
  formData.append('exames_obrigatorios', JSON.stringify(exames));

  const response = await fetch('/v1/processar-documento-async', {
    method: 'POST',
    body: formData
  });

  const data = await response.json();
  return data.job_id;
}

async function consultarJobStatus(jobId: string): Promise<JobStatus> {
  const response = await fetch(`/v1/jobs/${jobId}`);
  return await response.json();
}

async function aguardarJobCompleto(jobId: string): Promise<any> {
  const pollInterval = 2000; // 2 segundos

  while (true) {
    const status = await consultarJobStatus(jobId);

    // Atualizar UI com progresso
    console.log(`${status.progress}% - ${status.message}`);

    if (status.status === 'completed') {
      return status.result;
    }

    if (status.status === 'failed') {
      throw new Error(status.error || 'Erro desconhecido');
    }

    // Aguardar antes do próximo poll
    await new Promise(resolve => setTimeout(resolve, pollInterval));
  }
}

// Uso
async function handleSubmit() {
  try {
    const jobId = await processarDocumentoAsync(arquivo, examesObrigatorios);
    const resultado = await aguardarJobCompleto(jobId);
    console.log('Processamento concluído:', resultado);
  } catch (error) {
    console.error('Erro:', error);
  }
}
```

## Migração Gradual

Os endpoints antigos **continuam funcionando**:

- `/v1/processar-documento` - Síncrono (pode dar timeout)
- `/v1/processar-documento-stream` - SSE streaming (pode dar timeout)

**Recomendação:** Migrar para `/v1/processar-documento-async` para evitar timeouts.

## Limitações e Considerações

### Armazenamento em Memória

Jobs são armazenados em memória (não persistentes). Jobs antigos são removidos após 24h.

**Para produção:** Considerar migração para Redis para:
- Persistência entre reinicializações
- Compartilhamento entre múltiplos workers/servidores
- Melhor performance em alta carga

### Cleanup Automático

- Jobs completos/falhos são mantidos por **24 horas**
- Máximo de **1000 jobs** no histórico
- Cleanup automático ao exceder limites

### Arquivos Temporários

Arquivos enviados são salvos temporariamente em `/tmp` e removidos após processamento.
Certifique-se de ter espaço em disco suficiente.

## Troubleshooting

### Job não encontrado (404)

- Job pode ter expirado (>24h)
- `job_id` inválido
- Job foi removido durante cleanup

### Job travado em `in_progress`

- Worker pode ter morrido durante processamento
- Verificar logs do worker
- Job será marcado como falho após timeout (implementar em versão futura)

### Performance

Para otimizar polling:
- **Intervalo recomendado:** 2-5 segundos
- **Evitar:** Polling mais rápido que 1 segundo
- **Alternativa:** Implementar WebSocket para push notifications (versão futura)
