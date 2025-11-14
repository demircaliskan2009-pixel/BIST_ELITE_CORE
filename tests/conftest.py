import os, sys

# Repo kökünü (içinde 'src/' olan dizini) sys.path'e ekle
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
