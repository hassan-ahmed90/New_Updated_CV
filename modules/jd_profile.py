# modules/jd_profile.py
"""
Parses a Job Description into an explicit requirement profile.

Previously this logic lived as loose helpers at the top of app.py and
inside experience.py, so "what does this JD actually ask for?" had no
single answer and each consumer re-derived its own. Everything the
scoring model needs to know about the JD is now resolved once, here.
"""
import re
from dataclasses import dataclass, field

from modules.cleaner import clean_text, normalize_for_skills
from modules.skill_extractor import extract_skills
from modules.education import extract_education

# ── Role vocabulary ──────────────────────────────────────────
ROLE_NOUNS = (
    r'engineer|developer|programmer|scientist|analyst|designer|'
    r'manager|architect|administrator|consultant|specialist|'
    r'intern|trainee|officer|executive|lead|researcher|tester'
)

# Head nouns that mean substantially the same job. Without this,
# "AI Engineer" vs "AI Developer" scored zero title match.
ROLE_FAMILIES = {
    "engineer": "build", "developer": "build", "programmer": "build",
    "architect": "build", "tester": "build",
    "scientist": "analyse", "analyst": "analyse", "researcher": "analyse",
    "manager": "manage", "lead": "manage", "executive": "manage",
    "officer": "manage",
    "designer": "design",
    "intern": "junior", "trainee": "junior",
}

_TITLE_LABEL_RE = re.compile(
    r'(?:^|\n)\s*(?:position|job\s*title|role|designation|vacancy|job)\s*'
    r'[:\-]\s*(.+)', re.IGNORECASE
)
_TITLE_INLINE_RE = re.compile(
    r'\b([A-Za-z][A-Za-z+/#.\- ]{2,40}?\b(?:' + ROLE_NOUNS + r')s?)\b',
    re.IGNORECASE
)

# Words stripped from a title before comparison — they describe
# seniority, not the job.
_TITLE_NOISE = {
    "senior", "sr", "junior", "jr", "lead", "principal", "staff",
    "trainee", "intern", "internship", "entry", "level", "mid",
    "associate", "assistant", "head", "chief", "i", "ii", "iii",
    "full", "time", "part", "remote", "onsite", "hybrid", "contract",
    "position", "role", "job", "vacancy", "opening", "the", "a", "an",
    "of", "for", "and", "in", "at",
}

_SENIORITY_PATTERNS = [
    ("entry", r'\b(intern(?:ship)?|trainee|fresh\s+graduate|fresher|'
              r'entry[\s-]level|no\s+experience\s+required|graduate\s+program)\b'),
    ("lead", r'\b(lead|principal|staff\s+engineer|head\s+of|director|'
             r'architect|manager)\b'),
    ("senior", r'\bsenior\b|\bsr\.?\b'),
    ("junior", r'\bjunior\b|\bjr\.?\b'),
]

_FRESHER_PREFERRED_RE = re.compile(
    r'fresh\s+graduates?|freshers?|recent\s+graduates?|'
    r'no\s+(?:prior\s+)?experience\s+(?:is\s+)?required|'
    r'trainee|internship|entry[\s-]level',
    re.IGNORECASE
)

_REQUIRED_YEARS_PATTERNS = [
    r'(\d+\.?\d*)\s*\+?\s*years?\s*(?:of\s*)?(?:relevant\s*|professional\s*|industry\s*)?(?:experience|exp)\b',
    r'minimum\s*(?:of\s*)?(\d+\.?\d*)\s*years?',
    r'at\s*least\s*(\d+\.?\d*)\s*years?',
    r'(\d+\.?\d*)\s*(?:to|-|–)\s*\d+\.?\d*\s*years?',
    r'(\d+\.?\d*)\s*\+\s*years?',
]

# "Bachelor's degree (16 years)" is an education notation, not an
# experience requirement — it must never be read as "16 years of
# experience". Any year-count sitting next to a degree word is skipped.
_DEGREE_YEARS_RE = re.compile(
    r'(?:bachelor|master|degree|bs|ms|bsc|msc|be|phd|education|'
    r'qualification)[^.\n]{0,40}?\(?\s*\d+\s*years?\s*\)?',
    re.IGNORECASE
)


def _strip_degree_year_notation(text: str) -> str:
    return _DEGREE_YEARS_RE.sub(' ', text)


def extract_required_years(jd_text: str) -> float:
    """
    Years of experience the JD explicitly asks for, or 0.0 if it
    doesn't ask. Degree-length notations are removed first.
    """
    cleaned = _strip_degree_year_notation(jd_text.lower())
    for pat in _REQUIRED_YEARS_PATTERNS:
        matches = re.findall(pat, cleaned)
        if matches:
            try:
                return max(float(y) for y in matches)
            except ValueError:
                continue
    return 0.0


def detect_seniority(jd_text: str, title: str = "") -> str:
    """Return one of: entry / junior / mid / senior / lead."""
    haystack = f"{title}\n{jd_text}"
    for level, pattern in _SENIORITY_PATTERNS:
        if re.search(pattern, haystack, re.IGNORECASE):
            return level
    return "mid"


def extract_job_title(jd_text: str) -> str:
    """
    Pull the advertised job title. Prefers an explicit "Position:" /
    "Role:" label, falls back to the first role-noun phrase in the
    opening lines (where a title virtually always sits).
    """
    m = _TITLE_LABEL_RE.search(jd_text)
    if m:
        line = m.group(1).strip()
        line = re.split(r'[|\n]|\s{3,}', line)[0].strip()
        if line:
            return line[:80]

    head = "\n".join(jd_text.splitlines()[:12])
    m = _TITLE_INLINE_RE.search(head)
    if m:
        return m.group(1).strip()[:80]
    return ""


def title_tokens(title: str) -> list:
    """Content tokens of a title, seniority words removed."""
    if not title:
        return []
    title = re.sub(r'\([^)]*\)', ' ', title)          # drop "(Trainee)"
    words = re.findall(r"[A-Za-z][A-Za-z+#.]*", title.lower())
    return [w for w in words if w not in _TITLE_NOISE and len(w) > 1]


def extract_must_have_skills(jd_text: str, jd_skills_full: set) -> set:
    """
    Skills sitting in a "required / must-have / mandatory" block, as
    opposed to a "preferred / nice-to-have" block.

    FIX: the old pattern matched 'required' but not 'Requirements' —
    the single most common heading, and the exact word used in this
    project's own AI JD.txt. The must-have gate was therefore inert on
    the JDs it was written for.
    """
    # Both markers must look like SECTION HEADINGS — anchored to the
    # start of a line. Without the anchor, "…candidates with relevant
    # project experience are preferred." (ordinary prose two lines
    # below the Requirements heading in this project's own AI JD.txt)
    # was read as the start of the nice-to-have section, truncating
    # the required block to nothing.
    required_markers = (
        r'(?:^|\n)[^\S\n]*(?:required|requirements?|must[\s-]?have[s]?|'
        r'mandatory|essential|qualifications?|skills?\s+required|'
        r'what\s+you\s+(?:need|bring)|who\s+you\s+are)'
        r'[^\S\n]*(?:skills?)?[^\S\n]*:?'
    )
    preferred_markers = (
        r'(?:^|\n)[^\S\n]*(?:preferred|nice[\s-]?to[\s-]?have|bonus|'
        r'good\s+to\s+have|desirable|advantages?|plus)'
        r'[^\S\n]*(?:skills?|qualifications?)?[^\S\n]*:?'
    )

    req_match = re.search(required_markers, jd_text, re.IGNORECASE)
    if not req_match:
        return set()   # JD doesn't distinguish — all skills weigh equally

    start = req_match.end()
    pref_match = re.search(preferred_markers, jd_text[start:], re.IGNORECASE)
    end = start + pref_match.start() if pref_match else len(jd_text)

    chunk_skills = extract_skills(normalize_for_skills(jd_text[start:end]))
    must_haves = chunk_skills & jd_skills_full

    # A "Requirements" block that names essentially every skill in the
    # posting is a list, not a priority ordering. Keeping it would make
    # the weighting uniform (no information) while still arming the
    # score cap — which then fires on almost every candidate.
    from config import MUST_HAVE_MAX_SHARE
    if jd_skills_full and len(must_haves) / len(jd_skills_full) > MUST_HAVE_MAX_SHARE:
        return set()

    return must_haves


def requires_graduates_only(jd_text: str) -> bool:
    return bool(re.search(
        r'graduat(?:ed|es)\s+(?:students?\s+)?only'
        r'|must\s+(?:have\s+)?(?:already\s+)?graduated'
        r'|already\s+graduated'
        r'|completed\s+(?:their\s+)?degree\s+required'
        r'|no\s+longer\s+enrolled',
        jd_text, re.IGNORECASE
    ))


def requires_bachelors(jd_text: str) -> bool:
    return bool(re.search(
        r"bachelor'?s?\s+degree"
        r"|b\.?s\.?c?\.?\s+(?:degree|required)"
        r"|undergraduate\s+degree\s+required"
        r"|4[- ]year\s+degree"
        r"|degree\s+(?:is\s+)?required"
        r"|minimum\s+(?:qualification|education)\s*:?\s*bachelor",
        jd_text, re.IGNORECASE
    ))


@dataclass
class JDProfile:
    """Everything the scoring model needs to know about one JD."""
    text: str
    title: str = ""
    title_tokens: list = field(default_factory=list)
    seniority: str = "mid"
    required_years: float = 0.0
    prefers_freshers: bool = False
    graduates_only: bool = False
    bachelors_required: bool = False
    skills: set = field(default_factory=set)
    must_have_skills: set = field(default_factory=set)
    education_fields: set = field(default_factory=set)

    @property
    def effective_required_years(self) -> float:
        """
        Explicit "N years" if stated, otherwise the years implied by
        the seniority level. A "Senior Engineer" posting with no
        number still expects experience, and previously scored a
        fresher identically to a 10-year engineer.
        """
        if self.required_years > 0:
            return self.required_years
        from config import SENIORITY_YEARS
        return SENIORITY_YEARS.get(self.seniority, 0.0)


def build_profile(jd_text: str) -> JDProfile:
    """Resolve a JD into a requirement profile — call this once."""
    title = extract_job_title(jd_text)
    skills = extract_skills(normalize_for_skills(jd_text))

    return JDProfile(
        text=jd_text,
        title=title,
        title_tokens=title_tokens(title),
        seniority=detect_seniority(jd_text, title),
        required_years=extract_required_years(jd_text),
        prefers_freshers=bool(_FRESHER_PREFERRED_RE.search(jd_text)),
        graduates_only=requires_graduates_only(jd_text),
        bachelors_required=requires_bachelors(jd_text),
        skills=skills,
        must_have_skills=extract_must_have_skills(jd_text, skills),
        education_fields=extract_education(jd_text),
    )
