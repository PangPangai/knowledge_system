import requests
import json
import sys

url = "http://localhost:8000/chat/agentic/stream"
data = {
    "question": "compile_fusion 分哪些步骤",
    "conversation_id": "test_conv_id"
}

print(f"Testing {url}...")
try:
    with requests.post(url, json=data, stream=True) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                print(f"Received: {decoded_line}")
                if decoded_line.startswith("data: "):
                    try:
                        json_content = json.loads(decoded_line[6:])
                        # Print a dot for content to show progress without spam
                        if json_content.get("type") == "content":
                            print(".", end="", flush=True)
                        else:
                            print(f"\n[Metadata] {json_content.keys()}")
                    except json.JSONDecodeError as e:
                        print(f"\n[ERROR] JSON Parse Failed: {e}")
                        print(f"Bad Line: {decoded_line}")
except Exception as e:
    print(f"Request failed: {e}")
