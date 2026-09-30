# modules/cleaner.py
import re

# def clean_text(text):
#     text = text.lower()
#     text = re.sub(r'\s+', ' ', text)
#     text = re.sub(r'[^\w\s]', ' ', text)
#     return text.strip()


def clean_text(text):
    """
    Clean text while preserving degree abbreviations
    """
    # Now convert to lowercase for case-insensitive matching
    text = text.lower()
    
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove most punctuation but keep spaces and alphanumeric
    text = re.sub(r'[^\w\s]', ' ', text)
    
    # Clean up any double spaces created
    text = re.sub(r'\s+', ' ', text).strip()

    return text


# Punctuation that carries meaning inside technology names and must
# therefore survive normalization. Everything else becomes a space.
_SKILL_SAFE_PUNCT = r'+#./\-()_,;'


def normalize_for_skills(text: str) -> str:
    """
    Light normalization for skill extraction ONLY.

    clean_text() lowercases and strips every non-word character, which
    silently disabled most of extract_skills():
      - Step 2 looks for [A-Z]  → no uppercase survived → dead
      - Step 3 splits on '/'    → no slashes survived   → dead
      - Step 4 reads '( ... )'  → no brackets survived  → dead
      - Step 1 could never match any vocabulary entry containing
        punctuation: c++, c#, node.js, next.js, scikit-learn, ci/cd,
        objective-c, pl/sql.

    This keeps case and technology punctuation so all four steps work.
    clean_text() is still the right input for education matching, which
    depends on its degree-abbreviation normalization — do not swap them.
    """
    text = re.sub(r'[^\w\s' + _SKILL_SAFE_PUNCT + r']', ' ', text)
    # Collapse runs of spaces/tabs but keep newlines, so bracket and
    # slash patterns can't span unrelated lines.
    return re.sub(r'[ \t ]+', ' ', text).strip()