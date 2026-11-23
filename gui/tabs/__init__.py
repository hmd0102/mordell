"""Các tab chức năng của giao diện."""
from .encryption_tab import EncryptionTab
from .home_tab import HomeTab
from .image_benchmark_tab import ImageBenchmarkTab
from .sbox_benchmark_tab import SboxBenchmarkTab
from .sbox_compare_tab import SboxCompareTab

__all__ = [
    "HomeTab",
    "EncryptionTab",
    "SboxBenchmarkTab",
    "SboxCompareTab",
    "ImageBenchmarkTab",
]
