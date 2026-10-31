"""Stable paths shared by the organized test suites."""
from pathlib import Path
TESTS_ROOT=Path(__file__).resolve().parent
BACKEND_ROOT=TESTS_ROOT.parent
REPO_ROOT=BACKEND_ROOT.parent
