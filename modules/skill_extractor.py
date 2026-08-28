# modules/skill_extractor.py
import re
import spacy

nlp = spacy.load("en_core_web_md")

STOPWORDS = {
    # Generic HR / JD language
    "skills", "experience", "mentoring", "knowledge", "ability",
    "understanding", "familiar", "exposure", "proficiency", "expertise",
    "background", "capability", "competency", "working", "strong",
    "good", "excellent", "hands", "years", "year", "month", "months",
    "team", "teams", "work", "job", "role", "position", "candidate",
    "requirement", "requirements", "responsibilities", "responsibility",
    "description", "looking", "seeking", "required", "preferred",
    "plus", "bonus", "etc", "use", "using", "used", "able", "must",
    "need", "needs", "well", "also", "new", "high", "level", "based",
    "related", "field", "area", "areas", "type", "types", "way",
    "best", "great", "key", "core", "main", "real", "set", "sets",
    "time", "day", "days", "week", "project", "projects", "task",
    "tasks", "management", "manager", "lead", "leader", "senior",
    "junior", "intern", "internship", "company", "organization",
    "client", "clients", "customer", "customers", "service", "services",
    "solution", "solutions", "product", "products", "system", "systems",
    "application", "applications", "platform", "platforms", "tool",
    "tools", "process", "processes", "method", "methods", "approach",
    "communication", "collaboration", "problem", "problems", "solving",
    "space", "science", "survey", "data", "other", "with", "gnu",
    "octave", "topcat", "sdss", "wise", "astronomical",
    # FIX: common words that were leaking into skills via capitalization
    "figure", "table", "section", "chapter", "page", "note", "see",
    "ref", "include", "includes", "including", "such", "like", "per",
    "via", "both", "each", "their", "have", "has", "had", "been",
    "being", "will", "would", "could", "should", "may", "might",
    "january", "february", "march", "april", "june", "july",
    "august", "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct",
    "nov", "dec", "present", "current",
    # FIX: logical / boolean words extracted by slash splitting
    "or", "and", "not", "but", "for", "from", "into", "onto",
    "over", "under", "up", "down", "in", "out", "on", "off",
    # FIX: short all-caps / mixed-caps tokens that are common in CVs
    # but are never skills. Needed now that Steps 2-4 actually run:
    # the acronym and internal-caps rules below would otherwise let
    # these through (e.g. "BSc" satisfies the internal-caps rule).
    "cv", "pdf", "doc", "ltd", "inc", "pvt", "llc", "llp", "co",
    "usa", "uk", "uae", "ksa", "pk", "eu", "dob", "cnic", "nic",
    "gpa", "cgpa", "phone", "email", "www", "com", "org", "net",
    "bsc", "msc", "bs", "ms", "be", "me", "phd", "mba", "bba", "llb",
    "mphil", "matric", "fsc", "ics", "hssc", "sscbe",
    "education", "profile", "objective", "summary", "certifications",
    "certification", "awards", "achievements", "languages",
    "references", "reference", "interests", "hobbies", "contact",
    "address", "nationality", "gender", "linkedin", "github.com",
}

# ── Short tokens that ARE real skills ────────────────────────
# NOISE_PATTERNS kills anything matching ^[a-z]{1,2}$ to suppress
# stray single letters. These few are genuine and high-signal, and
# without them "AI/ML" (Step 3) contributes nothing at all.
# NOTE: "c", "r" and "go" are deliberately NOT here — they collide
# with ordinary prose too often to be worth the false positives, so
# those three KNOWN_SKILLS entries remain unreachable by design.
SHORT_SKILL_ALLOWLIST = {"ai", "ml", "js", "ts", "qa", "bi"}

# FIX: Words that are purely structural / grammatical — never skills
NOISE_PATTERNS = re.compile(
    r'^\d+$'                          # pure numbers
    r'|^\d{4}$'                       # year like 2023
    r'|^\d+[\.\-]\d+$'               # version-like 3.10, 2-5
    r'|^[a-z]{1,2}$'                 # single/double letters
    r'|^(https?|www)\b'              # URLs
)

# FIX: Slash pairs that should NOT be split
SLASH_STOPWORDS = {
    "and/or", "i/o", "b/w", "r/w", "n/a", "w/o", "w/",
    "mr/ms", "he/she", "him/her", "his/her",
}

KNOWN_SKILLS = {
    # ── Programming Languages ────────────────────────────
    "python", "java", "javascript", "typescript", "c", "c++", "c#",
    "ruby", "php", "swift", "kotlin", "go", "rust", "scala", "r",
    "matlab", "perl", "bash", "shell", "powershell", "golang",
    "spring boot", "spring mvc", "spring security",
    "hibernate", "jpa", "maven", "gradle", "junit",
    "tomcat", "swagger", "oauth2", "jwt", "websocket",
    "kafka", "microservices",

    # ── Web Development ──────────────────────────────────
    "html", "css", "react", "angular", "vue", "nodejs", "node.js",
    "django", "flask", "fastapi", "spring", "laravel", "express",
    "jquery", "bootstrap", "tailwind", "rest api", "graphql",
    "next.js", "nuxt.js", "webpack",

    # ── Data Science & AI ────────────────────────────────
    "machine learning", "deep learning", "natural language processing",
    "nlp", "computer vision", "data science", "data analysis",
    "data engineering", "big data", "data mining", "data visualization",
    "artificial intelligence", "neural networks", "transformers",
    "reinforcement learning", "feature engineering", "predictive modeling",
    "statistical modeling", "time series", "transfer learning",

    # ── ML / DL Frameworks ───────────────────────────────
    "tensorflow", "pytorch", "keras", "scikit-learn", "sklearn",
    "pandas", "numpy", "matplotlib", "seaborn", "plotly",
    "hugging face", "spacy", "nltk", "opencv", "xgboost", "lightgbm",
    "catboost", "yolo", "bert", "gpt", "llm", "stable diffusion",
    "langchain", "llama", "fastai", "onnx", "tensorrt",

    # ── Computer Vision ──────────────────────────────────
    "image processing", "object detection", "image segmentation",
    "face recognition", "optical flow", "3d reconstruction",

    # ── Databases ────────────────────────────────────────
    "sql", "mysql", "postgresql", "mongodb", "redis", "oracle",
    "sqlite", "cassandra", "elasticsearch", "firebase", "dynamodb",
    "nosql", "neo4j", "influxdb",
    "sql server", "mssql", "pl/sql", "plsql", "mariadb", "couchbase",
    "snowflake", "bigquery", "redshift", "stored procedures",
    "query optimization", "database administration", "dba",
    "data warehouse", "data warehousing", "replication", "sharding",
    "normalization", "database design", "etl",

    # ── Mobile Development ───────────────────────────────
    "flutter", "dart", "react native", "swiftui", "jetpack compose",
    "objective-c", "ionic", "xamarin", "android sdk", "cocoapods",
    "android", "ios",

    # ── Cloud & DevOps ───────────────────────────────────
    "aws", "azure", "gcp", "google cloud", "docker", "kubernetes",
    "jenkins", "git", "github", "gitlab", "ci/cd", "terraform",
    "ansible", "linux", "unix", "devops", "mlops", "airflow",

    # ── Tools & Platforms ────────────────────────────────
    "jupyter", "jupyter notebook", "vs code", "pycharm", "intellij",
    "android studio", "xcode", "postman", "jira", "confluence",
    "excel", "power bi", "tableau", "sap", "erp", "figma",
    "adobe xd", "photoshop", "illustrator",

    # ── Embedded & Hardware ──────────────────────────────
    "embedded systems", "arduino", "raspberry pi", "fpga",
    "microcontroller", "teensy", "rtos", "vhdl", "verilog",
    "iot", "robotics", "ros",

    # ── Science Tools ────────────────────────────────────
    "astropy", "topcat", "sdss", "wise",

    # ── Methodologies ────────────────────────────────────
    "agile", "scrum", "kanban", "tdd", "bdd", "ci cd",
    "rest", "soap", "api development",

    # ── Soft Skills ──────────────────────────────────────
    "project management", "leadership", "teamwork",
    "problem solving", "critical thinking", "time management",
    "presentation", "communication",

    # ── LLM / GenAI stack ────────────────────────────────
    # The guard in _looks_technical() deliberately rejects bare
    # Capitalized prose words, so single-cap product names only get
    # picked up if they are listed here. These were all invisible.
    "streamlit", "gradio", "openai", "anthropic", "gemini", "claude",
    "ollama", "vllm", "mistral", "llama index", "llamaindex",
    "rag", "retrieval augmented generation", "vector database",
    "vector search", "embeddings", "pinecone", "chromadb", "chroma",
    "faiss", "weaviate", "qdrant", "milvus", "pgvector",
    "prompt engineering", "fine-tuning", "fine tuning", "lora", "peft",
    "quantization", "diffusers", "whisper", "langgraph", "llamafile",
    "semantic search", "agents", "function calling", "mcp",

    # ── Modern web / backend ─────────────────────────────
    "svelte", "remix", "astro", "vite", "nestjs", "nest.js",
    "redux", "zustand", "tanstack", "shadcn", "material ui", "mui",
    "sass", "scss", "less", "storybook", "trpc", "prisma", "drizzle",
    "supabase", "appwrite", "socket.io", "grpc", "protobuf",
    "rabbitmq", "celery", "nginx", "apache", "serverless",
    "mern", "mean", "lamp", "jamstack",

    # ── Testing / QA ─────────────────────────────────────
    "jest", "vitest", "cypress", "playwright", "selenium", "appium",
    "pytest", "unittest", "mocha", "chai", "testing library",

    # ── DevOps / observability ───────────────────────────
    "github actions", "gitlab ci", "circleci", "travis ci", "argocd",
    "helm", "prometheus", "grafana", "datadog", "sentry", "splunk",
    "cloudformation", "pulumi", "vagrant", "openshift", "svn",
    "bitbucket", "mercurial",

    # ── Data / MLOps ─────────────────────────────────────
    "mlflow", "kubeflow", "dvc", "wandb", "weights and biases",
    "dbt", "spark", "pyspark", "hadoop", "hive", "flink", "databricks",
    "sagemaker", "vertex ai", "azure ml", "great expectations",
    "polars", "duckdb", "streamlit cloud",
}

# ── Synonym canonicalization ─────────────────────────────────
# Collapses different spellings of the SAME skill to one canonical
# form, on both the JD and CV side, BEFORE the semantic matcher runs.
#
# This is a scoring fix as much as an extraction one. Previously a CV
# listing "ML", "Machine Learning" and "machine-learning" produced
# three separate skills competing to match one JD skill, and a JD
# listing both "NLP" and "Natural Language Processing" counted the
# same requirement twice in the denominator. Canonicalizing first
# makes the JD skill set a set of distinct REQUIREMENTS.
SKILL_ALIASES = {
    "js": "javascript",
    "ts": "typescript",
    "ml": "machine learning",
    "dl": "deep learning",
    "ai": "artificial intelligence",
    "nlp": "natural language processing",
    "cv2": "opencv",
    "k8s": "kubernetes",
    "postgres": "postgresql",
    "psql": "postgresql",
    "node": "nodejs",
    "node.js": "nodejs",
    "nextjs": "next.js",
    "nuxtjs": "nuxt.js",
    "nest.js": "nestjs",
    "sklearn": "scikit-learn",
    "scikit learn": "scikit-learn",
    "hugging face": "huggingface",
    "hf": "huggingface",
    "tf": "tensorflow",
    "torch": "pytorch",
    "gcp": "google cloud",
    "ms sql": "sql server",
    "mssql": "sql server",
    "plsql": "pl/sql",
    "ci cd": "ci/cd",
    "cicd": "ci/cd",
    "restful api": "rest api",
    "restful apis": "rest api",
    "rest apis": "rest api",
    "apis": "rest api",
    "api": "rest api",
    "chroma": "chromadb",
    "llama index": "llamaindex",
    "fine tuning": "fine-tuning",
    "retrieval augmented generation": "rag",
    "weights and biases": "wandb",
    "mui": "material ui",
    "scss": "sass",
    "artificial intelligence": "artificial intelligence",
}


def canonicalize(skills) -> set:
    """Map every skill to its canonical form and drop the duplicates."""
    return {SKILL_ALIASES.get(s, s) for s in skills}


# ── Technology-token guard ───────────────────────────────────
# Steps 2-4 discover tokens that are NOT in KNOWN_SKILLS. Now that
# they receive case- and punctuation-preserving text they actually
# fire, and without a guard they absorb ordinary prose ("Sapphire",
# "Jamshoro", "Requirements", "Familiarity"). That is fatal on the JD
# side specifically: len(jd_skills) is the denominator of the match %,
# so every junk token silently lowers EVERY candidate's score.
#
# A discovered token is kept only if it looks like technology. This is
# deliberately precision-first — a real skill missed here costs one
# candidate some recall, but a junk JD token costs every candidate.

_INTERNAL_CAPS_RE = re.compile(r'^[A-Za-z][a-z0-9.]*[A-Z]')
_TECH_PUNCT_RE = re.compile(r'[A-Za-z0-9][+#]|[A-Za-z0-9][./][A-Za-z0-9]')
_ALNUM_MIX_RE = re.compile(r'^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9.\-]+$')
_ACRONYM_RE = re.compile(r'^[A-Z]{2,5}$')


def _looks_technical(token: str) -> bool:
    """
    True if a token found OUTSIDE the curated vocabulary still looks
    like a technology name rather than ordinary prose.

    Accepts, in order:
      KNOWN_SKILLS      → pandas, keras, tensorflow
      tech punctuation  → c++, c#, node.js, ci/cd
      letter+digit mix  → gpt-4, oauth2, s3, llama3
      short acronym     → NLP, AWS, RAG, YOLO, SVN  (2-5 caps; the
                          5-char ceiling is what keeps ALL-CAPS
                          section headings like EDUCATION out)
      internal capital  → PyTorch, NumPy, FastAPI, PostgreSQL, iOS

    Rejects single-capital prose words, which is why product names
    such as "Streamlit" or "Gemini" still need a KNOWN_SKILLS entry.
    """
    if token.lower() in KNOWN_SKILLS:
        return True
    if _TECH_PUNCT_RE.search(token):
        return True
    if _ALNUM_MIX_RE.match(token):
        return True
    if _ACRONYM_RE.match(token):
        return True
    if _INTERNAL_CAPS_RE.match(token):
        return True
    return False


def _is_noise(token: str) -> bool:
    """Return True if token should never be treated as a skill."""
    t = token.strip().lower()
    if t in SHORT_SKILL_ALLOWLIST:
        return False
    return (
        not t
        or t in STOPWORDS
        or bool(NOISE_PATTERNS.match(t))
        or len(t) < 2
        or len(t.split()) > 4
    )


def extract_skills(text: str) -> set:
    skills = set()
    text_lower = text.lower()

    # ── Step 1: Match known skills (word-boundary safe) ──
    for skill in KNOWN_SKILLS:
        pattern = r'(?<![a-z\d])' + re.escape(skill) + r'(?![a-z\d])'
        if re.search(pattern, text_lower):
            skills.add(skill)

    # ── Step 2: Capitalized technical words ─────────────
    # Catches PyTorch, TensorFlow, OpenCV, NumPy, YOLO etc.
    # FIX: skip pure digits and year-like tokens (2023, 2024)
    # FIX: the old `len(word) > 3` rule was suppressing "In"/"At"/"By"
    # but also every 3-letter acronym that matters here — NLP, AWS,
    # SQL, RAG, GPT, SVN, ETL. _looks_technical() now does that job
    # properly, so the length floor drops to 2.
    cap_pattern = re.findall(
        r'\b[A-Z][a-zA-Z0-9]*(?:[./][a-zA-Z0-9]+)*\b', text
    )
    for word in cap_pattern:
        # Slash compounds are Step 3's job. Leaving them here too would
        # emit "AI/ML" alongside "ai" and "ml" — a duplicate that adds
        # nothing but still inflates the JD denominator. Dotted names
        # (Node.js, Next.js) are single names and DO belong here.
        if '/' in word:
            continue
        w = word.lower()
        if len(word) >= 2 and not _is_noise(w) and _looks_technical(word):
            skills.add(w)

    # ── Step 3: Slash-separated skills ──────────────────
    # Catches TensorFlow/Keras, C/C++ but NOT "and/or", "i/o"
    slash_pattern = re.findall(r'\b\w[\w.]*\/\w[\w.]*\b', text)
    for item in slash_pattern:
        if item.lower() in SLASH_STOPWORDS:
            continue
        # Only split if both sides look like tech tokens (len > 1, not pure stopword)
        parts = item.split('/')
        if all(len(p) > 1 for p in parts):
            for part in parts:
                part = part.strip()
                p = part.lower()
                if not _is_noise(p) and _looks_technical(part):
                    skills.add(p)

    # ── Step 4: Bracket content ──────────────────────────
    # Catches: Python (Pandas, NumPy, OpenCV)
    # FIX: skip brackets that look like date ranges "(2020-2023)"
    # or experience annotations "(3 years)" 
    bracket_pattern = re.findall(r'\(([^)]{2,80})\)', text)
    for group in bracket_pattern:
        # Skip if the bracket group is mostly digits/dates
        digit_ratio = sum(c.isdigit() for c in group) / max(len(group), 1)
        if digit_ratio > 0.4:
            continue
        # FIX: split on '/' too, so "(Django/Flask)" yields two real
        # skills instead of the junk compound "django/flask" (which
        # would pass the tech-punctuation rule and inflate the JD
        # denominator by one).
        items = re.split(r'[,;/]', group)
        for item in items:
            item = item.strip()
            item_clean = item.lower()
            if not _is_noise(item_clean) and _looks_technical(item):
                skills.add(item_clean)

    # ── Step 5: Final noise sweep ────────────────────────
    cleaned = set()
    for skill in skills:
        skill = skill.strip()
        if not _is_noise(skill):
            cleaned.add(skill)

    # ── Step 6: Canonicalize synonyms ────────────────────
    # Done last so every path (vocabulary, capitals, slashes,
    # brackets) lands on the same canonical form.
    return canonicalize(cleaned)