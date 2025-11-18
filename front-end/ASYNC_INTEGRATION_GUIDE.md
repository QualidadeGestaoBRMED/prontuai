# Guia de Integração: API Assíncrona de Jobs

## Visão Geral

O sistema de processamento de documentos agora suporta **processamento assíncrono com polling**, eliminando timeouts de workers durante OCR de documentos grandes.

## O que mudou?

### Antes (SSE - Server-Sent Events)
```typescript
// Cliente ficava conectado aguardando eventos
fetch('/v1/processar-documento-stream') -> Stream de eventos -> Resultado

Problema: Workers morriam após 20-30 segundos em documentos grandes
```

### Agora (Async + Polling)
```typescript
// 1. Cliente envia documento
POST /v1/processar-documento-async -> job_id (retorna imediatamente)

// 2. Cliente faz polling
GET /v1/jobs/{job_id} -> { progress: 45%, status: "in_progress" }

// 3. Resultado quando completo
GET /v1/jobs/{job_id} -> { progress: 100%, status: "completed", result: {...} }

Benefício: Worker não trava, cliente recebe progresso em tempo real
```

## Como Usar

### 1. Componente DocumentBatchProcessor (Padrão)

O `DocumentBatchProcessor` já está configurado para usar a API assíncrona por padrão:

```tsx
import { DocumentBatchProcessor } from "@/components/document-batch-processor"

// Usa API assíncrona (recomendado)
<DocumentBatchProcessor
  files={files}
  onComplete={(results) => console.log(results)}
  onError={(error) => console.error(error)}
/>

// Fallback para SSE (se necessário)
<DocumentBatchProcessor
  files={files}
  useAsync={false} // Força SSE
  onComplete={(results) => console.log(results)}
/>
```

### 2. Hook useAsyncJob (Uso Manual)

Para implementações customizadas:

```typescript
import { useAsyncJob } from "@/hooks/use-async-job"

function MyComponent() {
  const { startJob, pollJob, currentJob, isPolling, error } = useAsyncJob()

  const handleUpload = async (file: File) => {
    try {
      // 1. Iniciar job
      const jobId = await startJob(file, ["HEMOGRAMA", "GLICEMIA"])
      console.log("Job criado:", jobId)

      // 2. Fazer polling com callbacks de progresso
      const result = await pollJob(jobId, {
        interval: 2000,         // Poll a cada 2 segundos
        timeout: 300000,        // Timeout de 5 minutos
        onProgress: (job) => {
          console.log(`${job.progress}% - ${job.message}`)
          // Atualizar UI com progresso
        },
        onComplete: (result) => {
          console.log("Processamento concluído!", result)
        },
        onError: (error) => {
          console.error("Erro:", error)
        },
      })

      console.log("Resultado final:", result)
    } catch (err) {
      console.error("Erro no processamento:", err)
    }
  }

  return (
    <div>
      {isPolling && currentJob && (
        <div>
          <progress value={currentJob.progress} max={100} />
          <p>{currentJob.message}</p>
        </div>
      )}
      {error && <p className="text-red-500">{error}</p>}
      <input type="file" onChange={(e) => handleUpload(e.target.files[0])} />
    </div>
  )
}
```

### 3. API Direta (Fetch)

Para casos avançados sem hook:

```typescript
async function processDocumentManually(file: File) {
  // 1. Criar job
  const formData = new FormData()
  formData.append("arquivo", file)
  formData.append("exames_obrigatorios", JSON.stringify([]))

  const createResponse = await fetch("/v1/processar-documento-async", {
    method: "POST",
    body: formData,
  })

  const { job_id } = await createResponse.json()
  console.log("Job ID:", job_id)

  // 2. Polling
  const pollInterval = setInterval(async () => {
    const statusResponse = await fetch(`/v1/jobs/${job_id}`)
    const job = await statusResponse.json()

    console.log(`${job.progress}% - ${job.message}`)

    if (job.status === "completed") {
      clearInterval(pollInterval)
      console.log("Resultado:", job.result)
    }

    if (job.status === "failed") {
      clearInterval(pollInterval)
      console.error("Erro:", job.error)
    }
  }, 2000)
}
```

## Tipos TypeScript

### Job
```typescript
interface Job {
  job_id: string
  job_type: string
  status: "pending" | "in_progress" | "completed" | "failed" | "cancelled"
  progress: number // 0-100
  current_step: "pending" | "upload" | "ocr" | "brmed" | "validacao" | "concluido" | "erro"
  message: string
  created_at: string
  started_at: string | null
  completed_at: string | null
  result: DocumentProcessingResult | null
  error: string | null
  metadata: {
    filename: string
    file_size: string
    num_exames_obrigatorios: number
  }
}
```

### Etapas e Progresso

| Etapa | Progress | Descrição |
|-------|----------|-----------|
| `pending` | 0-10% | Job criado, aguardando |
| `ocr` | 10-30% | Processando OCR |
| `brmed` | 30-60% | Consultando BRMED |
| `validacao` | 60-90% | Validando exames |
| `concluido` | 100% | Completo |

## Endpoints da API

### Criar Job
```bash
POST /v1/processar-documento-async
Content-Type: multipart/form-data

arquivo: <file>
exames_obrigatorios: ["EXAME1", "EXAME2"]

Response:
{
  "job_id": "550e8400-...",
  "status": "pending",
  "message": "Documento recebido...",
  "poll_url": "/v1/jobs/550e8400-..."
}
```

### Consultar Status
```bash
GET /v1/jobs/{job_id}

Response:
{
  "job_id": "550e8400-...",
  "status": "in_progress",
  "progress": 45,
  "current_step": "brmed",
  "message": "Consultando exames...",
  "result": null,
  "error": null
}
```

### Listar Jobs
```bash
GET /v1/jobs?status_filter=in_progress&limit=10

Response:
{
  "total": 3,
  "jobs": [...]
}
```

### Cancelar Job
```bash
DELETE /v1/jobs/{job_id}

Response:
{
  "job_id": "550e8400-...",
  "status": "cancelled",
  "message": "Job marcado como cancelado"
}
```

## Migração de Código Existente

### De SSE para Async

#### Antes (SSE)
```typescript
const response = await fetch("/v1/processar-documento-stream", {
  method: "POST",
  body: formData,
})

const reader = response.body.getReader()
const decoder = new TextDecoder()

while (true) {
  const { done, value } = await reader.read()
  if (done) break

  const data = decoder.decode(value)
  const event = JSON.parse(data)

  if (event.progress === 100) {
    console.log("Resultado:", event.resultado)
    break
  }
}
```

#### Depois (Async)
```typescript
const { startJob, pollJob } = useAsyncJob()

const jobId = await startJob(file, exames)

const result = await pollJob(jobId, {
  onProgress: (job) => console.log(`${job.progress}%`),
  onComplete: (result) => console.log("Resultado:", result),
})
```

## Configuração de Variáveis de Ambiente

### Frontend (.env.local)
```bash
NEXT_PUBLIC_API_URL=https://api.prontuai.grupobrmed.com.br
```

### Backend (.env)
```bash
# CORS para aceitar frontend staging/prod
ALLOWED_ORIGINS=https://prontuai.grupobrmed.com.br,https://prontuai-staging.onrender.com
```

## Troubleshooting

### Polling não atualiza
- Verifique se `interval` não está muito baixo (< 1000ms)
- Confirme que o backend está retornando `job_id` correto

### Job não encontrado (404)
- Job pode ter expirado (>24h)
- Verifique se o `job_id` está correto

### Timeout durante polling
- Aumente o `timeout` em `pollJob` options
- Padrão é 5 minutos (300000ms)

### Worker ainda dá timeout
- Verifique se está usando `/v1/processar-documento-async` e não `/v1/processar-documento-stream`
- Confirme que `useAsync={true}` no componente

## Performance e Boas Práticas

### Intervalo de Polling Recomendado
```typescript
pollJob(jobId, {
  interval: 2000, // ✅ Recomendado: 2 segundos
  interval: 500,  // ❌ Muito rápido: sobrecarga no servidor
  interval: 10000, // ❌ Muito lento: UX ruim
})
```

### Cleanup de Jobs
- Jobs são automaticamente removidos após 24h
- Para produção: Considerar migrar para Redis para persistência

### Múltiplos Documentos
```typescript
// Processar em paralelo (recomendado)
const jobIds = await Promise.all(
  files.map(file => startJob(file, exames))
)

// Polling em paralelo
const results = await Promise.all(
  jobIds.map(jobId => pollJob(jobId, options))
)
```

## Roadmap Futuro

- [ ] WebSocket para push notifications (eliminar polling)
- [ ] Redis para persistência de jobs
- [ ] Dashboard de monitoramento de jobs
- [ ] Retry automático em caso de falha
- [ ] Estimativa de tempo restante

## Suporte

Para dúvidas ou problemas:
1. Verificar logs do backend: `[JOB {job_id}]`
2. Verificar logs do frontend: `[FRONTEND-ASYNC]`
3. Consultar documentação completa: `back-end/ASYNC_JOBS_API.md`
