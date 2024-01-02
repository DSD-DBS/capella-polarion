# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""The capella2polarion package."""
from importlib import metadata

try:
    __version__ = metadata.version("capella2polarion")
except metadata.PackageNotFoundError:
    __version__ = "0.0.0+unknown"
del metadata
