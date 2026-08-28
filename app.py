# app.py
import re
from datetime import datetime

import streamlit as st
import pandas as pd

from modules.extractor import extract_text
from modules.cleaner import clean_text, normalize_for_skills
from modules.skill_extractor import extract_skills
from modules.matcher import match_skills
from modules.ranker import rank_candidates
from modules.jd_profile import build_profile
from modules.education import (
    extract_education,
    has_bachelors,
    extract_degree_years, format_degree_years,
)
from modules.experience import extract_experience_years, extract_job_titles

st.set_page_config(page_title="CV Shortlisting System", page_icon="🤖", layout="wide")
st.title("🤖 AI-Based CV Shortlisting System")
st.markdown("Upload a Job Description and CVs — get ranked results instantly!")
st.divider()

# ── Session state init ───────────────────────────────────────
# FIX: results/rejected used to live only inside the button's
# `if st.button(...)` block. Streamlit reruns the whole script on
# every interaction (including clicking "Download CSV"), and on
# that rerun the button is False again — so the results table and
# download button vanished immediately after being clicked. Now
# everything the user needs to see survives across reruns.
if "results" not in st.session_state:
    st.session_state.results = None
if "rejected" not in st.session_state:
    st.session_state.rejected = None
if "cv_count" not in st.session_state:
    st.session_state.cv_count = 0
if "profile" not in st.session_state:
    st.session_state.profile = None


# ── JD requirement detectors ─────────────────────────────────
# MOVED to modules/jd_profile.py, resolved once per run by
# build_profile(). These sat here as loose helpers, so "what does
# this JD actually ask for?" had no single answer and every
# consumer re-derived its own. jd_profile.py also fixes the
# must-have detector, which matched 'required' but not
# 'Requirements' — the heading this project's own AI JD.txt uses.


# ── Step 1: Job Description ──────────────────────────────
st.header("📋 Step 1: Enter Job Description")
jd_input_type = st.radio("How do you want to provide the JD?",
                          ["Type / Paste it", "Upload a file"])
jd_text = ""

if jd_input_type == "Type / Paste it":
    jd_text = st.text_area("Paste Job Description here", height=200,
                            placeholder="e.g. Looking for a Python developer with Django, SQL...")
else:
    jd_file = st.file_uploader("Upload Job Description", type=["pdf", "docx", "txt"])
    if jd_file:
        ext = jd_file.name.split('.')[-1].lower()
        jd_text = extract_text(jd_file, ext)
        st.success("✅ Job Description loaded!")
        with st.expander("Preview"):
            st.write(jd_text[:1000])

st.divider()

# ── Step 2: Upload CVs ───────────────────────────────────
st.header("📁 Step 2: Upload Candidate CVs")
cv_files = st.file_uploader("Upload CVs (PDF, DOCX, TXT)",
                              type=["pdf", "docx", "txt"],
                              accept_multiple_files=True)
if cv_files:
    st.success(f"✅ {len(cv_files)} CV(s) uploaded!")

st.divider()

# ── Step 3: Evaluate ─────────────────────────────────────
st.header("🚀 Step 3: Evaluate Candidates")

if st.button("▶️ Start Evaluation", use_container_width=True):

    if not jd_text.strip():
        st.error("❌ Please enter a Job Description first!")
        st.stop()

    if not cv_files:
        st.error("❌ Please upload at least one CV!")
        st.stop()

    results = []
    rejected = []

    with st.spinner("🔍 Analyzing CVs... please wait"):
        # Resolve the JD once: title, seniority, required years,
        # must-have skills, degree gates, skills, education fields.
        profile = build_profile(jd_text)
        progress = st.progress(0)

        for i, cv_file in enumerate(cv_files):

            ext = cv_file.name.split('.')[-1].lower()
            try:
                raw_text = extract_text(cv_file, ext)
            except Exception as exc:
                # One unreadable PDF must not abort the whole batch.
                rejected.append({
                    "rank": "Rejected",
                    "name": cv_file.name,
                    "match_pct": "0%",
                    "category": "❌ Rejected (Unreadable)",
                    "skills_col": "—",
                    "experience_detail": "—",
                    "degree_years": "—",
                    "is_graduate": "—",
                    "candidate_fields": "—",
                    "new_grad_flag": "—",
                    "matched_skills": "—",
                    "education_detail": f"❌ Could not read file ({type(exc).__name__})",
                    "reason": f"❌ Could not read file ({type(exc).__name__})",
                })
                progress.progress((i + 1) / len(cv_files))
                continue

            if not raw_text.strip():
                rejected.append({
                    "rank": "Rejected",
                    "name": cv_file.name,
                    "match_pct": "0%",
                    "category": "❌ Rejected (No Text)",
                    "skills_col": "—",
                    "experience_detail": "—",
                    "degree_years": "—",
                    "is_graduate": "—",
                    "candidate_fields": "—",
                    "new_grad_flag": "—",
                    "matched_skills": "—",
                    "education_detail": "❌ No text extracted (scanned image PDF?)",
                    "reason": "❌ No text extracted (scanned image PDF?)",
                })
                progress.progress((i + 1) / len(cv_files))
                continue

            cleaned = clean_text(raw_text)

            # ── Education Fields (all fields found in CV) ──
            cv_edu = extract_education(cleaned)
            candidate_fields_str = ", ".join(cv_edu).title() if cv_edu else "None Detected"

            # ── Per-degree graduation years ───────────────
            degree_years = extract_degree_years(raw_text)
            degree_years_str = format_degree_years(degree_years)
            still_enrolled = degree_years.get("bachelors_in_progress", False)

            # ── Raw measurements ──────────────────────────
            cv_years = extract_experience_years(raw_text)
            cv_titles = extract_job_titles(raw_text)
            cv_skills = extract_skills(normalize_for_skills(raw_text))

            gate_score, gate_matched, _ = match_skills(profile.skills, cv_skills, raw_text)
            matched_skills_str = ", ".join(sorted(gate_matched)[:10]) if gate_matched else "None"
            skills_pct_val = f"{round((len(gate_matched) / len(profile.skills)) * 100)}%" if profile.skills else "—"

            # ── Hard rejection: no bachelor's degree ─────
            if profile.bachelors_required and not has_bachelors(raw_text):
                rejected.append({
                    "rank": "Rejected",
                    "name": cv_file.name,
                    "match_pct": "0%",
                    "category": "❌ Rejected (No Bachelor's)",
                    "skills_col": skills_pct_val,
                    "experience_detail": f"{cv_years} yrs" if cv_years > 0 else "No experience",
                    "degree_years": degree_years_str or "None Detected",
                    "is_graduate": "📖 No (Undergraduate)" if still_enrolled else "No Degree Found",
                    "candidate_fields": candidate_fields_str,
                    "new_grad_flag": "🎒 Undergraduate" if still_enrolled else "📄 No Degree",
                    "matched_skills": matched_skills_str,
                    "education_detail": "❌ No Bachelor's Degree found (JD requires one)",
                    "reason": "❌ No Bachelor's Degree found (JD requires one)",
                })
                progress.progress((i + 1) / len(cv_files))
                continue

            # ── Hard rejection: still enrolled, but JD wants graduates only ──
            if still_enrolled and profile.graduates_only:
                rejected.append({
                    "rank": "Rejected",
                    "name": cv_file.name,
                    "match_pct": "0%",
                    "category": "❌ Rejected (Still Enrolled)",
                    "skills_col": skills_pct_val,
                    "experience_detail": f"{cv_years} yrs" if cv_years > 0 else "No experience",
                    "degree_years": degree_years_str,
                    "is_graduate": "📖 No (Undergraduate)",
                    "candidate_fields": candidate_fields_str,
                    "new_grad_flag": "🎒 Undergraduate",
                    "matched_skills": matched_skills_str,
                    "education_detail": "❌ Still enrolled (degree in progress) — JD requires graduates only",
                    "reason": "❌ Still enrolled (degree not yet completed) — JD requires graduates only",
                })
                progress.progress((i + 1) / len(cv_files))
                continue

            bachelors_year = degree_years.get("bachelors")
            masters_year = degree_years.get("masters")
            phd_year = degree_years.get("phd")
            mphil_year = degree_years.get("mphil")

            current_year = datetime.now().year
            has_higher = bool(masters_year or phd_year or mphil_year)
            new_grad = (
                bachelors_year is not None
                and not still_enrolled
                and 0 <= (current_year - bachelors_year) <= 2
                and cv_years < 1.0
                and not has_higher
            )

            score, matched, quality_map = match_skills(profile.skills, cv_skills, raw_text)

            missing_must_haves = sorted(profile.must_have_skills - matched)

            results.append({
                "name": cv_file.name,
                "score": score,
                "total_jd_skills": len(profile.skills),
                "matched_skills": ", ".join(sorted(matched)[:10]) if matched else "None",
                "missing_must_haves": missing_must_haves,
                "quality_map": quality_map,
                "candidate_fields": candidate_fields_str,
                "cv_education": cv_edu,
                "cv_titles": cv_titles,
                "current_title": cv_titles[0] if cv_titles else "—",
                "degree_years": degree_years_str,
                "is_new_grad": new_grad,
                "still_enrolled": still_enrolled,
                "cv_years": cv_years,
            })
            progress.progress((i + 1) / len(cv_files))

    # Save into session_state so results survive reruns (e.g. clicking Download)
    st.session_state.results = results
    st.session_state.rejected = rejected
    st.session_state.cv_count = len(cv_files)
    st.session_state.profile = profile

st.divider()

# ── Render from session_state (persists across reruns) ───────
if st.session_state.results is not None:
    results = st.session_state.results
    rejected = st.session_state.rejected
    cv_count = st.session_state.cv_count
    profile = st.session_state.profile

    # ── What the system understood the JD to require ─────
    # Scores are only as good as this reading of the JD, so show it
    # instead of asking HR to trust an unexplained number.
    if profile is not None:
        with st.expander("🔎 How this Job Description was interpreted", expanded=False):
            c1, c2, c3 = st.columns(3)
            c1.metric("Detected role", profile.title or "—")
            c2.metric("Seniority", profile.seniority.title())
            c3.metric(
                "Experience wanted",
                f"{profile.effective_required_years:g} yrs"
                if profile.effective_required_years else "Not specified",
            )
            st.write(f"**Skills required ({len(profile.skills)}):** "
                     + (", ".join(sorted(profile.skills)) or "none detected"))
            st.write("**Must-haves:** "
                     + (", ".join(sorted(profile.must_have_skills))
                        or "JD did not separate must-have from nice-to-have"))
            st.write("**Field(s) of study:** "
                     + (", ".join(sorted(profile.education_fields)) or "not specified"))
            if profile.prefers_freshers:
                st.info("This JD favours fresh graduates — the new-grad "
                        "penalty is disabled and a small bonus applies.")

    # ── Process Shortlisted and Rejected ─────────────────────
    ranked = rank_candidates(results, profile) if results else []

    for r in ranked:
        if r.get('still_enrolled'):
            r['new_grad_flag'] = "🎒 Undergraduate"
        elif r.get('cv_years', 0) >= 1.0:
            r['new_grad_flag'] = "💼 Experienced"
        elif r.get('is_new_grad'):
            r['new_grad_flag'] = "🎓 New Grad"
        else:
            r['new_grad_flag'] = "📄 No Experience"

        r['is_graduate'] = "📖 No (Undergraduate)" if r.get('still_enrolled') else "🎓 Yes"

        for comp in ("skills", "experience", "education", "title"):
            pct = r.get(f"{comp}_pct")
            r[f"{comp}_col"] = "—" if pct is None else f"{pct}%"

    shortlisted = [r for r in ranked if "Not Suitable" not in r.get('category', '')]
    unsuitable = [r for r in ranked if "Not Suitable" in r.get('category', '')]
    for r in unsuitable:
        if "Ideal" in r.get('experience_detail', ''):
            r['experience_detail'] = f"{r.get('cv_years', 0.0)} yrs"
    all_unsuitable_and_rejected = unsuitable + (rejected or [])

    table_cols = [
        'rank', 'name', 'match_pct', 'category',
        'skills_col',
        'experience_detail',
        'degree_years', 'is_graduate', 'candidate_fields',
        'new_grad_flag', 'matched_skills', 'education_detail'
    ]
    col_names = [
        'Rank', 'CV File', 'Match %', 'Category',
        'Skills',
        'Experience',
        'Degrees & Years', 'Is Graduate', 'Graduate Field(s)',
        'Profile', 'Matched Skills', 'Matched Education'
    ]

    def color_row(val):
        if "Highly" in val:
            return 'background-color: #28a745; color: white; font-weight: bold'
        elif "Suitable" in val and "Not" not in val:
            return 'background-color: #17a2b8; color: white; font-weight: bold'
        elif "Moderate" in val:
            return 'background-color: #fd7e14; color: white; font-weight: bold'
        else:
            return 'background-color: #dc3545; color: white; font-weight: bold'

    # ── 1. Shortlisted Candidates Table ──────────────────────
    if shortlisted:
        st.header("🏆 Shortlisted Candidates")
        df_shortlisted = pd.DataFrame(shortlisted)[table_cols]
        df_shortlisted.columns = col_names

        st.dataframe(
            df_shortlisted.style.map(color_row, subset=['Category']),
            use_container_width=True,
            hide_index=True
        )
        st.divider()

    # ── 2. Not Suitable & Rejected Candidates Table ──────────
    if all_unsuitable_and_rejected:
        st.header("🚫 Not Suitable & Rejected Candidates")
        st.caption(f"{len(all_unsuitable_and_rejected)} candidate(s) did not meet suitability thresholds or mandatory requirements.")
        df_unsuitable = pd.DataFrame(all_unsuitable_and_rejected)[table_cols]
        df_unsuitable.columns = col_names

        st.dataframe(
            df_unsuitable.style.map(color_row, subset=['Category']),
            use_container_width=True,
            hide_index=True
        )
        st.divider()

    # ── Summary metrics ──────────────────────────────────────
    if shortlisted or all_unsuitable_and_rejected:
        col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
        col1.metric("Total CVs", cv_count)
        col2.metric("🚫 Rejected", len(rejected or []))
        col3.metric("🎓 New Grads", sum(1 for r in ranked if r.get('is_new_grad')))
        col4.metric("✅ Highly Suitable", sum(1 for r in shortlisted if "Highly" in r.get('category', '')))
        col5.metric("🟢 Suitable", sum(1 for r in shortlisted if "Suitable" in r.get('category', '') and "Highly" not in r.get('category', '')))
        col6.metric("🟡 Moderate", sum(1 for r in shortlisted if "Moderate" in r.get('category', '')))
        col7.metric("❌ Not Suitable", len(unsuitable))

        st.divider()

        # ── Download ──────────────────────────────────────
        all_export = shortlisted + all_unsuitable_and_rejected
        df_export = pd.DataFrame(all_export)[table_cols]
        df_export.columns = col_names

        st.download_button(
            "⬇️ Download All Results as CSV",
            df_export.to_csv(index=False),
            file_name="cv_results.csv",
            mime="text/csv",
            use_container_width=True
        )
    else:
        st.error("❌ No candidates evaluated.")

