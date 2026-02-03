from bs4 import BeautifulSoup
import re

def parse_grades(html):

    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table tr")

    semesters = []
    current = None

    for row in rows:

        # ---------- Detect semester header ----------
        if "yrsm" in row.get("class", []):

            text = row.get_text(" ", strip=True)

            if "Academic Year" in text:

                year_match = re.search(r"Year\s+(I+)", text)
                semester_match = re.search(r"Semester\s*:\s*(\w+)", text)
                academic_year_match = re.search(r"Academic Year\s*:\s*([\d/]+)", text)

                current = {
                    "academic_year": academic_year_match.group(1),
                    "year_level": year_match.group(1),
                    "semester": semester_match.group(1),
                    "courses": [],
                    "summary": {}
                }

                semesters.append(current)

            elif "SGPA" in text and current:

                sgpa = re.search(r"SGPA\s*:\s*([\d.]+)", text)
                cgpa = re.search(r"CGPA\s*:\s*([\d.]+)", text)

                current["summary"] = {
                    "sgpa": sgpa.group(1) if sgpa else None,
                    "cgpa": cgpa.group(1) if cgpa else None
                }

        # ---------- Course row ----------
        else:

            cols = row.find_all("td")

            if len(cols) == 7 and current:

                course = {
                    "title": cols[1].get_text(strip=True),
                    "code": cols[2].get_text(strip=True),
                    "credit": cols[3].get_text(strip=True),
                    "ects": cols[4].get_text(strip=True),
                    "grade": cols[5].get_text(strip=True)
                }

                current["courses"].append(course)

    return semesters
