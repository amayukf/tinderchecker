
import httpx
import datetime

# Test with a sample username
username = "john"  # Replace with a real Tinder username to test
api_url = "https://vvip.tinderfz.com/api.php"
params = {"username": username}

print(f"Calling API: {api_url} with params={params}\n")

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
