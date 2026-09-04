# modules/experience.py
import re
from datetime import datetime

CURRENT_YEAR = datetime.now().year
CURRENT_MONTH = datetime.now().month

MONTHS_MAP = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
    'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
    'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'june': 6, 'july': 7, 'august': 8, 'september': 9,
    'october': 10, 'november': 11, 'december': 12,
}

# ═══════════════════════════════════════════════════════════
#  SECTION SPLITTER
#  Works on BOTH multi-line and single-line (compressed) text.
#  Finds section keywords inline — no line anchors needed.
# ═══════════════════════════════════════════════════════════

_SEC_PATTERNS = [
    ('experience', r'(?:work\s+experience|professional\s+experience|employment(?:\s+history)?|career\s+history|professional\s+background|positions?\s+held|work\s+history|job\s+history|career\s+summary|work\s+experiences?|professional\s+experiences?|e\s*x\s*p\s*e\s*r\s*i\s*e\s*n\s*c\s*e\s*s?|experience)'),
    ('education', r'(?:e\s*d\s*u\s*c\s*a\s*t\s*i\s*o\s*n|education(?:\s+(?:and|&)\s+(?:training|qualifications?))?|academic\s+background|qualifications?|schooling|academic\s+qualifications?)'),
    ('skills', r'(?:t\s*e\s*c\s*h\s*n\s*i\s*c\s*a\s*l\s+s\s*k\s*i\s*l\s*l\s*s|technical\s+skills?|additional\s+skills?|core\s+skills?|s\s*k\s*i\s*l\s*l\s*s|skills|languages?\s+and\s+tools)'),
    ('projects', r'(?:p\s*r\s*o\s*j\s*e\s*c\s*t\s*s?|projects?|personal\s+projects?|academic\s+projects?|key\s+projects?|research\s+(?:and|&)\s+projects?|proects|final\s+year\s+project)'),
    ('certifications', r'(?:c\s*e\s*r\s*t\s*i\s*f\s*i\s*c\s*a\s*t\s*e\s*s?|certifications?|c\s*e\s*r\s*i\s*t\s*i\s*f\s*a\s*c\s*t\s*e|certificates?|courses?|certifications?\s+(?:and|&)\s+courses?|training)'),
    ('other', r'(?:leadership(?:\s+experience)?|extracurricular(?:\s+(?:and|&)\s+social\s+work)?|activities|volunteer(?:ing)?|publications?|research|achievements?|awards?|honors?|languages?|l\s*a\s*n\s*g\s*u\s*a\s*g\s*e|references?|hobbies?|interests?|objective|summary|profile|about\s+me|additional\s+information|personal\s+information)'),
]

_COMBINED_PAT = '|'.join(f'(?P<{name}>{pat})' for name, pat in _SEC_PATTERNS)
_HEADER_RE = re.compile(
    r'(?:^|[\n\r]|(?:\s{2,}))'
    r'(?!(?:with|in|on|user|hands-on|real|mini|my|their|of|for|practical|academic|agile|key|all|some|more|and|learning|following|using)\s+)'
    r'(?<![\(\[\/])'
    r'(?:' + _COMBINED_PAT + r')'
    r'(?:\s*[:\-\|]|\s*$|\s*[\n\r]|\s{2,})',
    re.IGNORECASE | re.MULTILINE
)


def _find_section_spans(text: str) -> list:
    """
    Scan text for all section header occurrences and return a list of
    (header_category, start_char, end_char) tuples, where the span covers
    the section's content (from this header to the next one).
    """
    markers = []
    for m in _HEADER_RE.finditer(text):
        cat = 'other'
        for name, _ in _SEC_PATTERNS:
            if m.group(name):
                cat = name
                break
        markers.append((cat, m.start(), m.end()))

    spans = []
    for i, (name, hdr_start, hdr_end) in enumerate(markers):
        content_start = hdr_end
        content_end = markers[i + 1][1] if i + 1 < len(markers) else len(text)
        spans.append((name, content_start, content_end))
    return spans


def _extract_experience_section(text: str) -> str:
    """
    Return only the content belonging to the Experience section(s).
    Falls back to empty string if no experience header is found.
    """
    spans = _find_section_spans(text)
    chunks = []
    for name, start, end in spans:
        if name == 'experience':
            chunks.append(text[start:end])
    return " ".join(chunks)


def _strip_education_block(text: str) -> str:
    """
    Remove the Education section content from text so that education
    date ranges (e.g. Jan 2021 – Apr 2025) are never counted as
    work experience.
    """
    spans = _find_section_spans(text)
    if not spans:
        return text

    result = []
    for name, start, end in spans:
        if name != 'education':
            result.append(text[start:end])
    return " ".join(result)


# ═══════════════════════════════════════════════════════════
#  DATE-RANGE PATTERNS
# ═══════════════════════════════════════════════════════════

_MONTH_PAT = (
    r'(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|'
    r'jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|'
    r'nov(?:ember)?|dec(?:ember)?)'
)
_PRESENT_PAT = r'(present|current|now|till\s*date|to\s*date|ongoing)'
_YEAR_PAT = r'(20\d{2})'

# "Month YYYY – Month YYYY"  or  "Month YYYY – Present"
_RANGE_MONTH_YEAR_RE = re.compile(
    _MONTH_PAT + r'[\s\.\-]*' + _YEAR_PAT + r'\s*[-–—]+\s*'
    r'(?:' + _MONTH_PAT + r'[\s\.\-]*' + _YEAR_PAT + r'|' + _PRESENT_PAT + r')',
    re.IGNORECASE
)

# "YYYY – YYYY"  or  "YYYY – Present"
_RANGE_YEAR_ONLY_RE = re.compile(
    _YEAR_PAT + r'\s*[-–—]+\s*(?:' + _YEAR_PAT + r'|' + _PRESENT_PAT + r')',
    re.IGNORECASE
)

# "MM/YYYY – MM/YYYY"  or  "MM/YYYY – Present"   (e.g. "06/2025 – 07/2025")
# Also handles DD/MM/YYYY by ignoring the leading DD/ part.
_NUM_MONTH = r'(?:\d{1,2}/)?(0?[1-9]|1[0-2])'   # optional day-prefix, then MM
_RANGE_NUMERIC_RE = re.compile(
    _NUM_MONTH + r'/' + _YEAR_PAT + r'\s*[-–—\u2013\u2014]+\s*'
    r'(?:' + _NUM_MONTH + r'/' + _YEAR_PAT + r'|' + _PRESENT_PAT + r')',
    re.IGNORECASE
)


# ═══════════════════════════════════════════════════════════
#  UTILITY
# ═══════════════════════════════════════════════════════════

def _parse_month_year(month_str, year_str):
    if not year_str:
        return None, None
    m = MONTHS_MAP.get((month_str or '').lower()[:3], 1)
    try:
        return m, int(year_str)
    except Exception:
        return None, None


def _to_abs_month(month, year):
    return year * 12 + month


def _merge_overlapping_intervals(intervals):
    """Merge overlapping (start, end) month intervals and return total months."""
    if not intervals:
        return 0
    sorted_intervals = sorted(intervals, key=lambda x: x[0])
    merged = [list(sorted_intervals[0])]
    for start, end in sorted_intervals[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return sum(max(0, e - s) for s, e in merged)


# ═══════════════════════════════════════════════════════════
#  COMPANY-LEVEL INTERVAL EXTRACTION
# ═══════════════════════════════════════════════════════════

_EDU_CERT_KEYWORD_RE = re.compile(
    r'\b(?:bachelor|master|b\.?s\b|m\.?s\b|m\.?phil|ph\.?d|b\.?e\b|associate(?:\s+of|\s+degree)|'
    r'degree|certificate|certification|certified|diploma|matric|intermediate|fsc|ics|'
    r'coursework|dissertation|thesis)\b',
    re.IGNORECASE
)


def _extract_intervals_from_section(section_text: str) -> list:
    """
    Parse every date range found in section_text and return a list
    of (abs_start, abs_end) tuples, one per company role.
    Sanity-check: only accept ranges between 1 month and 20 years.
    Filters out dates belonging to academic degrees or certifications.
    """
    intervals = []
    seen = set()

    # Pass 1: Spelled-out Month-Year ranges  (Jun 2025 – Jul 2025)
    for m in _RANGE_MONTH_YEAR_RE.finditer(section_text):
        ctx_before = section_text[max(0, m.start() - 100):m.start()]
        ctx_after = section_text[m.end():min(len(section_text), m.end() + 60)]
        if _EDU_CERT_KEYWORD_RE.search(ctx_before) or _EDU_CERT_KEYWORD_RE.search(ctx_after):
            continue

        sm, sy, em, ey, present = m.groups()
        start_m, start_y = _parse_month_year(sm, sy)

        if present:
            end_m, end_y = CURRENT_MONTH, CURRENT_YEAR
        else:
            end_m, end_y = _parse_month_year(em, ey)

        if start_m and start_y and end_m and end_y:
            abs_start = _to_abs_month(start_m, start_y)
            abs_end   = _to_abs_month(end_m, end_y)
            if 0 < (abs_end - abs_start) <= 240 and (abs_start, abs_end) not in seen:
                intervals.append((abs_start, abs_end))
                seen.add((abs_start, abs_end))

    # Pass 2: Numeric MM/YYYY or DD/MM/YYYY ranges  (06/2025 – 07/2025)
    for m in _RANGE_NUMERIC_RE.finditer(section_text):
        ctx_before = section_text[max(0, m.start() - 100):m.start()]
        ctx_after = section_text[m.end():min(len(section_text), m.end() + 60)]
        if _EDU_CERT_KEYWORD_RE.search(ctx_before) or _EDU_CERT_KEYWORD_RE.search(ctx_after):
            continue

        # groups: (sm, sy, em, ey, present)
        sm, sy, em, ey, present = m.groups()
        try:
            start_m, start_y = int(sm), int(sy)
        except (TypeError, ValueError):
            continue
        if present:
            end_m, end_y = CURRENT_MONTH, CURRENT_YEAR
        else:
            try:
                end_m, end_y = int(em), int(ey)
            except (TypeError, ValueError):
                continue
        abs_start = _to_abs_month(start_m, start_y)
        abs_end   = _to_abs_month(end_m, end_y)
        key = (abs_start, abs_end)
        if 0 < (abs_end - abs_start) <= 240 and key not in seen:
            intervals.append((abs_start, abs_end))
            seen.add(key)

    # Pass 3: Year-only ranges — fallback if nothing found yet
    if not intervals:
        for m in _RANGE_YEAR_ONLY_RE.finditer(section_text):
            ctx_before = section_text[max(0, m.start() - 100):m.start()]
            ctx_after = section_text[m.end():min(len(section_text), m.end() + 60)]
            if _EDU_CERT_KEYWORD_RE.search(ctx_before) or _EDU_CERT_KEYWORD_RE.search(ctx_after):
                continue

            sy, ey, present = m.groups()
            try:
                start_y = int(sy)
            except (TypeError, ValueError):
                continue

            if present:
                end_y = CURRENT_YEAR
            else:
                try:
                    end_y = int(ey)
                except (TypeError, ValueError):
                    continue

            abs_start = _to_abs_month(6, start_y)
            abs_end   = _to_abs_month(6, end_y)
            key = (abs_start, abs_end)
            if 0 < (abs_end - abs_start) <= 240 and key not in seen:
                intervals.append((abs_start, abs_end))
                seen.add(key)

    return intervals


# ═══════════════════════════════════════════════════════════
#  PUBLIC: extract total years of experience
# ═══════════════════════════════════════════════════════════

def extract_experience_years(text: str) -> float:
    """
    Returns total years of professional experience by:
      1. Isolating the Experience section (works on both multi-line
         and compressed single-line PDF text).
      2. Parsing every company date-range within that section.
      3. Merging overlapping intervals (concurrent roles).
      4. If no section detected, strips Education block first then
         scans the remaining text.
      5. Falls back to explicit "X years experience" phrases.
    """
    # Step 1: isolate experience section
    exp_section = _extract_experience_section(text)

    if exp_section.strip():
        search_text = exp_section
    else:
        # Strip education block so its dates don't bleed in
        search_text = _strip_education_block(text)

    # Step 2: extract date-range intervals
    intervals = _extract_intervals_from_section(search_text)
    total_months = _merge_overlapping_intervals(intervals)

    # Step 3: fallback — "X years of experience" in exp section only
    if total_months == 0 and exp_section.strip():
        direct = re.findall(
            r'(\d+\.?\d*)\s*\+?\s*years?\s*(?:of\s*)?(?:experience|exp)',
            exp_section, re.IGNORECASE
        )
        if direct:
            total_months = max(float(y) for y in direct) * 12

    # Step 4: last-resort — "X years of professional/work experience" anywhere
    if total_months == 0:
        summary = re.findall(
            r'(\d+\.?\d*)\s*years?\s*(?:of\s*)?'
            r'(?:industry|professional|work|total)\s*experience',
            text, re.IGNORECASE
        )
        if summary:
            total_months = max(float(y) for y in summary) * 12

    return round(total_months / 12, 1)


# ═══════════════════════════════════════════════════════════
#  BACKWARD-COMPAT helpers (used by app.py)
# ═══════════════════════════════════════════════════════════

def is_newly_graduated(text: str) -> bool:
    """Kept for import compatibility; logic lives in app.py now."""
    return False


# ═══════════════════════════════════════════════════════════
#  CANDIDATE JOB TITLES  (for the title-match component)
# ═══════════════════════════════════════════════════════════

_ROLE_NOUNS = (
    r'engineer|developer|programmer|scientist|analyst|designer|'
    r'manager|architect|administrator|consultant|specialist|'
    r'intern|trainee|officer|executive|lead|researcher|tester'
)

_CANDIDATE_TITLE_RE = re.compile(
    r'\b([A-Z][A-Za-z+/#.\-]*(?:[ ][A-Z][A-Za-z+/#.\-]*){0,3}[ ]'
    r'(?:' + _ROLE_NOUNS + r')s?)\b',
    re.IGNORECASE
)


def extract_job_titles(text: str) -> list:
    """
    Job titles the candidate has actually held.

    Scoped to the Experience section so that a "Looking for a Senior
    Engineer role" line in an objective, or a university's "Research
    Officer" in the education block, isn't read as held experience.
    Falls back to the education-stripped text when a CV has no
    recognizable Experience heading.
    """
    section = _extract_experience_section(text)
    if not section.strip():
        section = _strip_education_block(text)

    titles = []
    seen = set()
    for m in _CANDIDATE_TITLE_RE.finditer(section):
        t = re.sub(r'\s+', ' ', m.group(1)).strip()
        key = t.lower()
        if key not in seen and len(t) <= 60:
            seen.add(key)
            titles.append(t)
    return titles[:12]


def get_experience_score(cv_text: str, jd_text: str):
    """
    Returns (score, cv_years, required_years, label).
    score: 0 (none) / 1 (partial) / 2 (no requirement) / 3 (meets requirement)
    """
    cv_years = extract_experience_years(cv_text)
    jd_lower = jd_text.lower()

    required_years = 0
    req_patterns = [
        r'(\d+\.?\d*)\s*\+?\s*years?\s*(?:of\s*)?(?:experience|exp)',
        r'minimum\s*(\d+\.?\d*)\s*years?',
        r'at\s*least\s*(\d+\.?\d*)\s*years?',
        r'(\d+\.?\d*)\s*to\s*\d+\.?\d*\s*years?',
        r'(\d+\.?\d*)\s*\+\s*years?',
    ]
    for pat in req_patterns:
        matches = re.findall(pat, jd_lower)
        if matches:
            required_years = max(float(y) for y in matches)
            break

    if required_years == 0:
        exp_score = 2
        exp_label = f"{cv_years} yrs experience"
    elif cv_years >= required_years:
        exp_score = 3
        exp_label = f"{cv_years} yrs (Required: {required_years}+) ✅"
    elif cv_years >= required_years * 0.5:
        exp_score = 1
        exp_label = f"{cv_years} yrs (Required: {required_years}+) 🟡"
    else:
        exp_score = 0
        exp_label = f"{cv_years} yrs (Required: {required_years}+) ❌"

    return exp_score, cv_years, required_years, exp_label