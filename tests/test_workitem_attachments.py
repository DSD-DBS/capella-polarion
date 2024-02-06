# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
import base64
import hashlib
import json
from unittest import mock

import cairosvg
import capellambse
import polarion_rest_api_client as polarion_api
import pytest

from capella2polarion import data_models
from capella2polarion.connectors import polarion_repo, polarion_worker
from capella2polarion.converters import (
    converter_config,
    data_session,
    model_converter,
)

from .conftest import TEST_DIAGRAM_CACHE

DIAGRAM_WI_CHECKSUM = (
    "37121e4c32bfae03ab387051f676f976de3b5b8b92c22351d906534ddf0a3ee8"
)

TEST_DIAG_UUID = "_APMboAPhEeynfbzU12yy7w"

with open(
    TEST_DIAGRAM_CACHE / "_APMboAPhEeynfbzU12yy7w.svg", "r", encoding="utf8"
) as f:
    diagram_svg = f.read()

wia_dict = {
    "work_item_id": "",
    "title": "Diagram",
    "content_bytes": base64.b64encode(
        cairosvg.svg2png(diagram_svg, dpi=400)
    ).decode("utf8"),
    "mime_type": "image/png",
    "file_name": "__C2P__diagram.png",
}

DIAGRAM_PNG_CHECKSUM = hashlib.sha256(
    json.dumps(wia_dict).encode("utf8")
).hexdigest()
DIAGRAM_CHECKSUM = json.dumps(
    {
        "__C2P__WORK_ITEM": DIAGRAM_WI_CHECKSUM,
        "__C2P__diagram.png": DIAGRAM_PNG_CHECKSUM,
    }
)


@pytest.fixture
def worker(monkeypatch: pytest.MonkeyPatch):
    mock_api = mock.MagicMock(spec=polarion_api.OpenAPIPolarionProjectClient)
    monkeypatch.setattr(polarion_api, "OpenAPIPolarionProjectClient", mock_api)
    config = mock.Mock(converter_config.ConverterConfig)
    worker = polarion_worker.CapellaPolarionWorker(
        polarion_worker.PolarionWorkerParams(
            "TEST",
            "http://localhost",
            "TESTPAT",
            False,
        ),
        config,
    )

    return worker


def set_attachment_ids(attachments: list[polarion_api.WorkItemAttachment]):
    counter = 0
    attachments = sorted(attachments, key=lambda a: a.file_name)
    for attachment in attachments:
        attachment.id = f"{counter}-{attachment.file_name}"
        counter += 1


def test_diagram_attachments_new(
    model: capellambse.MelodyModel,
    worker: polarion_worker.CapellaPolarionWorker,
):
    converter = model_converter.ModelConverter(model, "TEST")
    worker.polarion_data_repo = polarion_repo.PolarionDataRepository(
        [data_models.CapellaWorkItem("TEST-ID", uuid_capella=TEST_DIAG_UUID)]
    )
    worker.client.create_work_item_attachments = mock.MagicMock()
    worker.client.create_work_item_attachments.side_effect = set_attachment_ids

    converter.converter_session[TEST_DIAG_UUID] = data_session.ConverterData(
        "",
        converter_config.CapellaTypeConfig("diagram", "diagram", []),
        model.diagrams.by_uuid(TEST_DIAG_UUID),
    )

    converter.generate_work_items(worker.polarion_data_repo, False, True)

    worker.patch_work_item(TEST_DIAG_UUID, converter.converter_session)

    assert worker.client.update_work_item.call_count == 1
    assert worker.client.create_work_item_attachments.call_count == 1

    created_attachments: list[
        polarion_api.WorkItemAttachment
    ] = worker.client.create_work_item_attachments.call_args.args[0]
    work_item: data_models.CapellaWorkItem = (
        worker.client.update_work_item.call_args.args[0]
    )

    assert len(created_attachments) == 2
    assert created_attachments[0].title == created_attachments[1].title
    assert (
        created_attachments[0].file_name[:3]
        == created_attachments[0].file_name[:3]
    )

    assert (
        work_item.description == '<p><img style="max-width: 100%" '
        'src="workitemimg:1-__C2P__diagram.svg"/>'
        "</p>"
    )
    assert work_item.get_current_checksum() == DIAGRAM_CHECKSUM


def test_diagram_attachments_updated(
    model: capellambse.MelodyModel,
    worker: polarion_worker.CapellaPolarionWorker,
):
    converter = model_converter.ModelConverter(model, "TEST")
    worker.polarion_data_repo = polarion_repo.PolarionDataRepository(
        [data_models.CapellaWorkItem("TEST-ID", uuid_capella=TEST_DIAG_UUID)]
    )
    worker.client.get_all_work_item_attachments = mock.MagicMock()
    worker.client.get_all_work_item_attachments.return_value = [
        polarion_api.WorkItemAttachment(
            "TEST-ID", "SVG-ATTACHMENT", "test", file_name="__C2P__diagram.svg"
        ),
        polarion_api.WorkItemAttachment(
            "TEST-ID", "PNG-ATTACHMENT", "test", file_name="__C2P__diagram.png"
        ),
    ]

    converter.converter_session[TEST_DIAG_UUID] = data_session.ConverterData(
        "",
        converter_config.CapellaTypeConfig("diagram", "diagram", []),
        model.diagrams.by_uuid(TEST_DIAG_UUID),
    )

    converter.generate_work_items(worker.polarion_data_repo, False, True)

    worker.patch_work_item(TEST_DIAG_UUID, converter.converter_session)

    assert worker.client.update_work_item.call_count == 1
    assert worker.client.create_work_item_attachments.call_count == 0
    assert worker.client.update_work_item_attachment.call_count == 2

    work_item: data_models.CapellaWorkItem = (
        worker.client.update_work_item.call_args.args[0]
    )

    assert (
        work_item.description == '<p><img style="max-width: 100%" '
        'src="workitemimg:SVG-ATTACHMENT"/>'
        "</p>"
    )


def test_diagram_attachments_unchanged_work_item_changed(
    model: capellambse.MelodyModel,
    worker: polarion_worker.CapellaPolarionWorker,
):
    converter = model_converter.ModelConverter(model, "TEST")
    worker.polarion_data_repo = polarion_repo.PolarionDataRepository(
        [
            data_models.CapellaWorkItem(
                "TEST-ID",
                uuid_capella=TEST_DIAG_UUID,
                checksum=json.dumps(
                    {
                        "__C2P__WORK_ITEM": "123",
                        "__C2P__diagram.png": DIAGRAM_PNG_CHECKSUM,
                    }
                ),
            )
        ]
    )
    worker.client.get_all_work_item_attachments = mock.MagicMock()
    worker.client.get_all_work_item_attachments.return_value = [
        polarion_api.WorkItemAttachment(
            "TEST-ID", "SVG-ATTACHMENT", "test", file_name="__C2P__diagram.svg"
        ),
        polarion_api.WorkItemAttachment(
            "TEST-ID", "PNG-ATTACHMENT", "test", file_name="__C2P__diagram.png"
        ),
    ]

    converter.converter_session[TEST_DIAG_UUID] = data_session.ConverterData(
        "",
        converter_config.CapellaTypeConfig("diagram", "diagram", []),
        model.diagrams.by_uuid(TEST_DIAG_UUID),
    )

    converter.generate_work_items(worker.polarion_data_repo, False, True)

    worker.patch_work_item(TEST_DIAG_UUID, converter.converter_session)

    assert worker.client.update_work_item.call_count == 1
    assert worker.client.create_work_item_attachments.call_count == 0
    assert worker.client.update_work_item_attachment.call_count == 0

    work_item: data_models.CapellaWorkItem = (
        worker.client.update_work_item.call_args.args[0]
    )

    assert (
        work_item.description == '<p><img style="max-width: 100%" '
        'src="workitemimg:SVG-ATTACHMENT"/>'
        "</p>"
    )


def test_diagram_attachments_fully_unchanged(
    model: capellambse.MelodyModel,
    worker: polarion_worker.CapellaPolarionWorker,
):
    converter = model_converter.ModelConverter(model, "TEST")
    worker.polarion_data_repo = polarion_repo.PolarionDataRepository(
        [
            data_models.CapellaWorkItem(
                "TEST-ID",
                uuid_capella=TEST_DIAG_UUID,
                checksum=DIAGRAM_CHECKSUM,
            )
        ]
    )

    converter.converter_session[TEST_DIAG_UUID] = data_session.ConverterData(
        "",
        converter_config.CapellaTypeConfig("diagram", "diagram", []),
        model.diagrams.by_uuid(TEST_DIAG_UUID),
    )

    converter.generate_work_items(worker.polarion_data_repo, False, True)

    worker.patch_work_item(TEST_DIAG_UUID, converter.converter_session)

    assert worker.client.update_work_item.call_count == 0
    assert worker.client.create_work_item_attachments.call_count == 0
    assert worker.client.update_work_item_attachment.call_count == 0
    assert worker.client.get_all_work_item_attachments.call_count == 0


def test_add_context_diagram(
    model: capellambse.MelodyModel,
    worker: polarion_worker.CapellaPolarionWorker,
):
    uuid = "11906f7b-3ae9-4343-b998-95b170be2e2b"
    converter = model_converter.ModelConverter(model, "TEST")
    worker.polarion_data_repo = polarion_repo.PolarionDataRepository(
        [data_models.CapellaWorkItem("TEST-ID", uuid_capella=uuid)]
    )

    converter.converter_session[uuid] = data_session.ConverterData(
        "",
        converter_config.CapellaTypeConfig("test", "add_context_diagram", []),
        model.by_uuid(uuid),
    )

    worker.client.create_work_item_attachments = mock.MagicMock()
    worker.client.create_work_item_attachments.side_effect = set_attachment_ids

    converter.generate_work_items(worker.polarion_data_repo, False, True)

    worker.patch_work_item(uuid, converter.converter_session)

    assert worker.client.update_work_item.call_count == 1
    assert worker.client.create_work_item_attachments.call_count == 1

    created_attachments: list[
        polarion_api.WorkItemAttachment
    ] = worker.client.create_work_item_attachments.call_args.args[0]
    work_item: data_models.CapellaWorkItem = (
        worker.client.update_work_item.call_args.args[0]
    )

    assert len(created_attachments) == 2
    assert created_attachments[0].title == created_attachments[1].title
    assert (
        created_attachments[0].file_name[:3]
        == created_attachments[0].file_name[:3]
    )

    assert (
        str(work_item.additional_attributes["context_diagram"]["value"])
        == '<p><img style="max-width: 100%" '
        'src="workitemimg:1-__C2P__context_diagram.svg"/></p>'
    )


def test_diagram_delete_attachments(
    model: capellambse.MelodyModel,
    worker: polarion_worker.CapellaPolarionWorker,
):
    converter = model_converter.ModelConverter(model, "TEST")
    worker.polarion_data_repo = polarion_repo.PolarionDataRepository(
        [
            data_models.CapellaWorkItem(
                "TEST-ID",
                uuid_capella=TEST_DIAG_UUID,
                checksum=json.dumps(
                    {
                        "__C2P__WORK_ITEM": DIAGRAM_WI_CHECKSUM,
                        "__C2P__diagram.png": DIAGRAM_PNG_CHECKSUM,
                        "delete_me.png": "123",
                    }
                ),
            )
        ]
    )
    worker.client.get_all_work_item_attachments = mock.MagicMock()
    worker.client.get_all_work_item_attachments.return_value = [
        polarion_api.WorkItemAttachment(
            "TEST-ID", "SVG-ATTACHMENT", "test", file_name="__C2P__diagram.svg"
        ),
        polarion_api.WorkItemAttachment(
            "TEST-ID", "PNG-ATTACHMENT", "test", file_name="__C2P__diagram.png"
        ),
        polarion_api.WorkItemAttachment(
            "TEST-ID", "SVG-DELETE", "test", file_name="delete_me.svg"
        ),
        polarion_api.WorkItemAttachment(
            "TEST-ID", "PNG-DELETE", "test", file_name="delete_me.png"
        ),
    ]

    converter.converter_session[TEST_DIAG_UUID] = data_session.ConverterData(
        "",
        converter_config.CapellaTypeConfig("diagram", "diagram", []),
        model.diagrams.by_uuid(TEST_DIAG_UUID),
    )

    converter.generate_work_items(worker.polarion_data_repo, False, True)

    worker.patch_work_item(TEST_DIAG_UUID, converter.converter_session)

    assert worker.client.update_work_item.call_count == 1
    assert worker.client.create_work_item_attachments.call_count == 0
    assert worker.client.update_work_item_attachment.call_count == 0
    assert worker.client.delete_work_item_attachment.call_count == 2

    work_item: data_models.CapellaWorkItem = (
        worker.client.update_work_item.call_args.args[0]
    )

    assert work_item.description is None
    assert work_item.additional_attributes == {}
    assert work_item.title is None
    assert work_item.get_current_checksum() == DIAGRAM_CHECKSUM
