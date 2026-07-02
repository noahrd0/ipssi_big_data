import sys
from pathlib import Path

# Permet d'importer db.* et filters.* depuis dags/
ROOT = Path(__file__).resolve().parents[1]
DAGS = ROOT / "dags"
if str(DAGS) not in sys.path:
    sys.path.insert(0, str(DAGS))

from db.mongo_client import get_db  # noqa: E402

__all__ = ["get_db"]
