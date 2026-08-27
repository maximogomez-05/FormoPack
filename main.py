"""Punto de entrada de pruebas para Formopack Express."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from tests.test_auth import main as run_tests

if __name__ == "__main__":
    run_tests()
