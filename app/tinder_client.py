import httpx
import hashlib
import re
import datetime

class TinderClient:
    def __init__(self):
        self.base_api = "https://tinder6.com/getUser.php"

    @staticmethod
    def extract_username(input_text: str) -> str | None:
        """Extracts username from URL or direct username input."""
        input_text = input_text.strip()
        
        url_pattern = r"(?:https?://)?(?:www\.)?tinder\.com/@([a-zA-Z0-9_]+)"
        match = re.search(url_pattern, input_text)
        if match:
            return match.group(1)
            
        if re.match(r"^@?[a-zA-Z0-9_]+$", input_text):
            return input_text.lstrip("@")
            
        return None

    async def get_profile_data(self, username: str) -> dict:
        """Fetches Tinder profile data using tinder6.com API (100% accurate!)."""
        t = int(datetime.datetime.now().timestamp() * 1000)
        sign_str = f"asd94{username}{t}"
        sign = hashlib.md5(sign_str.encode()).hexdigest()
        
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
                response = await client.get(
                    self.base_api,
                    params={"user": username, "t": t, "sign": sign},
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    }
                )
                if response.status_code == 404:
                    return {"status": "not_found"}
                elif response.status_code != 200:
                    return {"status": "error", "message": f"HTTP {response.status_code}"}
                
                data = response.json()
                if not data or not data.get("birthDate"):
                    return {"status": "not_found"}
                
                alive = data.get("alive", False)
                account_ok = data.get("accountOk", False)
                
                name = data.get("name") or "Hidden"
                birth_date = data.get("birthDate") or "Hidden"
                age = "Unknown"
                
                if birth_date and birth_date != "Hidden":
                    try:
                        # First try to get age directly from API
                        if data.get("age"):
                            age = data.get("age")
                        else:
                            # Calculate from birthDate
                            if "T" in birth_date:
                                birth_date = birth_date.split("T")[0]
                            dob = datetime.datetime.strptime(birth_date, "%Y-%m-%d")
                            today = datetime.datetime.today()
                            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                    except Exception:
                        pass
                
                photos_list = data.get("photos", [])
                photos_count = len(photos_list)
                image_url = ""
                if photos_list:
                    image_url = photos_list[0]
                
                creation_date = "Hidden"
                account_age = "Unknown"
                reg_time = data.get("regtime") or data.get("createdAt") or data.get("created_at")
                
                if reg_time:
                    try:
                        # Try multiple date formats
                        dt = None
                        if isinstance(reg_time, int):
                            # If it's a timestamp (seconds)
                            dt = datetime.datetime.fromtimestamp(reg_time, datetime.timezone.utc)
                        elif isinstance(reg_time, float):
                            # If it's a timestamp (milliseconds)
                            dt = datetime.datetime.fromtimestamp(reg_time / 1000, datetime.timezone.utc)
                        else:
                            # Try ISO format
                            if reg_time.endswith('Z'):
                                reg_time = reg_time.replace('Z', '+00:00')
                            dt = datetime.datetime.fromisoformat(reg_time)
                        
                        if dt:
                            creation_date = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                            
                            now = datetime.datetime.now(datetime.timezone.utc)
                            delta = now - dt
                            
                            years = delta.days // 365
                            remaining_days = delta.days % 365
                            months = remaining_days // 30
                            days = remaining_days % 30
                            
                            age_parts = []
                            if years > 0:
                                age_parts.append(f"{years}y")
                            if months > 0:
                                age_parts.append(f"{months}m")
                            if days > 0:
                                age_parts.append(f"{days}d")
                            
                            if age_parts:
                                account_age = " ".join(age_parts)
                            else:
                                account_age = f"{delta.total_seconds() // 3600}h"
                                
                    except Exception as e:
                        # Fallback if parsing fails
                        account_age = "Unknown"
                        creation_date = str(reg_time)
                
                is_restricted = False
                if alive and not account_ok:
                    is_restricted = True
                
                verified = data.get("verified", False)
                
                return {
                    "status": "success",
                    "username": username,
                    "name": name,
                    "age": age,
                    "birth_date": birth_date,
                    "is_restricted": is_restricted,
                    "image_url": image_url,
                    "account_age": account_age,
                    "creation_date": creation_date,
                    "photos_count": photos_count,
                    "verified": verified,
                    "token_status": "api (tinder6.com)"
                }
                
        except Exception as e:
            return {"status": "error", "message": str(e)}
