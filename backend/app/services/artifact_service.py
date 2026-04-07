import os
import json
from datetime import datetime

ARTIFACTS_DIR = "./artifacts"

def ensure_dir():
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)

def store_artifact(run_id: int, description: str, raw_response: str):
    """Save the raw Physis response for a run to disk for debugging."""
    ensure_dir()
    artifact = {
        "run_id": run_id,
        "description": description,
        "raw_response": raw_response,
        "saved_at": datetime.utcnow().isoformat()
    }
    path = os.path.join(ARTIFACTS_DIR, f"run_{run_id}.json")
    with open(path, "w") as f:
        json.dump(artifact, f, indent=2)
    return path

def load_artifact(run_id: int) -> dict | None:
    path = os.path.join(ARTIFACTS_DIR, f"run_{run_id}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)
