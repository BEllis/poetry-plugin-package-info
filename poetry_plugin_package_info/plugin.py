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
import importlib.metadata
import io
import tarfile
import tempfile
import typing
import zipfile
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from types import NoneType, UnionType
from typing import Any

from cleo.commands.command import Command
from cleo.events.console_events import TERMINATE
from cleo.events.console_terminate_event import ConsoleTerminateEvent
from cleo.events.event import Event
from cleo.events.event_dispatcher import EventDispatcher
from cleo.io.io import IO
from colorama import Fore
from jinja2 import Environment, Template
from poetry.console.application import Application
from poetry.console.commands.build import BuildCommand
from poetry.core.masonry.builder import Builder
from poetry.core.masonry.builders.sdist import SdistBuilder
from poetry.core.masonry.builders.wheel import WheelBuilder
from poetry.core.masonry.utils.helpers import distribution_name
from poetry.plugins.application_plugin import ApplicationPlugin
from tomlkit.container import Container, OutOfOrderTableProxy
from tomlkit.items import AbstractTable, Array, InlineTable


def type_as_python(value: type) -> str:
    """Returns the python code for the type.

    Returns the python code to represent the given type in the generated
    .py file.
    """
    if issubclass(value, NoneType):
        return "None"

    builtins = (str, int, float, bool)
    if issubclass(value, builtins):
        return value.__name__

    if len(typing.get_args(value)) > 0:
        args = (
            "["
            + ", ".join([as_python(arg) for arg in typing.get_args(value)])
            + "]"
        )
        return value.__name__ + args

    # workaround for freezegun
    if issubclass(value, datetime):
        return "datetime.datetime"

    return value.__name__.__module__ + "." + value.__name__


def as_python(value: Any) -> str:
    """Generate Python code to represent the given value."""
    if value is None:
        return "None"

    if isinstance(value, UnionType):
        return " | ".join([as_python(arg) for arg in typing.get_args(value)])

    if isinstance(value, type):
        return type_as_python(value)

    if isinstance(value, str):
        return f'"{value}"'

    if isinstance(value, datetime):
        return f'datetime.datetime.fromisoformat("{value.isoformat()}")'

    return str(value)


class PropertyConfig(typing.NamedTuple):
    """Configuration for properties to be included."""

    property_generator: "PropertyGenerator"
    property_name: str
    variable_name: str
    metadata: dict[str, Any]


class Property(typing.NamedTuple):
    """A generated property."""

    property_config: PropertyConfig
    property_value: Any
    property_type: type
    metadata: dict[str, Any]


class PropertyGenerator(ABC):
    """Abstract generator of properties."""

    @abstractmethod
    def short_name(self: "PropertyGenerator") -> str:
        """Shortname/Prefix for properties belonging to this generator."""

    @abstractmethod
    def init(
        self: "PropertyGenerator",
        plugin: "PackageInfoApplicationPlugin",
    ) -> None:
        """Initialise the PropertyGenerator for the provided plugin."""

    @abstractmethod
    def generate_property(
        self: "PropertyGenerator",
        property_config: PropertyConfig,
    ) -> Property:
        """Generate the property for the given include configuration."""


class ContentFormatter(ABC):
    """Abstract formatter of python file content."""

    @abstractmethod
    def init(
        self: "ContentFormatter",
        plugin: "PackageInfoApplicationPlugin",
    ) -> None:
        """Initialise the ContentFormatter for the provided plugin."""

    @abstractmethod
    def format_content(self: "ContentFormatter", content: str) -> str:
        """Format the given python file content."""


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

    _plugin: "PackageInfoApplicationPlugin"

    def __init__(
        self: "GenerateFilePackageInfoCommand",
        plugin: "PackageInfoApplicationPlugin",
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
        try:
            return self._plugin.generate_package_info(self.io)
        except Exception as e:
            self.io.write_error_line(
                f"""\
[{Fore.BLUE}poetry-plugin-package-info{Fore.RESET}]: \
{Fore.RED}Error encountered while generating package_info file\
 - {e} \
{Fore.RESET}\
""",
            )
            raise


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

    def get(self: "ContainerWrapper", param: str) -> Any:
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
        default: Any,
    ) -> Any:
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
    ) -> Any:
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
    ) -> Any:
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


def get_variable_type(value: Any) -> str:
    """Determine the type of the variable for the given value."""
    if isinstance(value, datetime):
        return "str"

    if isinstance(value, Array):
        return "list[str]"

    if isinstance(value, bool):
        return "bool"

    return "str"


def types_in(cls: type) -> list[type]:
    """Recursively returns the type and any type arguments into a list."""
    result = [cls]
    for arg in typing.get_args(cls):
        result += types_in(arg)

    return result


def get_imports_from_properties(properties: list[Property]) -> set[str]:
    """Gets a list of modules that will need importing into the python file."""
    imports = set()
    for property_item in properties:
        types = types_in(property_item.property_type)
        for cls in types:
            # Workaround for freezegun
            if isinstance(cls, type) and issubclass(cls, datetime):
                imports.add("datetime")
            elif cls.__module__ != "builtins" and not isinstance(
                cls,
                UnionType,
            ):
                imports.add(cls.__module__)

    return imports


class PackageInfoApplicationPlugin(
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
    patch_build_formats: list[str]
    pyproject_file_dir: Path
    formatter: ContentFormatter
    template: Template
    line_separator: str
    property_configs: list[PropertyConfig]
    package_info_relative_file_path: Path
    package_info_absolute_file_path: Path
    plugin_config: ContainerWrapper

    def __init__(self: "PackageInfoApplicationPlugin") -> None:
        """Creates a new instance of GeneratePackageInfoApplicationPlugin."""
        super().__init__()

    def new_instance(
        self: "PackageInfoApplicationPlugin",
        entry_point: str,
    ) -> Any:
        """Create and initialise a new instance of the given entry_point."""
        module = importlib.import_module(entry_point.split(":", 1)[0])
        cls = getattr(module, entry_point.split(":", 1)[1])
        instance = cls()
        instance.init(self)
        return instance

    def write_package_info_py(
        self: "PackageInfoApplicationPlugin",
        package_info_file_stream: typing.TextIO,
    ) -> None:
        """
        Write the contents of the package_info.py file to the given stream.

        :param package_info_file_stream: The stream to write the
                                         package_info.py file content to.
        """
        properties: list[Property] = []
        for include in self.property_configs:
            properties.append(
                include.property_generator.generate_property(include),
            )

        imports = get_imports_from_properties(properties)

        package_info_file_stream.write(
            self.formatter.format_content(
                self.template.render(properties=properties, imports=imports),
            ),
        )

    def generate_package_info(
        self: "PackageInfoApplicationPlugin",
        out: IO,
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

        out.write_line(
            f"""\
[{Fore.BLUE}poetry-plugin-package-info{Fore.RESET}]: \
Generated file {Fore.GREEN}{
        Path(self.package_info_absolute_file_path).relative_to(self.pyproject_file_dir)
        }{Fore.RESET}\
""",
        )

        return 0

    def parse_include_property_configs(
        self: "PackageInfoApplicationPlugin",
        property_configs: list[Any],
    ) -> list[PropertyConfig]:
        """Parse the property configurations."""
        includes = []
        for item in property_configs:
            if isinstance(item, str):
                property_generator = self.generators.get(
                    item.split("-", maxsplit=1)[0],
                    None,
                )
                property_name = item.split("-", maxsplit=1)[1]
                if property_generator is None:
                    # TODO: More descriptive error
                    raise ValueError
                variable_name = (
                    property_generator.short_name()
                    + "_"
                    + property_name.replace("-", "_")
                )
                metadata: dict[str, Any] = {}
                includes.append(
                    PropertyConfig(
                        property_generator,
                        property_name,
                        variable_name,
                        metadata,
                    ),
                )
            elif isinstance(item, InlineTable):
                property_generator = self.generators.get(
                    item["property-generator"]
                    if "property-generator" in item
                    else None,
                    None,
                )
                property_name = (
                    item["property-name"] if "property-name" in item else None
                )
                if property_name is None or property_generator is None:
                    # Ignore invalid includes?
                    continue
                variable_name = (
                    item["variable-name"]
                    if "variable-name" in item
                    else property_generator.short_name()
                    + "_"
                    + property_name.replace("-", "_")
                )
                metadata = item["metadata"] if "metadata" in item else {}
                includes.append(
                    PropertyConfig(
                        property_generator,
                        property_name,
                        variable_name,
                        metadata,
                    ),
                )
            else:
                # Ignore invalid includes?
                pass
        return includes

    def load_generators(
        self: "PackageInfoApplicationPlugin",
        generators: dict[str, str],
    ) -> dict[str, PropertyGenerator]:
        """Load the given list of generators."""
        return {
            k: typing.cast(PropertyGenerator, self.new_instance(v))
            for k, v in generators.items()
        }

    def load_formatter(
        self: "PackageInfoApplicationPlugin",
        formatter: str,
    ) -> ContentFormatter:
        """Load the formatter."""
        return typing.cast(ContentFormatter, self.new_instance(formatter))

    def initialise(self: "PackageInfoApplicationPlugin") -> None:
        """Initialises the plugin based on pyproject.toml configuration."""
        if self.initialized:
            return

        self.pyproject_file_dir = (
            self.application.poetry.pyproject.file.path.parent
        )

        self.default_src_directory = Path(
            self.application.poetry.package.name.replace("-", "_"),
        )

        self.plugin_config: ContainerWrapper = ContainerWrapper(
            self.application.poetry.pyproject.data.get("tool"),
        ).get_or_empty("poetry-plugin-package-info")

        self.patch_build_formats = self.plugin_config.get_or_default(
            "patch-build-formats",
            default=[],
        )
        if isinstance(self.patch_build_formats, str):
            if not self.patch_build_formats:
                self.patch_build_formats = []
            else:
                self.patch_build_formats = [self.patch_build_formats]

        self.package_info_relative_file_path = (
            self.plugin_config.get_or_default(
                "package-info-file-path",
                f"{self.default_src_directory}/package_info.py",
            )
        )

        self.package_info_absolute_file_path = (
            self.pyproject_file_dir / self.package_info_relative_file_path
        )

        # PEP-8 specifies 79 as recommended.
        self.formatter = self.load_formatter(
            self.plugin_config.get_or_default(
                "formatter",
                "poetry_plugin_package_info.formatters.black:BlackContentFormatter",
            ),
        )

        env = Environment()
        self.template = env.from_string(
            self.plugin_config.get_or_default(
                "template",
                """\
\"\"\"Auto-generated by poetry-plugin-package-info at {{\
 now().replace(microsecond=0).isoformat() \
 }}.\"\"\"\
{% for import in imports %}
import {{import}}
{% endfor %}
class PackageInfo:
{% for property in properties %}\
{{ "    " }}{{property.property_config.variable_name}}: \
{{as_python(property.property_type)}} = \
{{as_python(property.property_value)}}
{% endfor %}
""",
            ),
            globals={"now": datetime.now, "as_python": as_python},
        )
        self.line_separator = self.plugin_config.get_or_default(
            "line-separator",
            "\n",
        )
        self.generators = self.load_generators(
            self.plugin_config.get_or_default(
                "generators",
                {
                    "git": (
                        "poetry_plugin_package_info"
                        ".generators.git:"
                        "GitPropertyGenerator"
                    ),
                    "project": (
                        "poetry_plugin_package_info"
                        ".generators.project:"
                        "ProjectPropertyGenerator"
                    ),
                },
            ),
        )
        self.property_configs = self.parse_include_property_configs(
            self.plugin_config.get_or_default(
                "properties",
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
            ),
        )

        self.initialized = True

    def activate(
        self: "PackageInfoApplicationPlugin",
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
            self.try_on_terminate,
        )
        application.command_loader.register_factory(
            "package-info generate-file",
            lambda: GenerateFilePackageInfoCommand(self),
        )

    def get_builder_types(
        self: "PackageInfoApplicationPlugin",
        command: BuildCommand,
    ) -> list[type[Builder]]:
        """Get the list of build_types set to run as part of BuildCommand."""
        fmt = command.option("format") or "all"
        builder = Builder(command.poetry)
        if fmt in builder._formats:  # noqa: SLF001
            return [builder._formats[fmt]]  # noqa: SLF001
        if fmt == "all":
            return list(builder._formats.values())  # noqa: SLF001

        raise ValueError(f"Unsupported format: {fmt}")  # noqa: TRY003

    def handle_builder_type(
        self: "PackageInfoApplicationPlugin",
        builder_type: type[Builder],
        out: IO,
    ) -> None:
        """Handle and processing for the given builder type."""
        format_all = "all" in self.patch_build_formats
        if issubclass(builder_type, WheelBuilder) and (
            builder_type.format in self.patch_build_formats or format_all
        ):
            builder_instance = builder_type(self.application.poetry)
            self.update_wheel(
                Path(builder_instance.default_target_dir)
                / builder_instance.wheel_filename,
                out,
            )
        elif issubclass(builder_type, SdistBuilder) and (
            builder_type.format in self.patch_build_formats or format_all
        ):
            builder_instance = builder_type(self.application.poetry)
            dist_name = distribution_name(
                self.application.poetry.package.name,
            )
            version = builder_instance._meta.version  # noqa: SLF001
            tar_file_name = f"{dist_name!s}-{version}.tar.gz"
            self.update_sdist(
                builder_instance.default_target_dir / tar_file_name,
                out,
            )
        elif format_all:
            out.write_line(
                f"""\
[{Fore.BLUE}poetry-plugin-package-info{Fore.RESET}]: \
{Fore.YELLOW}Skipped unsupported distribution format \
{builder_type.format}{Fore.RESET}\
""",
            )

    def on_terminate(
        self: "PackageInfoApplicationPlugin",
        command: BuildCommand,
        out: IO,
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
        self.initialise()

        if len(self.patch_build_formats) == 0:
            return

        for builder_type in self.get_builder_types(command):
            self.handle_builder_type(builder_type, out)

    def try_on_terminate(
        self: "PackageInfoApplicationPlugin",
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
        out = event.io
        try:
            if not isinstance(event, ConsoleTerminateEvent):
                return
            command = event.command
            if not isinstance(command, BuildCommand):
                return

            self.on_terminate(command, out)
        except Exception as e:
            out.write_error_line(
                f"""\
[{Fore.BLUE}poetry-plugin-package-info{Fore.RESET}]: \
{Fore.RED}Error encountered while patching distribution files\
 - {e} \
{Fore.RESET}\
""",
            )
            raise

    def update_wheel(
        self: "PackageInfoApplicationPlugin",
        wheel_file: Path,
        out: IO,
    ) -> None:
        """Update the wheel distribution with the package_info.py file."""
        with io.StringIO() as package_info_py_stream:
            self.write_package_info_py(package_info_py_stream)
            data = package_info_py_stream.getvalue()

        out.write_line(
            f"""\
[{Fore.BLUE}poetry-plugin-package-info{Fore.RESET}]: Patching {Fore.GREEN}\
{wheel_file.relative_to(self.pyproject_file_dir)!s}{Fore.RESET} with \
{Fore.GREEN}{self.package_info_relative_file_path}{Fore.RESET}\
""",
        )
        with zipfile.ZipFile(
            str(wheel_file),
            mode="a",
            compression=zipfile.ZIP_DEFLATED,
        ) as zip_file:
            zip_file.writestr(str(self.package_info_relative_file_path), data)

    def update_sdist(
        self: "PackageInfoApplicationPlugin",
        tar_gz_file: Path,
        out: IO,
    ) -> None:
        """Update the wheel distribution with the package_info.py file."""
        with io.StringIO() as package_info_py_stream:
            self.write_package_info_py(package_info_py_stream)
            data = package_info_py_stream.getvalue()

        out.write_line(
            f"""\
[{Fore.BLUE}poetry-plugin-package-info{Fore.RESET}]: Patching \
{Fore.GREEN}{tar_gz_file.relative_to(self.pyproject_file_dir)!s}\
{Fore.RESET} with {Fore.GREEN}{self.package_info_relative_file_path}\
{Fore.RESET}\
        """,
        )

        append_tar_file(
            data.encode("utf-8"),
            str(self.package_info_relative_file_path),
            tar_gz_file,
        )


def append_tar_file(
    data_bytes: bytes,
    file_name: str,
    tar_file_path: Path,
    *,
    replace: bool = True,
) -> None:
    """Append data to an tar file if not already there, or if replace=True."""
    if not Path(tar_file_path).is_file():
        return

    compression = get_compression(tar_file_path)

    with tempfile.TemporaryDirectory() as _tempdir:
        tempdir = Path(_tempdir)
        tmp_path = tempdir / ("tmp.tar." + compression)

        with tarfile.open(tar_file_path, "r:" + compression) as tar:
            if not replace and file_name in (member.name for member in tar):
                return

            fileobj = io.BytesIO(data_bytes)
            tarinfo = tarfile.TarInfo(file_name)
            tarinfo.size = len(fileobj.getvalue())

            with tarfile.open(tmp_path, "w:" + compression) as tmp:
                for member in tar:
                    if member.name != file_name:
                        tmp.addfile(member, tar.extractfile(member.name))
                tmp.addfile(tarinfo, fileobj)

        tmp_path.rename(tar_file_path)


def get_compression(filename: Path) -> str:
    """Determine the compression type of a tar file."""
    suffixes = filename.suffixes
    tar, compression = (s.lstrip(".") for s in suffixes[-2:])

    if tar == "tgz":
        if compression:
            raise RuntimeError(
                "Too much suffixes, cannot infer compression scheme from \
                {}".format(
                    "".join(suffixes),
                ),
            )
        return "gz"

    if tar != "tar":
        raise RuntimeError(  # noqa: TRY003
            "Unable to determine tar compression",
        )

    if not compression:
        return ""

    return compression
