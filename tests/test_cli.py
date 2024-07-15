# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from unittest import mock

import polarion_rest_api_client as polarion_api
import pytest
from click import testing

import capella2polarion.__main__ as main
from capella2polarion.connectors.polarion_worker import CapellaPolarionWorker

# pylint: disable-next=relative-beyond-top-level, useless-suppression
from .conftest import (  # type: ignore[import]
    TEST_MODEL,
    TEST_MODEL_ELEMENTS_CONFIG,
)


def test_migrate_model_elements(monkeypatch: pytest.MonkeyPatch):
    mock_api = mock.MagicMock(spec=polarion_api.OpenAPIPolarionProjectClient)
    monkeypatch.setattr(polarion_api, "OpenAPIPolarionProjectClient", mock_api)
    mock_get_polarion_wi_map = mock.MagicMock()
    monkeypatch.setattr(
        CapellaPolarionWorker,
        "load_polarion_work_item_map",
        mock_get_polarion_wi_map,
    )
    mock_delete_work_items = mock.MagicMock()
    monkeypatch.setattr(
        CapellaPolarionWorker,
        "delete_orphaned_work_items",
        mock_delete_work_items,
    )
    mock_post_work_items = mock.MagicMock()
    monkeypatch.setattr(
        CapellaPolarionWorker,
        "create_missing_work_items",
        mock_post_work_items,
    )
    mock_patch_work_items = mock.MagicMock()
    monkeypatch.setattr(
        CapellaPolarionWorker,
        "compare_and_update_work_items",
        mock_patch_work_items,
    )

    command: list[str] = [
        "--polarion-project-id",
        "{project-id}",
        "--polarion-url",
        "https://www.czy.de",
        "--polarion-pat",
        "AlexandersPrivateAcessToken",
        "--polarion-delete-work-items",
        "--capella-model",
        json.dumps(TEST_MODEL),
        "synchronize",
        "--synchronize-config",
        str(TEST_MODEL_ELEMENTS_CONFIG),
    ]

    result = testing.CliRunner().invoke(main.cli, command, terminal_width=60)

    assert result.exit_code == 0

    assert mock_get_polarion_wi_map.call_count == 1
    assert mock_delete_work_items.call_count == 1
    assert mock_patch_work_items.call_count == 1
    assert mock_post_work_items.call_count == 1
