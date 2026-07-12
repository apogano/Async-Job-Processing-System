import enum, uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, Integer, String
from sqlalchemy.dialects.postgresql import JSONB,UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class JobStatus(str,enum.Enum):
    pending = "pending"
    processing = "processing"
    succeeded = "succeeded"
    failed = "failed"
    retrying = "retrying"
	
class Job(Base):
	__tablename__ = "jobs"
	
	id = Column (UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	type = Column(String,nullable=False)
	payload = Column(JSONB, nullable=False, default=dict)
	status = Column(Enum(JobStatus), nullable=False, default=JobStatus.pending)
	attempts = Column(Integer, nullable=False,default=0)
	max_attempts = Column(Integer, nullable=False, default=3)
	idempotency_key = Column(String, nullable=True, index=True, unique=True)
	result = Column(JSONB, nullable=True)
	created_at = Column(DateTime, default = datetime.utcnow)
	updated_at = Column(DateTime, default = datetime.utcnow, onupdate=datetime.utcnow)
	
	
	 
	
