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
HEADLESS = True

FORMS = {"v1": APP_DIR / "order_v1.html", "v2": APP_DIR / "order_v2.html"}
DEMOS = {"clean": DATA_DIR / "demo_clean.json", "bad": DATA_DIR / "demo_bad.json"}

# condition -> (form version, demo name)
CONDITIONS = {
    "normal": ("v1", "clean"),
    "drift": ("v2", "clean"),
    "bad_demo": ("v1", "bad"),
}

# config -> (skeptic skill compile, verifier on)
CONFIGS = {
    "A": {"skeptic": False, "verify": False},
    "B": {"skeptic": False, "verify": True},
    "C": {"skeptic": True, "verify": True},
}
