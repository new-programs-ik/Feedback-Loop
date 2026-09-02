"""course_rules.py - map raw ratings-source rows to course labels and session kinds.

MIRROR: analysis/ratings_data.py carries the same rules for the local study scripts.
The worker cannot import analysis/ (only this package ships in the Docker image), so the
rules live twice - edit BOTH files together.
"""

# Cohort text -> the course label a PM would name. FIRST MATCH WINS: cohort strings often glue
# several programmes together ("Agentic AI SWE Deprecated, Forward Deployed Engineering - ...").
COURSE_RULES = [
    ("PwC x IK Agentic AI Accelerator", ["pwc"]),
    ("FDE (Forward Deployed Engineering)", ["forward deployed engineering", "fde program"]),
    ("Advanced ML Program", ["advanced machine learning"]),
    ("ML Flagship (IND)", ["machine learning flagship"]),
    ("ML Program", ["machine learning program"]),
    ("AI Data Science SwitchUp", ["ai data science switchup"]),
    ("Transformative GenAI", ["transformative genai"]),
    ("Applied Agentic AI", ["applied agentic ai", "agentic ai"]),
]


def course_of(cohort: str, type_: str) -> str:
    """The course label for a row, from its Cohorts text (falling back to the session Type)."""
    text = (cohort or "").lower()
    for label, keys in COURSE_RULES:
        if any(k in text for k in keys):
            return label
    t = (type_ or "").lower()
    if "genai" in t:
        return "Transformative GenAI"
    if "agentic" in t:
        return "Applied Agentic AI"
    if "switchup" in t or "mlsu" in t:
        return "ML SwitchUp (unmapped cohort)"
    return "Other / unmapped"


def kind_of(type_: str) -> str:
    """Live Class vs Test Review, from the source's Type column."""
    t = (type_ or "").lower()
    if "review" in t:
        return "Test Review"
    if "live" in t:
        return "Live Class"
    return "Other"
