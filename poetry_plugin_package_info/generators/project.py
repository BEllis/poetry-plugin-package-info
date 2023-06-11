"""
Built-in Project (poetry.toml) properties generator for package-info plugin.

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
from typing import Any

from poetry_plugin_package_info.plugin import (
    ContainerWrapper,
    PackageInfoApplicationPlugin,
    Property,
    PropertyConfig,
    PropertyGenerator,
)


def get_type_for_property(property_name: str) -> Any:
    """Gets the expected type for the given project property."""
    match property_name:
        case "authors" | "classifiers" | "maintainers" | "keywords":
            return list[str] | None
        case _:
            return str | None


class ProjectPropertyGenerator(PropertyGenerator):
    """
    Built-in Project properties generator for poetry-plugin-package-info.

    Built-in Project (poetry.toml) properties generator for
    poetry-plugin-package-info.
    """

    tool_poetry_section: ContainerWrapper

    def short_name(self: "ProjectPropertyGenerator") -> str:
        """Shortname/Prefix for properties belonging to this generator."""
        return "project"

    def init(
        self: "ProjectPropertyGenerator",
        plugin: PackageInfoApplicationPlugin,
    ) -> None:
        """Initialise the PropertyGenerator for the provided plugin."""
        self.tool_poetry_section: ContainerWrapper = ContainerWrapper(
            plugin.application.poetry.pyproject.data.get("tool"),
        ).get_or_error("poetry")

    def generate_property(
        self: "ProjectPropertyGenerator",
        property_config: PropertyConfig,
    ) -> Property:
        """Generate the property for the given include configuration."""
        value = self.tool_poetry_section.get_or_default(
            property_config.property_name,
            None,
        )
        property_type = get_type_for_property(property_config.property_name)
        return Property(
            property_config=property_config,
            property_value=value.unwrap() if value is not None else None,
            property_type=property_type,
            metadata={},
        )
