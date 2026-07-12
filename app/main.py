from fastapi import FastAPI

from app.config import settings
from app.db import init_db

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
