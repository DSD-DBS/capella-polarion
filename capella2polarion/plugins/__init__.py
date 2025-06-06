# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""A package providing plugin interface related modules."""

from importlib.metadata import entry_points


def load_plugins() -> dict[str, type]:
    eps = entry_points().select(group="capella2polarion.plugins")
    return {ep.name: ep.load() for ep in eps}
