import httpx
import hashlib
import re
import datetime
from bs4 import BeautifulSoup

class TinderClient:
    def __init__(self):
        self.base_api = "https://tinder6.com/getUser.php"
        self.base_url = "https://tinder.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

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
        """First try tinder6.com API, if that fails fall back to scraping public Tinder page."""
        # First try tinder6.com API
        t = int(datetime.datetime.now().timestamp() * 1000)
        sign_str = f"asd94{username}{t}"
        sign = hashlib.md5(sign_str.encode()).hexdigest()
        
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
                response = await client.get(
                    self.base_api,
                    params={"user": username, "t": t, "sign": sign},
                    headers=self.headers
                )
                if response.status_code == 200:
                    data = response.json()
                    # Check if API returned meaningful data
                    if data and (data.get("birthDate") or data.get("name")):
                        alive = data.get("alive", False)
                        account_ok = data.get("accountOk", False)
                        
                        name = data.get("name") or "Hidden"
                        birth_date_val = data.get("birthDate") or "Hidden"
                        age = "Unknown"
                        
                        if birth_date_val and birth_date_val != "Hidden":
                            try:
                                if data.get("age"):
                                    age = data.get("age")
                                else:
                                    if "T" in birth_date_val:
                                        birth_date_val = birth_date_val.split("T")[0]
                                    dob = datetime.datetime.strptime(birth_date_val, "%Y-%m-%d")
                                    today = datetime.datetime.today()
                                    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                            except Exception:
                                pass
                        
                        photos_list = data.get("photos", [])
                        photos_count = len(photos_list)
                        image_url = ""
                        if photos_list:
                            image_url = photos_list[0]
                        
                        reg_date = data.get("regtime")
                        creation_date = "Not available"
                        account_age = "Not available"
                        
                        if reg_date:
                            creation_date = str(reg_date)
                            try:
                                reg_dt = None
                                reg_str = str(reg_date)
                                if reg_str.endswith('Z'):
                                    reg_str = reg_str.replace('Z', '+00:00')
                                try:
                                    reg_dt = datetime.datetime.fromisoformat(reg_str)
                                except Exception:
                                    pass
                                if not reg_dt:
                                    try:
                                        reg_str = str(reg_date).split('T')[0]
                                        reg_dt = datetime.datetime.strptime(reg_str, "%Y-%m-%d")
                                    except Exception:
                                        pass
                                if reg_dt:
                                    if reg_dt.tzinfo is None:
                                        reg_dt = reg_dt.replace(tzinfo=datetime.timezone.utc)
                                    creation_date = reg_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                                    today = datetime.datetime.now(datetime.timezone.utc)
                                    delta = today - reg_dt
                                    days = delta.days
                                    if days >= 365:
                                        years = days // 365
                                        remaining_days = days % 365
                                        months = remaining_days // 30
                                        account_age = f"{years}y {months}m {remaining_days % 30}d"
                                    elif days >= 30:
                                        months = days // 30
                                        remaining_days = days % 30
                                        account_age = f"{months}m {remaining_days}d"
                                    else:
                                        account_age = f"{days} days"
                            except Exception:
                                account_age = "Not available"
                        
                        is_restricted = False
                        if alive and not account_ok:
                            is_restricted = True
                        
                        verified = data.get("verified", False)
                        
                        return {
                            "status": "success",
                            "username": username,
                            "name": name,
                            "age": age,
                            "birth_date": birth_date_val,
                            "is_restricted": is_restricted,
                            "image_url": image_url,
                            "account_age": account_age,
                            "creation_date": creation_date,
                            "photos_count": photos_count,
                            "verified": verified,
                            "token_status": "api (tinder6.com)"
                        }
        except Exception:
            pass
        
        # Fallback to scraping public Tinder profile
        return await self._scrape_public_profile(username)
    
    async def _scrape_public_profile(self, username: str) -> dict:
        """Scrapes publicly available metadata from Tinder profile page."""
        url = f"{self.base_url}/@{username}"
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(url, headers=self.headers, timeout=10.0)
                if response.status_code == 404:
                    return {"status": "not_found"}
                elif response.status_code != 200:
                    return {"status": "error", "message": f"HTTP {response.status_code}"}

                soup = BeautifulSoup(response.text, 'html.parser')
                og_title = soup.find("meta", property="og:title")
                og_desc = soup.find("meta", property="og:description")
                og_image = soup.find("meta", property="og:image")

                title = og_title["content"] if og_title else ""
                desc = og_desc["content"] if og_desc else ""
                image = og_image["content"] if og_image else ""

                # Clean up title to remove Tinder branding
                title_clean = re.sub(r'\s*\(@[a-zA-Z0-9_]+\)\s*\|\s*Tinder', '', title).strip()
                title_clean = title_clean.replace(" - Tinder", "").replace(" | Tinder", "").strip()

                name, age = None, None
                title_match = re.match(r"^([^,]+)(?:,\s*(\d+))?", title_clean)        
                if title_match:
                    name = title_match.group(1).strip()
                    if title_match.group(2):
                        age = title_match.group(2)

                account_id = None
                creation_date = "Hidden"
                account_age = "Unknown"

                id_match = re.search(r'"_id":"([a-f0-9]{24})"', response.text)  
                if id_match:
                    account_id = id_match.group(1)
                    try:
                        timestamp = int(account_id[:8], 16)
                        dt = datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc)
                        creation_date = dt.strftime("%Y-%m-%d %H:%M:%S UTC")    

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

                is_restricted = False
                meta_robots = soup.find("meta", attrs={"name": "robots"})       
                if meta_robots and "noindex" in meta_robots.get("content", "").lower():
                    is_restricted = True

                return {
                    "status": "success",
                    "username": username,
                    "name": name or "Hidden",
                    "age": age or "Unknown",
                    "birth_date": "Hidden",
                    "is_restricted": is_restricted,
                    "image_url": image,
                    "account_id": account_id or "Hidden",
                    "account_age": account_age,
                    "creation_date": creation_date,
                    "photos_count": "1+",
                    "verified": False,
                    "token_status": "scraping (public)"
                }

        except Exception as e:
            return {"status": "error", "message": str(e)}
