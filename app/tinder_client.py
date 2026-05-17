import httpx
from bs4 import BeautifulSoup
import re
import json
from app.config import settings

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
                
                # Primary attempt: Parse raw JSON state injected by Tinder in script tags
                user_obj = None
                try:
                    script_tags = soup.find_all("script")
                    for s in script_tags:
                        if s.string and '"_id":"' in s.string:
                            start_idx = s.string.find('{')
                            end_idx = s.string.rfind('}')
                            if start_idx != -1 and end_idx != -1:
                                json_data = json.loads(s.string[start_idx:end_idx+1])
                                
                                def find_user_dict(d):
                                    if isinstance(d, dict):
                                        if "user" in d and isinstance(d["user"], dict) and "_id" in d["user"]:
                                            return d["user"]
                                        for k, v in d.items():
                                            res = find_user_dict(v)
                                            if res is not None:
                                                return res
                                    elif isinstance(d, list):
                                        for item in d:
                                            res = find_user_dict(item)
                                            if res is not None:
                                                return res
                                    return None
                                
                                user_obj = find_user_dict(json_data)
                                if user_obj:
                                    break
                except Exception:
                    pass
                
                # Extract meta fallback data
                og_title = soup.find("meta", property="og:title")
                og_desc = soup.find("meta", property="og:description")
                og_image = soup.find("meta", property="og:image")
                
                title = og_title["content"] if og_title else ""
                title_clean = re.sub(r'\s*\(@[a-zA-Z0-9_]+\)\s*\|\s*Tinder', '', title).strip()
                title_clean = title_clean.replace(" - Tinder", "").replace(" | Tinder", "").strip()
                desc = og_desc["content"] if og_desc else ""
                image = og_image["content"] if og_image else ""
                
                # Map extracted JSON or fallbacks
                if user_obj:
                    name = user_obj.get("name") or title_clean
                    birth_date_full = user_obj.get("birth_date") or ""
                    
                    # Calculate Age
                    birth_date = "Hidden"
                    age = "Unknown"
                    if birth_date_full:
                        try:
                            import datetime
                            birth_date = birth_date_full.split('T')[0]
                            dob = datetime.datetime.strptime(birth_date, "%Y-%m-%d")
                            today = datetime.datetime.today()
                            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                        except Exception:
                            pass
                            
                    account_id = user_obj.get("_id")
                    
                    # Process photos
                    photos_list = user_obj.get("photos", [])
                    photos_count = len(photos_list)
                    image_url = image
                    if photos_list:
                        # Grab highest resolution of primary photo
                        primary_files = photos_list[0].get("processedFiles", [])
                        if primary_files:
                            sorted_files = sorted(primary_files, key=lambda x: x.get("width", 0), reverse=True)
                            image_url = sorted_files[0].get("url")
                            
                    # Jobs and Schools
                    jobs_list = []
                    for j in user_obj.get("jobs", []):
                        job_title = j.get("title", {}).get("name")
                        job_company = j.get("company", {}).get("name")
                        if job_title and job_company:
                            jobs_list.append(f"{job_title} at {job_company}")
                        elif job_title:
                            jobs_list.append(job_title)
                    jobs = ", ".join(jobs_list) if jobs_list else "Not Specified"
                    
                    schools = ", ".join([s.get("name") for s in user_obj.get("schools", []) if s.get("name")]) or "Not Specified"
                    
                    # Verification check
                    badges = user_obj.get("badges", [])
                    verified = False
                    for b in badges:
                        if b.get("type") == "verified" or "verified" in str(b).lower():
                            verified = True
                else:
                    # Fallback Mode
                    if title_clean == "Tinder" or "Dating, Make Friends" in title or "Looking for someone?" in response.text:
                        return {"status": "not_found"}
                        
                    name = title_clean
                    desc = desc
                    birth_date = "Hidden"
                    age = "Unknown"
                    dob_match = re.search(r'"birth_date":"([^"]+)"', response.text)
                    if dob_match:
                        try:
                            import datetime
                            birth_date_full = dob_match.group(1)
                            birth_date = birth_date_full.split('T')[0]
                            dob = datetime.datetime.strptime(birth_date, "%Y-%m-%d")
                            today = datetime.datetime.today()
                            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                        except Exception:
                            pass
                    
                    account_id = None
                    id_match = re.search(r'"_id":"([a-f0-9]{24})"', response.text)
                    if id_match:
                        account_id = id_match.group(1)
                        
                    photos_count = "1+"
                    image_url = image
                    jobs = "Not Specified"
                    schools = "Not Specified"
                    verified = False

                # Calculate Account Registration Age
                creation_date = "Hidden"
                account_age = "Unknown"
                if account_id:
                    try:
                        import datetime
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
                
                # Check shadowban status via robots meta tag
                is_restricted = False
                meta_robots = soup.find("meta", attrs={"name": "robots"})
                if meta_robots and "noindex" in meta_robots.get("content", "").lower():
                    is_restricted = True
                
                # Private API Lookup for accurate limitation/shadowban detection
                if settings.TINDER_AUTH_TOKEN and account_id:
                    try:
                        api_url = f"https://api.gotinder.com/user/{account_id}"
                        api_headers = {
                            "X-Auth-Token": settings.TINDER_AUTH_TOKEN,
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        }
                        async with httpx.AsyncClient(timeout=10) as client:
                            api_resp = await client.get(api_url, headers=api_headers)
                            if api_resp.status_code in [401, 403, 404]:
                                # Private API hides/denies the profile, but public page works -> Limited/Restricted!
                                is_restricted = True
                            elif api_resp.status_code == 200:
                                api_data = api_resp.json().get("results", {})
                                if api_data:
                                    name = api_data.get("name") or name
                                    desc = api_data.get("bio") or desc
                                    
                                    # Parse exact jobs
                                    jobs_list = []
                                    for j in api_data.get("jobs", []):
                                        job_title = j.get("title", {}).get("name")
                                        job_company = j.get("company", {}).get("name")
                                        if job_title and job_company:
                                            jobs_list.append(f"{job_title} at {job_company}")
                                        elif job_title:
                                            jobs_list.append(job_title)
                                    if jobs_list:
                                        jobs = ", ".join(jobs_list)
                                        
                                    # Parse exact schools
                                    schools = ", ".join([s.get("name") for s in api_data.get("schools", []) if s.get("name")]) or schools
                                    
                                    # Parse exact photos count
                                    photos_list = api_data.get("photos", [])
                                    if photos_list:
                                        photos_count = len(photos_list)
                                        
                                    # Verification
                                    if api_data.get("badges") or api_data.get("verified"):
                                        verified = True
                    except Exception:
                        pass
                
                return {
                    "status": "success",
                    "username": username,
                    "name": name,
                    "age": age,
                    "birth_date": birth_date,
                    "is_restricted": is_restricted,
                    "bio": desc or "No bio written.",
                    "image_url": image_url,
                    "account_id": account_id or "Hidden",
                    "account_age": account_age,
                    "creation_date": creation_date,
                    "photos_count": photos_count,
                    "verified": verified,
                    "jobs": jobs,
                    "schools": schools
                }
                
            except Exception as e:
                return {"status": "error", "message": str(e)}
