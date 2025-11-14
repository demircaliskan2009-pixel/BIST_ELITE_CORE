import os, sys
# repo köküne git
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
# pytest çalışırken src yolunu sys.path'e en öne ekle
if SRC not in sys.path:
    sys.path.insert(0, SRC)
