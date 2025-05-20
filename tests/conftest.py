import sys
import os

# Add the project root to sys.path so tests can import project modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest

@pytest.fixture
def example_fixture():
    return "example"