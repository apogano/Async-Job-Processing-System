import os
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from PIL import Image

from app.main import app
from app.db import get_db
from app.config import settings
from app.models.job import Job, JobStatus
from app.models.job import Base

from app.workers.tasks import _apply_operation, _mark_status
from app.workers.tasks import process_image_job

TEST_DATABASE_URL = settings.database_url+"_test"

engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    
TestingSessionLocal = sessionmaker(bind=engine)

@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()
   # Base.metadata.drop_all(bind=engine)



def test_resize():
    image = Image.new("RGB", (100, 100))

    result = _apply_operation(
        image,
        {
            "op": "resize",
            "width": 50,
            "height": 20,
        },
    )

    assert result.size == (50, 20)

def test_convert():
    image = Image.new("RGB", (100, 100))

    result = _apply_operation(
        image,
        {
            "op": "convert",
            "format": "L",
        },
    )

    assert result.mode == "L"    

def test_unknown_operation_returns_original():
    image = Image.new("RGB", (100, 100))

    result = _apply_operation(image, {"op": "does_not_exist"})

    assert result is image    


def test_mark_status(db):
    job = Job(
        type="image_resize",
        status=JobStatus.pending,
        payload={}
    )
    db.add(job)
    db.commit()
    _mark_status(db, job, JobStatus.processing)
    db.refresh(job)
    assert job.status == JobStatus.processing


from unittest.mock import patch

@patch("app.workers.tasks.SessionLocal")
def test_process_image_job_success(mock_session, db, tmp_path):
    # Make the task use the test database session
    mock_session.return_value = db

    # Create input image
    input_image = settings.upload_dir + "/test_image.png"
    Image.new("RGB", (100, 100), color="red").save(input_image)

    # Store processed image inside pytest's temp directory
    with patch("app.workers.tasks.settings.upload_dir", 'processed/test_'+str(tmp_path)):

        job = Job(
            type="image_resize",
            status=JobStatus.pending,
            attempts=0,
            payload={
                "source_path": str(input_image),
                "operations": [
                    {
                        "op": "resize",
                        "width": 50,
                        "height": 50,
                    }
                ],
            },
        )

        db.add(job)
        db.commit()
        db.refresh(job)

        # Execute the Celery task synchronously
        process_image_job.run(str(job.id))
        db.close()

        new_db = TestingSessionLocal()

        updated_job = new_db.get(Job, job.id)
        assert updated_job.status == JobStatus.succeeded
        assert updated_job.attempts == 1

        assert updated_job.result is not None
        assert "output_path" in updated_job.result
        assert os.path.exists(updated_job.result["output_path"])

        # Verify image was actually resized
        output = Image.open(updated_job.result["output_path"])
        assert output.size == (50, 50)
