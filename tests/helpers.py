from typing import Any

from poetry.console.application import Application
from poetry.core.packages.package import Package
from poetry.factory import Factory
from poetry.installation.executor import Executor
from poetry.installation.operations.operation import Operation
from poetry.poetry import Poetry


class PoetryTestApplication(Application):  # type: ignore[misc]
    def __init__(self: "PoetryTestApplication", poetry: Poetry) -> None:
        super().__init__()
        self._poetry = poetry

    def reset_poetry(self: "PoetryTestApplication") -> None:
        poetry = self._poetry
        assert poetry
        self._poetry = Factory().create_poetry(poetry.file.path.parent)
        self._poetry.set_pool(poetry.pool)
        self._poetry.set_config(poetry.config)
        self._poetry.set_locker(poetry.locker)


class TestExecutor(Executor):  # type: ignore[misc]
    def __init__(
        self: "TestExecutor",
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)

        self._installs: list[Package] = []
        self._updates: list[Package] = []
        self._uninstalls: list[Package] = []

    @property
    def installations(self: "TestExecutor") -> list[Package]:
        return self._installs

    @property
    def updates(self: "TestExecutor") -> list[Package]:
        return self._updates

    @property
    def removals(self: "TestExecutor") -> list[Package]:
        return self._uninstalls

    def _do_execute_operation(
        self: "TestExecutor",
        operation: Operation,
    ) -> int:
        super()._do_execute_operation(operation)

        if not operation.skipped:
            getattr(self, f"_{operation.job_type}s").append(operation.package)

        return 0

    def _execute_install(self: "TestExecutor", _: Operation) -> int:
        return 0

    def _execute_update(self: "TestExecutor", _: Operation) -> int:
        return 0

    def _execute_remove(self: "TestExecutor", _: Operation) -> int:
        return 0
