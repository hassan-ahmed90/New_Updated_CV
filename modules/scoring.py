# modules/scoring.py
"""
The scoring model.

Design rule: every component reports whether the JD actually gave it
something to measure. Weights are renormalized across the AVAILABLE
components only, so a JD that says nothing about education does not
quietly cost every candidate the education slice. Under the old fixed
15% slice, match_education() returned 0 for everyone whenever the JD
had no recognizable field — shifting the entire population down
against thresholds that never moved.

Every component also returns a human-readable reason, so a score can
be explained to the person it was applied to.
"""
import math
from dataclasses import dataclass

from config import (
    THRESHOLDS, WEIGHTS, MUST_HAVE_WEIGHT,
    MUST_HAVE_MIN_COVERAGE, MUST_HAVE_SCORE_CAP,
    EXP_NO_REQUIREMENT_FLOOR, EXP_SATURATION_YEARS, EXP_SHORTFALL_EXPONENT,
    NEW_GRAD_PENALTY, NEW_GRAD_BONUS,
)
from modules.education import get_education_score
from modules.jd_profile import ROLE_FAMILIES


@dataclass
class Component:
    name: str
    value: float        # 0.0 - 1.0
    available: bool     # did the JD give us anything to measure?
    detail: str = ""


# ═══════════════════════════════════════════════════════════
#  COMPONENTS
# ═══════════════════════════════════════════════════════════

def skills_component(jd_skills, must_haves, quality_map) -> Component:
    """
    Weighted coverage of the JD's skill requirements.

    A must-have counts MUST_HAVE_WEIGHT times a nice-to-have. This
    replaces the old flat count/total, where missing "Python" on a
    Python role cost exactly as much as missing an optional "Figma".
    Partial matches contribute their similarity-derived quality
    rather than a flat 0.5.
    """
    if not jd_skills:
        return Component("skills", 0.0, False, "JD listed no recognizable skills")

    earned = 0.0
    possible = 0.0
    for skill in jd_skills:
        w = MUST_HAVE_WEIGHT if skill in must_haves else 1.0
        possible += w
        earned += w * quality_map.get(skill, 0.0)

    value = earned / possible if possible else 0.0
    hit = sum(1 for s in jd_skills if quality_map.get(s, 0.0) > 0)
    return Component(
        "skills", value, True,
        f"{hit}/{len(jd_skills)} JD skills matched"
    )


def experience_component(cv_years: float, profile, cv_titles: list = None,
                         quality_map: dict = None, is_new_grad: bool = False) -> Component:
    """
    Continuous experience fit prioritizing domain relevance over raw tenure.

    1. Domain Relevance:
       Raw tenure in an unrelated domain (e.g. space science, civil) is discounted
       relative to directly relevant AI/ML/Software experience. Domain relevance
       is computed from verified skill coverage and role alignment.

    2. Positive Signal for Junior / Fresher / Trainee Roles:
       When the JD states a preference for fresh graduates or is an entry/trainee role,
       junior candidates and new grads are treated as the ideal target profile
       (earning top marks) rather than being penalized against overqualified senior profiles.
    """
    required = profile.effective_required_years
    prefers_freshers = profile.prefers_freshers or profile.seniority == "entry"

    # ── 1. Domain Relevance Factor ───────────────────────────
    if quality_map is not None and profile.skills:
        skill_relevance = sum(quality_map.get(s, 0.0) for s in profile.skills) / len(profile.skills)
    else:
        skill_relevance = 0.0

    # Role/Title match fraction against target JD
    from modules.jd_profile import title_tokens
    title_relevance = 0.0
    if profile.title_tokens and cv_titles:
        for t in cv_titles:
            sim = _title_similarity(profile.title_tokens, title_tokens(t))
            if sim > title_relevance:
                title_relevance = sim

    raw_factor = 0.65 * skill_relevance + 0.35 * max(title_relevance, skill_relevance * 0.8)
    domain_factor = max(0.0, min(1.0, raw_factor))
    effective_years = cv_years * domain_factor

    # ── 2. Fresher / Trainee JD Handling ─────────────────────
    if prefers_freshers:
        if cv_years <= 1.5:
            value = 1.0 * domain_factor
            detail = f"{cv_years} yrs (Ideal Trainee fit ✅)" if domain_factor > 0 else f"{cv_years} yrs (No domain relevance) ❌"
        elif cv_years <= 2.5:
            value = 0.80 * domain_factor
            detail = f"{cv_years} yrs (Slightly overqualified for Trainee)" if domain_factor > 0 else f"{cv_years} yrs (No domain relevance) ❌"
        elif cv_years <= 3.5:
            value = 0.60 * domain_factor
            detail = f"{cv_years} yrs (Overqualified for Trainee) 🟡" if domain_factor > 0 else f"{cv_years} yrs (No domain relevance) ❌"
        elif cv_years <= 4.5:
            value = 0.40 * domain_factor
            detail = f"{cv_years} yrs (Highly overqualified) ❌"
        else:
            value = 0.20 * domain_factor
            detail = f"{cv_years} yrs (Mismatch for Trainee role) ❌"
        return Component("experience", min(1.0, value), True, detail)

    # ── 3. Mid / Senior / Explicit Experience Requirement ────
    if required <= 0:
        span = 1.0 - EXP_NO_REQUIREMENT_FLOOR
        curve = 1.0 - math.exp(-cv_years / EXP_SATURATION_YEARS)
        value = (EXP_NO_REQUIREMENT_FLOOR + span * curve) * domain_factor
        return Component(
            "experience", min(1.0, value), True,
            f"{cv_years} yrs" if domain_factor > 0 else f"{cv_years} yrs (No domain relevance) ❌"
        )

    target_min = required
    target_max = required + 2.0

    if cv_years >= target_min and cv_years <= target_max:
        # Sweet spot
        value = 1.0 * domain_factor
        detail = f"{cv_years} yrs (Ideal target range ✅)" if domain_factor > 0 else f"{cv_years} yrs (No domain relevance) ❌"
    elif cv_years > target_max:
        # Slightly Over
        value = 0.90 * domain_factor
        detail = f"{cv_years} yrs (Slightly over target ✅)" if domain_factor > 0 else f"{cv_years} yrs (No domain relevance) ❌"
    else:
        # Underqualified
        if cv_years >= target_min - 1.0 and cv_years >= 0.5:
            # Slightly under
            value = 0.85 * domain_factor
            detail = f"{cv_years} yrs (Slightly under target 🟡)" if domain_factor > 0 else f"{cv_years} yrs (No domain relevance) ❌"
        else:
            raw_ratio = cv_years / target_min
            value = (raw_ratio ** EXP_SHORTFALL_EXPONENT) * domain_factor
            mark = "🟡" if raw_ratio >= 0.5 else "❌"
            detail = f"{cv_years} yrs (needs {target_min:g}+) {mark}" if domain_factor > 0 else f"{cv_years} yrs (No domain relevance) ❌"

    return Component("experience", min(1.0, value), True, detail)


def education_component(jd_fields, cv_fields) -> Component:
    """
    Field-of-study alignment, AVERAGED over the JD's fields.

    The old version summed get_education_score() across JD fields and
    divided by 3, so a JD naming two fields could reach 200% (clamped
    to 100) while a JD naming one field topped out at exactly 100 —
    the same threshold meant two different things depending on how the
    JD happened to be written.
    """
    if not jd_fields:
        return Component("education", 0.0, False, "JD stated no field of study")
    if not cv_fields:
        return Component("education", 0.0, True, "No field of study detected in CV")

    total = 0
    best_names = []
    for jd_field in jd_fields:
        best, best_name = 0, None
        for cv_field in cv_fields:
            s = get_education_score(jd_field, cv_field)
            if s > best:
                best, best_name = s, cv_field
        total += best
        if best_name:
            best_names.append(best_name)

    value = total / (3.0 * len(jd_fields))
    detail = ", ".join(list(dict.fromkeys(best_names))[:3]) if best_names else "No field match"
    return Component("education", min(1.0, value), True, detail)


def _title_similarity(jd_tokens, cv_tokens) -> float:
    """
    Head noun carries most of the weight (an "Engineer" and a
    "Developer" do the same job; an "Engineer" and an "Account
    Manager" do not), with the remaining weight on overall overlap.
    """
    if not jd_tokens or not cv_tokens:
        return 0.0

    jd_head, cv_head = jd_tokens[-1], cv_tokens[-1]
    if jd_head == cv_head:
        head = 1.0
    elif ROLE_FAMILIES.get(jd_head) and ROLE_FAMILIES.get(jd_head) == ROLE_FAMILIES.get(cv_head):
        head = 0.75
    else:
        head = 0.0

    a, b = set(jd_tokens), set(cv_tokens)
    overlap = len(a & b) / min(len(a), len(b))
    return 0.6 * head + 0.4 * overlap


def title_component(profile, cv_titles) -> Component:
    """
    Role alignment — a signal the model previously had none of, which
    is why an Account Manager résumé could only be separated from an
    AI Engineer résumé by incidental keyword overlap.
    """
    from modules.jd_profile import title_tokens

    if not profile.title_tokens:
        return Component("title", 0.0, False, "No job title found in JD")
    if not cv_titles:
        return Component("title", 0.0, False, "No job titles found in CV")

    best, best_title = 0.0, ""
    for t in cv_titles:
        s = _title_similarity(profile.title_tokens, title_tokens(t))
        if s > best:
            best, best_title = s, t

    detail = f"{best_title} ≈ {profile.title}" if best_title else "No role match"
    return Component("title", best, True, detail)


# ═══════════════════════════════════════════════════════════
#  COMBINATION
# ═══════════════════════════════════════════════════════════

def combine(components, cv_years=0.0, is_new_grad=False, profile=None,
            must_have_coverage=None):
    """
    Renormalize weights over the available components, then apply
    modifiers. Returns (combined_pct, notes).
    """
    available = [c for c in components if c.available]
    if not available:
        return 0.0, ["No scoreable signal in this JD"]

    total_weight = sum(WEIGHTS[c.name] for c in available)
    if total_weight <= 0:
        return 0.0, ["No scoreable signal in this JD"]

    combined = sum(WEIGHTS[c.name] * c.value for c in available)
    combined = (combined / total_weight) * 100.0

    notes = []
    skipped = [c.name for c in components if not c.available]
    if skipped:
        notes.append("Not scored (JD silent): " + ", ".join(skipped))

    # ── New-grad modifier ────────────────────────────────────
    # Only a penalty when the JD actually wants experience. On a
    # trainee / "fresh graduates preferred" posting it becomes a small
    # bonus — the old flat 0.80 multiplier penalized new grads on
    # exactly the postings written for them.
    if is_new_grad and profile is not None:
        if profile.prefers_freshers or profile.seniority == "entry":
            combined *= NEW_GRAD_BONUS
            notes.append("New-grad bonus (JD prefers fresh graduates)")
        elif profile.effective_required_years > 0:
            combined *= NEW_GRAD_PENALTY
            notes.append("New-grad penalty (JD expects experience)")

    # ── Global Role-Fit Multiplier ───────────────────────────
    # Neutralize the "skill inflation" advantage of highly mismatched candidates.
    if profile is not None:
        prefers_freshers = profile.prefers_freshers or profile.seniority == "entry"
        if prefers_freshers:
            if cv_years > 4.5:
                combined *= 0.60
                notes.append("Major penalty: Highly overqualified for Trainee role")
            elif cv_years > 3.0:
                combined *= 0.75
                notes.append("Penalty: Overqualified for Trainee role")
        elif profile.effective_required_years >= 3.0:
            # Mid/Senior role
            if cv_years <= 1.0:
                combined *= 0.60
                notes.append(f"Major penalty: Severe experience mismatch (has {cv_years}y, needs {profile.effective_required_years}y)")
            elif cv_years <= 2.0 and profile.effective_required_years >= 5.0:
                combined *= 0.75
                notes.append(f"Penalty: Underqualified for Senior role")

    # ── Must-have gate ───────────────────────────────────────
    # Proportional weighting above already handles partial gaps. The
    # hard cap now fires only when most must-haves are missing,
    # instead of on a single miss.
    if must_have_coverage is not None and must_have_coverage < MUST_HAVE_MIN_COVERAGE:
        if combined > MUST_HAVE_SCORE_CAP:
            combined = MUST_HAVE_SCORE_CAP
            notes.append(
                f"Capped at {MUST_HAVE_SCORE_CAP}% — only "
                f"{must_have_coverage * 100:.0f}% of must-have skills met"
            )

    return round(min(100.0, max(0.0, combined)), 2), notes


def must_have_coverage(must_haves, quality_map):
    """Fraction of must-have skill weight the candidate actually met."""
    if not must_haves:
        return None          # JD drew no distinction — gate not applicable
    return sum(quality_map.get(s, 0.0) for s in must_haves) / len(must_haves)


def classify_candidate(combined_pct):
    if combined_pct >= THRESHOLDS["Highly Suitable"]:
        return "✅ Highly Suitable"
    elif combined_pct >= THRESHOLDS["Suitable"]:
        return "🟢 Suitable"
    elif combined_pct >= THRESHOLDS["Moderate"]:
        return "🟡 Moderate"
    else:
        return "❌ Not Suitable"
