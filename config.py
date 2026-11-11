"""Central configuration for SkillBench."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"
DATA_DIR = ROOT / "data"
POS_DIR = DATA_DIR / "pos"
TRUTH_DIR = DATA_DIR / "truth"
RESULTS_DIR = ROOT / "results"
TRACES_DIR = RESULTS_DIR / "traces"
SKILL_CACHE_DIR = RESULTS_DIR / "skills"
CATALOG_PATH = APP_DIR / "catalog.json"

MODEL = "qwen3:8b"
TEMPERATURE = 0
SEED = 0
NUM_CTX = 8192  # Ollama's default window can silently truncate the agent prompt
MAX_STEPS = 30
MAX_FIX_ATTEMPTS = 2
VERIFIER_VERSION = "v2"  # v1 = single LLM judge (results/archive_v1); v2 = rules + LLM extraction + code diff
HEADLESS = True

FORMS = {"v1": APP_DIR / "order_v1.html", "v2": APP_DIR / "order_v2.html"}
DEMOS = {"clean": DATA_DIR / "demo_clean.json", "bad": DATA_DIR / "demo_bad.json"}
CORRECTIONS_PATH = DATA_DIR / "corrections.json"

# Dev POs were used while building the agent and verifier; held-out POs were written
# before verifier v2 and never used for tuning.
SPLITS = {
    "dev": [f"{i:03d}" for i in range(1, 21)],
    "heldout": [f"{i:03d}" for i in range(21, 29)],
}

# condition -> (form version, demo name, human correction applied to the skill or None)
CONDITIONS = {
    "normal": ("v1", "clean", None),
    "drift": ("v2", "clean", None),
    "bad_demo": ("v1", "bad", None),
    "good_correction": ("v1", "clean", "good"),
    "bad_correction": ("v1", "clean", "bad"),
}
CORE_CONDITIONS = ["normal", "drift", "bad_demo"]

# config -> (skeptic skill compile, verifier on)
CONFIGS = {
    "A": {"skeptic": False, "verify": False},
    "B": {"skeptic": False, "verify": True},
    "C": {"skeptic": True, "verify": True},
}
