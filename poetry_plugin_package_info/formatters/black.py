"""Black content formatter for applying black formatting to generated code."""

import black

from poetry_plugin_package_info.plugin import (
    ContentFormatter,
    PackageInfoApplicationPlugin,
)


class BlackContentFormatter(ContentFormatter):
    """Black content formatter for applying formatting to generated code."""

    def init(
        self: "BlackContentFormatter",
        plugin: PackageInfoApplicationPlugin,
    ) -> None:
        """Initialise the ContentFormatter for the provided plugin."""
        ...

    def format_content(self: "BlackContentFormatter", content: str) -> str:
        """Format the given python file content."""
        return black.format_file_contents(
            content,
            fast=False,
            mode=black.mode.Mode(),
        )
