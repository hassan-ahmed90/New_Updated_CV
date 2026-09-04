# config.py


"""
Tuning surface for the whole scoring model. Nothing here should be
duplicated in app.py or ranker.py — that duplication is what let the
rank order and the category disagree in earlier versions.
"""

# ── Category thresholds (based on combined weighted %) ──────
# "Rejected" is NOT a score band — it's reserved for hard-gate
# failures (missing required degree, graduates-only violation) and is
# applied before scoring matters. These thresholds only decide among
# candidates that passed the hard gates.


THRESHOLDS = {
    "Highly Suitable": 75,   # 75% and above
    "Suitable": 55,          # 55% to 74%
    "Moderate": 25,          # 35% to 54%
    "Not Suitable": 0,       # below 35%
}

# ── Component weights ────────────────────────────────────────
# These are NOT applied as fixed slices. Each component reports
# whether the JD actually gave it something to measure, and the
# weights are renormalized across only the AVAILABLE components.
#
# Why this matters: previously a JD that never stated an education
# requirement still carried a 15% education slice, and match_education
# returned 0 for everyone — so every candidate silently lost 15 points
# against fixed thresholds. Same for the title component. Weight now
# flows to whatever the JD did specify.

WEIGHTS = {
    "skills": 0.45,
    "experience": 0.32,
    "education": 0.13,
    "title": 0.10,
}

# ── Skills component ─────────────────────────────────────────
# A JD must-have counts this many times a nice-to-have when computing
# skill coverage. Missing a critical skill should cost more than
# missing an optional one — proportionally, not as a cliff.

MUST_HAVE_WEIGHT = 2.5

# Similarity → match-quality ramp. Replaces the old two-step
# 1.0 / 0.5 / 0.0 function, which treated a 0.72 match and a 0.84
# match as identical and then jumped to full credit at 0.85.


SIM_FULL_MATCH = 0.85      # at or above this → quality 1.0
SIM_FLOOR = 0.70           # below this → quality 0.0 (no match)
SIM_FLOOR_CREDIT = 0.40    # quality awarded exactly at SIM_FLOOR

# ── Must-have gate ───────────────────────────────────────────
# The weighting above already penalizes each missing must-have in
# proportion. This hard cap now only fires when a candidate misses
# MOST of the must-haves, instead of firing on a single miss.


MUST_HAVE_MIN_COVERAGE = 0.50   # fraction of must-have weight required
MUST_HAVE_SCORE_CAP = 45

# If a JD's "Requirements" block covers essentially every skill it
# names, it isn't actually separating critical from optional — it just
# has one long list. Treating all of those as must-haves makes the
# weighting uniform (so it carries no information) while still arming
# the cap, which then fires on nearly everyone. Above this share, the
# distinction is discarded and all skills weigh equally.
MUST_HAVE_MAX_SHARE = 0.80

# ── Experience component ─────────────────────────────────────
# Years inferred when a JD names a seniority level but no number.
# Without this, "Senior ML Engineer" with no explicit "5+ years"
# scored experience identically for a fresher and a 10-year engineer.
SENIORITY_YEARS = {
    "entry": 0.0,
    "junior": 1.0,
    "mid": 3.0,
    "senior": 5.0,
    "lead": 8.0,
}

# When the JD genuinely asks for no experience, more experience should
# still rank marginally higher — but a fresher must not be punished
# for something the JD never required. The curve therefore starts at
# this floor rather than at zero.
EXP_NO_REQUIREMENT_FLOOR = 0.60
EXP_SATURATION_YEARS = 4.0

# Shortfall curve exponent. < 1.0 is concave: someone at 80% of the
# required years keeps most of the credit, someone at 20% keeps little.
EXP_SHORTFALL_EXPONENT = 0.85

# ── New graduates ────────────────────────────────────────────
# Applied ONLY when the JD implies it wants experience. A trainee /
# internship / "fresh graduates preferred" posting gets the bonus
# instead — the old flat 0.80 multiplier penalized new grads on
# exactly the postings written for them.
NEW_GRAD_PENALTY = 0.90
NEW_GRAD_BONUS = 1.05
