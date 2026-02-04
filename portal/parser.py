from bs4 import BeautifulSoup
import re
from typing import List, Dict, Any

class PortalParser:
    @staticmethod
    def parse_grade_report(html_content: str) -> Dict[str, Any]:
        """
        Parses the main grade report page to get a list of courses and their grades.
        Also extracts IDs for assessment details and semester summaries.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        table = soup.find("table", class_="table-bordered")
        if not table:
            return {"courses": [], "summaries": []}

        courses = []
        summaries = []
        current_year = ""
        current_semester = ""
        current_year_level = ""
        current_year_number = None

        rows = table.find_all("tr")
        for row in rows:
            classes = row.get("class", [])
            # Check for year/semester headers
            if "yrsm" in classes:
                text = row.get_text(strip=True)
                
                # Header row: Academic Year : 2025/26, Year III, Semester : One
                if "Academic Year" in text:
                    year_match = re.search(r"Academic Year\s*:\s*([^,]+)", text)
                    year_level_match = re.search(r",\s*(Year [^,]+)", text)
                    sem_match = re.search(r"Semester\s*:\s*([^,]+)", text)
                    
                    if year_match:
                        current_year = year_match.group(1).strip()
                        if year_level_match:
                            current_year += f", {year_level_match.group(1).strip()}"
                            current_year_level = year_level_match.group(1).strip()
                            
                            # Extract numeric year (I->1, II->2, III->3, IV->4, V->5)
                            year_num_match = re.search(r"Year\s+(I{1,3}|IV|V)", current_year_level)
                            if year_num_match:
                                roman = year_num_match.group(1)
                                roman_to_num = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5}
                                current_year_number = roman_to_num.get(roman)
                    
                    if sem_match:
                        current_semester = sem_match.group(1).strip()
                    continue
                
                # Summary row: SGP : 131.75 ... SGPA : 3.88
                if "SGPA" in text:
                    sgp = re.search(r"SGP\s*:\s*([\d.]+)", text)
                    sgpa = re.search(r"SGPA\s*:\s*([\d.]+)", text)
                    cgp = re.search(r"CGP\s*:\s*([\d.]+)", text)
                    cgpa = re.search(r"CGPA\s*:\s*([\d.]+)", text)
                    status = re.search(r"Academic Status\s*:\s*([^!]+)", text)
                    
                    summaries.append({
                        "academic_year": current_year,
                        "semester": current_semester,
                        "year_level": current_year_level,
                        "year_number": current_year_number,
                        "sgp": sgp.group(1) if sgp else "0",
                        "sgpa": sgpa.group(1) if sgpa else "0",
                        "cgp": cgp.group(1) if cgp else "0",
                        "cgpa": cgpa.group(1) if cgpa else "0",
                        "status": status.group(1).strip() if status else "N/A"
                    })
                continue

            # Check for course rows (they have 7 columns usually)
            cols = row.find_all("td")
            if len(cols) == 7 and cols[0].get_text(strip=True).isdigit():
                course_name = cols[1].get_text(strip=True)
                course_code = cols[2].get_text(strip=True)
                credit_hour = cols[3].get_text(strip=True)
                ects = cols[4].get_text(strip=True)
                grade = cols[5].get_text(strip=True)
                
                button = cols[6].find("button")
                assessment_ids = {}
                if button and button.has_attr("onclick"):
                    onclick = button["onclick"]
                    ids = re.findall(r"'([^']+)'", onclick)
                    if len(ids) == 3:
                        assessment_ids = {
                            "academicYearId": ids[0],
                            "semesterId": ids[1],
                            "courseId": ids[2]
                        }

                courses.append({
                    "academic_year": current_year,
                    "semester": current_semester,
                    "year_level": current_year_level,
                    "year_number": current_year_number,
                    "course_name": course_name,
                    "course_code": course_code,
                    "credit_hour": credit_hour,
                    "ects": ects,
                    "grade": grade,
                    "assessment_ids": assessment_ids
                })

        return {"courses": courses, "summaries": summaries}

    @staticmethod
    def parse_assessment_detail(html_content: str) -> Dict[str, Any]:
        """
        Parses the assessment detail modal HTML.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        table = soup.find("table", class_="table-bordered")
        if not table:
            return {}

        course_title_row = soup.find("tr", class_="text-primary")
        course_title = course_title_row.get_text(strip=True).replace("Course :", "").strip() if course_title_row else ""

        grades = []
        total_mark = ""

        rows = table.find_all("tr")
        for row in rows:
            if "success" in row.get("class", []):
                # Check if it's the header or the footer (Total Mark)
                text = row.get_text(strip=True)
                if "Total Mark" in text:
                    total_mark = text.replace("Total Mark :", "").strip()
                continue

            cols = row.find_all("td")
            if len(cols) == 3 and cols[0].get_text(strip=True).isdigit():
                name_with_weight = cols[1].get_text(strip=True)
                result = cols[2].get_text(strip=True)
                
                # Split name and weight if possible: "Individual Assignment ( 10% )"
                name = name_with_weight
                weight = ""
                weight_match = re.search(r"\(([^)]+)\)", name_with_weight)
                if weight_match:
                    weight = weight_match.group(1).strip()
                    name = re.sub(r"\([^)]+\)", "", name_with_weight).strip()

                grades.append({
                    "name": name,
                    "weight": weight,
                    "result": result
                })

        return {
            "course": course_title,
            "grades": grades,
            "totalMark": total_mark
        }
