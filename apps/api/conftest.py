# conftest.py — pytest configuration for apps/api/
# Ensures the frankenledger package is importable when running from apps/api/
import sys
import pathlib

# tests/ directory is at repo root; add apps/api/ so frankenledger is importable
sys.path.insert(0, str(pathlib.Path(__file__).parent))
