# modules/ranker.py
"""
Ranking layer. The scoring model itself lives in scoring.py — this
file only orchestrates and sorts.

The invariant that fixed the original rank/category disagreement still
holds and is now structural: score_candidate() produces exactly one
combined_pct per candidate, and BOTH the sort key and the category are
derived from that single value.
"""
from modules import scoring


def score_candidate(candidate, profile):
    """
    Score one candidate against the JD profile.

    `candidate` must carry: quality_map, cv_years, cv_education,
    cv_titles, is_new_grad. Returns the candidate dict, mutated with
    combined_pct / match_pct / category / component breakdown.
    """
    quality_map = candidate.get("quality_map", {})

    components = [
        scoring.skills_component(
            profile.skills, profile.must_have_skills, quality_map
        ),
        scoring.experience_component(
            candidate.get("cv_years", 0.0), profile,
            cv_titles=candidate.get("cv_titles", []),
            quality_map=quality_map,
            is_new_grad=candidate.get("is_new_grad", False)
        ),
        scoring.education_component(
            profile.education_fields, candidate.get("cv_education", set())
        ),
        scoring.title_component(
            profile, candidate.get("cv_titles", [])
        ),
    ]

    coverage = scoring.must_have_coverage(profile.must_have_skills, quality_map)
    combined_pct, notes = scoring.combine(
        components,
        is_new_grad=candidate.get("is_new_grad", False),
        profile=profile,
        must_have_coverage=coverage,
    )

    candidate["combined_pct"] = combined_pct
    candidate["match_pct"] = f"{round(combined_pct)}%"
    candidate["category"] = scoring.classify_candidate(combined_pct)
    candidate["components"] = {c.name: c for c in components}
    candidate["score_notes"] = notes
    candidate["must_have_coverage"] = coverage

    # Per-component display strings, so a score can be explained
    # rather than just asserted.
    for c in components:
        candidate[f"{c.name}_pct"] = round(c.value * 100) if c.available else None
        candidate[f"{c.name}_detail"] = c.detail

    return candidate


def rank_candidates(results, profile):
    """Score every candidate, sort by the same number, assign ranks."""
    for candidate in results:
        score_candidate(candidate, profile)

    sorted_results = sorted(
        results, key=lambda x: x["combined_pct"], reverse=True
    )
    for i, candidate in enumerate(sorted_results):
        candidate["rank"] = i + 1
    return sorted_results


# Re-exported so existing imports of these names keep working.
classify_candidate = scoring.classify_candidate
