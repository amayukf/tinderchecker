import httpx
import hashlib
import re
import datetime
from bs4 import BeautifulSoup

class TinderClient:
    def __init__(self):
        self.fallback_apis = [
            "https://shieracc.com/getUser.php",
            "https://tinder6.com/getUser.php",
            "https://th666.co/getUser.php"
        ]
        self.base_url = "https://tinder.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://shieracc.com/"
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

    def calculate_risk_score(self, data: dict) -> dict:
        """Calculates OSINT Authenticity & Risk Analysis score for a profile."""
        if data.get("status") == "not_found" or data.get("is_restricted"):
            if data.get("is_restricted"):
                return {
                    "level": "🔴 High Risk",
                    "label": "Shadowbanned / Restricted",
                    "badge": "🔴 SHADOWBANNED",
                    "score": 25,
                    "reasons": ["Marked as limited/restricted by Tinder algorithms", "Match visibility severely degraded"]
                }
            return {
                "level": "💣 Critical Risk",
                "label": "Banned / Terminated",
                "badge": "❌ INACTIVE",
                "score": 0,
                "reasons": ["Username does not exist or account deleted"]
            }
        
        score = 100
        reasons = []
        
        photos_count = data.get("photos_count", 0)
        if isinstance(photos_count, str):
            try:
                photos_count = int(photos_count.replace("+", ""))
            except Exception:
                photos_count = 1
        
        if not data.get("verified"):
            score -= 15
            reasons.append("Account lacks ID/Selfie verification badge")
        
        if photos_count <= 1:
            score -= 20
            reasons.append("Only 1 photo uploaded (catfish probability elevated)")
        
        account_age = data.get("account_age", "")
        if "d" in str(account_age) and "y" not in str(account_age) and "m" not in str(account_age):
            days_match = re.search(r'(\d+)', str(account_age))
            if days_match and int(days_match.group(1)) < 14:
                score -= 25
                reasons.append("Newly registered account (< 14 days old)")
        
        if score >= 85:
            level = "🟢 Low Risk"
            label = "Authentic / Verified Patterns"
            badge = "🟢 LOW RISK"
        elif score >= 60:
            level = "🟡 Moderate Risk"
            label = "Unverified / Standard Profile"
            badge = "🟡 MODERATE RISK"
        else:
            level = "🟠 Elevated Risk"
            label = "Suspicious Profile Activity"
            badge = "🟠 ELEVATED RISK"
            
        return {
            "level": level,
            "label": label,
            "badge": badge,
            "score": max(0, score),
            "reasons": reasons if reasons else ["High verification signals", "Established account activity history"]
        }

    async def get_profile_data(self, username: str) -> dict:
        """High Availability Multi-API Failover Engine: shieracc -> tinder6 -> th666 -> public scraper."""
        t = int(datetime.datetime.now().timestamp() * 1000)
        sign_str = f"asd94{username}{t}"
        sign = hashlib.md5(sign_str.encode()).hexdigest()
        
        for api_url in self.fallback_apis:
            try:
                async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
                    response = await client.get(
                        api_url,
                        params={"user": username, "t": t, "sign": sign},
                        headers=self.headers
                    )
                    if response.status_code == 200:
                        data = response.json()
                        if isinstance(data, dict):
                            alive = data.get("alive", False)
                            account_ok = data.get("accountOk", False)
                            
                            if data.get("birthDate") or data.get("name") or data.get("photos"):
                                name = data.get("name") or "Hidden"
                                birth_date_val = data.get("birthDate") or "Hidden"
                                age = "Unknown"
                                
                                if data.get("age"):
                                    age = str(data.get("age"))
                                elif birth_date_val and birth_date_val != "Hidden":
                                    try:
                                        bd_str = birth_date_val.split("T")[0]
                                        dob = datetime.datetime.strptime(bd_str, "%Y-%m-%d")
                                        today = datetime.datetime.today()
                                        age = str(today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day)))
                                    except Exception:
                                        pass
                                
                                photos_list = data.get("photos", [])
                                photos_count = len(photos_list)
                                image_url = photos_list[0] if photos_list else ""
                                
                                # Extract Mongo Account ID from photo CDN link for high precision timestamp
                                account_id = None
                                creation_date = "Not available"
                                account_age = "Not available"
                                
                                if photos_list:
                                    id_match = re.search(r'gotinder\.com/([a-f0-9]{24})/', photos_list[0])
                                    if id_match:
                                        account_id = id_match.group(1)
                                
                                reg_date = data.get("regtime")
                                reg_dt = None
                                if reg_date:
                                    try:
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
                                    except Exception:
                                        pass
                                
                                # Fallback timestamp from Mongo ObjectId if regtime missing
                                if not reg_dt and account_id:
                                    try:
                                        timestamp = int(account_id[:8], 16)
                                        reg_dt = datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc)
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
                                
                                is_restricted = False
                                if alive and not account_ok:
                                    is_restricted = True
                                
                                verified = data.get("verified", False)
                                domain_name = api_url.split("//")[-1].split("/")[0]
                                
                                res_dict = {
                                    "status": "success",
                                    "username": username,
                                    "name": name,
                                    "age": age,
                                    "birth_date": birth_date_val,
                                    "is_restricted": is_restricted,
                                    "image_url": image_url,
                                    "account_id": account_id or "Hidden",
                                    "account_age": account_age,
                                    "creation_date": creation_date,
                                    "photos_count": photos_count,
                                    "all_photos": photos_list,
                                    "verified": verified,
                                    "token_status": f"api ({domain_name})"
                                }
                                res_dict["risk_analysis"] = self.calculate_risk_score(res_dict)
                                return res_dict
                            elif not alive or not account_ok:
                                domain_name = api_url.split("//")[-1].split("/")[0]
                                res_dict = {
                                    "status": "not_found",
                                    "username": username,
                                    "is_restricted": True,
                                    "token_status": f"api ({domain_name})"
                                }
                                res_dict["risk_analysis"] = self.calculate_risk_score(res_dict)
                                return res_dict
            except Exception:
                continue
        
        # Fallback to scraping public Tinder profile
        res_dict = await self._scrape_public_profile(username)
        if isinstance(res_dict, dict):
            res_dict["risk_analysis"] = self.calculate_risk_score(res_dict)
        return res_dict
    
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
                    "bio": desc or "No bio provided",
                    "is_restricted": is_restricted,
                    "image_url": image,
                    "all_photos": [image] if image else [],
                    "account_id": account_id or "Hidden",
                    "account_age": account_age,
                    "creation_date": creation_date,
                    "photos_count": "1+",
                    "verified": False,
                    "token_status": "scraping (public)"
                }

        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def ping_endpoints(self) -> dict:
        """Health check for all upstream API endpoints for Admin telemetry."""
        results = {}
        t = int(datetime.datetime.now().timestamp() * 1000)
        sign = hashlib.md5(f"asd94test{t}".encode()).hexdigest()
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            for api_url in self.fallback_apis:
                domain = api_url.split("//")[-1].split("/")[0]
                try:
                    start = datetime.datetime.now()
                    res = await client.get(api_url, params={"user": "test", "t": t, "sign": sign}, headers=self.headers)
                    latency = int((datetime.datetime.now() - start).total_seconds() * 1000)
                    if res.status_code == 200:
                        results[domain] = f"🟢 Online ({latency}ms)"
                    else:
                        results[domain] = f"🟡 HTTP {res.status_code}"
                except Exception:
                    results[domain] = "🔴 Offline"
        return results
