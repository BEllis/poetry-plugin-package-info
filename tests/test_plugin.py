import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from cleo.io.null_io import NullIO
from freezegun import freeze_time
from poetry.factory import Factory
from poetry.poetry import Poetry

from poetry_plugin_package_info.plugin import (
    GeneratePackageInfoApplicationPlugin,
)
from tests.helpers import PoetryTestApplication


def get_fixture_root() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture()
def fixture_root() -> Path:
    return get_fixture_root()


@pytest.fixture(
    params=[
        fixture_dir.name
        for fixture_dir in get_fixture_root().iterdir()
        if fixture_dir.is_dir()
    ],
)

def fixture_path(
    request: pytest.FixtureRequest,
    fixture_root: Path,
) -> Iterator[Path]:
    fixture_path = fixture_root / request.param
    git_file = fixture_path / ".git"

    # Rename _gitignore to .gitignore
    if (fixture_path / "_gitignore").exists():
        (fixture_path / "_gitignore").rename(fixture_path / ".gitignore")

    # Backup index file
    if (fixture_path / "_git" / "index").exists():
        shutil.copy(
            fixture_path / "_git" / "index",
            fixture_path / "_git" / "index_bak",
        )
        git_file.unlink(missing_ok=True)

    # Add .git file if needed
    if (fixture_path / "_git").exists():
        git_file.write_text(f"gitdir: {fixture_path}/_git\n")

    yield fixture_path

    # Delete .git file (if present)
    git_file.unlink(missing_ok=True)

    # Restore index backup (and tidy)
    if (fixture_path / "_git" / "index_bak").exists():
        (fixture_path / "_git" / "index").unlink()
        shutil.copy(
            fixture_path / "_git" / "index_bak",
            fixture_path / "_git" / "index",
        )
    (fixture_path / "_git" / "index_bak").unlink(missing_ok=True)

    # Rename .gitignore to _gitignore
    if (fixture_path / ".gitignore").exists():
        (fixture_path / ".gitignore").rename(fixture_path / "_gitignore")

@pytest.fixture()
def poetry(
    fixture_path: Path,
) -> Poetry:
    yield Factory().create_poetry(fixture_path)


@pytest.fixture()
def app(poetry: Poetry) -> PoetryTestApplication:
    return PoetryTestApplication(poetry)


def test_plugin(app: PoetryTestApplication, fixture_path: Path) -> None:
    with freeze_time("2023-06-09T01:23:45.678Z"):
        plugin = GeneratePackageInfoApplicationPlugin()
        plugin.activate(app)
        if app.event_dispatcher is None:
            raise ValueError
        plugin.generate_package_info(NullIO())

        expected_file = [file for file in fixture_path.glob('**/*.py.expected')][0]
        actual_file = Path(str(expected_file)[:-9])

        assert expected_file.read_text() == actual_file.read_text()