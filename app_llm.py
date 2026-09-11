# app_llm.py
import re
import time
import base64
import concurrent.futures
from datetime import datetime
import pandas as pd
import streamlit as st


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
from modules.jd_profile import build_profile, JDProfile
from modules.education import (
    extract_education,
    extract_raw_degree_fields,
    has_bachelors,
    extract_degree_years,
    format_degree_years,
)
from modules.experience import extract_experience_years, extract_job_titles
from modules.llm_engine import (
    check_ollama_available,
    get_installed_models,
    set_model_name,
    match_cv_to_requirements,
    extract_evidence_quote,
    LLMError,
)

st.set_page_config(
    page_title="CV Shortlisting System (LLM Powered)",
    page_icon="🧠",
    layout="wide"
)

st.title("🧠 AI-Powered CV Shortlisting System (LLM Engine)")
st.markdown("Upload a Job Description and CVs — powered by local LLM reasoning & evidence quotation!")
st.divider()

# ── Sidebar: Ollama Connection & Settings ─────────────────────
with st.sidebar:
    st.header("⚙️ LLM Configuration")
    ollama_online = check_ollama_available()
    
    if ollama_online:
        st.success("🟢 **Ollama Connected** (`localhost:11434`)")
        installed_models = get_installed_models()
        default_model = "llama3.2:1b" if "llama3.2:1b" in installed_models else (installed_models[0] if installed_models else "llama3.2:1b")
        
        selected_model = st.selectbox(
            "Select Ollama Model",
            options=installed_models if installed_models else ["llama3.1:8b", "llama3.2:3b", "mistral"],
            index=installed_models.index(default_model) if default_model in installed_models else 0
        )
        set_model_name(selected_model)
        use_llm = st.toggle("Enable LLM Reasoning Mode", value=True)
    else:
        st.error("🔴 **Ollama Offline**")
        st.info(
            "To use LLM mode, start Ollama locally:\n"
            "1. Run `ollama serve` in terminal\n"
            "2. Run `ollama pull llama3.2:1b`"
        )
        use_llm = False
        st.caption("⚡ *Running in ultra-fast Regex & Transformer fallback mode.*")
    
    st.divider()
    st.markdown("### 💡 LLM Capabilities")
    st.markdown(
        "- **Stack Decomposition**: Recognizes that *Mongo + Express + React + Node* satisfies *MERN*.\n"
        "- **Context Awareness**: Separates genuine jobs from student societies & academic projects.\n"
        "- **Evidence Quotes**: Cites exact sentences from each CV as proof.\n"
        "- **Recruiter Summaries**: Generates human-readable evaluation notes."
    )

# ── Session state init ───────────────────────────────────────
if "results" not in st.session_state:
    st.session_state.results = None
if "rejected" not in st.session_state:
    st.session_state.rejected = None
if "cv_count" not in st.session_state:
    st.session_state.cv_count = 0
if "profile" not in st.session_state:
    st.session_state.profile = None
if "jd_llm_data" not in st.session_state:
    st.session_state.jd_llm_data = None
if "use_llm_mode" not in st.session_state:
    st.session_state.use_llm_mode = True
if "eval_time" not in st.session_state:
    st.session_state.eval_time = None

# ── Step 1: Job Description ──────────────────────────────────
st.header("📋 Step 1: Enter Job Description")
jd_input_type = st.radio(
    "How do you want to provide the JD?",
    ["Type / Paste it", "Upload a file"]
)
jd_text = ""

if jd_input_type == "Type / Paste it":
    jd_text = st.text_area(
        "Paste Job Description here",
        height=200,
        placeholder="e.g. Looking for a Full Stack Developer with Python, React, PostgreSQL, and 2+ years of experience..."
    )
else:
    jd_file = st.file_uploader("Upload Job Description", type=["pdf", "docx", "txt"])
    if jd_file:
        ext = jd_file.name.split('.')[-1].lower()
        jd_text = extract_text(jd_file, ext)
        st.success("✅ Job Description loaded!")
        with st.expander("Preview"):
            st.write(jd_text[:1000])

st.divider()

# ── Step 2: Upload CVs ───────────────────────────────────────
st.header("📁 Step 2: Upload Candidate CVs")
cv_files = st.file_uploader(
    "Upload CVs (PDF, DOCX, TXT)",
    type=["pdf", "docx", "txt"],
    accept_multiple_files=True
)
if cv_files:
    st.success(f"✅ {len(cv_files)} CV(s) uploaded!")

st.divider()

# ── Step 3: Evaluate Candidates ──────────────────────────────
st.header("🚀 Step 3: Evaluate Candidates")

if st.button("▶️ Start AI Evaluation", use_container_width=True):
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
    jd_llm_data = None

    with st.spinner("🔍 Evaluating candidate CVs..."):
        # 1. Base JD Profile (Fast Regex + Semantic foundation without LLM)
        profile = build_profile(jd_text)
        jd_requirements = sorted(profile.skills)
        progress = st.progress(0)

        def _process_single_cv(cv_file):
            ext = cv_file.name.split('.')[-1].lower()
            try:
                raw_text = extract_text(cv_file, ext)
            except Exception as exc:
                return "rejected", {
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
                }

            if not raw_text.strip():
                return "rejected", {
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
                }

            cleaned = clean_text(raw_text)

            # ── Degree Years & Completion Status (without LLM) ────────
            degree_years = extract_degree_years(raw_text)
            degree_years_str = format_degree_years(degree_years)
            still_enrolled = degree_years.get("bachelors_in_progress", False)
            has_deg = has_bachelors(raw_text) or bool(degree_years)

            # ── Education Fields (Domain & Raw Fallback without LLM) ──
            if has_deg:
                cv_edu = extract_education(cleaned)
                if cv_edu:
                    candidate_fields_str = ", ".join(cv_edu).title()
                else:
                    raw_fields = extract_raw_degree_fields(raw_text)
                    candidate_fields_str = ", ".join(raw_fields).title() if raw_fields else "None Detected"
            else:
                cv_edu = set()
                candidate_fields_str = "None Detected"

            # ── Extract Experience, Titles & Skills ───────────────────
            cv_years = extract_experience_years(raw_text)
            cv_titles = extract_job_titles(raw_text)
            cv_skills = extract_skills(normalize_for_skills(raw_text))

            # Strictly match against CV text
            gate_score, gate_matched, _ = match_skills(profile.skills, cv_skills, raw_text)
            matched_skills_str = ", ".join(sorted(gate_matched)[:10]) if gate_matched else "None"
            skills_pct_val = f"{round((len(gate_matched) / len(profile.skills)) * 100)}%" if profile.skills else "—"

            # ── Hard Gate 1: Bachelor's Degree ────────────────────────
            if profile.bachelors_required and not has_bachelors(raw_text):
                return "rejected", {
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
                }

            # ── Hard Gate 2: Graduates Only ───────────────────────────
            if still_enrolled and profile.graduates_only:
                return "rejected", {
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
                }

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

            # Fast verified text matching as baseline & pre-filtering gate
            fast_score, fast_matched, fast_quality_map = match_skills(profile.skills, cv_skills, raw_text)

            # ── LLM Intelligent Matching & Evidence Quotation (Early Pre-Filtering) ──
            used_llm_for_cv = False
            llm_evidence_list = []

            # Determine whether this CV actually needs LLM evaluation:
            # 1. Skip if 0 skills matched (clear mismatch - avoids ~12s wasted on Ollama)
            # 2. Skip if all skills are already 100% cleanly matched (no ambiguity)
            # 3. Only run LLM for borderline candidates with partial matches where semantic reasoning helps
            needs_llm = (
                use_llm
                and jd_requirements
                and len(fast_matched) > 0
                and len(fast_matched) < len(profile.skills)
            )

            if needs_llm:
                try:
                    match_result = match_cv_to_requirements(
                        jd_requirements,
                        raw_text,
                        detected_skills=sorted(cv_skills)
                    )
                    matches = match_result.get("matches", [])

                    matched_reqs = set()
                    quality_map = {}
                    for m in matches:
                        req_name = m.get("requirement", "").strip()
                        req_lower = req_name.lower()
                        is_matched = m.get("matched", False)
                        if is_matched:
                            matched_reqs.add(req_lower)
                            quality_map[req_lower] = 1.0
                            llm_evidence_list.append({
                                "requirement": req_name,
                                "type": m.get("match_type", "direct"),
                                "evidence": m.get("evidence", ""),
                                "reasoning": m.get("reasoning", "")
                            })
                        else:
                            quality_map[req_lower] = 0.0

                    # Sync with detected cv_skills directly matching profile.skills
                    from modules.matcher import is_skill_in_text
                    for skill in profile.skills:
                        s_low = skill.lower()
                        if is_skill_in_text(s_low, text=raw_text, cv_skills=cv_skills):
                            quality_map[s_low] = 1.0
                            matched_reqs.add(s_low)
                        elif s_low not in quality_map:
                            quality_map[s_low] = 0.0

                    score = round(sum(quality_map.values()), 2)
                    matched = matched_reqs
                    used_llm_for_cv = True

                except Exception:
                    used_llm_for_cv = False

            if not used_llm_for_cv:
                # Fast verified text matching fallback & instant zero/perfect bypass
                score, matched, quality_map = fast_score, fast_matched, fast_quality_map
                for s in sorted(matched):
                    quote = extract_evidence_quote(s, raw_text)
                    llm_evidence_list.append({
                        "requirement": s,
                        "type": "exact match",
                        "evidence": quote if quote else f"Matched skill: {s}",
                        "reasoning": "Directly verified via CV keywords and section extraction."
                    })

            missing_skills = sorted(profile.skills - matched)
            missing_must_haves = sorted(profile.must_have_skills - matched)

            return "result", {
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
                "llm_evidence": llm_evidence_list,
                "used_llm": used_llm_for_cv,
            }

        # Concurrently process in parallel threads (cuts batch runtime significantly)
        workers = min(4, max(1, len(cv_files)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_cv = {executor.submit(_process_single_cv, f): f for f in cv_files}
            completed_count = 0
            for future in concurrent.futures.as_completed(future_to_cv):
                completed_count += 1
                status_type, data = future.result()
                if status_type == "rejected":
                    rejected.append(data)
                else:
                    results.append(data)
                progress.progress(completed_count / len(cv_files))
                elapsed_now = time.time() - start_time
                time_placeholder.markdown(
                    f"⚡ **Evaluated {completed_count}/{len(cv_files)} CVs (Parallel Batch)** | Elapsed: **{elapsed_now:.1f}s**"
                )

        total_time = round(time.time() - start_time, 2)
        total_minutes = round(total_time / 60, 1)
        min_unit = "minute" if total_minutes == 1.0 else "minutes"
        st.session_state.eval_time = total_time
        time_placeholder.success(
            f"⚡ **Evaluation Completed:** Total time **{total_minutes} {min_unit}** for **{len(cv_files)}** CVs ({total_time:.1f}s)"
        )

    # Persist session state
    st.session_state.results = results
    st.session_state.rejected = rejected
    st.session_state.cv_count = len(cv_files)
    st.session_state.profile = profile
    st.session_state.jd_llm_data = jd_llm_data
    st.session_state.use_llm_mode = use_llm
    st.session_state.cv_files_map = {f.name: (f.getvalue(), f.name.split('.')[-1].lower()) for f in cv_files}

st.divider()

# ── Render Results ───────────────────────────────────────────
if st.session_state.results is not None:
    results = st.session_state.results
    rejected = st.session_state.rejected
    cv_count = st.session_state.cv_count
    profile = st.session_state.profile
    jd_llm_data = st.session_state.jd_llm_data
    eval_time = st.session_state.get("eval_time")

    if eval_time is not None:
        eval_minutes = round(eval_time / 60, 1)
        min_unit = "minute" if eval_minutes == 1.0 else "minutes"
        st.caption(f"⏱️ **Total time {eval_minutes} {min_unit} for {cv_count} CVs** ({eval_time:.1f}s)")

    # ── How JD was interpreted ──────────────────────────────
    if profile is not None:
        with st.expander("🔎 How this Job Description was interpreted", expanded=False):
            c1, c2, c3 = st.columns(3)
            c1.metric("Detected Role", profile.title or "—")
            c2.metric("Seniority Level", profile.seniority.title())
            c3.metric(
                "Experience Wanted",
                f"{profile.effective_required_years:g} yrs"
                if profile.effective_required_years else "Not specified"
            )
            st.write(f"**Skills/Requirements ({len(profile.skills)}):** "
                     + (", ".join(sorted(profile.skills)) or "None detected"))
            st.write("**Field(s) of Study:** "
                     + (", ".join(sorted(profile.education_fields)) or "Not specified"))

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
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Total CVs", cv_count)
        c2.metric("🚫 Rejected", len(all_unsuitable_and_rejected))
        c3.metric("🎓 New Grads", sum(1 for r in ranked if r.get('is_new_grad')))
        c4.metric("✅ Highly Suitable", sum(1 for r in shortlisted if "Highly" in r.get('category', '')))
        c5.metric("🟢 Suitable", sum(1 for r in shortlisted if "Suitable" in r.get('category', '') and "Highly" not in r.get('category', '')))
        c6.metric("🟡 Moderate", sum(1 for r in shortlisted if "Moderate" in r.get('category', '')))

        st.divider()

        # ── Download CSV ─────────────────────────────────────
        all_export = shortlisted + all_unsuitable_and_rejected
        df_export = pd.DataFrame(all_export)[table_cols]
        df_export.columns = col_names

        st.download_button(
            "⬇️ Download All Results as CSV",
            df_export.to_csv(index=False),
            file_name="cv_results_llm.csv",
            mime="text/csv",
            use_container_width=True
        )

        st.divider()

        # ── 3. Candidate Deep Dive & PDF Preview ─────────────────
        st.header("🔍 Candidate Deep Dive & PDF Preview")
        st.caption("Inspect matched/missing skills, verified CV citations, and the original PDF document.")

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
                tab_breakdown, tab_evidence, tab_pdf = st.tabs([
                    "📊 Skills & Component Breakdown",
                    "📜 Verified Evidence & Citations",
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

                with tab_evidence:
                    st.markdown("#### 🔍 Exact Citations from Candidate Resume")
                    ev_list = cand.get("llm_evidence", [])
                    if ev_list:
                        for ev in ev_list:
                            with st.expander(f"🔹 **{ev.get('requirement', '').title()}** (Direct Evidence)", expanded=True):
                                st.info(f"❝ {ev.get('evidence', '')} ❞")
                    else:
                        st.write(f"Matched skills directly verified in CV text: `{cand.get('matched_skills', 'None')}`")

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



