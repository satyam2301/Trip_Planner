
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import os
import streamlit as st

# Sync Streamlit Cloud secrets into os.environ before child modules load
try:
    if hasattr(st, "secrets"):
        for _sec_k, _sec_v in st.secrets.items():
            if isinstance(_sec_v, (str, int, float, bool)):
                os.environ[_sec_k] = str(_sec_v)
except Exception:
    pass

# Execute frontend/app.py
frontend_app_path = ROOT_DIR / "frontend" / "app.py"
with open(frontend_app_path, "r", encoding="utf-8") as f:
    code = compile(f.read(), str(frontend_app_path), "exec")
    exec(code, globals())
