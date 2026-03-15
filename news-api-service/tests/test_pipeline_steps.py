import requests
import json

API_BASE = "http://localhost:8001/api/v2/pipeline"

def test_pipeline():
    print("=== Step 1: Create Task ===")
    resp = requests.post(f"{API_BASE}/task/create", json={
        "target_type": "主题",
        "keyword": "今天a股怎么跳水了",
        "time_range": "近7天",
        "analysis_depth": "标准版"
    })
    result = resp.json()
    print(f"Status: {resp.status_code}")
    print(f"task_id: {result.get('task_id')}")
    task_id = result.get('task_id')
    
    print("\n=== Step 2: Keyword Analysis ===")
    resp = requests.post(f"{API_BASE}/step/keyword-analysis", json={
        "task_id": task_id,
        "keyword": "今天a股怎么跳水了"
    })
    result = resp.json()
    print(f"Status: {resp.status_code}")
    print(f"Success: {result.get('success')}")
    print(f"Output: {json.dumps(result.get('output', {}), ensure_ascii=False, indent=2)}")
    
    print("\n=== Step 3: News Retrieval ===")
    resp = requests.post(f"{API_BASE}/step/news-retrieval", json={
        "task_id": task_id,
        "step_name": "news_retrieval",
        "input_data": {}
    })
    result = resp.json()
    print(f"Status: {resp.status_code}")
    print(f"Success: {result.get('success')}")
    print(f"News count: {result.get('news_count')}")
    output = result.get('output', {})
    print(f"Execution log: {json.dumps(output.get('execution_log', {}), ensure_ascii=False, indent=2)}")
    print(f"Quality report: {json.dumps(output.get('data_quality_report', {}), ensure_ascii=False, indent=2)}")

if __name__ == "__main__":
    test_pipeline()
