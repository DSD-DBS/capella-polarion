# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import pathlib
import typing as t

import capellambse
import markupsafe
import polarion_rest_api_client as polarion_api
import pytest

from capella2polarion import data_models

TEST_DATA_ROOT = pathlib.Path(__file__).parent / "data"
TEST_DIAGRAM_CACHE = TEST_DATA_ROOT / "diagram_cache"
TEST_MODEL_ELEMENTS = TEST_DATA_ROOT / "model_elements"
TEST_MODEL_ELEMENTS_CONFIG = TEST_MODEL_ELEMENTS / "new_config.yaml"
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


@pytest.fixture
def dummy_work_items() -> dict[str, data_models.CapellaWorkItem]:
    return {
        f"uuid{i}": data_models.CapellaWorkItem(
            id=f"Obj-{i}",
            uuid_capella=f"uuid{i}",
            title=f"Fake {i}",
            type="fakeModelObject",
            description_type="text/html",
            description=markupsafe.Markup(""),
            linked_work_items=[
                polarion_api.WorkItemLink(
                    f"Obj-{i}", f"Obj-{j}", "attribute", True, "project_id"
                )
                for j in range(3)
                if (i not in (j, 2))
            ],
            status="open",
        )
        for i in range(3)
    }
