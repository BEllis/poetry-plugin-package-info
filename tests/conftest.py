from pathlib import Path
from typing import Protocol

import pytest
from poetry.config.config import Config
from poetry.core.packages.package import Package
from poetry.core.poetry import Poetry
from poetry.factory import Factory
from poetry.layouts import layout
from poetry.repositories import Repository


class ProjectFactory(Protocol):
    def __call__(
        self: "ProjectFactory",
        name: str,
        dependencies: dict[str, str] | None = None,
        dev_dependencies: dict[str, str] | None = None,
        pyproject_content: str | None = None,
        poetry_lock_content: str | None = None,
        *,
        install_deps: bool = True,
    ) -> Poetry:
        ...


@pytest.fixture()
def project_factory(
    tmp_path: Path,
    config: Config,
    repo: Repository,
    installed: Repository,
    default_python: str,
) -> ProjectFactory:
    def _factory(
        name: str,
        dependencies: dict[str, str] | None = None,
        dev_dependencies: dict[str, str] | None = None,
        pyproject_content: str | None = None,
        poetry_lock_content: str | None = None,
        *,
        install_deps: bool = True,
    ) -> Poetry:
        project_dir = tmp_path / f"poetry-fixture-{name}"
        dependencies = dependencies or {}
        dev_dependencies = dev_dependencies or {}

        if pyproject_content:
            project_dir.mkdir(parents=True, exist_ok=True)
            with project_dir.joinpath("pyproject.toml").open(
                "w",
                encoding="utf-8",
            ) as f:
                f.write(pyproject_content)
        else:
            layout("src")(
                name,
                "0.1.0",
                author="PyTest Tester <mc.testy@testface.com>",
                readme_format="md",
                python=default_python,
                dependencies=dict(dependencies),
                dev_dependencies=dict(dev_dependencies),
            ).create(project_dir, with_tests=False)

        if poetry_lock_content:
            lock_file = project_dir / "poetry.lock"
            lock_file.write_text(data=poetry_lock_content, encoding="utf-8")

        poetry = Factory().create_poetry(project_dir)

        poetry.set_config(config)

        if install_deps:
            for deps in [dependencies, dev_dependencies]:
                for name, version in deps.items():
                    pkg = Package(name, version)
                    repo.add_package(pkg)
                    installed.add_package(pkg)

        return poetry

    return _factory
