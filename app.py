# app.py
import re
import time
import base64
from datetime import datetime

import streamlit as st
import pandas as pd


def display_pdf(pdf_bytes):
    """Render an embedded base64 PDF viewer inside Streamlit."""
    base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
    pdf_display = (
        f'<iframe src="data:application/pdf;base64,{base64_pdf}#toolbar=0" '
        f'width="100%" height="750" type="application/pdf" '
        f'style="border-radius: 8px; border: 1px solid #ccd0d5; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">'
        f'</iframe>'
    )
    st.markdown(pdf_display, unsafe_allow_html=True)

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
if "results" not in st.session_state:
    st.session_state.results = None
if "rejected" not in st.session_state:
    st.session_state.rejected = None
if "cv_count" not in st.session_state:
    st.session_state.cv_count = 0
if "profile" not in st.session_state:
    st.session_state.profile = None
if "eval_time" not in st.session_state:
    st.session_state.eval_time = None


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

    start_time = time.time()
    time_placeholder = st.empty()

    results = []
    rejected = []

    with st.spinner("🔍 Analyzing CVs... please wait"):
        # Resolve the JD once: title, seniority, required years,
        # must-have skills, degree gates, skills, education fields.
        profile = build_profile(jd_text)
        progress = st.progress(0)

        for i, cv_file in enumerate(cv_files):
            elapsed_now = time.time() - start_time
            time_placeholder.markdown(
                f"⏱️ **Evaluating {i + 1}/{len(cv_files)}:** `{cv_file.name}` | Elapsed: **{elapsed_now:.1f}s**"
            )
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

            # ── Per-degree graduation years ───────────────
            degree_years = extract_degree_years(raw_text)
            degree_years_str = format_degree_years(degree_years)
            still_enrolled = degree_years.get("bachelors_in_progress", False)
            has_deg = has_bachelors(raw_text) or bool(degree_years)

            # ── Education Fields (all fields found in CV) ──
            if has_deg:
                cv_edu = extract_education(raw_text)
                candidate_fields_str = ", ".join(cv_edu).title() if cv_edu else "None Detected"
            else:
                cv_edu = set()
                candidate_fields_str = "None Detected"

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
                    "new_grad_flag": "Degree in Progress" if still_enrolled else "📄 No Degree",
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
                    "new_grad_flag": "Degree in Progress",
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

            missing_skills = sorted(profile.skills - matched)
            missing_must_haves = sorted(profile.must_have_skills - matched)

            results.append({
                "name": cv_file.name,
                "score": score,
                "total_jd_skills": len(profile.skills),
                "matched_skills": ", ".join(sorted(matched)[:10]) if matched else "None",
                "missing_skills": missing_skills,
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

        total_time = round(time.time() - start_time, 2)
        total_minutes = round(total_time / 60, 1)
        min_unit = "minute" if total_minutes == 1.0 else "minutes"
        st.session_state.eval_time = total_time
        time_placeholder.success(
            f"⚡ **Evaluation Completed:** Total time **{total_minutes} {min_unit}** for **{len(cv_files)}** CVs ({total_time:.1f}s)"
        )

    # Save into session_state so results survive reruns (e.g. clicking Download)
    st.session_state.results = results
    st.session_state.rejected = rejected
    st.session_state.cv_count = len(cv_files)
    st.session_state.profile = profile
    st.session_state.cv_files_map = {f.name: (f.getvalue(), f.name.split('.')[-1].lower()) for f in cv_files}

st.divider()

# ── Render from session_state (persists across reruns) ───────
if st.session_state.results is not None:
    results = st.session_state.results
    rejected = st.session_state.rejected
    cv_count = st.session_state.cv_count
    profile = st.session_state.profile
    eval_time = st.session_state.get("eval_time")

    if eval_time is not None:
        eval_minutes = round(eval_time / 60, 1)
        min_unit = "minute" if eval_minutes == 1.0 else "minutes"
        st.caption(f"⏱️ **Total time {eval_minutes} {min_unit} for {cv_count} CVs** ({eval_time:.1f}s)")

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
            r['new_grad_flag'] = "Degree in Progress"
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
    for r in all_unsuitable_and_rejected:
        r['category'] = "❌ Not Suitable"
        r['rank'] = "—"

    table_cols = [
        'rank', 'name', 'match_pct', 'category',
        'experience_detail',
        'degree_years', 'candidate_fields',
        'new_grad_flag', 'matched_skills'
    ]
    col_names = [
        'Rank', 'CV File', 'Match %', 'Category',
        'Experience',
        'Degrees & Years', 'Graduate Field(s)',
        'Profile', 'Matched Skills'
    ]

    rejected_table_cols = [
        'name', 'match_pct', 'category',
        'experience_detail',
        'degree_years', 'candidate_fields',
        'new_grad_flag', 'matched_skills'
    ]
    rejected_col_names = [
        'CV File', 'Match %', 'Category',
        'Experience',
        'Degrees & Years', 'Graduate Field(s)',
        'Profile', 'Matched Skills'
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

    # ── 2. Rejected Candidates Table ─────────────────────────
    if all_unsuitable_and_rejected:
        st.header("🚫 Rejected Candidates")
        st.caption(f"{len(all_unsuitable_and_rejected)} candidate(s) did not meet suitability thresholds or mandatory requirements.")
        df_unsuitable = pd.DataFrame(all_unsuitable_and_rejected)[rejected_table_cols]
        df_unsuitable.columns = rejected_col_names

        st.dataframe(
            df_unsuitable.style.map(color_row, subset=['Category']),
            use_container_width=True,
            hide_index=True
        )
        st.divider()

    # ── Summary metrics ──────────────────────────────────────
    if shortlisted or all_unsuitable_and_rejected:
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        col1.metric("Total CVs", cv_count)
        col2.metric("🚫 Rejected", len(all_unsuitable_and_rejected))
        col3.metric("🎓 New Grads", sum(1 for r in ranked if r.get('is_new_grad')))
        col4.metric("✅ Highly Suitable", sum(1 for r in shortlisted if "Highly" in r.get('category', '')))
        col5.metric("🟢 Suitable", sum(1 for r in shortlisted if "Suitable" in r.get('category', '') and "Highly" not in r.get('category', '')))
        col6.metric("🟡 Moderate", sum(1 for r in shortlisted if "Moderate" in r.get('category', '')))

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

        st.divider()

        # ── 3. Candidate Deep Dive & PDF Preview ─────────────────
        st.header("🔍 Candidate Deep Dive & PDF Preview")
        st.caption("Inspect matched/missing skills, score details, and the original PDF resume.")

        cand_options = ["-- Select a Candidate to Inspect --"] + [r["name"] for r in all_export]
        selected_cand_name = st.selectbox(
            "Select a candidate to view full details & original resume:",
            options=cand_options,
            index=0
        )

        if selected_cand_name and selected_cand_name != "-- Select a Candidate to Inspect --":
            cand = next((r for r in all_export if r["name"] == selected_cand_name), None)

            if cand:
                st.markdown(f"### 📄 **{cand['name']}** — `{cand.get('match_pct', '0%')}` ({cand.get('category', '')})")

                # Metric Cards
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Overall Match", cand.get("match_pct", "0%"))
                m2.metric("Experience", f"{cand.get('cv_years', 0.0)} yrs")
                m3.metric("Degrees & Status", cand.get("degree_years", "—"))
                m4.metric("Role Alignment", cand.get("current_title", "—") or "—")

                # Tabs
                tab_breakdown, tab_pdf = st.tabs([
                    "📊 Skills & Component Breakdown",
                    "👁️ Original Resume Document"
                ])

                with tab_breakdown:
                    col_l, col_r = st.columns(2)
                    with col_l:
                        st.markdown("#### ✅ Matched Requirements")
                        matched_str = cand.get("matched_skills", "")
                        if matched_str and matched_str not in ("None", "—"):
                            for s in matched_str.split(", "):
                                st.success(f"✓ **{s}**")
                        else:
                            st.info("No matching requirements found.")

                    with col_r:
                        st.markdown("#### ❌ Missing JD Skills")
                        missing_skills = cand.get("missing_skills", [])
                        if missing_skills:
                            must_haves = cand.get("missing_must_haves", [])
                            for s in missing_skills:
                                if s in must_haves:
                                    st.error(f"✗ **{s}** *(Mandatory Requirement ⚠️)*")
                                else:
                                    st.error(f"✗ **{s}**")
                        else:
                            st.success("🎉 Candidate covers 100% of the JD skills!")

                    st.markdown("---")
                    st.markdown("#### 📈 Component Fit Details")
                    comp_cols = st.columns(4)
                    comp_cols[0].markdown(f"**Skills Score**: `{cand.get('skills_col', '—')}`")
                    comp_cols[1].markdown(f"**Experience Fit**: `{cand.get('experience_detail', '—')}`")
                    comp_cols[2].markdown(f"**Education Field**: `{cand.get('candidate_fields', '—')}`")
                    comp_cols[3].markdown(f"**Target Role**: `{cand.get('current_title', '—')}`")

                with tab_pdf:
                    st.markdown("#### 📑 Original Resume Document")
                    files_map = st.session_state.get("cv_files_map", {})
                    file_tuple = files_map.get(selected_cand_name)
                    if file_tuple:
                        raw_bytes, ext = file_tuple
                        if ext == "pdf":
                            try:
                                display_pdf(raw_bytes)
                            except Exception as e:
                                st.warning(f"Could not render PDF preview: {e}")
                        else:
                            st.info(f"File format `.{ext}` preview:")
                            st.text(raw_bytes.decode('utf-8', errors='ignore')[:3000])
                    else:
                        st.info("Upload CVs in Step 2 to enable interactive PDF viewing.")
        else:
            st.info("👆 Please select a candidate from the dropdown above to view their evaluation details and original resume.")
    else:
        st.error("❌ No candidates evaluated.")

