# Sourcebeam production and quality guide

## Implemented architecture

Sourcebeam now includes all ten portfolio hardening areas:

1. Scanned pages fall back to Poppler rendering plus Tesseract OCR.
2. Retrieval combines pgvector cosine search with PostgreSQL full-text search.
3. A bounded Gemini reranker reorders the hybrid candidate pool and fails open.
4. `evals/cases.json` is a versioned, synthetic evaluation dataset.
5. `python -m evals.run` reports Recall@3, reciprocal rank, citation validity,
   lexical groundedness, and expected-answer term coverage.
6. Uploads create durable `document_ingestion_jobs`; `python worker.py` claims jobs
   with `FOR UPDATE SKIP LOCKED`, retries transient failures, recovers stale jobs,
   and reports document progress.
7. Docker Compose starts PostgreSQL/pgvector, MinIO, FastAPI, the worker, and the
   Nginx-served React build.
8. Original PDFs and sanitized images use a local or S3-compatible private object
   storage abstraction. Database rows retain ownership metadata and storage keys.
9. Playwright covers workspace startup and streamed multimodal image chat.
10. Per-user daily message/upload and total-storage quotas protect a public demo.

## Full Docker startup

```powershell
cd C:\py
Copy-Item .env.docker.example .env.docker
```

Replace every placeholder in `.env.docker`, then:

```powershell
docker compose --env-file .env.docker up --build
```

Open `http://localhost:5173`. Use `docker compose --env-file .env.docker logs -f
backend worker` to inspect API and ingestion activity.

## Manual development startup

Start PostgreSQL/pgvector and an S3-compatible service, or keep
`STORAGE_BACKEND=local`. Then use three terminals:

```powershell
cd C:\py
python -m alembic upgrade head
python run_server.py
```

```powershell
cd C:\py
python worker.py
```

```powershell
cd C:\py-frontend
npm run dev
```

Tesseract and `pdftoppm` must be on `PATH` for scanned-PDF OCR. The backend Docker
image installs both automatically.

## Quality checks

```powershell
cd C:\py
python -m pytest -q
python -m evals.run
```

The live evaluation command consumes Gemini quota. It uses synthetic evidence and
does not upload private documents.

```powershell
cd C:\py-frontend
npm run lint
npm run build
npm run test:e2e
```

Install a Playwright browser once with `npx playwright install chromium`.

## Public deployment checklist

- Put the frontend and API behind HTTPS.
- Use managed secrets; never deploy `.env` files.
- Use a strong database password and JWT secret.
- Set exact production origins in `ALLOWED_ORIGINS`.
- Use a private bucket and private network paths for PostgreSQL and object storage.
- Keep the included quotas conservative until real cost and latency data exists.
- Add provider billing alerts, database backups, retention rules, and centralized logs.
- Expand `evals/cases.json` before changing chunking, embedding, or ranking settings.
