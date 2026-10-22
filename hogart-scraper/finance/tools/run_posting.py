"""Service entrypoint using installed reporting dependencies and existing CRM credentials."""
import sys,runpy
from pathlib import Path
sys.path.insert(0,'/home/kocher.av/.report-venv/lib/python3.14/site-packages')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
runpy.run_path(str(Path(__file__).resolve().parents[1]/'post_confirmed.py'),run_name='__main__')
