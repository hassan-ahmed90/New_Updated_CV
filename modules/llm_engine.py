
import json
import logging
import re
import requests

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "llama3.2:1b"        # switched to 1b — fastest local option for analysis tasks
REQUEST_TIMEOUT = 90              # seconds
MAX_RETRIES = 1                   # total attempts = 1 + MAX_RETRIES


class LLMError(Exception):
    pass


def safe_json_loads(content: str) -> dict:
    """Robust parser that cleans markdown fences and repairs truncated JSON."""
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)

    # 1. Direct standard parse
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 2. Extract outermost {...} block
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # 3. Truncated JSON auto-repair (e.g. cut off mid-array)
    last_brace = content.rfind("}")
    if last_brace != -1:
        repaired = content[:last_brace + 1]
        if repaired.count("[") > repaired.count("]"):
            repaired += "]"
        if repaired.count("{") > repaired.count("}"):
            repaired += "}"
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("Failed to parse JSON", content, 0)


# ═══════════════════════════════════════════════════════════
#  CORE CLIENT — every LLM call in this file goes through this
# ═══════════════════════════════════════════════════════════

def _call_llm_json(system_prompt: str, user_prompt: str, temperature: float = 0.1) -> dict:
    """Calls Ollama with format="json" and returns the parsed dict.
    Retries on invalid JSON / timeouts."""
    last_error = None

    for _ in range(1 + MAX_RETRIES):
        try:
            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL_NAME,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "format": "json",
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_ctx": 1024,     # optimized context window for fast CPU processing
                        "num_predict": 800,  # ample headroom to prevent string truncation
                        "num_thread": 4,     # utilize all physical CPU cores
                    },
                },
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            content = response.json()["message"]["content"]
            return safe_json_loads(content)

        except requests.exceptions.ConnectionError as e:
            raise LLMError(
                f"Could not reach Ollama at {OLLAMA_URL}. "
                f"Is it running? (try: ollama serve)"
            ) from e
        except requests.exceptions.Timeout as e:
            last_error = e
            continue
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            continue
        except (KeyError, requests.exceptions.RequestException) as e:
            last_error = e
            continue

    raise LLMError(f"LLM call failed after {1 + MAX_RETRIES} attempts. Last error: {last_error}")


def set_model_name(name: str):
    """Set the Ollama model to use for LLM calls."""
    global MODEL_NAME
    MODEL_NAME = name


def get_installed_models() -> list:
    """Returns a list of model names currently installed in local Ollama."""
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            data = r.json()
            return [m["name"] for m in data.get("models", [])]
        return []
    except requests.exceptions.RequestException:
        return []


def check_ollama_available() -> bool:
    """Quick health check — call once at app startup so you can show a
    clear warning instead of every CV silently falling back with no
    explanation."""
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        return r.status_code == 200
    except requests.exceptions.RequestException:
        return False


# ═══════════════════════════════════════════════════════════
#  1. CV EXTRACTION — replaces education.py / experience.py /
#     skill_extractor.py's job in one pass
# ═══════════════════════════════════════════════════════════

_CV_SYSTEM_PROMPT = """You are an expert CV/resume parser. Extract structured
information from the candidate's CV text below. Be precise and only report
what the text actually supports — do not guess or invent details.

DEGREE EXTRACTION:
- Report the HIGHEST degree level found: one of "bachelors", "masters",
  "mphil", "phd", or "none" if no bachelor's-level degree or higher is
  present (diplomas, intermediate/high-school-level qualifications do NOT
  count).
- Recognize ANY wording or abbreviation: "Bachelor of Science", "BSc",
  "B.E", "BE", "BSSE", "BSCS", common misspellings ("Bechorlar",
  "Becholars"), etc. Ignore diplomas/certificates listed near a degree —
  they are separate credentials, not part of the degree itself.
- Report the field of study (e.g. "Computer Science", "Software
  Engineering") as written or clearly implied.
- Report the graduation year as a 4-digit number, using the degree's OWN
  date range — not a nearby diploma/certificate's date. If the CV shows
  a date range (e.g. "2020 - 2024"), use the END year. If it says
  "Present"/"Current" for an ongoing degree, use null and set
  "in_progress": true.

WORK EXPERIENCE:
- List each REAL, paid or formal (including internships) employment
  entry: job title, company, start date, end date (or "present"),
  approximate duration in months.
- Do NOT include: volunteer roles, club/society membership,
  organizational/leadership positions (e.g. "Student Ambassador"),
  academic projects, or coursework — even if dated "Present". Use your
  judgment the way a recruiter would: was the candidate actually
  EMPLOYED to do this?
- If uncertain whether an entry is a real job, exclude it and note it in
  "excluded_entries" with a one-line reason.

SKILLS:
- List every specific technology/skill/tool the CV demonstrates, whether
  from an explicit "Skills" section OR clearly described in work/project
  text (e.g. "built REST APIs in Python" implies Python).
- Normalize obvious variant spellings ("ReactJS"/"React.js" → "React";
  "NodeJS" → "Node.js").
- Watch for common words that LOOK like skill names but are ordinary
  English in context — e.g. "react punctually to requirements" is the
  verb "react", NOT the React framework. Only count a skill if it's
  genuinely being named as a technology.
- Do not invent skills that aren't stated or clearly demonstrated.

Respond with ONLY valid JSON, no other text, in this exact shape:
{
  "degree": {
    "level": "bachelors" | "masters" | "mphil" | "phd" | "none",
    "field": "<string or null>",
    "graduation_year": <int or null>,
    "in_progress": true or false
  },
  "work_experience": [
    {"title": "<string>", "company": "<string>", "start": "<YYYY-MM or YYYY>",
     "end": "<YYYY-MM or YYYY or 'present'>", "duration_months": <int>}
  ],
  "total_experience_months": <int, sum of REAL job durations only, overlapping periods counted once>,
  "excluded_entries": [{"text": "<what it was>", "reason": "<why not counted as a job>"}],
  "skills": ["<skill1>", "<skill2>", ...]
}
"""


def extract_cv_data(cv_text: str) -> dict:
    """cv_text: raw extracted CV text (original case, not pre-cleaned).
    Raises LLMError on failure — caller should fall back to the regex
    pipeline."""
    result = _call_llm_json(_CV_SYSTEM_PROMPT, f"CV TEXT:\n{cv_text}", temperature=0.1)
    logger.debug("LLM CV extraction result: %s", result)
    _validate_cv_schema(result)
    return result


def _validate_cv_schema(result: dict) -> None:
    required = {"degree", "work_experience", "total_experience_months", "skills"}
    missing = required - result.keys()
    if missing:
        raise LLMError(f"LLM CV extraction missing required fields: {missing}")
    level = result.get("degree", {}).get("level")
    if level not in ("bachelors", "masters", "mphil", "phd", "none"):
        raise LLMError(f"LLM CV extraction returned invalid degree.level: {level!r}")


# ═══════════════════════════════════════════════════════════
#  2. JD PARSING — replaces extract_skills(jd_text) on the JD side.
#     Keeps stack names ("MERN") and categories ("Database experience")
#     intact instead of silently dropping anything not in KNOWN_SKILLS.
# ═══════════════════════════════════════════════════════════

_JD_SYSTEM_PROMPT = """You are an expert technical recruiter. Read the job
description below and extract structured hiring requirements.

For "skills_required", include EVERY distinct requirement, however it's
phrased:
  - specific named technologies ("Python", "React")
  - technology STACKS or acronyms as their own single entry — do NOT
    expand "MERN" into four separate entries; keep it as one entry
    "MERN" and let the matching step reason about it
  - general CATEGORIES if that's genuinely how the JD phrases it
    ("Database experience", "Cloud platform experience") — keep as
    their own entry, don't guess a specific technology the JD didn't name

For "min_experience_years", extract the minimum years required as a
number. Use 0 if unspecified or if the JD explicitly welcomes new/fresh
graduates.

For "required_education_fields", list acceptable fields of study. Use an
empty list if unspecified.

For "graduates_only", true if the JD explicitly requires the candidate
to have ALREADY graduated (e.g. "graduated students only"), false
otherwise — an internship posting welcoming current students is false.

Respond with ONLY valid JSON, no other text, in this exact shape:
{
  "job_title": "<string>",
  "skills_required": ["<requirement1>", "<requirement2>", ...],
  "min_experience_years": <number>,
  "required_education_fields": ["<field1>", ...],
  "graduates_only": true or false
}
"""


def parse_jd(jd_text: str) -> dict:
    """Raises LLMError on failure."""
    result = _call_llm_json(_JD_SYSTEM_PROMPT, f"JOB DESCRIPTION:\n{jd_text}", temperature=0.1)
    _validate_jd_schema(result)
    return result


def _validate_jd_schema(result: dict) -> None:
    required = {"skills_required", "min_experience_years",
                "required_education_fields", "graduates_only"}
    missing = required - result.keys()
    if missing:
        raise LLMError(f"LLM JD parsing missing required fields: {missing}")
    if not isinstance(result["skills_required"], list) or not result["skills_required"]:
        raise LLMError("LLM JD parsing returned an empty or invalid skills_required list")


# ═══════════════════════════════════════════════════════════
#  3. SKILL MATCHING — handles stack decomposition (MERN → Mongo/
#     Express/React/Node found individually) and category matching
#     (Database → MongoDB). Every match requires a quoted excerpt
#     from the CV as evidence — the hallucination guardrail.
# ═══════════════════════════════════════════════════════════

_MATCH_SYSTEM_PROMPT = """You are an expert technical recruiter assistant.
Given a list of job requirements and candidate CV text, determine strictly which requirements the candidate satisfies.

STRICT EVALUATION RULES:
1. ONLY include a requirement in "matched_skills" if the candidate's CV text explicitly mentions or clearly demonstrates it.
2. If the candidate is in an unrelated field (e.g., Account Management, Fashion Design, Hospitality, Bar Management, Sales, Nursing) and has none of the technical skills, return an empty list: {"matched_skills": []}.
3. DO NOT guess, hallucinate, or repeat the job requirements blindly. Every match is strictly verified against the CV text.

Respond with ONLY valid JSON in this exact shape:
{
  "matched_skills": ["<matched skill from list>"]
}
"""


def _extract_evidence_quote(skill: str, cv_text: str) -> str:
    """Extracts a short sentence/phrase from cv_text mentioning the skill or common aliases.
    Returns empty string if the skill is not actually found in the CV text."""
    if not cv_text or not skill:
        return ""

    escaped = re.escape(skill.strip())
    pattern = re.compile(rf"([^.\n\r•\-\|]*?\b{escaped}\b[^.\n\r•\-\|]*)", re.IGNORECASE)
    m = pattern.search(cv_text)
    if m:
        quote = m.group(1).strip()
        if len(quote) >= 3:
            return quote[:140]

    # Check known aliases/components (e.g. MERN -> mongo/express/react/node)
    aliases = {
        "mern": [r"mongo(?:db)?", r"express(?:\.js)?", r"react(?:\.js)?", r"node(?:\.js)?"],
        "mean": [r"mongo(?:db)?", r"express(?:\.js)?", r"angular", r"node(?:\.js)?"],
        "rag": [r"retrieval[\s-]augmented", r"vector[\s-]search", r"vector[\s-]database"],
        "nlp": [r"natural[\s-]language[\s-]processing"],
        "cv": [r"computer[\s-]vision"],
        "ml": [r"machine[\s-]learning"],
        "ai": [r"artificial[\s-]intelligence"],
    }
    skill_lower = skill.lower().strip()
    if skill_lower in aliases:
        for alias_pat in aliases[skill_lower]:
            m = re.search(rf"([^.\n\r•\-\|]*?\b{alias_pat}\b[^.\n\r•\-\|]*)", cv_text, re.IGNORECASE)
            if m:
                quote = m.group(1).strip()
                if len(quote) >= 3:
                    return quote[:140]

    return ""


def match_cv_to_requirements(jd_requirements: list, cv_text: str, detected_skills: list = None) -> dict:
    """jd_requirements: list of JD skills/requirements.
    cv_text: extracted CV text.
    detected_skills: optional list of skills detected by keyword/regex parser.
    Raises LLMError on failure."""
    skills_hint = ""
    if detected_skills:
        skills_hint = f"\nDETECTED CV SKILLS:\n{', '.join(detected_skills)}\n"

    user_prompt = (
        "JOB REQUIREMENTS TO EVALUATE:\n" + "\n".join(f"- {r}" for r in jd_requirements)
        + skills_hint
        + "\n\nCANDIDATE CV TEXT:\n" + cv_text[:1800]
    )
    result = _call_llm_json(_MATCH_SYSTEM_PROMPT, user_prompt, temperature=0.1)
    _validate_match_schema(result, jd_requirements, cv_text, detected_skills=detected_skills)
    return result


def _validate_match_schema(result: dict, jd_requirements: list, cv_text: str = "", detected_skills: list = None) -> None:
    # Accept 'matched_skills', 'matched_requirements', or 'matches'
    raw_matched = result.get("matched_skills") or result.get("matched_requirements") or []
    
    matched_set = set()
    custom_evidence = {}

    if isinstance(raw_matched, list):
        for item in raw_matched:
            if isinstance(item, str):
                s = item.strip().lower()
                if s:
                    matched_set.add(s)
            elif isinstance(item, dict):
                req_name = item.get("requirement", item.get("name", "")).strip().lower()
                if req_name:
                    matched_set.add(req_name)
                    if item.get("evidence"):
                        custom_evidence[req_name] = item.get("evidence")

    # If result had 'matches' key
    for m in result.get("matches", []):
        if isinstance(m, dict) and m.get("matched"):
            req_name = m.get("requirement", "").strip().lower()
            if req_name:
                matched_set.add(req_name)
                if m.get("evidence"):
                    custom_evidence[req_name] = m.get("evidence")

    detected_set = {s.strip().lower() for s in (detected_skills or [])}

    final_matches = []
    matched_names = []
    lacked_names = []

    for req in jd_requirements:
        req_norm = req.strip().lower()
        
        # Check if claimed by LLM
        is_claimed = req_norm in matched_set or any(req_norm in s or s in req_norm for s in matched_set)
        
        # Check if in deterministic extracted skills
        is_detected = req_norm in detected_set or any(req_norm == s for s in detected_set)

        # Extract genuine quote from CV text
        evidence = custom_evidence.get(req_norm) or _extract_evidence_quote(req, cv_text)

        # STRICT GUARDRAIL: Match is valid ONLY IF:
        # 1. Found in deterministic detected_skills, OR
        # 2. Claimed by LLM AND real evidence was actually verified in the CV text.
        if is_detected or (is_claimed and evidence):
            if not evidence:
                evidence = f"Identified in CV: {req}"
            final_matches.append({
                "requirement": req,
                "matched": True,
                "match_type": "direct",
                "evidence": evidence,
                "reasoning": f"Evidence in CV: {evidence}"
            })
            matched_names.append(req)
        else:
            final_matches.append({
                "requirement": req,
                "matched": False,
                "match_type": "none",
                "evidence": "",
                "reasoning": "Not found or demonstrated in CV."
            })
            lacked_names.append(req)

    result["matches"] = final_matches

    # Ensure overall summary exists and is free of literal prompt templates
    summary = (result.get("career_summary") or result.get("overall_summary") or "").strip()
    is_placeholder = (
        not summary
        or "Matches X" in summary
        or "Lacks Y" in summary
        or "(Career Alignment: Role)" in summary
    )

    if is_placeholder:
        matched_str = ", ".join(matched_names[:6]) if matched_names else "limited JD skills"
        lacked_str = ", ".join(lacked_names[:4]) if lacked_names else "none"
        result["overall_summary"] = f"Demonstrates strong alignment in {matched_str}. Lacks explicit coverage in {lacked_str}."
    else:
        result["overall_summary"] = summary


def matched_count(match_result: dict) -> int:
    """How many requirements were satisfied — feeds into ranker.py's
    existing scoring math unchanged."""
    return sum(1 for m in match_result["matches"] if m["matched"])


# ═══════════════════════════════════════════════════════════
#  4. EXPERIENCE SCORE HELPER — translates total_experience_months
#     into the SAME 0/2/3 scale get_experience_score() already uses,
#     so ranker.py doesn't need to change at all.
# ═══════════════════════════════════════════════════════════

def llm_exp_score(cv_months: int, req_years: float):
    """
    Mirrors experience.py's get_experience_score() scale:
      0 = well below requirement
      2 = no requirement specified, OR close-but-under
      3 = meets or exceeds requirement
    Returns (exp_score, cv_years, req_years, exp_label) — same shape as
    get_experience_score(), so it's a drop-in replacement.
    """
    cv_years = round(cv_months / 12, 1)
    if req_years <= 0:
        return 2, cv_years, req_years, f"{cv_years} yrs experience"
    if cv_years >= req_years:
        return 3, cv_years, req_years, f"{cv_years} yrs (Required: {req_years}+) ✅"
    if cv_years >= req_years * 0.85:
        return 2, cv_years, req_years, f"{cv_years} yrs (Required: {req_years}+) 🟡"
    return 0, cv_years, req_years, f"{cv_years} yrs (Required: {req_years}+) ❌"



