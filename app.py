"""
Travel Planner - Root Streamlit Entrypoint Wrapper.
The full frontend UI application is segregated in `frontend/app.py`.
To launch directly:
    streamlit run frontend/app.py
"""
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Execute frontend/app.py
frontend_app_path = ROOT_DIR / "frontend" / "app.py"
with open(frontend_app_path, "r", encoding="utf-8") as f:
    code = compile(f.read(), str(frontend_app_path), "exec")
    exec(code, globals())
