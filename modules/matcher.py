# modules/matcher.py
import re

# Comprehensive aliases for technical terms so exact matching handles standard variations
SKILL_TEXT_PATTERNS = {
    "artificial intelligence": [r"\b(?:artificial\s+intelligence|ai)\b"],
    "machine learning": [r"\b(?:machine\s+learning|ml)\b"],
    "deep learning": [r"\b(?:deep\s+learning|dl)\b"],
    "natural language processing": [r"\b(?:natural\s+language\s+processing|nlp)\b"],
    "computer vision": [r"\b(?:computer\s+vision|opencv|cv2)\b"],
    "tensorflow": [r"\b(?:tensorflow|tf)\b"],
    "pytorch": [r"\b(?:pytorch|torch)\b"],
    "scikit-learn": [r"\b(?:scikit[\s-]learn|sklearn)\b"],
    "postgresql": [r"\b(?:postgresql|postgres|psql)\b"],
    "sql server": [r"\b(?:sql\s*server|mssql)\b"],
    "rest api": [r"\b(?:rest(?:ful)?\s*apis?|rest\s*api|apis?)\b"],
    "ci/cd": [r"\b(?:ci[\s/]?cd|continuous\s+integration)\b"],
    "huggingface": [r"\b(?:hugging[\s-]?face|huggingface|transformers)\b"],
    "rag": [r"\b(?:rag|retrieval[\s-]augmented[\s-]generation)\b"],
    "fine-tuning": [r"\b(?:fine[\s-]?tuning|finetuning|peft|lora)\b"],
    "nodejs": [r"\b(?:node(?:\.js)?|nodejs)\b"],
    "node.js": [r"\b(?:node(?:\.js)?|nodejs)\b"],
    "react": [r"\b(?:react(?:\.js)?|reactjs|react-native|react\s+native)\b"],
    "vue": [r"\b(?:vue(?:\.js)?|vuejs)\b"],
    "angular": [r"\b(?:angular(?:\.js)?|angularjs)\b"],
    "golang": [r"\b(?:golang|go\s+language)\b"],
    "javascript": [r"\b(?:javascript|js)\b"],
    "typescript": [r"\b(?:typescript|ts)\b"],
    "kubernetes": [r"\b(?:kubernetes|k8s)\b"],
    "google cloud": [r"\b(?:google\s+cloud|gcp)\b"],
    "django": [r"\b(?:django)\b"],
    "flask": [r"\b(?:flask)\b"],
    "fastapi": [r"\b(?:fastapi)\b"],
    "python": [r"\b(?:python)\b"],
    "git": [r"\b(?:git|github|gitlab)\b"],
    "mysql": [r"\b(?:mysql)\b"],
    "streamlit": [r"\b(?:streamlit)\b"],
    "gemini": [r"\b(?:gemini)\b"],
    "openai": [r"\b(?:openai|chatgpt|gpt-?4|gpt-?3)\b"],
    "svn": [r"\b(?:svn|subversion)\b"],
    "vector search": [r"\b(?:vector\s+search|vector\s+database|embeddings?|pinecone|chromadb|faiss|qdrant)\b"],
    "supervised learning": [r"\b(?:supervised\s+learning)\b"],
    "neural networks": [r"\b(?:neural\s+networks?|anns?|cnns?|rnns?)\b"],
}


COMPOSITE_STACKS = {
    "mern": [
        ["mongodb", "mongoose"],
        ["express", "express.js", "expressjs"],
        ["react", "react.js", "reactjs", "react-native", "react native"],
        ["nodejs", "node.js", "node"]
    ],
    "mean": [
        ["mongodb", "mongoose"],
        ["express", "express.js", "expressjs"],
        ["angular", "angular.js", "angularjs"],
        ["nodejs", "node.js", "node"]
    ],
    "lamp": [
        ["linux"],
        ["apache"],
        ["mysql", "mariadb"],
        ["php", "python", "perl"]
    ],
    "rag": [
        ["vector search", "vector database", "pinecone", "chromadb", "faiss", "qdrant", "weaviate", "embeddings", "pgvector"],
        ["llm", "langchain", "llamaindex", "llama index", "openai", "gemini", "claude", "transformers", "huggingface", "gpt", "rag", "prompt engineering", "langgraph"]
    ]
}


def is_skill_in_text(skill: str, text: str = "", cv_skills: set = None) -> bool:
    """
    Returns True IF AND ONLY IF the skill or its valid alias is genuinely 
    present in the CV text or detected skills. Case-insensitive.
    """
    if not skill:
        return False
        
    s_clean = skill.strip().lower()

    if s_clean == "react":
        from modules.skill_extractor import _is_react_skill
        if cv_skills and "react" in cv_skills:
            return True
        return _is_react_skill(text) if text else False
    
    # Check cv_skills set
    if cv_skills and s_clean in cv_skills:
        return True

    # Check composite stack deduction (e.g. Mongo + Express + React + Node -> MERN)
    if s_clean in COMPOSITE_STACKS:
        req_groups = COMPOSITE_STACKS[s_clean]
        if all(any(is_skill_in_text(sub, text=text, cv_skills=cv_skills) for sub in group) for group in req_groups):
            return True

    if not text:
        return False

    # Check dedicated regex pattern
    patterns = SKILL_TEXT_PATTERNS.get(s_clean)
    if patterns:
        for p in patterns:
            if re.search(p, text, re.IGNORECASE):
                return True
    else:
        # Generic word-boundary pattern
        escaped = re.escape(s_clean)
        if re.search(rf"\b{escaped}\b", text, re.IGNORECASE):
            return True
            
    return False


def match_skills(jd_skills, cv_skills, *args, **kwargs):
    """
    Match JD skills against CV skills with strict textual verification.
    Only skills that actually exist in the CV text/detected skills are credited.
    
    Returns (total_score, matched_jd_skills, quality_map).
    """
    if not jd_skills:
        return 0.0, set(), {}

    cv_text = kwargs.get("cv_text", "")
    if not cv_text and len(args) >= 1:
        cv_text = args[0]

    quality = {}
    matched_skills = set()

    for skill in jd_skills:
        s_norm = skill.strip().lower()
        if is_skill_in_text(s_norm, text=cv_text, cv_skills=cv_skills):
            quality[s_norm] = 1.0
            matched_skills.add(s_norm)
        else:
            quality[s_norm] = 0.0

    total_score = round(sum(quality.values()), 2)
    return total_score, matched_skills, quality

