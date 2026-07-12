from fastapi import FastAPI
from fastapi import FastAPI, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db import init_db, get_db
from app.schemas import JobCreate, JobResponse
from app.models.job import Job, JobStatus

app = FastAPI(
    title="Async Job Processing System",
    description="Submit image-processing jobs, track status, and view results asynchronously.",
    version="1.0.0",
)

@app.on_event("startup")
def on_startup():
    init_db()

@app.get("/health")
async def health():
	"""
	   Checks if app is running and is ok.
	"""
	return {"status": "ok"}
    
    
@app.get("/info")
async def info():
	"""
	  Shows settings info - for dev only! 
	"""
	return {
        "database_url": settings.database_url
    }
    
@app.post("/jobs", response_model=JobResponse, status_code=202)
def create_job(job_in:JobCreate, db: Session = Depends(get_db)):
	"""
	   Submits a new job. Returns 202 Accepted 
	   
	   Idempotency: if 'idempotency_key' is provided and a job with that 
	   key already exists, the exististing job is returned instead of creating a
	   duplicate - protects against double-submission from clients retries.
	"""
	if job_in.idempotency_key:
		existing = (
			db.query(Job)
			.filter(Job.idempotency_key == job_in.idempotency_key)
			.first()
		)
		if existing:
			return existing
			
	job = Job(
	    type = job_in.type,
	    payload = job_in.payload.model_dump(),
	    max_attempts = settings.max_jobs_attempts,
	    idempotency_key = job_in.idempotency_key,
	    status = JobStatus.pending	    
	)
	db.add(job)
	db.commit()
	db.refresh(job)
	
	return job
    
