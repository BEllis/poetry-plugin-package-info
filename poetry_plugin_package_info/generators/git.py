"""
Built-in Git properties generator for poetry-plugin-package-info.

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

from datetime import datetime
from typing import Any

from git import InvalidGitRepositoryError
from git.repo import Repo as GitRepo

from poetry_plugin_package_info.plugin import (
    PackageInfoApplicationPlugin,
    Property,
    PropertyConfig,
    PropertyGenerator,
    UnsupportedIncludeItemError,
)


class GitPropertyGenerator(PropertyGenerator):
    """Built-in Git properties generator for poetry-plugin-package-info."""

    git_search_parent_directories: bool
    git_is_bare: bool = False
    detached_head: bool = False
    git_repo: GitRepo | None

    def short_name(self: "GitPropertyGenerator") -> str:
        """Shortname/Prefix for properties belonging to this generator."""
        return "git"

    def init(
        self: "GitPropertyGenerator",
        plugin: PackageInfoApplicationPlugin,
    ) -> None:
        """Initialise the PropertyGenerator for the provided plugin."""
        self.git_search_parent_directories = (
            plugin.plugin_config.get_or_default(
                "git-search-parent-directories",
                default=False,
            )
        )

        try:
            self.git_repo = GitRepo(
                plugin.pyproject_file_dir,
                search_parent_directories=self.git_search_parent_directories,
            )

            # Check there is at least one commit in the repo.
            try:
                self.git_repo.head.commit  # noqa: B018
            except ValueError as e:
                if len(e.args) > 0 and e.args[0].startswith("Reference at"):
                    self.git_is_bare = True

            # Patch active_branch for detached head case.
            try:
                _ = self.git_repo.active_branch
            except TypeError:
                self.detached_head = True

        except InvalidGitRepositoryError:
            self.git_repo = None

    def generate_property(
        self: "GitPropertyGenerator",
        property_config: PropertyConfig,
    ) -> Property:
        """Generate the property for the given include configuration."""
        property_value: Any = None
        property_type: Any = None
        match property_config.property_name:
            case "commit-id":
                property_value = (
                    (
                        self.git_repo.head.commit.hexsha
                        if not self.git_is_bare
                        else None
                    )
                    if self.git_repo is not None
                    else None
                )
                property_type = str | None
            case "commit-author-name":
                property_value = (
                    (
                        self.git_repo.head.commit.author.name
                        if not self.git_is_bare
                        else None
                    )
                    if self.git_repo is not None
                    else None
                )
                property_type = str | None
            case "commit-author-email":
                property_value = (
                    (
                        self.git_repo.head.commit.author.email
                        if not self.git_is_bare
                        else None
                    )
                    if self.git_repo is not None
                    else None
                )
                property_type = str | None
            case "commit-timestamp":
                property_value = (
                    (
                        self.git_repo.head.commit.committed_datetime
                        if not self.git_is_bare
                        else None
                    )
                    if self.git_repo is not None
                    else None
                )
                property_type = datetime | None

            case "is-dirty":
                property_value = (
                    self.git_repo.is_dirty(untracked_files=True)
                    if self.git_repo is not None
                    else None
                )
                property_type = bool | None

            case "is-dirty-excluding-untracked":
                property_value = (
                    self.git_repo.is_dirty(untracked_files=False)
                    if self.git_repo is not None
                    else None
                )
                property_type = bool | None

            case "has-staged-changes":
                property_value = (
                    (
                        (len(self.git_repo.index.diff("HEAD")) > 0)
                        if not self.git_is_bare
                        else False
                    )
                    if self.git_repo is not None
                    else None
                )

                property_type = bool | None

            case "has-unstaged-changes":
                property_value = (
                    (len(self.git_repo.index.diff(None)) > 0)
                    if self.git_repo is not None
                    else None
                )
                property_type = bool | None

            case "has-untracked-changes":
                property_value = (
                    (len(self.git_repo.untracked_files) > 0)
                    if self.git_repo is not None
                    else None
                )
                property_type = bool | None

            case "branch-name":
                property_value = (
                    self.git_repo.active_branch.name
                    if self.git_repo is not None and not self.detached_head
                    else None
                )
                property_type = str | None

            case "branch-path":
                property_value = (
                    self.git_repo.active_branch.path
                    if self.git_repo is not None and not self.detached_head
                    else None
                )
                property_type = str | None

            case "tags":
                property_value = (
                    [
                        tag.name
                        for tag in self.git_repo.tags
                        if tag.commit == self.git_repo.head.commit
                    ]
                    if self.git_repo is not None
                    else None
                )
                property_type = list[str] | None

            case _:
                raise UnsupportedIncludeItemError(
                    f"{property_config.property_name}",
                )

        return Property(
            property_config=property_config,
            property_value=property_value,
            property_type=property_type,
            metadata={"git_is_bare": self.git_is_bare},
        )
