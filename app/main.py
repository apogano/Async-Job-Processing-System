import os
import shutil
import uuid

from fastapi import FastAPI
from fastapi import FastAPI, Depends, Query, HTTPException, File, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.db import init_db, get_db
from app.schemas import JobCreate, JobResponse
from app.models.job import Job, JobStatus
from app.workers.tasks import process_image_job

from typing import Optional

app = FastAPI(
    title="Async Job Processing System",
    description="Submit image-processing jobs, track status, and view results asynchronously.",
    version="1.0.0",
)

@app.on_event("startup")
def on_startup():
    init_db()
    os.makedirs(settings.upload_dir, exist_ok=True)

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
    
    process_image_job.delay(str(job.id))
    
    return job
    
@app.get("/jobs", response_model=list[JobResponse])
def list_jobs(
    status: Optional[JobStatus] = Query(default=None),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Job)
    if status:
        query = query.filter(Job.status == status)
    jobs = query.order_by(Job.created_at.desc()).offset(offset).limit(limit).all()
    return [j for j in jobs]     
   
@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.post("/jobs/{job_id}/retry", response_model=JobResponse)
def retry_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.failed:
        raise HTTPException(status_code=400, detail="Only failed jobs can be retried")

    job.status = JobStatus.pending
    job.attempts = 0
    job.result = None
    db.add(job)
    db.commit()
    db.refresh(job)

    process_image_job.delay(str(job.id))

    return job.to_dict()    
    
@app.delete("/jobs/{job_id}", status_code=204)
def cancel_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in [ JobStatus.pending, JobStatus.failed]:
        raise HTTPException(
            status_code=400, detail="Only pending or failed jobs can be cancelled"
        )
    db.delete(job)
    db.commit()
    return None

@app.post("/uploads", status_code=201)
async def upload_image(file: UploadFile = File(...)):
    """Uploads a source image, returns the path to use in a job payload."""
    ext = os.path.splitext(file.filename)[1] or ".png"
    dest_name = f"{uuid.uuid4()}{ext}"
    dest_path = os.path.join(settings.upload_dir, dest_name)
    os.makedirs(settings.upload_dir, exist_ok=True)
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"path": dest_path}  
