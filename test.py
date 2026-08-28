import sys
sys.path.insert(0, 'd:/AI Trainee Projects/EMIS/cv_shortlister')
from modules.extractor import extract_text
from modules.experience import extract_experience_years
from modules.education import extract_degree_years

for label, path in [
    ("Ahsan",  "C:/Users/SCS-AI-HASSAN-AHMED/Downloads/Ahsan's CV FullStack.pdf"),
    ("Irfan",  "C:/Users/SCS-AI-HASSAN-AHMED/Downloads/Irfan Ali Al Full Stack Develop.pdf"),
]:
    try:
        with open(path, 'rb') as f:
            raw = extract_text(f, 'pdf')
        yrs   = extract_experience_years(raw)
        degs  = extract_degree_years(raw)
        print("%s: experience=%.1f yrs  |  degrees=%s" % (label, yrs, degs))
    except FileNotFoundError:
        print("%s: file not found, skipping" % label)
