from uuid import UUID
from datetime import datetime
from typing import Any, Optional, Literal
from pydantic import BaseModel, Field

class ImageOperations(BaseModel):
	op: Literal["resize","convert","watermark"]
	width: Optional[int] = Field(default=None, gt=0)
	height: Optional[int] = Field(default=None, gt=0)
	format: Optional[str] = None
	
class ImageJobPayload(BaseModel):
	source_path: str
	operations: list[ImageOperations] = Field(default_factory=list)
	
	
class JobCreate(BaseModel):
	type: Literal["image_resize"] = Field(examples=["image_resize"]) 
	payload: ImageJobPayload
	idempotency_key: Optional[str] = None
	
class JobResponse(BaseModel):
    id: UUID
    type: str
    payload: ImageJobPayload
    status: str
    attempts: int
    max_attempts: int
    result: Optional[dict[str, Any]] = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
