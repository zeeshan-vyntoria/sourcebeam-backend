# Phase 2: PDF RAG learning guide

## What the application now does

1. An authenticated user uploads a searchable PDF.
2. The API validates the file, extracts text page by page, and splits each page into overlapping chunks.
3. Gemini Embedding 2 converts every chunk into a 768-number vector.
4. PostgreSQL stores the chunk text, page metadata, and vector using pgvector.
5. A PDF can be attached to one or more conversations owned by the same user.
6. For each question, the API runs pgvector cosine search and PostgreSQL full-text search over only the attached documents.
7. Reciprocal-rank fusion combines both result sets, then Gemini reranks a bounded candidate pool.
8. The most relevant passages are placed in a guarded system instruction.
9. Gemini streams a grounded answer. The answer and its source metadata are saved together.

Uploads now retain originals in private object storage and queue a durable ingestion job. A separate worker extracts text, falls back to Poppler plus Tesseract OCR for scanned pages, reports progress, retries failures, chunks pages, and generates embeddings.

## Core concepts

### Tokens and context windows

Models read tokens rather than characters. A token is often part of a word. The application stores an approximate token count (`characters / 4`) for observability, while Gemini enforces its exact tokenizer and context limit. Only the top retrieved chunks are sent to chat, keeping the prompt focused and bounded.

### Embeddings

An embedding is a numeric representation of meaning. Similar text produces vectors pointing in similar directions. Gemini Embedding 2 does not use the older `task_type` setting, so the application prefixes passages and questions with short retrieval instructions instead. Both produce 768-dimensional vectors, which are L2-normalized before storage/search.

### Hybrid retrieval and cosine similarity

Cosine similarity compares vector direction rather than raw size:

```text
similarity(a, b) = (a dot b) / (length(a) * length(b))
```

pgvector's `<=>` operator returns cosine distance, so the query converts it to similarity with `1 - distance`. Higher scores mean closer semantic meaning.

Semantic retrieval is complemented by PostgreSQL `to_tsvector`/`plainto_tsquery` search, which is especially useful for exact identifiers and names. Reciprocal-rank fusion avoids treating vector and keyword scores as if they had the same numerical scale. A bounded Gemini reranking pass then considers the question and candidate passages together; failures fall back to the fused ranking.

### Chunking and metadata

Each chunk belongs to exactly one PDF page and stores:

- document and user IDs;
- one-based page number;
- stable chunk order;
- extracted text;
- approximate token count;
- embedding vector.

Chunks overlap so a sentence near a boundary is not split out of context. Page boundaries are never crossed, keeping citations precise.

### Retrieval-Augmented Generation

RAG does not retrain Gemini. It retrieves relevant information at request time and adds it to the model prompt. The model is instructed to use only those passages, ignore instructions contained inside uploaded files, cite numbered sources, and admit when the retrieved evidence is insufficient.

## Important files

- `app/services/rag.py`: PDF extraction/OCR, chunking, hybrid retrieval, reranking, and grounding instructions.
- `app/services/ingestion.py` and `worker.py`: durable background ingestion, retries, and progress.
- `app/services/storage.py`: private local or S3-compatible object storage.
- `app/api/routes/documents.py`: private upload/library/attachment endpoints.
- `app/api/routes/conversations.py`: retrieval plus streamed grounded generation.
- `app/models.py`: documents, chunks, attachments, and persisted citations.
- `alembic/versions/20261019_0003_rag_documents.py`: pgvector schema and HNSW index.
- `alembic/versions/20261020_0005_production_rag.py`: object keys, job state, progress, and the full-text GIN index.
- `evals/run.py`: retrieval recall, reciprocal-rank, citation, groundedness, and expected-term evaluation.
- `C:/py-frontend/src/App.jsx`: document library, attachment state, streamed sources, and citation cards.

## Database setup

pgvector must be installed in the PostgreSQL 18 server, then the migration is applied:

```powershell
cd C:\py
& "$env:LOCALAPPDATA\Python\bin\python.exe" -m alembic upgrade head
```

The migrations enable `vector`, add a `vector(768)` column, create an HNSW cosine index, and add a PostgreSQL GIN full-text index.

## Running the application

```powershell
cd C:\py
& "$env:LOCALAPPDATA\Python\bin\python.exe" run_server.py
```

In another terminal, run the ingestion worker:

```powershell
cd C:\py
& "$env:LOCALAPPDATA\Python\bin\python.exe" worker.py
```

```powershell
cd C:\py-frontend
npm run dev
```

Open the Knowledge base, upload a searchable PDF, attach it to a conversation, and ask a question whose wording differs from the PDF. Semantic retrieval should still find the relevant passage.

## Current boundaries

- PDFs are limited to 15 MB, 250 pages, and one million extracted characters.
- Password-protected PDFs are rejected. Scanned pages require `pdftoppm` and Tesseract, both included in the backend Docker image.
- Original PDFs and sanitized images are private objects; PostgreSQL stores their keys and ownership metadata.
- The upload API queues processing and returns immediately; `worker.py` must be running for documents to become ready.
- Rate limits are process-local. Multi-instance production should use Redis or an API gateway.
