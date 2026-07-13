import logging
import os
import uuid
from datetime import datetime,timedelta

from celery import Task
from PIL import Image, UnidentifiedImageError
from PIL import ImageDraw , ImageFont

from app.config import settings
from app.db import SessionLocal
from app.models.job import Job, JobStatus
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class PermanentJobError(Exception):
    """
        Raised for failures that retrying will never fix: 
        missing/corrupt input, invalid operation parameters,unsupported conversions,etc.
    """
    
class DatabaseTask(Task):
    """Base task that owns its own DB session per invocation."""

    def get_job(self, db, job_id):
        return db.query(Job).filter(Job.id == job_id).first()
    
        
def _mark_status(db, job: Job, status: JobStatus, result: dict | None = None):
    job.status = status
    if result is not None:
        job.result = result
    db.add(job)
    db.commit()
    db.refresh(job)
    return job
    
    
@celery_app.task(
    bind=True,
    base=DatabaseTask,
    name="process_image_job",
    autoretry_for=(OSError,),  
    max_retries=settings.max_jobs_attempts - 1, 
    retry_backoff=True,        
    retry_backoff_max=60,
    retry_jitter=True,
)
def process_image_job(self, job_id: str):
    """
        Processes an image_job: applies requested operations (resize,convert,watermark)
        to an uploaded image.
    """
    db = SessionLocal()
    
    try:
        job = self.get_job(db,job_id)
        if job is None:
            logger.error("Job %s not found,skipping", job_id)
            return      
            
        job.attempts += 1
        _mark_status(db, job, JobStatus.processing)
        
        payload = job.payload
        source_path = payload.get("source_path")
        operations = payload.get("operations",[])
        
        if not source_path or not os.path.exists(source_path):
            raise PermanentJobError("Source file not found: %s")
            
        try:
            image = Image.open(source_path)
            image.load()
        except UnidentifiedImageError:
            raise PermanentJobError("Unsupported or corrupt image file")
            
            
        try:
            for op in operations:
                image = _apply_operation(image, op)
        except PermanentJobError:
            raise
        except Exception as exc:
            raise PermanentJobError("Invalid operation:%s",exc)

        output_filename = f"{uuid.uuid4()}.png"
        output_path = os.path.join(settings.upload_dir, "processed", output_filename)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        image.save(output_path)
        
        _mark_status(
            db,
            job,
            JobStatus.succeeded,
            {"output_path":output_path,
            "operations_applied":operations}
        )
    
    except PermanentJobError as exc:
        if job:
            _mark_status(db, job, JobStatus.failed, {"error": str(exc)})
        logger.warning("Job %s failed permanently: %s", job_id, exc)
        return job.to_dict() if job else None
            
    except OSError as exc:
        is_final_attempt = self.request.retries >= self.max_retries
        if job:
            status = JobStatus.failed if is_final_attempt else JobStatus.retrying
            _mark_status(db, job, status, {"error": str(exc), "attempts": job.attempts})
        logger.exception(
            "Job %s failed on attempt %s/%s%s",
            job_id,
            self.request.retries + 1,
            self.max_retries + 1,
            " (final attempt)" if is_final_attempt else " (will retry)",
        )
        raise 
    except Exception as exc:  # noqa: BLE001 - genuinely unexpected: treat as permanent
        if job:
            _mark_status(db, job, JobStatus.failed, {"error": str(exc)})
        logger.exception("Job %s failed on unexpected error", job_id)
        raise
    finally:
        db.close()        
        

def _apply_operation(image: Image.Image, operation: dict) -> Image.Image:
    op_type = operation.get("op")
    if op_type == "resize":
        width = operation.get("width", image.width)
        height = operation.get("height", image.height)
        return image.resize((width, height))
    if op_type == "convert":
        fmt = operation.get("format", "RGB")
        return image.convert(fmt)
    if op_type == "watermark":
        drawing = ImageDraw.Draw(image)
        font = ImageFont.truetype("RobotoBlack.ttf", 68)
        text = " watermark  ©   "
        text_w, text_h = drawing.textsize(text, font)
        pos = w - text_w, (h - text_h) - 50
            
        c_text = Image.new('RGB', (text_w, (text_h)), color = '#000000')
        drawing = ImageDraw.Draw(c_text)
        
        drawing.text((0,0), text, fill="#ffffff", font=font)
        c_text.putalpha(100)
           
        image.paste(c_text, pos, c_text)
        return image
    logger.warning("Unknown operation %s, skipping", op_type)
    return image
