import requests
from bs4 import BeautifulSoup
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class PortalLoginClient:
    def __init__(self, base_url: str = "https://portal.aau.edu.et"):
        self.base_url = base_url
        self.session = requests.Session()
        # 🧪 match test.py behavior: standard User-Agent, no extra headers
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        })
        self.timeout = 60 # Stay at 60 for Render latency

    def login(self, username: str, password: str) -> Tuple[str, Optional[str]]:
        """
        Attempts to login to the AAU portal.
        Returns (status, grade_report_html)
        Statuses: "SUCCESS", "BAD_CREDENTIALS", "PORTAL_DOWN"
        """
        try:
            # 1. Get login page to extract CSRF token
            login_url = f"{self.base_url}/login"
            response = self.session.get(login_url, timeout=self.timeout)
            
            if response.status_code != 200 or "Server is not available" in response.text:
                return "PORTAL_DOWN", None

            soup = BeautifulSoup(response.text, "html.parser")
            token_element = soup.find("input", {"name": "__RequestVerificationToken"})
            if not token_element:
                return "PORTAL_DOWN", None
            
            token = token_element["value"]
            
            # 2. Post login data
            payload = {
                "__RequestVerificationToken": token,
                "UserName": username,
                "Password": password
            }
            
            # Match test.py: Direct post followed by verify
            self.session.post(login_url, data=payload, timeout=self.timeout)
            
            # 3. Verify success and get HTML in one go (Efficiency!)
            report_url = f"{self.base_url}/Grade/GradeReport"
            response = self.session.get(report_url, timeout=self.timeout)
            
            if "login" in response.url.lower() or "login" in response.text.lower()[0:2000]:
                logger.warning(f"Login failed for user {username}")
                return "BAD_CREDENTIALS", None
            
            return "SUCCESS", response.text
        except Exception as e:
            logger.error(f"Error during portal interaction for {username}: {e}")
            return "PORTAL_DOWN", None

    def get_grade_report_html(self) -> Optional[str]:
        """Manual fetch if already logged in"""
        try:
            response = self.session.get(f"{self.base_url}/Grade/GradeReport", timeout=self.timeout)
            if response.status_code == 200 and "login" not in response.url.lower():
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
        if self.session:
            self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
