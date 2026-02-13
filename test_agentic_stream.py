import requests
import json
import os
import sys

# Configure environment to bypass proxies for local testing
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'

def test_agentic_stream():
    url = "http://127.0.0.1:8000/chat/agentic/stream"
    health_url = "http://127.0.0.1:8000/health"
    question = "FC中有哪些改善congestion的手段"
    
    print(f"🔍 [Check 1/2] Connecting to Backend Health: {health_url}")
    try:
        # Check health first
        h_resp = requests.get(health_url, timeout=5)
        if h_resp.status_code == 200:
            print("✅ Backend is UP and reachable.")
        else:
            print(f"❌ Backend reachable but returned status {h_resp.status_code}")
    except Exception as e:
        print(f"❌ Failed to connect to backend: {e}")
        print("💡 Suggestion: Verify uvicorn is running on port 8000 and not crashed.")
        return

    print(f"\n🔍 [Check 2/2] Testing Agentic Stream Endpoint: {url}")
    try:
        session = requests.Session()
        session.trust_env = False
        
        response = session.post(
            url, 
            json={"question": question}, 
            stream=True,
            timeout=60
        )
        
        if response.status_code != 200:
            print(f"❌ Endpoint returned API Error: {response.status_code}")
            print(f"📄 Response: {response.text}")
            return
            
        print("✅ Connection Established. Streaming response...")
        print("-" * 40)
        
        full_text = ""
        sources = []
        
        for line in response.iter_lines():
            if line:
                decoded = line.decode('utf-8')
                if decoded.startswith("data: "):
                    try:
                        data = json.loads(decoded[6:])
                        if data["type"] == "content":
                            print(data["content"], end="", flush=True)
                            full_text += data["content"]
                        elif data["type"] == "metadata":
                            sources = data.get("sources", [])
                            print(f"\n[Metadata received: {len(sources)} sources]")
                            for idx, s in enumerate(sources[:2]):
                                print(f"  - Source {idx+1}: {s.get('source')} (Section: {s.get('section')})")
                    except:
                        pass
                        
        print("\n" + "-" * 40)
        print(f"✅ Test Complete using Agentic Stream")
        print(f"📊 Response Length: {len(full_text)} chars")
        
        if len(full_text) > 500:
             print("🎉 Quality: Detailed response received.")
        else:
             print("⚠️ Quality: Response seems short.")
             
    except Exception as e:
        print(f"❌ Exception during streaming: {e}")

if __name__ == "__main__":
    test_agentic_stream()
