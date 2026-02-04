import requests
from bs4 import BeautifulSoup
from typing import Optional
import logging
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

class PortalLoginClient:
    def __init__(self, base_url: str = "https://portal.aau.edu.et"):
        self.base_url = base_url
        self.session = requests.Session()
        
        # 🛡️ Configure retries for unstable connections
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        # 🕵️ Emulate a real browser from Ethiopia
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,am;q=0.8", # English and Amharic
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Referer": f"{self.base_url}/login",
            "X-Forwarded-For": "196.188.0.1" # Mock Ethio Telecom IP
        })
        self.timeout = 60 # Increased from 30 to 60 due to persistent timeouts on Render

    def login(self, username: str, password: str) -> str:
        """
        Attempts to login to the AAU portal.
        Returns "SUCCESS", "BAD_CREDENTIALS", or "PORTAL_DOWN"
        """
        try:
            # 1. Get login page to extract CSRF token
            login_url = f"{self.base_url}/login"
            response = self.session.get(login_url, timeout=self.timeout)
            
            if response.status_code != 200 or "Server is not available" in response.text or "The service is unavailable." in response.text:
                return "PORTAL_DOWN"

            soup = BeautifulSoup(response.text, "html.parser")
            token_element = soup.find("input", {"name": "__RequestVerificationToken"})
            if not token_element:
                return "PORTAL_DOWN"
            
            token = token_element["value"]
            
            # 2. Post login data
            payload = {
                "__RequestVerificationToken": token,
                "UserName": username,
                "Password": password
            }
            
            # Need to set headers for the post specifically
            post_headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": self.base_url,
                "Referer": login_url
            }
            
            response = self.session.post(login_url, data=payload, headers=post_headers, timeout=self.timeout)
            
            # 3. Verify if login was successful
            # We check the GradeReport page to be absolutely sure
            test_url = f"{self.base_url}/Grade/GradeReport"
            test_response = self.session.get(test_url, timeout=self.timeout)
            
            if "login" in test_response.url.lower() or "login" in test_response.text.lower()[0:2000]:
                logger.warning(f"Login failed for user {username}")
                return "BAD_CREDENTIALS"
            
            return "SUCCESS"
        except (requests.RequestException, Exception) as e:
            logger.error(f"Error during login for {username}: {e}")
            return "PORTAL_DOWN"

    def get_grade_report_html(self) -> Optional[str]:
        try:
            response = self.session.get(f"{self.base_url}/Grade/GradeReport", timeout=self.timeout)
            if response.status_code == 200:
                return response.text
            return None
        except Exception as e:
            logger.error(f"Error fetching grade report: {e}")
            return None

    def get_assessment_detail_html(self, year_id: str, sem_id: str, course_id: str) -> Optional[str]:
        try:
            url = f"{self.base_url}/Grade/GradeReport/AssessmentDetail"
            params = {
                "academicYearId": year_id,
                "semesterId": sem_id,
                "courseId": course_id
            }
            response = self.session.get(url, params=params, timeout=self.timeout)
            if response.status_code == 200:
                return response.text
            return None
        except Exception as e:
            logger.error(f"Error fetching assessment detail: {e}")
            return None

    def close(self):
        """Close the session to prevent resource leaks"""
        if self.session:
            self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
