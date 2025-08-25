# tests/conftest.py
import os, sys
from pathlib import Path

# 项目根目录：tests/ 的上一级
ROOT = Path(__file__).resolve().parents[1]
DJANGO_DIR = ROOT / "apps" / "web-django"

# 关键：把 Django 项目目录放到 sys.path 顶部
sys.path.insert(0, str(DJANGO_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web.settings")

try:
    import django
    django.setup()
except Exception:
    pass
