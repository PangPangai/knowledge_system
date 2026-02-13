import requests
import json

print("=== Testing Agentic RAG API ===")
try:
    r = requests.post('http://localhost:8000/chat/agentic', 
                     json={'question': 'FC中有哪些改善congestion的手段'},
                     timeout=30)
    print(f'Status: {r.status_code}')
    if r.status_code == 200:
        data = r.json()
        print(f'\nAnswer ({len(data.get("answer", ""))} chars):')
        print(data.get("answer", "No answer")[:300] + "...")
        print(f'\nSources: {len(data.get("sources", []))}')
    else:
        print(f'Error: {r.text}')
except Exception as e:
    print(f'Failed: {e}')
