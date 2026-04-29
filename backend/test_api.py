"""Quick API connectivity test"""
import asyncio
from openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage

API_KEY = "sk-Wj2pcmIx04XplCNB8J9sBtBu7hP0mMmLQjaZ08WXKdPdKWoG"
BASE_URL = "https://once.novai.su/v1"

def test_openai_sdk():
    """Test 1: OpenAI SDK direct call"""
    print("=" * 50)
    print("[Test 1] OpenAI SDK - chat completions")
    try:
        client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
        resp = client.chat.completions.create(
            model="nano-banana",
            messages=[{"role": "user", "content": "Say hi in one word"}],
            stream=False,
        )
        print(f"  OK: {resp.choices[0].message.content}")
    except Exception as e:
        print(f"  FAIL: {e}")

def test_langchain():
    """Test 2: LangChain ChatOpenAI"""
    print("=" * 50)
    print("[Test 2] LangChain ChatOpenAI")
    try:
        llm = ChatOpenAI(
            api_key=API_KEY,
            base_url=BASE_URL,
            model="nano-banana",
            temperature=0.7,
        )
        resp = asyncio.run(llm.ainvoke([HumanMessage(content="Say hi in one word")]))
        print(f"  OK: {resp.content}")
    except Exception as e:
        print(f"  FAIL: {e}")

def test_image_gen():
    """Test 3: Image generation endpoint"""
    print("=" * 50)
    print("[Test 3] Image generation /images/generations")
    import httpx
    url = f"{BASE_URL}/images/generations"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    body = {"model": "gpt-image-2", "prompt": "a red apple on white background", "n": 1, "size": "1024x1024"}
    try:
        resp = httpx.post(url, json=body, headers=headers, timeout=60)
        print(f"  Status: {resp.status_code}")
        print(f"  Response: {resp.text[:300]}")
    except Exception as e:
        print(f"  FAIL: {e}")

if __name__ == "__main__":
    test_openai_sdk()
    test_langchain()
    test_image_gen()
