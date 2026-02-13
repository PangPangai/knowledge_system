import requests
import json

question = "FC中有哪些改善congestion的手段"

print("=" * 60)
print("RAG质量对比测试")
print("=" * 60)
print(f"\n测试问题：{question}\n")

# Test Traditional RAG
print("\n" + "=" * 60)
print("1. 传统 RAG (/chat/stream)")
print("=" * 60)
try:
    r = requests.post('http://localhost:8000/chat/stream', 
                     json={'question': question},
                     timeout=30,
                     stream=True)
    
    if r.status_code == 200:
        # Parse SSE stream
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
        
        print(f"\n✅ 状态：成功")
        print(f"📏 回答长度：{len(content)} 字符")
        print(f"📚 参考来源数：{len(sources)}")
        print(f"\n💬 回答内容：\n{content[:500]}...")
        if sources:
            print(f"\n📖 来源：")
            for i, src in enumerate(sources[:3], 1):
                print(f"   {i}. {src.get('source', 'Unknown')}")
    else:
        print(f"❌ 错误：HTTP {r.status_code}")
except Exception as e:
    print(f"❌ 失败：{e}")

# Test Agentic RAG
print("\n" + "=" * 60)
print("2. Agentic RAG (/chat/agentic)")
print("=" * 60)
try:
    r = requests.post('http://localhost:8000/chat/agentic', 
                     json={'question': question},
                     timeout=30)
    
    if r.status_code == 200:
        data = r.json()
        answer = data.get('answer', '')
        sources = data.get('sources', [])
        
        print(f"\n✅ 状态：成功")
        print(f"📏 回答长度：{len(answer)} 字符")
        print(f"📚 参考来源数：{len(sources)}")
        print(f"\n💬 回答内容：\n{answer[:500]}...")
        if sources:
            print(f"\n📖 来源：")
            for i, src in enumerate(sources[:3], 1):
                print(f"   {i}. {src.get('source', 'Unknown')}")
    else:
        print(f"❌ 错误：HTTP {r.status_code}")
        print(f"详情：{r.text}")
except Exception as e:
    print(f"❌ 失败：{e}")

print("\n" + "=" * 60)
print("对比总结")
print("=" * 60)
