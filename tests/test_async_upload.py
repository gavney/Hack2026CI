from fastapi.testclient import TestClient
from backend.main import app
import time

client = TestClient(app)

def test_async_upload():
    with open('data/statements/C001.csv', 'rb') as f:
        files = {'file': ('C001.csv', f, 'text/csv')}
        r = client.post('/api/companies/C001/upload-statement-async', files=files)
        assert r.status_code == 200
        resp = r.json()
        task_id = resp['task_id']
        assert task_id is not None

    # Poll until completed
    completed = False
    for i in range(60):
        time.sleep(0.15)
        p = client.get(f'/api/companies/C001/upload-progress/{task_id}')
        assert p.status_code == 200
        d = p.json()
        if d['status'] == 'completed':
            completed = True
            break
        elif d['status'] == 'error':
            raise AssertionError(f"Task failed: {d['error']}")

    assert completed, "Task did not complete in time"

if __name__ == '__main__':
    test_async_upload()
