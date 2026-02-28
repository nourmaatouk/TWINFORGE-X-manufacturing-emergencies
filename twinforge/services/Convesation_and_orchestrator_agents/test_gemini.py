import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}"
}
body = {
    "model": "gemini-2.5-flash",
    "messages": [{"role": "user", "content": "Hello, are you working?"}]
}

try:
    print("Sending request to Gemini via OpenAI endpoint...")
    resp = requests.post(url, headers=headers, json=body, timeout=10)
    print(f"Status Code: {resp.status_code}")
    if resp.status_code == 200:
        print("Response:", resp.json()["choices"][0]["message"]["content"])
    else:
        print("Error Payload:", resp.text)
except Exception as e:
    print("Exception:", e)
