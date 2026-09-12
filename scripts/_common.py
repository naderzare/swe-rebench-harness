from pathlib import Path
import hashlib, json, os, re, subprocess, sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUITE_PATH = ROOT / "configs" / "suites" / "hard20.json"
SUITE_PATH = Path(os.environ.get("REBENCH_SUITE", DEFAULT_SUITE_PATH))
if not SUITE_PATH.is_absolute():
    SUITE_PATH = ROOT / SUITE_PATH

# The evaluator captures test-runner output containing Unicode symbols. Force
# child Python processes to decode it consistently on Windows instead of using
# the legacy system code page.
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
TASKS_DIR = ROOT / "tasks"
RUNS_DIR = ROOT / "runs"
EVALUATOR_DIR = ROOT / "SWE-rebench-V2"

def load_suite():
    if not SUITE_PATH.is_file():
        raise FileNotFoundError(f"Suite file not found: {SUITE_PATH}")
    return json.loads(SUITE_PATH.read_text(encoding="utf-8"))

def suite_fingerprint(suite):
    canonical = json.dumps(suite, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

def sanitize(s):
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", s)

def run(cmd, cwd=None, check=True, capture=False):
    print("+", " ".join(map(str, cmd)))
    return subprocess.run(
        list(map(str, cmd)),
        cwd=str(cwd) if cwd else None,
        check=check,
        text=True,
        capture_output=capture,
    )

def docker_container_exists(name):
    p = subprocess.run(
        ["docker", "inspect", name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return p.returncode == 0

def public_image_name(image):
    prefix = "prime/primeintellect/"
    if image.startswith(prefix):
        return "docker.io/swerebenchv2/" + image[len(prefix):]
    return image

def repo_dir(repo):
    return repo.split("/")[-1]
