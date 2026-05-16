import httpx
from bs4 import BeautifulSoup
import json
import asyncio
import re

async def main():
    url = "https://tinder.com/@fraol232"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        
        # Look for __NEXT_DATA__
        soup = BeautifulSoup(resp.text, 'html.parser')
        script = soup.find("script", id="__NEXT_DATA__")
        if script:
            data = json.loads(script.string)
            with open("dump.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print("Found __NEXT_DATA__")
        else:
            print("No __NEXT_DATA__")
            
        # Try to find Account ID in page source
        # MongoDB ObjectID is a 24-character hex string
        ids = re.findall(r'"_id":"([a-f0-9]{24})"', resp.text)
        if ids:
            print("Found IDs:", ids)

if __name__ == "__main__":
    asyncio.run(main())
