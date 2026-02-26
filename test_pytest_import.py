import os
os.environ.pop("OPENAI_API_KEY", None)

import pytest

class DummyConfig:
    pass

pytest.main(["tests/conftest.py", "--collect-only"])
