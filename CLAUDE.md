# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ProntuAI** is an AI-powered medical document processing platform for BRMED (occupational health company). The system validates patient medical exam documents by extracting exam information via OCR, cross-referencing against mandatory requirements from the BRMED authorization system (BRNET), and providing intelligent comparison using vector similarity and OpenAI GPT models.

The application consists of three main workflows:
1. **Submissão**: Upload documents for OCR extraction and validation against BRNET requirements
2. **Checagem**: Review rejected documents and manually validate/approve them
3. **Insights**: Analytics dashboard for FAQ queries and system usage

## Repository Structure

```
prontuai/
├── front-end/          # Next.js 15 + React 19 application
│   ├── app/            # Next.js App Router pages and API routes
│   ├── components/     # React components (including 23 shadcn/ui components)
│   ├── hooks/          # Custom React hooks
│   ├── lib/            # Utility functions
│   └── types/          # TypeScript type definitions
└── back-end/           # FastAPI + Python application
    ├── app/
    │   ├── api/        # FastAPI route handlers (v1_ocr, v1_brmed, v1_validacao, v1_faq)
    │   ├── core/       # Configuration, logging, and shared clients
    │   ├── services/   # Business logic (ocr, brmed, validacao, faq, workflow)
    │   └── models/     # Data models
    ├── data/           # FAISS vector indexes
    ├── scripts/        # Index generation scripts
    └── tests/          # Pytest test suite
```

**Detailed documentation** for each subsystem:
- Front-end: `front-end/CLAUDE.md`
- Back-end: `back-end/CLAUDE.md`

## Development Setup

### Prerequisites
- Node.js 20+ (for front-end)
- Python 3.11+ (for back-end)
- Playwright browsers (for BRMED web scraping)
- OpenAI API key

### Quick Start

**Front-end** (runs on http://localhost:3000):
```bash
cd front-end
npm install
npm run dev
```

**Back-end** (runs on http://localhost:8000):
```bash
cd back-end
pip install -r requirements.txt
playwright install chromium
uvicorn main:app --reload
```

### Environment Variables

**Front-end** (`front-end/.env.local`):
```env
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=your_nextauth_secret
```

**Back-end** (`back-end/.env`):
```env
OPENAI_API_KEY=your_openai_api_key
BRMED_USERNAME=your_brmed_username
BRMED_PASSWORD=your_brmed_password
MODELO_GPT=gpt-4o-mini
MODELO_EMBEDDING=text-embedding-3-large
```

## System Architecture

### Data Flow: Document Processing Pipeline

```
1. User uploads document (front-end)
   ↓
2. POST /v1/processar-documento → back-end workflow_service.py
   ↓
3. OCR extraction (ocr_service.py)
   - Convert document to markdown using Docling
   - Extract CPF using regex (UF/CPF pattern or fallback)
   - Extract exam names using OpenAI GPT
   ↓
4. BRMED query (brmed_service.py)
   - Playwright automation to scrape BRNET authorization system
   - Retrieve mandatory exams for patient CPF
   ↓
5. Validation (validacao_service.py)
   - Generate embeddings for exams
   - Search FAISS similarity index for synonyms
   - Compare via OpenAI GPT with synonym context
   ↓
6. Frontend exam comparison (POST /api/comparar-exames)
   - Additional GPT-based comparison with 74+ hardcoded medical equivalencies
   - Display results in exames-comparativo-table
   ↓
7. Results displayed in chat interface with localStorage persistence
```

### Authentication Flow

- **Provider**: NextAuth with Google OAuth
- **Restriction**: Only `@grupobrmed.com.br` corporate emails allowed
- **Protected Routes**: `/submissao`, `/checagem`, `/insights`, `/documentacao` (enforced by `front-end/middleware.ts`)
- **Public Routes**: `/login`, `/api/auth/*`

## Key Integration Points

### Front-end → Back-end API Calls

The front-end makes requests to these back-end endpoints:

| Endpoint | Purpose | Called From |
|----------|---------|-------------|
| `POST /v1/processar-documento` | Full OCR + BRMED + validation pipeline | `app/submissao/page.tsx` |
| `POST /v1/faq` | RAG-based Q&A for occupational health questions | `app/insights/page.tsx` |

### Front-end Internal API Routes

| Route | Purpose |
|-------|---------|
| `POST /api/comparar-exames` | Secondary exam comparison with medical equivalencies |
| `GET/POST /api/auth/[...nextauth]` | NextAuth authentication handler |

## Application Pages

### `/submissao` (Main Workflow)
- **Components**: `chat.tsx`, `settings-panel-submissao.tsx`, `file-uploader.tsx`, `exames-comparativo-table.tsx`
- **Features**: Document upload, OCR processing, exam comparison, chat interface with typewriter effect
- **State Management**: localStorage for `chat_history`

### `/checagem` (Manual Review)
- **Components**: `checagem-table.tsx`
- **Purpose**: Review and manually validate rejected documents
- **Data**: Currently using mock data (pending backend integration)

### `/insights` (Analytics)
- **Features**: FAQ chat interface for querying medical guidelines
- **Backend**: Uses FAISS L2 index for semantic search through `base.txt` knowledge base

### `/documentacao` (Documentation)
- **Purpose**: Internal documentation and user guides

## Testing

**Front-end**:
```bash
cd front-end
npm run lint          # ESLint
npm run build         # Production build (catches type errors)
```

**Back-end**:
```bash
cd back-end
pytest                # Run all tests
pytest -v             # Verbose output
pytest --cov=app      # With coverage
pytest tests/test_validacao.py  # Specific test file
```

## Common Development Tasks

### Adding a New Frontend Page

1. Create page file: `front-end/app/new-page/page.tsx`
2. Add sidebar link in `front-end/components/app-sidebar.tsx`
3. If route needs protection, it's already covered by middleware (all routes except `/login` and `/api/auth/*`)

### Modifying Medical Exam Equivalencies

**Front-end** (`app/api/comparar-exames/route.ts`):
- Update `normalizeExameName()` function with new medical term mappings

**Back-end** (`app/services/validacao_service.py`):
- Add new entries to `exames_similares_final.csv`
- Regenerate FAISS index: `python scripts/generate_exam_similarity_index.py`

### Regenerating Vector Indexes

When updating knowledge bases or exam synonyms:
```bash
cd back-end

# FAQ index from base.txt
python scripts/generate_faq_index.py

# Exam similarity index from exames_similares_final.csv
python scripts/generate_exam_similarity_index.py
```

### Changing Allowed Email Domain

Edit `front-end/app/api/auth/[...nextauth]/route.ts`:
```typescript
async signIn({ profile }) {
  // Change domain here
  if (profile?.email?.endsWith("@yourdomain.com")) {
    return true;
  }
  return false;
}
```

## Important Implementation Details

### FAISS Distance Metrics
- **FAQ Service**: Uses L2 distance (lower score = better match)
- **Threshold**: < 1.0 by default (configured via `MAX_DISTANCIA_FAQ`)
- **Critical**: Embeddings are NOT normalized (normalization disabled in `back-end/app/services/faq_service.py:69`)

### CPF Extraction Strategy (Back-end)
1. Regex search for `UF/CPF` pattern (e.g., "CE/12345678901")
2. Fallback to any 11-digit CPF if no UF pattern
3. Workflow fallback: If BRMED fails, extract all CPFs via LLM and retry each

### GPU Memory Management
- Backend OCR service uses PyTorch CUDA memory cleanup
- Environment variable: `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`
- Explicit cleanup: `torch.cuda.empty_cache()` after processing

### OpenAI Retry Logic
- All OpenAI API calls use tenacity retry decorators
- Configuration: `@retry(wait=wait_exponential(min=1, max=10), stop=stop_after_attempt(3))`
- Applies to embeddings and GPT completions

## Error Handling and Logging

**Back-end**:
- Logs written to `back-end/logs/` (configured in `app/core/logging.py`)
- Audit trails for validations: `back-end/auditoria_validacao/`
- BRMED automation outputs: `back-end/resultados/`
- OCR outputs: `back-end/ocr_resultados/`

**Front-end**:
- Console logging for debugging
- localStorage persistence for chat history and state

## Tech Stack Summary

| Layer | Technologies |
|-------|-------------|
| **Frontend** | Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS 4, shadcn/ui, NextAuth, OpenAI API |
| **Backend** | FastAPI, Python 3.11+, OpenAI API, FAISS (GPU), Playwright, Docling (OCR), PyTorch |
| **Vector DB** | FAISS with L2 distance (FAQ) and cosine similarity (exam matching) |
| **Authentication** | Google OAuth (NextAuth) restricted to @grupobrmed.com.br |
| **Deployment** | Development: uvicorn (backend) + Next.js dev server (frontend) |

## Known Limitations and Future Work

1. **Checagem page**: Currently uses mock data, pending backend integration
2. **BRMED scraping**: Depends on BRNET web interface stability (Playwright automation)
3. **OCR accuracy**: Dependent on document quality and Docling performance
4. **Hardcoded URLs**: Backend URL hardcoded in front-end as `http://localhost:8000` (consider environment variables)
5. **Chat history**: Stored in localStorage only (no database persistence)

## Git Workflow

- **Main branch**: `main`
- **Recent commits**: Check `git log` for latest changes
- Working directories have uncommitted changes (`m back-end`, `m front-end`)

## Additional Resources

- **Next.js Documentation**: https://nextjs.org/docs
- **FastAPI Documentation**: https://fastapi.tiangolo.com
- **FAISS Documentation**: https://github.com/facebookresearch/faiss
- **Docling (OCR)**: https://github.com/DS4SD/docling
