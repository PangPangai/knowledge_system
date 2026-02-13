import requests
import json

question = "FC中有哪些改善congestion的手段"

print("=" * 60)
print("RAG System Test")
print("=" * 60)

# Test 1: Traditional RAG
print("\n1. Testing Traditional RAG (/chat/stream)...")
try:
    r = requests.post('http://localhost:8000/chat/stream', 
                     json={'question': question},
                     timeout=60,
                     stream=True)
    
    if r.status_code == 200:
        content = ""
        sources = []
        for line in r.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    try:
                        data = json.loads(line[6:])
                        if data.get('type') == 'content':
                            content += data.get('content', '')
                        elif data.get('type') == 'metadata':
                            sources = data.get('sources', [])
                    except:
                        pass
        
        print(f"   ✅ Status: SUCCESS")
        print(f"   📏 Response length: {len(content)} chars")
        print(f"   📚 Sources: {len(sources)}")
    else:
        print(f"   ❌ Error: HTTP {r.status_code}")
except Exception as e:
    print(f"   ❌ Failed: {e}")

# Test 2: Agentic RAG
print("\n2. Testing Agentic RAG (/chat/agentic)...")
try:
    r = requests.post('http://localhost:8000/chat/agentic', 
                     json={'question': question},
                     timeout=60)
    
    if r.status_code == 200:
        data = r.json()
        answer = data.get('answer', '')
        sources = data.get('sources', [])
        
        print(f"   ✅ Status: SUCCESS")
        print(f"   📏 Response length: {len(answer)} chars")
        print(f"   📚 Sources: {len(sources)}")
    else:
        print(f"   ❌ Error: HTTP {r.status_code}")
        print(f"   Details: {r.text[:200]}")
except Exception as e:
    print(f"   ❌ Failed: {e}")

# Test 3: Frontend
print("\n3. Testing Frontend (http://localhost:3000)...")
try:
    r = requests.get('http://localhost:3000', timeout=5)
    print(f"   ✅ Status: HTTP {r.status_code}")
except Exception as e:
    print(f"   ❌ Failed: {e}")

print("\n" + "=" * 60)
print("Test Complete")
print("=" * 60)
