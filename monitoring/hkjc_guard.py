"""
HKJC HTML Page Validation & Date Guard.
Prevents silent date mismatches where HKJC ignores invalid query parameters
(e.g. `racedate=` vs `Date=`) and returns the latest meeting instead of the requested date.
"""
import re
import requests
from datetime import datetime


class HKJCDateMismatch(ValueError):
    """Raised when the HKJC page header date does not match the requested date."""
    pass


class HKJCFetchError(RuntimeError):
    """Raised when an HKJC page fails HTTP check or returns 'No information.'."""
    pass


def _normalize_date_to_ymd(date_str: str) -> str:
    """
    Normalizes a date string ('YYYY-MM-DD', 'YYYY/MM/DD', 'DD/MM/YYYY', 'YYYYMMDD',
    or 'October 21, 2026') into 'YYYY-MM-DD'.
    """
    if not date_str:
        return ""
    s = str(date_str).strip()

    # Pure 8-digit YYYYMMDD
    if re.match(r"^\d{8}$", s):
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"

    # YYYY-MM-DD or YYYY/MM/DD
    m_ymd = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", s)
    if m_ymd:
        return f"{int(m_ymd.group(1)):04d}-{int(m_ymd.group(2)):02d}-{int(m_ymd.group(3)):02d}"

    # DD/MM/YYYY or DD-MM-YYYY
    m_dmy = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", s)
    if m_dmy:
        return f"{int(m_dmy.group(3)):04d}-{int(m_dmy.group(2)):02d}-{int(m_dmy.group(1)):02d}"

    # Text dates like 'October 25, 2026' or '25 October 2026'
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%a %d %B %Y", "%A, %B %d, %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return s


def extract_hkjc_header_date(html_text: str) -> str:
    """
    Extracts the meeting date from HKJC page text.
    Supports patterns such as:
    - 'Race Meeting: 25/10/2026'
    - 'Meeting Date: 25/10/2026'
    - 'Date: 25/10/2026'
    - 'Wednesday, October 28, 2026'
    Returns normalized 'YYYY-MM-DD' or empty string if not found.
    """
    if not html_text:
        return ""

    # 1. Explicit DD/MM/YYYY after Race Meeting / Date label
    m = re.search(r"(?:Race\s*Meeting|Meeting\s*Date|Race\s*Date|Date)\s*[:：]?\s*(\d{2}/\d{2}/\d{4})", html_text, re.IGNORECASE)
    if m:
        return _normalize_date_to_ymd(m.group(1))

    # 2. Month DD, YYYY (e.g., 'October 25, 2026')
    m_text = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}",
        html_text,
        re.IGNORECASE,
    )
    if m_text:
        return _normalize_date_to_ymd(m_text.group(0))

    # 3. Fallback any DD/MM/YYYY in header region
    m_any = re.search(r"\b(\d{2}/\d{2}/20\d{2})\b", html_text[:4000])
    if m_any:
        return _normalize_date_to_ymd(m_any.group(1))

    return ""


def validate_hkjc_html(html_text: str, expect_date: str = None, expect_venue: str = None) -> str:
    """
    Validates HKJC HTML content:
    - Checks non-trivial payload
    - Checks absence of empty-page sentinel ('No information.')
    - If expect_date is provided, asserts the extracted page header date matches expect_date
    Returns extracted header date ('YYYY-MM-DD' or '').
    """
    if not html_text or len(html_text.strip()) < 50:
        raise HKJCFetchError("HKJC response is empty or trivially short.")

    # Check if page is an empty 'No information.' stub without data tables
    if "No information." in html_text and "<table" not in html_text.lower():
        raise HKJCFetchError("HKJC page returned 'No information.' with no data tables.")

    header_ymd = extract_hkjc_header_date(html_text)
    if expect_date:
        expected_ymd = _normalize_date_to_ymd(expect_date)
        if header_ymd and expected_ymd and header_ymd != expected_ymd:
            raise HKJCDateMismatch(
                f"HKJC page header date '{header_ymd}' does not match requested date '{expected_ymd}'."
            )

    if expect_venue:
        if expect_venue.upper() not in html_text.upper():
            raise HKJCDateMismatch(
                f"HKJC page does not contain expected venue '{expect_venue}'."
            )

    return header_ymd


def fetch_hkjc(url: str, expect_date: str = None, expect_venue: str = None, timeout: int = 12):
    """
    Fetches an HKJC HTML page with User-Agent headers and validates status, content, and date header.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    if resp.status_code != 200:
        raise HKJCFetchError(f"HKJC HTTP {resp.status_code} for {url}")

    html_text = resp.text
    validate_hkjc_html(html_text, expect_date=expect_date, expect_venue=expect_venue)
    return resp
