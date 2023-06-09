# Poetry Plugin: Package Info

[![PyPi](https://img.shields.io/pypi/v/poetry-plugin-package-info.svg)](https://pypi.org/project/poetry-plugin-package-info/)
[![Stable Version](https://img.shields.io/pypi/v/poetry-plugin-package-info?label=stable)](https://pypi.org/project/poetry-plugin-package-info/)
[![Pre-release Version](https://img.shields.io/github/v/release/bellis/poetry-plugin-package-info?label=pre-release&include_prereleases&sort=semver)](https://pypi.org/project/poetry-plugin-package-info)
[![Python Versions](https://img.shields.io/pypi/pyversions/poetry-plugin-package-info)](https://pypi.org/project/poetry-plugin-package-info)
[![Code coverage Status](https://codecov.io/gh/bellis/poetry-plugin-package-info/branch/main/graph/badge.svg)](https://codecov.io/gh/bellis/poetry-plugin-package-info)
[![PyTest](https://github.com/bellis/poetry-plugin-package-info/workflows/test/badge.svg)](https://github.com/bellis/poetry-plugin-package-info/actions?query=workflow%3Atest)
[![Download Stats](https://img.shields.io/pypi/dm/poetry-plugin-package-info)](https://pypistats.org/packages/poetry-plugin-package-info)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![Code Style](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

This package is a plugin that generates a `package_info.py` file with variables containing values from pyproject.toml and git.

## Installation

The easiest way to install the `package-info` plugin is via the `self add` command of Poetry.

```bash
poetry self add poetry-plugin-package-info
```

If you used `pipx` to install Poetry you can add the plugin via the `pipx inject` command.

```bash
pipx inject poetry poetry-plugin-package-info
```

Otherwise, if you used `pip` to install Poetry you can add the plugin packages via the `pip install` command.

```bash
pip install poetry-plugin-plugin-package-info
```

## Usage

By default, the `package-info.py` file is generated only when using the `package-info generate-file` command in poetry,

```
poetry package-info generate-file
```

The plugin can be enabled to automatically patch wheel files after `poetry build` is run by adding the `patch-wheels` to the project pyproject.toml file.

```toml
[tool.poetry-plugin-package-info]
patch-build-formats = ['wheel', 'sdist']  # or can just do ['all']
```

The plugin can be re-configured in the pyproject.toml file, below are the options and their defaults.

```toml
[tool.poetry-plugin-package-info]

# Patch any .whl files produced by `poetry build`
patch-build-formats = []

# The path relative to the pyproject.toml file
package-info-file-path = "package_name_in_snake_case/package_info.py"

# Search parent directories (relative to pyproject.toml) for .git
git-search-parent-directories = false

# The formatter to format the generated package_info.py file.
formatters = [ "poetry-plugin-package-info.formatters.black:BlackContentFormatter" ]

# The generators to use to extract property values.
generators = { project = "poetry-plugin-package-info.generators.project:ProjectPropertyGenerator", git = "poetry-plugin-package-info.generators.git:GitPropertyGenerator" }

template = """\
\"\"\"Auto-generated by poetry-plugin-package-info at {{ now().replace(microsecond=0).isoformat()  }}.\"\"\"\
{% for import in imports %}
import {{import}}
{% endfor %}
class PackageInfo:
{% for property in properties %}\
{{ "    " }}{{property.property_config.variable_name}}: {{as_python(property.property_type)}} = {{as_python(property.property_value)}}
{% endfor %}
"""

# ordered list of variables to include in the file.
properties = [
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
    "git-has-staged-changes",
    "git-has-unstaged-changes",
    "git-has-changes"
]
```

Give the defaults, below is an example `package_info.py` file.

```python
"""Auto-generated by poetry-plugin-package-info at 2023-06-11T00:38:17."""
import datetime


class PackageInfo:
    project_name: str | None = "poetry-plugin-package-info"
    project_description: str | None = "Plugin for poetry that creates/updates a package_info.py file with various details about the project/package."
    project_version: str | None = "0.2.0"
    project_authors: list[str] | None = ["Ben Ellis <ben.ellis@softweyr.co.uk>"]
    project_license: str | None = "MIT"
    project_classifiers: list[str] | None = [
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "Intended Audience :: System Administrators",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Software Development :: Libraries",
        "Topic :: Software Development :: Version Control :: Git",
        "Topic :: Software Development",
        "Topic :: System :: Archiving :: Packaging",
        "Topic :: System :: Installation/Setup",
        "Topic :: System :: Software Distribution",
        "Development Status :: 3 - Alpha",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "License :: OSI Approved :: MIT License",
    ]
    project_documentation: str | None = (
        "https://github.com/bellis/poetry-plugin-package-info"
    )
    project_repository: str | None = None
    project_homepage: str | None = (
        "https://github.com/bellis/poetry-plugin-package-info"
    )
    project_maintainers: list[str] | None = None
    project_keywords: list[str] | None = None
    git_commit_id: str | None = "b69755ca54300baaabe5f92bc99b7e101712739b"
    git_commit_author_name: str | None = "Ben Ellis"
    git_commit_author_email: str | None = "ben.ellis@softweyr.co.uk"
    git_commit_timestamp: datetime.datetime | None = datetime.datetime.fromisoformat(
        "2023-06-11T00:31:29+01:00"
    )
    git_branch_name: str | None = "main"
    git_branch_path: str | None = "refs/heads/main"
    git_is_dirty: bool | None = True
    git_is_dirty_excluding_untracked: bool | None = True
    git_has_staged_changes: bool | None = False
    git_has_unstaged_changes: bool | None = True
    git_has_untracked_changes: bool | None = False
```

## How-to

### Change variable names

It is possible to override the name of the generated variable by expanding the properties section to

```toml
[tool.poetry-plugin-package-info]

properties = [
    "project-name",
    "project-description",
    "git-commit-id",
    { "property-generator" = "git", "property-name" = "is-dirty", "variable_name" = "clean_me" },
    { "property-name" = "git-is-dirty", "variable_name" = "clean_me_too" }
]

```

### Create a custom formatter

To create a custom formatter for the generated `package-info.py` file, you can implement the `ContentFormatter` abstract class.

```python
from poetry_plugin_package_info.plugin import (
    ContentFormatter,
    PackageInfoApplicationPlugin,
)

class MyContentFormatter(ContentFormatter):
    def init(
        self,
        plugin: PackageInfoApplicationPlugin,
    ) -> None:
        """Initialise the ContentFormatter for the provided plugin."""
        ...

    def format_content(self, content: str) -> str:
        """Format the given python file content."""
        ...
```

Once your class is available, you can add it to the formatter configuration in the `pyproject.toml` file.

```toml
formatters = [
    "poetry-plugin-package-info.formatters.black:BlackContentFormatter",
    "my_package.formatters.my_formatter:MyContentFormatter",
]
```

### Create a custom generator

To create a custom generator for the generated `package-info.py` file, you can implement the `PropertyGenerator` abstract class.

```python
from poetry_plugin_package_info.plugin import (
    PackageInfoApplicationPlugin,
    Property,
    PropertyConfig,
    PropertyGenerator,
)

class MyPropertyGenerator(PropertyGenerator):

    def short_name(self) -> str:
        """Shortname/Prefix for properties belonging to this generator."""

    def init(
        self,
        plugin: PackageInfoApplicationPlugin,
    ) -> None:
        """Initialise the PropertyGenerator for the provided plugin."""

    def generate_property(
        self,
        property_config: PropertyConfig,
    ) -> Property:
        """Generate the property for the given include configuration."""
```

Once your class is available, you can add it to the generators configuration in the `pyproject.toml` file.

```toml
generators = { mycustom = "my_package.generators.my_generator:MyPropertyGenerator", project = "poetry-plugin-package-info.generators.project:ProjectPropertyGenerator", git = "poetry-plugin-package-info.generators.git:GitPropertyGenerator" }
```

## Related Projects

* [website](https://github.com/python-poetry/website): The official Poetry website and blog
* [poetry-plugin-export](https://github.com/python-poetry/poetry-plugin-export): Export Poetry projects/lock files to
foreign formats like requirements.txt (Used some test code from this project)
