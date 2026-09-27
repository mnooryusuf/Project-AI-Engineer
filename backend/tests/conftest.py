"""Test ini menguji aturan yang sengaja ditangani KODE, bukan prompt (lihat
laporan akhir Bab 6.5): pengenal pertanyaan, pagar data internal, validasi
SQL dan file, serta konfigurasi. Tidak butuh Ollama maupun database.

Jalankan dari direktori backend/:
    .venv/bin/pip install -r requirements-dev.txt
    .venv/bin/python -m pytest
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
