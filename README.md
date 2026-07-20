# Async Job Processing System

A backend service that accepts image-processing jobs, queues them, processes them asynchronously with retries and failure handling, and exposes status through a REST API — a simplified version of what powers background job systems in production (e.g. sending emails, generating reports, processing uploads).

## What it does

You upload an image and submit a job describing what to do with it (resize, convert format, or apply a watermark). The API responds immediately with a job ID (`202 Accepted`) while the actual work happens in the background via a Celery worker. You poll the job endpoint to check status and get the result. A scheduled cleanup task and a full observability stack (Prometheus, Grafana, Flower) run alongside it.

## Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│  REST API   │─────▶│ Redis/Celery │─────▶│  Worker(s)  │
│  (FastAPI)  │      │    Queue     │      │  (Celery)   │
└─────┬───────┘      └──────────────┘      └──────┬──────┘
      │                     ▲                     │
      │                     │                     ▼
      │              ┌─────────────┐       ┌─────────────┐
      │              │ Celery Beat │       │ PostgreSQL  │
      │              │ (scheduler) │       │ (job state) │
      │              └─────────────┘       └─────────────┘
      ▼
┌─────────────┐      ┌─────────────┐     ┌─────────────┐
│ Prometheus  │◀────▶│   Grafana   │     │   Flower    │
│  /metrics   │      │ (dashboards)│     │ (task/worker│
└─────────────┘      └─────────────┘     │  monitoring)│
                                         └─────────────┘
```

The API and worker are separate processes — the API never does the actual image processing itself, it only enqueues work and reports on state stored in Postgres. This is the core design choice that makes the system "async" rather than just non-blocking. Celery Beat is a third, independent process: it only *schedules* recurring work onto the queue, it never executes tasks itself — that's still the worker's job.

## How to run it

Requires Docker and Docker Compose (`docker compose`, not the older standalone `docker-compose`, depending on your Docker version).

```bash
cp .env.example .env    # if present -- otherwise create .env yourself, see Configuration below
docker compose up --build
```

This starts:

| Service | Port | Purpose |
|---|---|---|
| `api` | `8000` | FastAPI app — API docs at `/docs` |
| `worker` | — | Celery worker, processes jobs |
| `beat` | — | Celery Beat, schedules the periodic cleanup task |
| `flower` | `5555` | Real-time Celery monitoring dashboard |
| `postgres` | `5432` | Job state |
| `redis` | `6379` | Celery broker/result backend |
| `prometheus` | `9090` | Metrics scraping |
| `grafana` | `3000` | Dashboards (login `admin`/`admin`) — Prometheus datasource and the main dashboard are auto-provisioned, no manual setup needed |

### A note on Grafana provisioning permissions

The provisioning files under `observability/grafana/provisioning/` are bind-mounted into the Grafana container, which runs as a non-root user. If Grafana logs `permission denied` reading that directory, fix it with:
```bash
chmod -R a+rX observability/grafana/provisioning
```

## Configuration

Copy `.env.example` to `.env` (create one if it doesn't exist yet) with at least:
```
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/jobs
REDIS_URL=redis://redis:6379/0
MAX_JOBS_ATTEMPTS=3
UPLOAD_DIR=/tmp/uploads
```
Settings are resolved via an absolute path relative to `app/config.py`'s own location, so they load correctly regardless of which directory you run `uvicorn`/`celery` from.

## API reference

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/uploads` | Upload a source image, returns a file path to use in a job payload |
| `POST` | `/jobs` | Submit a job (returns `202 Accepted` with job ID); payload is validated against a strict schema before the job is even created |
| `GET` | `/jobs/{id}` | Get job status and result |
| `GET` | `/jobs?status=&limit=&offset=` | List/filter/paginate jobs |
| `POST` | `/jobs/{id}/retry` | Manually retry a failed job |
| `DELETE` | `/jobs/{id}` | Cancel a job (pending **or** failed) |
| `GET` | `/metrics` | Prometheus scrape target |
| `GET` | `/health` | Health check |

### Supported job operations

`type: "image_resize"` jobs accept an `operations` list, applied in order:

| `op` | Fields | What it does |
|---|---|---|
| `resize` | `width`, `height` | Resizes the image |
| `convert` | `format` | Converts color mode (e.g. `RGB`, `L`) |
| `watermark` | — | Overlays a semi-transparent text watermark in the bottom-right corner |

### Example: submit a job

```bash
# 1. Upload an image
curl -F "file=@photo.jpg" http://localhost:8000/uploads
# => {"path": "/tmp/uploads/abc123.jpg"}

# 2. Submit a job referencing that path
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "type": "image_resize",
    "payload": {
      "source_path": "/tmp/uploads/abc123.jpg",
      "operations": [
        {"op": "resize", "width": 200, "height": 200},
        {"op": "watermark"}
      ]
    },
    "idempotency_key": "optional-client-generated-key"
  }'
# => {"id": "...", "status": "pending", ...}

# 3. Poll for the result
curl http://localhost:8000/jobs/<job_id>
```

## Scheduled maintenance (Celery Beat)

A periodic task, `cleanup_stale_jobs`, runs every 15 minutes and marks any job stuck in `processing` for over 60 minutes as `failed`. This exists because a crashed or killed worker (OOM, redeploy, host reboot) leaves its in-flight job stuck in `processing` forever — nothing else would ever update it otherwise, since the task that was updating it no longer exists. Without this, such jobs would be invisible failures rather than visible ones.

## Monitoring

- **Flower** (`http://localhost:5555`) — live view of active/queued/completed tasks, worker status, and retry history. Also exposes its own `/metrics` endpoint, scraped by Prometheus alongside the API.
- **Grafana** (`http://localhost:3000`) — a pre-provisioned "Async Job System" dashboard with request rate, error rate, p95 latency, and requests-by-endpoint panels.

## Design decisions

- **Celery over a simpler queue library.** Celery gives production-realistic retry/backoff configuration out of the box and is the most widely used task queue in Python production systems — worth knowing well rather than reinventing a smaller version of it.
- **Job state lives in Postgres, not just Redis.** Redis data can be evicted or is ephemeral by design; job history needs to be durable and queryable (e.g. "show me all failed jobs from today"), which is a relational query, not a cache lookup.
- **`POST /jobs` returns `202 Accepted`, not `200`/`201`.** The job isn't complete when the response is sent — it's queued.
- **Idempotency via a client-supplied key.** Protects against a client's HTTP request timing out and retrying the *same logical submission*, which would otherwise silently create a duplicate job.
- **Payload validated at the API layer, not just the worker.** `payload` is a strict, typed schema (`ImageJobPayload`), checked before a job is ever created. A malformed payload (e.g. `operations` sent as a string instead of a list) is rejected immediately with a `422`, instead of being accepted and failing confusingly later inside the worker.
- **Permanent vs. transient failures are decided explicitly**, via a dedicated `PermanentJobError`, rather than by inspecting the *type* of exception a library happens to raise. Pillow raises plain `OSError` for a wide range of unrelated failures — some transient (a disk hiccup), some permanent (an invalid image mode). Branching on exception type conflates those; branching on an explicit, deliberate decision does not.
- **Retries use `autoretry_for` + `retry_backoff` on the task decorator**, letting Celery own retry scheduling and backoff math entirely, rather than computing backoff manually. An earlier version of this project called `self.retry()` manually to support a hypothetical per-job retry limit — but the API never actually exposes customizing that per job, and the manual path silently lost the decorator's backoff configuration (falling back to Celery's built-in 180-second default). Simplified back to the decorator-based approach once that limitation was clear.
- **Dead-letter behavior after max retries.** Once retries are exhausted, the job is marked `failed` with the error recorded — it doesn't retry forever, and it doesn't silently disappear.
- **Stale-job cleanup runs as a separate Celery Beat process**, not inside the worker or API. Only one Beat process should ever run (running multiple would schedule duplicate work), while workers scale independently — keeping Beat separate makes that constraint structural rather than something to remember.

## Known limitations

- Single worker process in the default `docker-compose.yml` — no horizontal worker scaling configured.
- No file-size limits or content-type validation on `/uploads` yet — needed before accepting untrusted uploads in production.
- `requirements.txt` is currently a full `pip freeze` output (many transitive dependencies pinned individually) rather than a curated top-level list — works correctly, but is harder to read at a glance than a minimal, hand-maintained requirements file.

## What I'd change at scale

- Move file storage from local disk to S3-compatible object storage, so workers and API don't need a shared filesystem.
- Add a dead-letter Celery queue (rather than just a `failed` DB status) so failed jobs can be inspected/replayed independently of the main queue.
- Add horizontal worker autoscaling based on queue depth.
- Add structured JSON logging with request IDs threaded through to the worker, for tracing a single job across both processes.


## Running tests locally

```bash
pip install -r requirements.txt
pytest app/tests/
```

Tests expect a reachable Postgres/Redis (either via `docker compose up -d postgres redis`, or your own local instances) and use a separate `..._test` database so they don't touch real job data.

## License

MIT — see `LICENSE`.
