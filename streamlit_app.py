"""Streamlit entrypoint for root deployments (Streamlit Community Cloud).
"""
import sys
from pathlib import Path

# Add dashboard directory to sys.path
dashboard_dir = Path(__file__).resolve().parent / "dashboard"
if str(dashboard_dir) not in sys.path:
    sys.path.insert(0, str(dashboard_dir))

# Execute dashboard/app.py
with open(dashboard_dir / "app.py") as f:
    code = compile(f.read(), str(dashboard_dir / "app.py"), "exec")
    exec(code, globals())
