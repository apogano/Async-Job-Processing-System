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
	payload: dict[ImageJobPayload] = Field(default_factory=dict)	
	idempotency_key: Optional[str] = None
	
class JobResponse(BaseModel):
    id: str
    type: str
    payload: dict[str, Any]
    status: str
    attempts: int
    max_attempts: int
    result: Optional[dict[str, Any]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
