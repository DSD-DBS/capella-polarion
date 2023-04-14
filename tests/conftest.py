# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import pathlib
import typing as t

import capellambse
import pytest

TEST_DATA_ROOT = pathlib.Path(__file__).parent / "data"
TEST_DIAGRAM_CACHE = TEST_DATA_ROOT / "diagram_cache"
TEST_MODEL_ELEMENTS = TEST_DATA_ROOT / "model_elements"
TEST_MODEL_ELEMENTS_CONFIG = TEST_MODEL_ELEMENTS / "config.yaml"
TEST_MODEL = TEST_DATA_ROOT / "model" / "Melody Model Test.aird"
TEST_HOST = "https://api.example.com"


@pytest.fixture
def diagram_cache_index() -> list[dict[str, t.Any]]:
    """Return the test diagram cache index."""
    path = TEST_DIAGRAM_CACHE / "index.json"
    return json.loads(path.read_text(encoding="utf8"))


@pytest.fixture
def model() -> capellambse.MelodyModel:
    """Return the test model."""
    return capellambse.MelodyModel(path=TEST_MODEL)
