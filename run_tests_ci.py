import subprocess
import os

env = os.environ.copy()
env["GITHUB_ACTIONS"] = "true"
env["CI"] = "true"
# remove local envs
env.pop("META_APP_ID", None)
env.pop("META_APP_SECRET", None)
env.pop("META_SHORT_LIVED_TOKEN", None)

subprocess.run(["uv", "run", "pytest", "tests/test_meta_client.py", "-v"], env=env)
