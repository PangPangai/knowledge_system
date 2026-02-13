import requests
import json

question = "FC中有哪些改善congestion的手段"

print("=" * 60)
print("Agentic RAG 技术问题测试")
print("=" * 60)
print(f"问题：{question}\n")

try:
    r = requests.post('http://localhost:8000/chat/agentic', 
                     json={'question': question},
                     timeout=120)
    
    print(f"Status: {r.status_code}")
    
    if r.status_code == 200:
        data = r.json()
        answer = data.get('answer', '')
        sources = data.get('sources', [])
        
        print(f"Answer length: {len(answer)} chars")
        print(f"Sources: {len(sources)}")
        print("\n" + "=" * 60)
        print("回答内容：")
        print("=" * 60)
        print(answer)
        
        if sources:
            print("\n" + "=" * 60)
            print("参考来源：")
            print("=" * 60)
            for i, src in enumerate(sources, 1):
                print(f"{i}. {src.get('source', 'Unknown')}")
    else:
        print(f"Error: {r.text}")
except Exception as e:
    print(f"Failed: {e}")
