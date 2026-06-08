
import httpx
import hashlib
import datetime

# Test with a sample username
username = "john"  # Replace with a real Tinder username to test
t = int(datetime.datetime.now().timestamp() * 1000)
sign_str = f"asd94{username}{t}"
sign = hashlib.md5(sign_str.encode()).hexdigest()

api_url = f"https://tinder6.com/getUser.php?user={username}&t={t}&sign={sign}"

print(f"Calling API: {api_url}\n")

try:
    response = httpx.get(api_url, timeout=30)
    print(f"Status Code: {response.status_code}")
    print(f"Full Response:")
    data = response.json()
    import json
    print(json.dumps(data, indent=4))
    print(f"\nAll keys in response: {list(data.keys())}")
except Exception as e:
    print(f"Error: {e}")
