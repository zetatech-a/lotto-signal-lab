import tomllib
from pathlib import Path

import lotto_lab


def test_runtime_version_matches_project_metadata() -> None:
    pyproject_path = Path(__file__).parents[1] / "pyproject.toml"
    with pyproject_path.open("rb") as pyproject_file:
        project_version = tomllib.load(pyproject_file)["project"]["version"]

    assert lotto_lab.__version__ == project_version
