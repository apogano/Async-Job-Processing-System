from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

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

def test_create_job_returns_202():
    response = client.post(
       "/jobs",
       json=job_correct_with_idempotency_key
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert "id" in body 
    
    
def test_create_job_without_idempotency_key_returns_202():
    response = client.post(
       "/jobs",
       json=job_correct_without_idempotency_key
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert "id" in body     


def test_create_or_get_job_with_idempotency_key_returns_202():
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
    
def test_create_or_get_job_with_idempotency_key_returns_202():
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
    

def test_invalid_type():
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
    
def test_missing_payload():
    response = client.post(
        "/jobs",
        json={
            "type": "image_resize",
            "payload": {},
        },
    )

    assert response.status_code == 422
    
def test_invalid_operation():
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
