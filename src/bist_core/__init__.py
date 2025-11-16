"""Top-level public API for bist_core."""
# DİKKAT: Göreli import kullanıyoruz; absolute 'from data import ...' KULLANMAYIN.
from .data import read_csv, register_dataset, load_registered_dataset
__all__ = ["read_csv", "register_dataset", "load_registered_dataset"]
