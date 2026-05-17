import httpx
from bs4 import BeautifulSoup
import re
import json

class TinderClient:
    def __init__(self):
        self.base_url = "https://tinder.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    @staticmethod
    def extract_username(input_text: str) -> str | None:
        """Extracts username from URL or direct username input."""
        input_text = input_text.strip()
        
        # Handle URLs
        url_pattern = r"(?:https?://)?(?:www\.)?tinder\.com/@([a-zA-Z0-9_]+)"
        match = re.search(url_pattern, input_text)
        if match:
            return match.group(1)
            
        # Handle direct username
        if re.match(r"^@?[a-zA-Z0-9_]+$", input_text):
            return input_text.lstrip("@")
            
        return None

    async def get_profile_data(self, username: str) -> dict:
        """
        Fetches publicly available metadata for a Tinder profile.
        Note: Many fields requested are NOT publicly available without authentication.
        """
        url = f"{self.base_url}/@{username}"
        
        async with httpx.AsyncClient(follow_redirects=True) as client:
            try:
                response = await client.get(url, headers=self.headers, timeout=10.0)
                if response.status_code == 404:
                    return {"status": "not_found"}
                elif response.status_code != 200:
                    return {"status": "error", "message": f"HTTP {response.status_code}"}
                    
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Fallback: Extract from OpenGraph tags
                og_title = soup.find("meta", property="og:title")
                og_desc = soup.find("meta", property="og:description")
                og_image = soup.find("meta", property="og:image")
                
                title = og_title["content"] if og_title else ""
                title = title.replace(" - Tinder", "").replace(" | Tinder", "").strip()
                desc = og_desc["content"] if og_desc else ""
                image = og_image["content"] if og_image else ""
                
                # Try to parse name and age from Title (e.g., "John, 25 - Tinder")
                name, age = None, None
                title_match = re.match(r"^([^,]+)(?:,\s*(\d+))?", title)
                if title_match:
                    name = title_match.group(1).strip()
                    if title_match.group(2):
                        age = title_match.group(2)
                        
                # Extract Account ID and Creation Date from internal _id
                # MongoDB ObjectIDs encode creation timestamp in first 4 bytes (8 hex chars)
                account_id = None
                creation_date = "Hidden"
                account_age = "Unknown"
                
                id_match = re.search(r'"_id":"([a-f0-9]{24})"', response.text)
                if id_match:
                    account_id = id_match.group(1)
                    try:
                        import datetime
                        timestamp = int(account_id[:8], 16)
                        dt = datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc)
                        creation_date = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                        
                        # Calculate age
                        delta = datetime.datetime.now(datetime.timezone.utc) - dt
                        years = delta.days // 365
                        months = (delta.days % 365) // 30
                        days = (delta.days % 365) % 30
                        if years > 0:
                            account_age = f"{years}y {months}m {days}d"
                        elif months > 0:
                            account_age = f"{months}m {days}d"
                        else:
                            account_age = f"{days}d"
                    except Exception:
                        pass
                
                return {
                    "status": "success",
                    "username": username,
                    "name": name,
                    "age": age,
                    "bio": desc,
                    "image_url": image,
                    "account_id": account_id or "Hidden",
                    "account_age": account_age,
                    "creation_date": creation_date,
                    # Below fields are practically impossible to get without auth/matching
                    "photos_count": "Unknown (Requires Auth)",
                    "verified": "Unknown (Requires Auth)",
                    "distance": "Hidden",
                    "last_active": "Hidden (Removed by Tinder)"
                }
                
            except Exception as e:
                return {"status": "error", "message": str(e)}
