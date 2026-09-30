# Evidence-Aware AI Research Assistant

> Transform uploaded scientific PDFs into a unified, evidence-aware literature review with interactive comparison tables and verifiable citations.

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.11-yellow)
![Next.js](https://img.shields.io/badge/Next.js-14-black)

---

## ✨ Features

- **Drag-and-drop PDF upload** — Upload 1–10 scientific papers per session
- **Automated text extraction** — PyMuPDF + pdfplumber for text and tables
- **Scientific metadata extraction** — Title, authors, year, abstract, methodology, datasets, results, limitations
- **Semantic chunking** — Section-aware document segmentation
- **Hybrid retrieval** — BM25 + dense embeddings + cross-encoder reranking
- **Scientific claim extraction** — Findings, methodology, limitations, comparisons, gaps
- **Evidence mapping** — Cross-paper claim-to-evidence relationships (supports, contradicts, extends)
- **Evidence-aware RAG** — Literature review generation grounded in source evidence
- **Citation verification** — Hallucination detection and evidence support classification
- **Structured output** — Introduction, synthesis, methodology comparison, dataset comparison, findings, gaps, conclusion
- **Interactive comparison table** — Side-by-side paper analysis
- **Export** — Download as PDF or DOCX
- **Real-time progress** — WebSocket-powered processing pipeline visualization

---

## 🏗️ Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Next.js    │────▶│   FastAPI     │────▶│  PostgreSQL  │
│   Frontend   │◀────│   Backend     │     │  (Metadata)  │
└──────────────┘     └──────┬───────┘     └──────────────┘
                           │
                    ┌──────┴───────┐
                    │              │
              ┌─────▼─────┐ ┌─────▼─────┐
              │  Celery    │ │  Qdrant   │
              │  Workers   │ │ (Vectors) │
              └─────┬─────┘ └───────────┘
                    │
              ┌─────▼─────┐ ┌───────────┐
              │  Redis     │ │  MinIO    │
              │  (Broker)  │ │  (S3/PDF) │
              └───────────┘ └───────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- A free **Groq API key** ([get one free here in 30 seconds](https://console.groq.com/keys)) *(or Gemini API key)*

### 1. Clone and configure

```bash
git clone <repo-url>
cd auto-literature-review

# Copy environment template
cp .env.example .env

# Add your Groq API key (free tier has high rate limits)
# Edit .env and set: GROQ_API_KEY=gsk_...
```

### 2. Start all services

```bash
docker-compose up --build
```

This starts:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **MinIO Console**: http://localhost:9001 (admin/minioadmin)
- **Qdrant Dashboard**: http://localhost:6333/dashboard

### 3. Upload papers and generate

1. Open http://localhost:3000
2. Drag and drop 1–10 scientific PDFs
3. Click **"Generate Literature Review"**
4. Watch real-time processing progress
5. Explore the review, comparison table, research gaps, and evidence
6. Download as PDF or DOCX

---

## 📁 Project Structure

```
├── frontend/               # Next.js + Tailwind CSS
│   ├── src/app/            # Pages and layouts
│   ├── src/lib/            # API client
│   └── Dockerfile
├── backend/                # Python FastAPI
│   ├── app/
│   │   ├── api/            # REST endpoints
│   │   ├── models/         # SQLAlchemy ORM
│   │   ├── schemas/        # Pydantic validation
│   │   ├── services/       # Business logic
│   │   │   ├── pdf_processor.py
│   │   │   ├── metadata_extractor.py
│   │   │   ├── chunker.py
│   │   │   ├── claim_extractor.py
│   │   │   ├── evidence_mapper.py
│   │   │   ├── retriever.py
│   │   │   ├── review_generator.py
│   │   │   ├── verifier.py
│   │   │   └── exporter.py
│   │   ├── workers/        # Celery tasks
│   │   ├── db/             # Database + migrations
│   │   └── storage/        # S3 client
│   ├── evaluation/         # Research evaluation
│   ├── tests/              # pytest suite
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/sessions` | Create upload session |
| `POST` | `/api/sessions/{id}/papers` | Upload PDFs |
| `GET` | `/api/sessions/{id}` | Get session status |
| `POST` | `/api/sessions/{id}/generate` | Start review generation |
| `GET` | `/api/sessions/{id}/review` | Get generated review |
| `GET` | `/api/sessions/{id}/comparison` | Get comparison table |
| `GET` | `/api/sessions/{id}/evidence/{claim_id}` | Inspect claim evidence |
| `GET` | `/api/sessions/{id}/export/pdf` | Download as PDF |
| `GET` | `/api/sessions/{id}/export/docx` | Download as DOCX |
| `WS` | `/ws/sessions/{id}/progress` | Real-time progress |

---

## 🧪 Testing

```bash
# Run backend tests
cd backend
pip install -r requirements.txt
pytest tests/ -v --cov=app

# Run with Docker
docker-compose exec backend pytest tests/ -v
```

---

## 🚢 Production Deployment

### Frontend → Vercel

```bash
cd frontend
npx vercel --prod
# Set environment variable: NEXT_PUBLIC_API_URL=https://your-backend.railway.app
```

### Backend → Railway/Render

1. Push to GitHub
2. Connect to Railway/Render
3. Set environment variables from `.env.example`
4. Deploy with `Dockerfile`

### Managed Services

| Service | Provider Options |
|---------|-----------------|
| PostgreSQL | Supabase, Neon, Railway |
| Redis | Upstash, Railway |
| Qdrant | Qdrant Cloud (free tier) |
| Object Storage | Cloudflare R2, AWS S3 |

---

## 🔒 Security

- PDF file validation (magic bytes, MIME type, size limits)
- Session-scoped data isolation
- Rate limiting on upload/generate endpoints
- CORS restricted to frontend domain
- Environment secrets never in code
- S3 presigned URLs for temporary access

---

## 📊 Evaluation Metrics

The system includes evaluation tools measuring:

- **Evidence Retrieval**: Precision, Recall, F1
- **Citation Correctness**: Accuracy, hallucination rate
- **Claim-Evidence Alignment**: Support/contradiction ratios
- **Factual Faithfulness**: Grounding score
- **Processing Latency**: Per-paper timing
- **Baseline Comparison**: Evidence-aware vs conventional RAG

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, React 18, Tailwind CSS |
| Backend | Python FastAPI |
| Database | PostgreSQL (metadata), Qdrant (vectors) |
| Cache/Queue | Redis, Celery |
| Storage | MinIO / Cloudflare R2 |
| LLM | Groq (Llama 3.3 70B Versatile) / Gemini 2.0 Flash |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 |
| PDF | PyMuPDF, pdfplumber |
| Export | WeasyPrint (PDF), python-docx (DOCX) |
| Container | Docker, Docker Compose |

---

## 📜 License

MIT License
