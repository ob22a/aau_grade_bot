import re

def cleanup_html(html: str) -> str:
    """
    Remove sensitive credentials or grades from HTML snippets before logging or raising exceptions.
    """
    if not html:
        return html
        
    # Mask passwords
    cleaned = re.sub(r'(?i)(name="password"[^>]*value=")([^"]+)(")', r'\1***\3', html)
    cleaned = re.sub(r'(?i)(password["\']?\s*:\s*["\'])([^"\']+)(["\'])', r'\1***\3', cleaned)
    
    # Mask grades (A, B+, C-, etc.) in table cells that look like grades
    cleaned = re.sub(r'<td>\s*[A-DF][+-]?\s*</td>', '<td>*</td>', cleaned)
    
    # Truncate if very long
    if len(cleaned) > 10000:
        cleaned = cleaned[:10000] + "\n...[TRUNCATED]"
        
    return cleaned
