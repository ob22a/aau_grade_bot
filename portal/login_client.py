import requests
from bs4 import BeautifulSoup
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class PortalLoginClient:
    def __init__(self, base_url: str = "https://portal.aau.edu.et"):
        self.base_url = base_url
        self.session = requests.Session()

    def login(self, username: str, password: str) -> str:
        """
        Attempts to login to the AAU portal.
        Returns "SUCCESS", "BAD_CREDENTIALS", or "PORTAL_DOWN"
        """
        try:
            # 1. Get login page to extract CSRF token
            login_url = f"{self.base_url}/login"
            response = self.session.get(login_url, timeout=10)
            
            if response.status_code != 200 or "Server is not available" in response.text:
                return "PORTAL_DOWN"

            soup = BeautifulSoup(response.text, "html.parser")
            token_element = soup.find("input", {"name": "__RequestVerificationToken"})
            if not token_element:
                if "Server is not available" in response.text:
                    return "PORTAL_DOWN"
                return "PORTAL_DOWN"
            
            token = token_element["value"]
            
            # 2. Post login data
            payload = {
                "__RequestVerificationToken": token,
                "UserName": username,
                "Password": password
            }
            
            response = self.session.post(login_url, data=payload, timeout=10)
            
            # 3. Verify if login was successful
            test_response = self.session.get(f"{self.base_url}/Grade/GradeReport", timeout=10)
            
            if "login" in test_response.url.lower() or "login" in test_response.text.lower()[0:2000]:
                logger.warning(f"Login failed for user {username}")
                return "BAD_CREDENTIALS"
            
            return "SUCCESS"
        except (requests.RequestException, Exception) as e:
            logger.error(f"Error during login for {username}: {e}")
            return "PORTAL_DOWN"

    def get_grade_report_html(self) -> Optional[str]:
        try:
            response = self.session.get(f"{self.base_url}/Grade/GradeReport")
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
            response = self.session.get(url, params=params)
            if response.status_code == 200:
                return response.text
            return None
        except Exception as e:
            logger.error(f"Error fetching assessment detail: {e}")
            return None
