# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import logging
from unittest import mock

import polarion_rest_api_client as polarion_api
import pytest
from click import testing

import capella2polarion.__main__ as main
from capella2polarion import cli
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
        CapellaPolarionWorker, "delete_work_items", mock_delete_work_items
    )
    mock_post_work_items = mock.MagicMock()
    monkeypatch.setattr(
        CapellaPolarionWorker, "post_work_items", mock_post_work_items
    )
    mock_patch_work_items = mock.MagicMock()
    monkeypatch.setattr(
        CapellaPolarionWorker, "patch_work_items", mock_patch_work_items
    )

    command: list[str] = [
        "--polarion-project-id",
        "{project-id}",
        "--polarion-url",
        "https://www.czy.de",
        "--polarion-pat",
        "PrivateAcessToken",
        "--polarion-delete-work-items",
        "--capella-model",
        json.dumps(TEST_MODEL),
        "--synchronize-config",
        str(TEST_MODEL_ELEMENTS_CONFIG),
        "synchronize",
    ]

    result = testing.CliRunner().invoke(main.cli, command, terminal_width=60)

    assert result.exit_code == 0

    assert mock_get_polarion_wi_map.call_count == 1
    assert mock_delete_work_items.call_count == 1
    assert mock_patch_work_items.call_count == 1
    assert mock_post_work_items.call_count == 1


@pytest.mark.parametrize(
    "log_level, expected_warning, expected_error, determine",
    [
        pytest.param(logging.WARNING, True, False, True, id="Only Warning"),
        pytest.param(logging.ERROR, False, True, True, id="Only Error"),
        pytest.param(logging.INFO, False, False, True, id="Only Info"),
        pytest.param(logging.DEBUG, False, False, True, id="Only Debug"),
        pytest.param(
            logging.WARNING, False, False, False, id="No Exit Code on Error"
        ),
        pytest.param(
            logging.ERROR, False, False, False, id="No Exit Code on Warning"
        ),
    ],
)
def test_exit_code_handler(
    c2p_polarion_cli: cli.Capella2PolarionCli,
    log_level,
    expected_warning,
    expected_error,
    determine,
):
    c2p_polarion_cli.exit_code_handler.determine = determine
    logger = logging.getLogger()

    logger.log(log_level, "This is a %s", log_level)

    assert c2p_polarion_cli.exit_code_handler.has_warning is expected_warning
    assert c2p_polarion_cli.exit_code_handler.has_error is expected_error
