import re
from datetime import datetime

CURRENT_YEAR = datetime.now().year


# ═══════════════════════════════════════════════════════════
#  DEGREE TRIGGER LISTS
#  Longer / more-specific triggers come first so alternation
#  is greedy-safe.  Every trigger is wrapped by _bp() in
#  (?<![a-zA-Z]) … (?![a-zA-Z]) boundaries.
# ═══════════════════════════════════════════════════════════

BACHELORS_TRIGGERS = [
    # Full-phrase patterns (most specific)
    r"bachelor(?:s|'s)?\s+(?:of|in)\b",   # "Bachelor of …" / "Bachelor in …"
    r"bachelor(?:s|'s)?",                   # bare "Bachelor" / "Bachelors"
    # Combined BS + subject abbreviations — very common on Pakistani CVs
    # ("BSCS", "BSSE", "BSIT", etc.) and NOT matched by the bare "BS" rule
    # below because there's no boundary between "BS" and the subject letters.
    r"bs(?:cs|se|it|ee|ce|ai|ds|cy|is)\b",  # BSCS, BSSE, BSIT, BSEE, BSCE, BSAI, BSDS, BSCY, BSIS
    # Abbreviations
    r"b\.?sc",                              # BSc, B.Sc
    # NOTE: "BE"/"B.E." is handled separately by _BE_ABBREV_RE below —
    # it is checked CASE-SENSITIVELY against the original text, because
    # once lowercased it is indistinguishable from the common English
    # word "be" (e.g. "I will be available"), which caused candidates
    # with no real degree to pass the rejection gate. Do NOT add a
    # case-insensitive "be" pattern here.
    r"b\.?tech",                            # BTech, B.Tech
    r"b\.?s(?![a-zA-Z])",                   # BS (not BSc, BSE…)  ← "BS Computer"
    r"bcs",                                 # BCS
    r"bba",                                 # BBA
    r"b\.?com",                             # BCom, B.Com
    r"mbbs",                                # MBBS
    r"b\.?arch",                            # B.Arch
    r"llb|l\.l\.b",                         # LLB
    r"undergraduate",                       # written out
    # A short, hand-verified list of common misspellings seen on real CVs
    # (in addition to the generic fuzzy-typo check further down, which
    # catches most other typos without needing to be listed here).
    r"bechorlar",                           # "Bechorlar in Information Technology"
    r"bechelor(?:s|'s)?",
    r"bacholar(?:s|'s)?",
    r"batchelor(?:s|'s)?",
    r"bacheler(?:s|'s)?",
    r"bachalor(?:s|'s)?",
]

MASTERS_TRIGGERS = [
    r"master(?:s|'s)?\s+(?:of|in)\b",      # "Master of …" / "Master in …"
    r"master(?:s|'s)?",                      # bare "Master" / "Masters"
    r"m\.?sc",                               # MSc, M.Sc
    r"m\.?eng\b",                            # MEng
    r"m\.?tech",                             # MTech, M.Tech
    r"mba",                                  # MBA
    r"mcs",                                  # MCS
    r"m\.?com",                              # M.Com
    r"m\.?s(?![a-zA-Z])(?!\.?\s*(?:word|excel|office|sql|access|powerpoint|windows|project|server|dynamics|azure|teams|paint|sharepoint|visio|publisher|dos|exchange|365)\b)",
    r"postgraduate|post[-\s]?graduate",      # written out
]

MPHIL_TRIGGERS = [
    r"mphil",
    r"m\.?\s*phil",                          # M.Phil, M Phil
    r"master\s+of\s+philosophy",
]

PHD_TRIGGERS = [
    r"ph\.?\s*d",                            # PhD, Ph.D, Ph D
    r"doctorate|doctoral",
    r"doctor\s+of\s+philosophy",
]


# ═══════════════════════════════════════════════════════════
#  PATTERN COMPILER
# ═══════════════════════════════════════════════════════════

def _bp(triggers: list) -> re.Pattern:
    """
    Build one compiled regex from trigger list.
    Each trigger is surrounded by non-alpha boundaries so
    "bs" won't match inside "jobs", "abs", etc.
    """
    parts = [r'(?<![a-zA-Z])(?:' + t + r')(?![a-zA-Z])' for t in triggers]
    return re.compile('|'.join(parts), re.IGNORECASE)


_BACHELORS_RE = _bp(BACHELORS_TRIGGERS)
_MPHIL_RE     = _bp(MPHIL_TRIGGERS)      # ← checked BEFORE masters
_MASTERS_RE   = _bp(MASTERS_TRIGGERS)
_PHD_RE       = _bp(PHD_TRIGGERS)

# "BE" / "B.E." / "B.E" abbreviation — deliberately CASE-SENSITIVE and
# NOT wrapped in re.IGNORECASE. Real abbreviations are written with
# capital letters ("BE Computer Science", "B.E. Mechanical"); the
# lowercase word "be" is just the common English verb and must never
# trigger a bachelor's match. This pattern must always be run against
# ORIGINAL-case text, never against already-lowercased text.
_BE_ABBREV_RE = re.compile(r'(?<![a-zA-Z])B\.?E\.?(?![a-zA-Z])')
# M.E. / ME only counts as a degree when followed by an engineering/academic
# context word — prevents 'ABOUT ME' and similar phrases from triggering it.
_ME_ABBREV_RE = re.compile(
    r'(?<![a-zA-Z])M\.?E\.?(?![a-zA-Z])'
    r'(?=\s*(?:in|of|\(|computer|electrical|mechanical|civil|software|electronic|'
    r'information|telecommunication|chemical|aerospace|biomedical|industrial|'
    r'engineering|technology|science|systems|networks))',
    re.IGNORECASE
)

# Sentinel — stops a snippet before it bleeds into the next degree entry
_NEXT_DEGREE_FENCE = re.compile(
    r'\b(?:bachelor|master|mphil|m\.phil|phd|ph\.d'
    r'|bsc|b\.sc|msc|m\.sc|b\.e|b\.tech|m\.tech|m\.e'
    r'|ms\b|bs\b|bba|llb|mbbs|undergraduate'
    r'|bscs|bsse|bsit|bsee|bsce|bsai|bsds|bscy|bsis)\b',
    re.IGNORECASE
)

# Sentinel — stops a snippet before it bleeds into an unrelated later
# section of the resume (e.g. reading a job's end year, or a
# volunteer role's "Present", as if it were the degree's graduation year).
_SECTION_FENCE = re.compile(
    r'\b(?:work\s+experience|professional\s+experience|employment'
    r'|projects?|organizations?|certifications?|achievements?'
    r'|publications?|references|volunteer(?:ing)?|extracurricular'
    r'|leadership\s+experience|internships?|awards?|activities'
    r'|presentations?|conferences?|workshops?|seminars?'
    r'|honou?rs?|community\s+service|hobbies|interests'
    r'|skills?|education|experience|summary|profile|objective|languages?)\b',
    re.IGNORECASE
)

_LEVEL_PATTERNS = [
    ("bachelors", _BACHELORS_RE),
    ("mphil",     _MPHIL_RE),
    ("masters",   _MASTERS_RE),
    ("phd",       _PHD_RE),
]

# ═══════════════════════════════════════════════════════════
#  FUZZY TYPO TOLERANCE (bachelor's-level only)
#  Catches misspellings not covered by the explicit trigger list
#  above, e.g. "Becholars", "Bacholars", "Bachlor", "Batchelor".
#  Uses plain edit distance (stdlib only, no dependencies) with a
#  length filter — tuned so it does NOT false-positive on ordinary
#  words like "backend", "before", "below", "background", "behavior".
# ═══════════════════════════════════════════════════════════

_WORD_RE = re.compile(r"[a-zA-Z']+")


def _levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1]


def _find_bachelor_typo_match(text: str):
    """
    Scan whitespace-delimited words for a close misspelling of
    "bachelor" / "bachelors". Length-gated (6-11 chars, starts with
    'b') and requires edit distance <= 3 — verified against common
    English words to avoid false positives (tested: backend, before,
    below, belong, because, background, behavior, benefit, business
    all correctly excluded at this threshold).

    Returns the FIRST typo match object, or None.
    """
    targets = ("bachelor", "bachelors")
    for m in _WORD_RE.finditer(text):
        w = m.group().lower().strip("'")
        if not (6 <= len(w) <= 11) or not w.startswith("b"):
            continue
        if any(_levenshtein(w, t) <= 3 for t in targets):
            return m
    return None


def _has_bachelor_typo(text: str) -> bool:
    return _find_bachelor_typo_match(text) is not None


# ═══════════════════════════════════════════════════════════
#  YEAR EXTRACTION
# ═══════════════════════════════════════════════════════════

_ALL_YEARS_RE     = re.compile(r'\b(20\d{2})\b')
_CURRENT_WORDS_RE = re.compile(r'\b(current|present|now|ongoing)\b', re.IGNORECASE)

CURRENT_MONTH = datetime.now().month
_MONTH_NAME_TO_NUM = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_MONTH_YEAR_RE = re.compile(r'\b([A-Za-z]{3,10})\.?\s*[-,]?\s*(20\d{2})\b')


def _get_snippet(text: str, match_start: int, match_end: int) -> str:
    """
    Return the text surrounding the degree match, bounded by:
      • the nearest preceding degree keyword or section header,
      • the nearest succeeding degree keyword or section header,
      • or max 120 chars backward and 180 chars forward.
    """
    window_start = max(0, match_start - 120)
    window_end = min(len(text), match_end + 180)
    
    raw_before = text[window_start:match_start]
    raw_after = text[match_end:window_end]

    before_cut = 0
    for fence in [_NEXT_DEGREE_FENCE, _SECTION_FENCE]:
        for m in fence.finditer(raw_before):
            before_cut = max(before_cut, m.end())
            
    after_cut = len(raw_after)
    for fence in [_NEXT_DEGREE_FENCE, _SECTION_FENCE]:
        m = fence.search(raw_after)
        if m:
            after_cut = min(after_cut, m.start())
            
    return raw_before[before_cut:] + text[match_start:match_end] + raw_after[:after_cut]


# Strip personal info lines (DOB, date of birth, gender, nationality, age)
# so they are never scanned for years in an education snippet.
_PERSONAL_INFO_RE = re.compile(
    r'(?:date\s+of\s+birth|dob|d\.?o\.?b|born|age|gender|nationality'
    r'|cnic|passport|religion|marital)\s*:?\s*[\d/\-,\w\s]*?(?=\n|$|[A-Z]{2,})',
    re.IGNORECASE
)


def _year_from_snippet(snippet: str):
    """
    Return the graduation (end) year from the snippet, or None.

    Algorithm:
      1. Strip personal-info tokens (DOB, nationality, gender…) so birth
         years never contaminate the result.
      2. If "current / present / now / ongoing" → return CURRENT_YEAR.
      3. Collect all 20XX years in the snippet.
      4. Return the MAXIMUM (= end year of a range, or the single year).
      Only years from 2005 onward are accepted as graduation years —
      this prevents birth years like 2003 from ever being returned.
    """
    # Remove personal-info substrings that carry birth/registration years
    clean = _PERSONAL_INFO_RE.sub('', snippet)
    if _CURRENT_WORDS_RE.search(clean):
        return CURRENT_YEAR
    years = [int(y) for y in _ALL_YEARS_RE.findall(clean)
             if 2005 <= int(y) <= CURRENT_YEAR + 5]
    return max(years) if years else None


def _degree_still_in_progress(snippet: str, year) -> bool:
    """
    Determine whether a degree is still being pursued (undergraduate /
    not yet graduated) rather than already completed, using the same
    snippet _year_from_snippet() used to resolve the year.

    True when:
      - "Present"/"Current"/"Ongoing"/"Now" appears in the snippet
        (e.g. "Dec 2022 - Present"), or
      - the resolved year is later than the current year (e.g. a CV
        stating "Expected 2027" without the word "present"), or
      - the resolved year equals the current year AND a month name
        attached to that same year is later than the current month
        (e.g. "Dec 2022 - Nov 2026" when today is August 2026 — same
        year, but the completion date hasn't actually arrived yet).

    False when the year is genuinely in the past, or no year could be
    determined at all (safer default: don't assume undergraduate status
    without positive evidence).
    """
    clean = _PERSONAL_INFO_RE.sub('', snippet)

    if _CURRENT_WORDS_RE.search(clean):
        return True

    if year is None:
        return False

    if year > CURRENT_YEAR:
        return True

    if year == CURRENT_YEAR:
        for month_name, yr in _MONTH_YEAR_RE.findall(clean):
            if int(yr) != year:
                continue
            month_num = _MONTH_NAME_TO_NUM.get(month_name.lower())
            if month_num and month_num > CURRENT_MONTH:
                return True
        return False

    return False


# ═══════════════════════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════════════════════

def extract_degree_years(text: str) -> dict:
    """
    Scan CV text and return a dict mapping each degree level found
    to its graduation (end) year.

    Return format
    ─────────────
    {
        "bachelors": 2025,   # found + year detected
        "masters":   2026,   # found + ongoing (current year)
        "mphil":     None,   # found but year not detectable
        # "phd" absent → not mentioned at all
    }

    For each level we scan ALL matches, fence each snippet to
    prevent year bleed-over, then keep the LATEST year seen
    (= most recently completed degree at that level).

    Scoped to the Education section (see _extract_education_section)
    before searching. Without this, degree keywords matched ANYWHERE
    in the CV — including incidental mentions with no connection to
    the candidate's own degree, e.g. "co-taught... to 6th-semester
    Bachelor's students" (a job description, not the candidate's
    education) or "Second Position in Bachelor of Science (Honours)"
    inside an Awards section (a real mention, but with a nearby year
    from unrelated surrounding text bleeding into the resolved year).
    Both produced wrong years by outranking the actual, correct
    Education-section entry in the "keep the latest year" comparison.
    """
    section = _extract_education_section(text)

    result = {}
    for level, pattern in _LEVEL_PATTERNS:
        best_year = None
        best_snippet = None
        found = False
        if level == "bachelors":
            matches = list(pattern.finditer(section)) + list(_BE_ABBREV_RE.finditer(section))
            matches.sort(key=lambda m: m.start())
        elif level == "masters":
            matches = list(pattern.finditer(section)) + list(_ME_ABBREV_RE.finditer(section))
            matches.sort(key=lambda m: m.start())
        else:
            matches = list(pattern.finditer(section))
            
        for m in matches:
            found = True
            snippet = _get_snippet(section, m.start(), m.end())
            year = _year_from_snippet(snippet)
            if year is not None:
                if best_year is None or year >= best_year:
                    best_year = year
                    best_snippet = snippet
                
        if level == "bachelors" and not found:
            typo_match = _find_bachelor_typo_match(section)
            if typo_match is not None:
                found = True
                snippet = _get_snippet(section, typo_match.start(), typo_match.end())
                year = _year_from_snippet(snippet)
                if year is not None:
                    best_year = year
                    best_snippet = snippet
        if found:
            result[level] = best_year
            if level == "bachelors":
                result["bachelors_in_progress"] = _degree_still_in_progress(
                    best_snippet or "", best_year
                )
    return result


def format_degree_years(degree_years: dict) -> str:
    """
    Convert degree_years dict to a human-readable display string.

    Examples
    ────────
    {"bachelors": 2025}                          → "BE/BS 2025"
    {"bachelors": 2026, "bachelors_in_progress": True}
                                                  → "BE/BS 2026 (Expected)"
    {"bachelors": 2021, "masters": 2026}         → "BE/BS 2021 | MS 2026"
    {"bachelors": None}                          → "BE/BS N/A"
    """
    LABELS = {"bachelors": "BE/BS", "masters": "MS", "mphil": "MPhil", "phd": "PhD"}
    ORDER  = ["bachelors", "masters", "mphil", "phd"]
    parts  = []
    for level in ORDER:
        if level in degree_years:
            yr = degree_years[level]
            label = f"{LABELS[level]} {yr if yr else 'N/A'}"
            if level == "bachelors" and degree_years.get("bachelors_in_progress"):
                label += " (Expected)"
            parts.append(label)
    return " | ".join(parts) if parts else "N/A"


def has_bachelors(text: str) -> bool:
    """
    Hard rejection gate.
    Returns True only if the CV mentions a bachelor's-level degree.
    Candidates without a bachelor's are rejected immediately.

    IMPORTANT: call this with the ORIGINAL-case text (not lowercased),
    since the "BE"/"B.E." check below is intentionally case-sensitive.
    """
    if _BACHELORS_RE.search(text):
        return True
    if _BE_ABBREV_RE.search(text):
        return True
    if _has_bachelor_typo(text):
        return True
    return False


def is_graduated(text: str) -> bool:
    """Backward-compat alias → delegates to has_bachelors()."""
    return has_bachelors(text)


# ═══════════════════════════════════════════════════════════
#  EDUCATION DOMAIN MATCHING  (Semantic Degree Alignment)
# ═══════════════════════════════════════════════════════════

COMPUTING_CORE = [
    "computer science", "software engineering", "artificial intelligence",
    "data science", "data engineering", "data analytics",
    "information technology", "information systems",
    "computer engineering", "computer systems engineering",
    "cybersecurity", "information security", "computer networks",
    "human computer interaction"
]

COMPUTING_RELATED = [
    "electrical engineering", "electronics engineering",
    "telecommunications engineering", "mathematics",
    "applied mathematics", "statistics", "computational mathematics",
    "mechatronics"
]

COMPUTING_BROAD = [
    "physics", "mechanical engineering", "aerospace engineering"
]

DOMAIN_GROUPS = {
    "computer science": {
        "core":    COMPUTING_CORE,
        "related": COMPUTING_RELATED,
        "broad":   COMPUTING_BROAD
    },
    "software engineering": {
        "core":    COMPUTING_CORE,
        "related": COMPUTING_RELATED,
        "broad":   COMPUTING_BROAD
    },
    "information technology": {
        "core":    COMPUTING_CORE,
        "related": COMPUTING_RELATED,
        "broad":   COMPUTING_BROAD
    },
    "data science": {
        "core":    COMPUTING_CORE,
        "related": COMPUTING_RELATED + ["economics"],
        "broad":   COMPUTING_BROAD
    },
    "artificial intelligence": {
        "core":    COMPUTING_CORE,
        "related": COMPUTING_RELATED,
        "broad":   COMPUTING_BROAD
    },
    "cybersecurity": {
        "core":    COMPUTING_CORE,
        "related": COMPUTING_RELATED,
        "broad":   COMPUTING_BROAD
    },
    "computer engineering": {
        "core":    COMPUTING_CORE,
        "related": COMPUTING_RELATED,
        "broad":   COMPUTING_BROAD
    },
    "computer systems engineering": {
        "core":    COMPUTING_CORE,
        "related": COMPUTING_RELATED,
        "broad":   COMPUTING_BROAD
    },
    "electrical engineering": {
        "core":    ["electrical engineering", "electronics engineering", "telecommunications engineering"],
        "related": ["computer engineering", "computer systems engineering", "mechatronics"],
        "broad":   ["computer science", "mechanical engineering", "physics"]
    },
    "mechanical engineering": {
        "core":    ["mechanical engineering", "industrial engineering"],
        "related": ["mechatronics", "aerospace engineering", "materials engineering"],
        "broad":   ["electrical engineering", "civil engineering", "physics"]
    },
    "civil engineering": {
        "core":    ["civil engineering"],
        "related": ["structural engineering", "environmental engineering", "construction management"],
        "broad":   ["mechanical engineering", "architecture"]
    },
    "business administration": {
        "core":    ["business administration", "business management", "project management"],
        "related": ["human resource management", "marketing management", "supply chain management", "finance", "accounting", "economics"],
        "broad":   ["information systems", "business analytics"]
    },
    "finance": {
        "core":    ["finance", "financial management", "accounting", "banking"],
        "related": ["economics", "risk management", "business administration", "statistics"],
        "broad":   ["mathematics", "data science"]
    },
    "economics": {
        "core":    ["economics", "applied economics", "econometrics"],
        "related": ["finance", "accounting", "banking", "statistics"],
        "broad":   ["business administration", "mathematics"]
    },
    "medicine": {
        "core":    ["medicine", "surgery"],
        "related": ["pharmacy", "nursing", "dentistry", "public health"],
        "broad":   ["biochemistry", "biology", "biomedical engineering"]
    },
    "mathematics": {
        "core":    ["mathematics", "applied mathematics", "statistics", "computational mathematics"],
        "related": ["data science", "physics", "computer science", "economics"],
        "broad":   ["electrical engineering", "finance"]
    },
    "physics": {
        "core":    ["physics", "applied physics", "space science", "astronomy"],
        "related": ["mathematics", "materials engineering", "electrical engineering"],
        "broad":   ["chemistry", "data science"]
    },
    "biology": {
        "core":    ["biology", "biochemistry", "molecular biology"],
        "related": ["biotechnology", "microbiology", "genetics"],
        "broad":   ["chemistry", "medicine", "pharmacy"]
    },
}


def _extract_education_section(text: str) -> str:
    """
    Scope the text down to just the EDUCATION section, so domain-field
    matching doesn't pick up field-sounding words sitting anywhere else
    in the CV. Real examples that were false-positiving before this fix:
      - "Data Science"    ← from a "365 Data Science" course/certification
      - "Architecture"    ← from "modular architecture patterns" in a
                             project description
      - "Data Analytics"  ← from an "AI & Data Analytics Intern" job title
      - "Data Engineering" ← from a "Data Engineering:" skills-category
                             heading
      - "Banking"          ← from a "Fintech Banking App" project title
                             sitting between an incidental EARLIER use of
                             the word "education" (e.g. "...facilitate
                             STEM education for school children...") and
                             the real Education heading. The naive
                             "first match of the word education" approach
                             latched onto that incidental mention instead
                             of the real heading, and everything between
                             it and the real heading (a whole different
                             section) got scanned as if it were the
                             education section.
      - "Data Science"     ← from a "Key Courses Knowledge: ... Data
                             Science & Analytics ..." coursework list
                             sitting INSIDE the real Education section,
                             genuinely between the heading and the next
                             section fence, but describing courses taken
                             rather than the degree itself.

    Two safeguards:
    1. A candidate "education" match is only accepted as the real
       heading if a university/degree/date signal appears shortly after
       it — an incidental mention like "STEM education for..." has no
       such signal nearby and is skipped in favor of the next match.
    2. Once a valid section is found, it's additionally truncated at a
       coursework-list marker ("key courses", "coursework", "subjects
       studied", etc.) if one appears, since those lists routinely
       mention many domain-adjacent buzzwords that aren't the actual
       degree field.

    If no valid heading is found at all (common in JD text, which often
    states a degree requirement inline without ever using the word
    "education"), falls back to scanning the full text.
    """
    edu_heading_re = re.compile(
        r'\b(?:e\s*d\s*u\s*c\s*a\s*t\s*i\s*o\s*n|education)(?:\s+and\s+training|al\s+background|\s+history)?\b',
        re.IGNORECASE
    )
    heading_confirm_re = re.compile(
        r'\b(university|college|institute|institution|bachelor|master|'
        r'b\.?e\b|b\.?sc|bs\b|bsse|bscs|bsit|bsee|bsce|bsai|bsds|bscy|bsis|degree|gpa|cgpa|'
        r'20\d{2}\s*[-–—]\s*20\d{2}|20\d{2}\s*[-–—]\s*present|'
        r'software|computer|engineering|science|technology)\b',
        re.IGNORECASE
    )
    coursework_fence_re = re.compile(
        r'\b(?:key\s+courses?|relevant\s+coursework|coursework|'
        r'courses?\s+(?:studied|taken|covered)|subjects?\s+(?:studied|covered)|'
        r'modules?\s+covered)\b',
        re.IGNORECASE
    )

    search_from = 0
    while True:
        m = edu_heading_re.search(text, search_from)
        if not m:
            return text   # no valid heading found anywhere — full-text fallback
        lookahead = text[m.end(): m.end() + 250]
        if heading_confirm_re.search(lookahead):
            start = m.end()
            break
        search_from = m.end()   # this match was incidental prose — keep looking

    end_m = _SECTION_FENCE.search(text, start)
    end = end_m.start() if end_m else len(text)
    section = text[start:end]

    course_m = coursework_fence_re.search(section)
    if course_m:
        section = section[:course_m.start()]

    return section


_FIELD_OF_STUDY_LABEL_RE = re.compile(
    r'field\(?s?\)?\s+of\s+study\s*:?', re.IGNORECASE
)
_DEGREE_ANCHOR_WINDOW = 200   # chars scanned after a degree keyword match
_FIELD_LABEL_WINDOW   = 80    # chars scanned after a "Field(s) of study:" label


def extract_education(text: str) -> set:
    """
    Extract degree field names, scoped to the Education section AND
    anchored to text surrounding an actual degree keyword (bidirectional) or
    a "Field(s) of study:" label.
    """
    section = _extract_education_section(text)

    anchor_spans = []
    for level, pattern in _LEVEL_PATTERNS:
        for m in pattern.finditer(section):
            anchor_spans.append((m.start(), m.end()))
    for m in _BE_ABBREV_RE.finditer(section):
        anchor_spans.append((m.start(), m.end()))
    for m in _ME_ABBREV_RE.finditer(section):
        anchor_spans.append((m.start(), m.end()))
    typo_match = _find_bachelor_typo_match(section)
    if typo_match is not None:
        anchor_spans.append((typo_match.start(), typo_match.end()))

    field_label_ends = [m.end() for m in _FIELD_OF_STUDY_LABEL_RE.finditer(section)]

    windows = [section[max(0, s - 80): min(len(section), e + _DEGREE_ANCHOR_WINDOW)] for s, e in anchor_spans]
    windows += [section[a: a + _FIELD_LABEL_WINDOW] for a in field_label_ends]

    if not windows:
        windows = [section]

    all_fields = set()
    for domain, levels in DOMAIN_GROUPS.items():
        all_fields.add(domain)
        for level_fields in levels.values():
            all_fields.update(level_fields)

    found = set()
    for window_text in windows:
        window_lower = window_text.lower()
        for field in all_fields:
            pattern = r'(?<![a-z])' + re.escape(field) + r'(?![a-z])'
            if re.search(pattern, window_lower):
                found.add(field)
    return found


def get_education_score(jd_field: str, cv_field: str) -> int:
    jd_field = jd_field.lower().strip()
    cv_field = cv_field.lower().strip()
    if jd_field == cv_field:
        return 3
    for domain, levels in DOMAIN_GROUPS.items():
        if jd_field in levels["core"] or jd_field == domain:
            if cv_field in levels["core"]:   return 3
            elif cv_field in levels["related"]: return 2
            elif cv_field in levels["broad"]:   return 1
    return 0


def match_education(jd_education: set, cv_education: set):
    if not jd_education or not cv_education:
        return 0, set()
    matched, already_matched = set(), set()
    total_score = 0
    for jd_field in jd_education:
        best_score, best_match = 0, None
        for cv_field in cv_education:
            if cv_field in already_matched:
                continue
            score = get_education_score(jd_field, cv_field)
            if score > best_score:
                best_score, best_match = score, cv_field
        if best_match and best_score > 0:
            matched.add(best_match)
            total_score += best_score
            already_matched.add(best_match)
    return total_score, matched


def extract_raw_degree_fields(text: str) -> list:
    """
    Extract raw, unstructured field names (e.g. 'Petroleum Engineering')
    for display purposes, without restricting to DOMAIN_GROUPS.
    """
    section = _extract_education_section(text)
    fields = []

    # 1. "Field of study:" label
    for m in _FIELD_OF_STUDY_LABEL_RE.finditer(section):
        snippet = section[m.end(): m.end() + 80]
        line = re.split(r'[\n,\-]', snippet)[0].strip()
        if line and len(line) > 2:
            fields.append(line)

    # 2. Degree + "in" / "of"
    pattern = re.compile(
        r'\b(?:bachelor(?:s|\'s)?|master(?:s|\'s)?|b\.?s\.?c|m\.?s\.?c|b\.?s|m\.?s|b\.?a|m\.?a|b\.?e|m\.?e|phd|bba|mba)\s+(?:of|in)\s+([^,\n\-\|]{3,40})',
        re.IGNORECASE
    )
    for match in pattern.finditer(section):
        field = match.group(1).strip()
        if field.lower().startswith("science in "):
            field = field[11:].strip()
        elif field.lower().startswith("arts in "):
            field = field[8:].strip()
        field = re.split(r'\b(?:at|from)\b|\b20\d{2}\b', field, flags=re.IGNORECASE)[0].strip()
        if field and len(field) > 2:
            fields.append(field)

    # 3. Field | BS / Degree abbreviation (e.g. "Software Engineering | BSSE")
    pipe_pattern = re.compile(
        r'\b([A-Za-z\s]{3,40})\s*\|\s*(?:bs[a-z]{0,4}|b\.?e|b\.?sc|b\.?tech|ms[a-z]{0,4}|m\.?sc|m\.?tech)\b',
        re.IGNORECASE
    )
    for match in pipe_pattern.finditer(section):
        field = match.group(1).strip()
        field = re.split(r'\b(?:at|from)\b|\b20\d{2}\b', field, flags=re.IGNORECASE)[0].strip()
        if field and len(field) > 2:
            fields.append(field)

    seen = set()
    unique_fields = []
    for f in fields:
        f_title = f.title()
        if f_title not in seen:
            seen.add(f_title)
            unique_fields.append(f_title)

    return unique_fields