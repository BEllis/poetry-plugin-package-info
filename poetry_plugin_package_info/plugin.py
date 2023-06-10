"""
plugin.py - GeneratePackageInfoApplicationPlugin.

MIT License

Copyright (c) 2023 Ben Ellis

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

"""
import io
import typing
import zipfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cleo.commands.command import Command
from cleo.events.console_events import TERMINATE
from cleo.events.console_terminate_event import ConsoleTerminateEvent
from cleo.events.event import Event
from cleo.events.event_dispatcher import EventDispatcher
from cleo.io.io import IO
from git import InvalidGitRepositoryError
from git import Repo as GitRepo
from poetry.console.application import Application
from poetry.console.commands.build import BuildCommand
from poetry.core.masonry.builder import Builder
from poetry.core.masonry.builders.wheel import WheelBuilder
from poetry.plugins.application_plugin import ApplicationPlugin
from tomlkit.container import Container, OutOfOrderTableProxy
from tomlkit.items import AbstractTable, Array, InlineTable


class MissingPropertyFromIncludeConfigItemError(Exception):
    """
    MissingPropertyFromIncludeConfigItemError.

    Missing required 'property' value from include item in TOML configuration.
    """

    def __init__(self: "MissingPropertyFromIncludeConfigItemError") -> None:
        """Construct a new MissingPropertyFromIncludeConfigItemError."""
        super().__init__(
            "Missing expected 'property' value in plugin configuration.",
        )


class NoSuchTomlPropertyError(Exception):
    """Unable to find the given section/property in the TOML file."""

    def __init__(self: "NoSuchTomlPropertyError", section_name: str) -> None:
        """
        Construct a new NoSuchTomlPropertyError.

        :param section_name: The name of the property or section that was
                             missing.
        """
        super().__init__(
            f"Missing expected TOML section/property {section_name}",
        )


class UnsupportedIncludeItemError(Exception):
    """Include option was given that is not supported."""

    def __init__(
        self: "UnsupportedIncludeItemError",
        include_value: str,
    ) -> None:
        """
        Construct a new UnsupportedIncludeItemError.

        :param include_value: The value that was specified that is unsupported
                              by the plugin.
        """
        super().__init__(f"Unsupported value in includes '{include_value}'")


class GenerateFilePackageInfoCommand(Command):  # type: ignore[misc]
    """
    'package-info generate-file' poetry command.

    'package-info generate-file' command to manually trigger the generation of
     the package_info.py file.
    """

    name = "package-info generate-file"
    description = """\
Generates a package_info.py file that contains pyproject.toml and git \
information.\
"""

    _plugin: "GeneratePackageInfoApplicationPlugin"

    def __init__(
        self: "GenerateFilePackageInfoCommand",
        plugin: "GeneratePackageInfoApplicationPlugin",
    ) -> None:
        """
        Construct a new GeneratePackageInfoCommand.

        :param plugin: The plugin that registered this command.
        """
        self._plugin = plugin
        super().__init__()

    def handle(self: "GenerateFilePackageInfoCommand") -> int:
        """
        Execute the command.

        Called by poetry when `poetry package-info generate-file` is run from
        the command line.

        :return: A status code indicating success (0) or failure (not 0).
        """
        return self._plugin.generate_package_info(self.io)


class ContainerWrapper:
    """
    A wrapper for TOML Container.

    A wrapper for TOML Container that decorates it with additional helper
    methods.
    """

    def __init__(
        self: "ContainerWrapper",
        container: Container | AbstractTable | OutOfOrderTableProxy | None,
    ) -> None:
        """
        Construct a new instance of ContainerWrapper.

        :param container: The container to be wrapped.
        """
        self._container = container

    def get(self: "ContainerWrapper", param: str) -> Any:  # noqa: ANN401
        """
        Get the TOML section/property (if present) otherwise None.

        :param param: The name of the TOML section/property
        :return: None if missing, otherwise str, int or wrapped
                 OutOfOrderTableProxy or Container
        """
        if self._container is None:
            return None
        value = self._container.get(param)
        if value is not None and issubclass(
            value.__class__,
            Container | AbstractTable | OutOfOrderTableProxy,
        ):
            return ContainerWrapper(value)

        return value

    def get_or_default(
        self: "ContainerWrapper",
        param: str,
        default: Any,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        """
        Get the TOML section/property (if present) otherwise a default.

        :param param: The name of the TOML section/property
        :param default: The default value to use if section or property is
                        missing.
        :return: str, int or wrapped OutOfOrderTableProxy or Container
        """
        if self._container is None:
            return default
        value = self._container.get(param)
        if value is None:
            value = default

        if issubclass(
            value.__class__,
            Container | AbstractTable | OutOfOrderTableProxy,
        ):
            return ContainerWrapper(value)

        return value

    def get_or_error(
        self: "ContainerWrapper",
        param: str,
    ) -> Any:  # noqa: ANN401
        """
        Get the TOML section/property, else raise NoSuchTomlPropertyError.

        Get the TOML section/property (if present) otherwise raise
        NoSuchTomlPropertyError.

        :param param: The name of the TOML section/property
        :return: str, int or wrapped OutOfOrderTableProxy or Container
        :raises NoSuchTomlPropertyError: section or property not found
        """
        if self._container is None:
            raise NoSuchTomlPropertyError(param)
        value = self._container.get(param)
        if value is None:
            raise NoSuchTomlPropertyError(param)

        if issubclass(
            value.__class__,
            Container | AbstractTable | OutOfOrderTableProxy,
        ):
            return ContainerWrapper(value)

        return value

    def get_or_empty(
        self: "ContainerWrapper",
        param: str,
    ) -> Any:  # noqa: ANN401
        """
        Get the TOML section/property, otherwise return an 'empty' value.

        Get the TOML section/property (if present) otherwise return an empty
        ContainerWrapper.

        :param param: The name of the TOML section/property
        :return: The value if not None, otherwise an empty ContainerWrapper.
        """
        if self._container is None:
            return ContainerWrapper(None)
        value = self._container.get(param)
        if value is None:
            return ContainerWrapper(None)

        if issubclass(
            value.__class__,
            Container | AbstractTable | OutOfOrderTableProxy,
        ):
            return ContainerWrapper(value)

        return value


def get_variable_type(value: Any) -> str:  # noqa: ANN401
    """Determine the type of the variable for the given value."""
    if isinstance(value, datetime):
        return "str"

    if isinstance(value, Array):
        return "list[str]"

    if isinstance(value, bool):
        return "bool"

    return "str"


class GeneratePackageInfoApplicationPlugin(
    ApplicationPlugin,  # type: ignore[misc]
):
    """
    Poetry Plugin to add package_info.py file generation.

    Poetry Plugin to add package_info.py file generation to build command and
    adds a package-info generate-file command to poetry CLI.
    """

    initialized: bool = False
    application: Application
    default_src_directory: Path
    patch_wheels: bool
    line_length: int
    pyproject_file_dir: Path
    line_separator: str
    include: dict[str, object]
    footer: str
    header: str
    indent: int
    package_info_relative_file_path: Path
    package_info_absolute_file_path: Path
    git_search_parent_directories: bool
    git_is_bare: bool = False
    git_repo: GitRepo | None

    def __init__(self: "GeneratePackageInfoApplicationPlugin") -> None:
        """Creates a new instance of GeneratePackageInfoApplicationPlugin."""
        super().__init__()

    def write_package_info_py(
        self: "GeneratePackageInfoApplicationPlugin",
        package_info_file_stream: typing.TextIO,
    ) -> None:
        """
        Write the contents of the package_info.py file to the given stream.

        :param package_info_file_stream: The stream to write the
                                         package_info.py file content to.
        """
        if self.header:
            self.write_header(package_info_file_stream)

        added_no_repo_comment = False
        added_is_bare_comment = False

        for item in self.include:
            match (
                item
                if isinstance(item, str)
                else item["property"]  # type: ignore[index]
            ).split("-", maxsplit=1):
                case ["project", pyproject_property_name]:
                    self.write_project_property(
                        package_info_file_stream,
                        pyproject_property_name,
                        item,
                    )
                case ["git", git_property_name]:
                    if self.git_repo is None:
                        if not added_no_repo_comment:
                            added_no_repo_comment = True
                            package_info_file_stream.write(" " * self.indent)
                            package_info_file_stream.write(
                                "# No git repository found, skipped git "
                                "properties.",
                            )
                            package_info_file_stream.write(
                                self.line_separator,
                            )
                        continue
                    if self.git_is_bare and not added_is_bare_comment:
                        added_is_bare_comment = True
                        package_info_file_stream.write(" " * self.indent)
                        package_info_file_stream.write(
                            "# Git repository is bare, skipped "
                            "git properties relating to commits.",
                        )
                        package_info_file_stream.write(self.line_separator)
                    self.handle_git_properties(
                        package_info_file_stream,
                        git_property_name,
                        item,
                    )
                case _:
                    raise UnsupportedIncludeItemError(item)

        if self.footer:
            package_info_file_stream.write(self.footer)
            package_info_file_stream.write(self.line_separator)

    def generate_package_info(
        self: "GeneratePackageInfoApplicationPlugin",
        _: IO,
    ) -> int:
        """
        Generate a package_info.py file.

        Generate a package_info.py file based on the configuration provided.
        :param _: The IO channel to log console messages to.
        :return: A status code indicating success(0) or failure (non-zero)
        """
        self.initialise()
        with Path(self.package_info_absolute_file_path).open(
            "w",
        ) as package_info_file_stream:
            self.write_package_info_py(package_info_file_stream)

        return 0

    def initialise(self: "GeneratePackageInfoApplicationPlugin") -> None:
        """Initialises the plugin based on pyproject.toml configuration."""
        if self.initialized:
            return

        self.pyproject_file_dir = (
            self.application.poetry.pyproject.file.path.parent
        )
        self.default_src_directory = Path(
            self.application.poetry.package.name.replace("-", "_"),
        )
        plugin_config: ContainerWrapper = ContainerWrapper(
            self.application.poetry.pyproject.data.get("tool"),
        ).get_or_empty("poetry-plugin-package-info")
        self.patch_wheels = plugin_config.get_or_default(
            "patch-wheels",
            default=False,
        )
        self.package_info_relative_file_path = plugin_config.get_or_default(
            "package-info-file-path",
            f"{self.default_src_directory}/package_info.py",
        )
        self.package_info_absolute_file_path = (
            self.pyproject_file_dir / self.package_info_relative_file_path
        )
        # PEP-8 specifies 79 as recommended.
        self.line_length = plugin_config.get_or_default("line-length", 79)
        self.line_separator = plugin_config.get_or_default(
            "line-separator",
            "\n",
        )
        self.header = plugin_config.get_or_default(
            "header",
            """\
\"\"\"Auto-generated by poetry-plugin-package-info at {file-write-time}.\"\"\"


class PackageInfo:
""",
        )
        self.footer = plugin_config.get_or_default("footer", "")
        self.indent = plugin_config.get_or_default("indent", 4)
        self.include = plugin_config.get_or_default(
            "include",
            [
                "project-name",
                "project-description",
                "project-version",
                "project-authors",
                "project-license",
                "project-classifiers",
                "project-documentation",
                "project-repository",
                "project-homepage",
                "project-maintainers",
                "project-keywords",
                "git-commit-id",
                "git-commit-author-name",
                "git-commit-author-email",
                "git-commit-timestamp",
                "git-branch-name",
                "git-branch-path",
                "git-is-dirty",
                "git-is-dirty-excluding-untracked",
                "git-has-staged-changes",
                "git-has-unstaged-changes",
                "git-has-untracked-changes",
            ],
        )
        self.git_search_parent_directories = plugin_config.get_or_default(
            "git-search-parent-directories",
            default=False,
        )
        try:
            self.git_repo = GitRepo(
                self.pyproject_file_dir,
                search_parent_directories=self.git_search_parent_directories,
            )

            # Check there is at least one commit in the repo.
            try:
                self.git_repo.head.commit  # noqa: B018
            except ValueError as e:
                if len(e.args) > 0 and e.args[0].startswith("Reference at"):
                    self.git_is_bare = True
        except InvalidGitRepositoryError:
            self.git_repo = None

        self.initialized = True

    def activate(
        self: "GeneratePackageInfoApplicationPlugin",
        application: Application,
    ) -> None:
        """
        Activate the plugin, load configuration and register commands.

        :param application: The poetry application.
        :return: None
        """
        self.application = application
        typing.cast(
            EventDispatcher,
            application.event_dispatcher,
        ).add_listener(
            TERMINATE,
            self.on_terminate,
        )
        application.command_loader.register_factory(
            "package-info generate-file",
            lambda: GenerateFilePackageInfoCommand(self),
        )

    def on_terminate(
        self: "GeneratePackageInfoApplicationPlugin",
        event: Event,
        event_name: str,  # noqa: ARG002
        dispatcher: EventDispatcher,  # noqa: ARG002
    ) -> None:
        """
        Event handler for when an event is triggered.

        Event handler for when an event is triggered on the poetry (cleo) event
        dispatcher.
        :param event: The event that was triggered.
        :param event_name: The name of the vent that was triggered.
        :param dispatcher: The dispatcher that dispatched the event.
        :return: None
        """
        if not isinstance(event, ConsoleTerminateEvent):
            return
        command = event.command
        if not isinstance(command, BuildCommand):
            return

        out = event.io
        self.initialise()

        if not self.patch_wheels:
            return

        fmt = command.option("format") or "all"
        builder = Builder(command.poetry)
        if fmt in builder._formats:  # noqa: SLF001
            builder_types = [builder._formats[fmt]]  # noqa: SLF001
        elif fmt == "all":
            builder_types = list(builder._formats.values())  # noqa: SLF001
        else:
            raise ValueError(f"Unsupported format: {fmt}")  # noqa: TRY003

        for builder_type in builder_types:
            if issubclass(builder_type, WheelBuilder):
                builder_instance = builder_type(self.application.poetry)
                self.update_wheel(
                    Path(builder_instance.default_target_dir)
                    / builder_instance.wheel_filename,
                    out,
                )

    def write_git_property(
        self: "GeneratePackageInfoApplicationPlugin",
        package_info_file_stream: typing.TextIO,
        item: Any,  # noqa: ignore[ANN401]
        repo_handler: Callable[[GitRepo], Any],
    ) -> None:
        """
        Write a git property to the stream.

        :param package_info_file_stream: The stream to write to.
        :param repo_handler: Function to extract the value from a git Repo.
        :param item: The property configuration.
        :return: None
        """
        value = repo_handler(
            GitRepo(self.pyproject_file_dir, search_parent_directories=True),
        )
        self.write_property_object(package_info_file_stream, item, value)

    def write_project_property(
        self: "GeneratePackageInfoApplicationPlugin",
        package_info_file_stream: typing.TextIO,
        param: str,
        item: InlineTable | str,
    ) -> None:
        """
        Write a project property to the stream.

        :param package_info_file_stream: The stream to write to.
        :param param: The name of the git property.
        :param variable_name: The name to give the variable in the stream.
        :return: None
        """
        tool_poetry_section: ContainerWrapper = ContainerWrapper(
            self.application.poetry.pyproject.data.get("tool"),
        ).get_or_error("poetry")
        value = tool_poetry_section.get_or_default(param, None)
        self.write_property_object(package_info_file_stream, item, value)

    def write_property_object(
        self: "GeneratePackageInfoApplicationPlugin",
        package_info_file_stream: typing.TextIO,
        item: str | InlineTable,
        value: Any,  # noqa: ANN401
    ) -> None:
        """
        Write a property to the stream.

        :param package_info_file_stream: The stream to write to.
        :param item: The configuration item for the property.
        :param value: The value to assign to the variable.
        :return: None
        """
        variable_name: str
        if isinstance(item, InlineTable) and "variable_name" in item:
            variable_name = str(item["variable_name"])
        elif isinstance(item, InlineTable) and "property" in item:
            variable_name = str(item["property"]).replace("-", "_")
        elif isinstance(item, InlineTable) and "property" not in item:
            raise MissingPropertyFromIncludeConfigItemError
        else:
            variable_name = str(item).replace("-", "_")

        if value is not None:
            indent = self.indent
            variable_type = get_variable_type(value)
            value = self.to_python(indent, value)
            value = self.adjust_to_fit(indent, value)
            package_info_file_stream.write(" " * self.indent)
            package_info_file_stream.write(
                f"{variable_name}: {variable_type} = {value}",
            )
            package_info_file_stream.write(self.line_separator)

    def adjust_to_fit(
        self: "GeneratePackageInfoApplicationPlugin",
        indent: int,
        value: Any,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        """
        Adjust any strings that would excess the line-length.

        :param indent: The number of characters to indent strings.
        :param value: The value to adjust.
        :return: Either original value, or, a multiline string that fits
                 within the line-length.
        """
        if (
            not isinstance(value, str)
            or not value.startswith('"')
            or len(value) <= self.line_length - indent - 2
        ):
            return value

        new_value = "("
        new_value += self.line_separator
        while len(value) > self.line_length - indent - 2:
            if new_value:
                new_value += " " * indent

            new_value += " " * self.indent
            new_value += value[: self.line_length - indent - 2]
            new_value += '"'
            new_value += self.line_separator
            value = '"' + value[self.line_length - indent - 2 :]

        new_value += " " * self.indent
        new_value += " " * indent
        new_value += value
        new_value += self.line_separator
        new_value += " " * self.indent
        new_value += ")"
        return new_value

    def to_python(
        self: "GeneratePackageInfoApplicationPlugin",
        indent: int,
        value: Any,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        """
        Try to turn the object into a valid python code value.

        :param indent: The number of spaces to indent the value.
        :param value: The value to convert to python code.
        :return: A python code string, or, the original value.
        """
        if isinstance(value, datetime):
            return '"' + value.isoformat() + '"'

        if isinstance(value, Array):
            new_value = "["
            new_value += self.line_separator

            for i in value:
                new_value += " " * self.indent
                new_value += " " * indent
                new_value += self.to_python(indent, i)
                new_value += ","
                new_value += self.line_separator

            new_value += " " * self.indent
            new_value += "]"
            return new_value

        if isinstance(value, str) and not value.startswith('"'):
            new_value = '"'
            new_value += value
            new_value += '"'
            return self.adjust_to_fit(
                indent,
                new_value,
            )

        return value

    def write_header(
        self: "GeneratePackageInfoApplicationPlugin",
        package_info_file_stream: typing.TextIO,
    ) -> None:
        """
        Write the header to the file.

        :param package_info_file_stream: stream to write to
        :return: None
        """
        package_info_file_stream.write(
            self.header.replace(
                "{file-write-time}",
                datetime.now(tz=timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
            ),
        )
        if not self.header.endswith(self.line_separator):
            package_info_file_stream.write(self.line_separator)

    def handle_git_properties(
        self: "GeneratePackageInfoApplicationPlugin",
        package_info_file_stream: typing.TextIO,
        git_property_name: str,
        item: Any,  # noqa: ignore[ANN401]
    ) -> None:
        """Handles processing of any properties related to git."""
        git_lookup_method: Callable[[GitRepo], Any]
        match git_property_name:
            case "commit-id":
                git_lookup_method = (
                    (lambda repo: repo.head.commit.hexsha)
                    if not self.git_is_bare
                    else lambda _: None
                )
            case "commit-author-name":
                git_lookup_method = (
                    (lambda repo: repo.head.commit.author.name)
                    if not self.git_is_bare
                    else lambda _: None
                )
            case "commit-author-email":
                git_lookup_method = (
                    (lambda repo: repo.head.commit.author.email)
                    if not self.git_is_bare
                    else lambda _: None
                )
            case "commit-timestamp":
                git_lookup_method = (
                    (lambda repo: repo.head.commit.committed_datetime)
                    if not self.git_is_bare
                    else lambda _: None
                )
            case "is-dirty":

                def git_lookup_method(repo: GitRepo) -> bool:
                    return repo.is_dirty(  # type: ignore[no-any-return]
                        untracked_files=True,
                    )

            case "is-dirty-excluding-untracked":

                def git_lookup_method(repo: GitRepo) -> bool:
                    return repo.is_dirty(  # type: ignore[no-any-return]
                        untracked_files=False,
                    )

            case "has-staged-changes":
                git_lookup_method = (
                    (
                        lambda repo: len(
                            repo.index.diff("HEAD"),
                        )
                        > 0
                    )
                    if not self.git_is_bare
                    else lambda _: False
                )
            case "has-unstaged-changes":

                def git_lookup_method(repo: GitRepo) -> bool:
                    return len(repo.index.diff(None)) > 0

            case "has-untracked-changes":

                def git_lookup_method(repo: GitRepo) -> bool:
                    return len(repo.untracked_files) > 0

            case "branch-name":

                def git_lookup_method(
                    repo: GitRepo,
                ) -> Any:  # noqa: ANN401
                    return repo.active_branch.name

            case "branch-path":

                def git_lookup_method(
                    repo: GitRepo,
                ) -> Any:  # noqa: ANN401
                    return repo.active_branch.path

            case _:
                raise UnsupportedIncludeItemError(
                    f"git-{git_property_name}",
                )
        self.write_git_property(
            package_info_file_stream,
            item,
            git_lookup_method,
        )

    def update_wheel(
        self: "GeneratePackageInfoApplicationPlugin",
        wheel_file: Path,
        out: IO,
    ) -> None:
        """Update the wheel distribution with the package_info.py file."""
        with io.StringIO() as package_info_py_stream:
            self.write_package_info_py(package_info_py_stream)
            data = package_info_py_stream.getvalue()

        out.write_line(
            f"""\
Patching {wheel_file!s} with {self.package_info_relative_file_path}\
""",
        )
        with zipfile.ZipFile(
            str(wheel_file),
            mode="a",
            compression=zipfile.ZIP_DEFLATED,
        ) as zip_file:
            zip_file.writestr(str(self.package_info_relative_file_path), data)
