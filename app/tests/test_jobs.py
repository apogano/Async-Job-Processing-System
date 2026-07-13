import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db import get_db
from app.config import settings
from app.models.job import Base

TEST_DATABASE_URL = settings.database_url+"_test"

engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)

@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    SQLModel.metadata.create_all(engine)
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(name="client")  
def client_fixture(session: Session):  
    def get_session_override():  
        return session
    app.dependency_overrides[get_db] = get_session_override  
    client = TestClient(app)  
    yield client  
    app.dependency_overrides.clear()  

job_correct_without_idempotency_key = {
    "type": "image_resize",
    "payload": {
        "source_path": "/tmp/images/input.jpg",
        "operations": [
            {
                "op": "resize",
                "width": 800,
                "height": 600
            },
            {
                "op": "convert",
                "format": "png"
            }
        ]
    }
}

job_correct_with_idempotency_key = {
    "type": "image_resize",
    "payload": {
        "source_path": "/tmp/images/input.jpg",
        "operations": [
            {
                "op": "resize",
                "width": 800,
                "height": 600
            },
            {
                "op": "convert",
                "format": "png"
            }
        ]
    },
    "idempotency_key": "test-job-001"
}

def test_create_job_returns_202(client: TestClient):
    response = client.post(
       "/jobs",
       json=job_correct_with_idempotency_key
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert "id" in body 
    
    
def test_create_job_without_idempotency_key_returns_202(client: TestClient):
    response = client.post(
       "/jobs",
       json=job_correct_without_idempotency_key
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert "id" in body     


def test_create_or_get_job_with_idempotency_key_returns_202(client: TestClient):
    response1 = client.post(
       "/jobs",
       json=job_correct_with_idempotency_key
    )
    response2 = client.post(
       "/jobs",
       json=job_correct_with_idempotency_key
    )   
    assert response1.status_code == 202
    assert response2.status_code == 202
    body1 = response1.json()
    body2= response2.json()  
    assert body1["id"] == body2["id"]
    
def test_create_or_get_job_with_idempotency_key_returns_202(client: TestClient):
    response1 = client.post(
       "/jobs",
       json=job_correct_with_idempotency_key
    )
    response2 = client.post(
       "/jobs",
       json=job_correct_with_idempotency_key
    )   
    assert response1.status_code == 202
    assert response2.status_code == 202
    body1 = response1.json()
    body2= response2.json()  
    assert body1["id"] == body2["id"]    
    

def test_invalid_type(client: TestClient):
    response = client.post(
        "/jobs",
        json={
            "type": "asdasdasdaxasx",
            "payload": {
            "source_path": "/tmp/images/input.jpg",
            "operations": [
                {
                    "op": "resize",
                    "width": 800,
                    "height": 600
                },
                {
                    "op": "convert",
                    "format": "png"
                }
            ]
        },
        "idempotency_key": "test-job-001"
        }
    )

    assert response.status_code == 422
    
def test_missing_payload(client: TestClient):
    response = client.post(
        "/jobs",
        json={
            "type": "image_resize",
            "payload": {},
        },
    )

    assert response.status_code == 422
    
def test_invalid_operation(client: TestClient):
    response = client.post(
        "/jobs",
        json={
            "type": "image_resize",
            "payload": {
                "source_path": "/tmp/a.jpg",
                "operations": [
                    {"op": "crop"}
                ],
            },
        },
    )

    assert response.status_code == 422 
    
def test_get_list_jobs(client: TestClient):
    response = client.get("/jobs")

    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)

def test_get_existing_job(client: TestClient):
    # Create a job
    create_response = client.post("/jobs", 
      json=job_correct_without_idempotency_key
    )
    job_id = create_response.json()["id"]

    # Retrieve it
    response = client.get(f"/jobs/{job_id}")

    assert response.status_code == 200

    data = response.json()
    assert data["id"] == job_id
    assert data["type"] == "image_resize"    

def test_post_retry_job(client: TestClient):
    # Create a job
    create_response = client.post(
        "/jobs", 
        json=job_correct_without_idempotency_key
    )
    job_id = create_response.json()["id"]

    # Retry it
    response = client.post(f"/jobs/{job_id}/retry")

    assert response.status_code == 400 
    assert response.json()["detail"] == "Only failed jobs can be retried"


def test_delete_job(client: TestClient):
    # Create a job
    create_response = client.post(
        "/jobs", 
        json=job_correct_without_idempotency_key
    )
    job_id = create_response.json()["id"]

    # Delete it
    response = client.delete(f"/jobs/{job_id}")

    assert response.status_code == 204
