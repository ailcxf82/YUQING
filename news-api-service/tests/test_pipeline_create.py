import requests
import json

API_BASE = "http://localhost:8001/api/v2/pipeline"

def test_create_task():
    url = f"{API_BASE}/task/create"
    payload = {
        "target_type": "主题",
        "keyword": "今天a股怎么跳水了",
        "time_range": "近7天",
        "analysis_depth": "标准版"
    }
    
    print(f"Testing: POST {url}")
    print(f"Payload: {json.dumps(payload, ensure_ascii=False)}")
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")
        return response.json()
    except requests.exceptions.ConnectionError:
        print("ERROR: Cannot connect to server. Is the service running?")
        return None
    except Exception as e:
        print(f"ERROR: {e}")
        return None

if __name__ == "__main__":
    test_create_task()
