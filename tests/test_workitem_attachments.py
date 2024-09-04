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

# pylint: disable=relative-beyond-top-level, useless-suppression
from .conftest import TEST_DIAGRAM_CACHE
from .test_elements import TEST_DIAG_DESCR

DIAGRAM_WI_CHECKSUM = (
    "2c3aadc9b145917810e1988ed463a4b45f6d3c6506c24378b006ba922c4141b8"
)

TEST_DIAG_UUID = "_APOQ0QPhEeynfbzU12yy7w"
WORKITEM_ID = "TEST-ID"

with open(
    TEST_DIAGRAM_CACHE / f"{TEST_DIAG_UUID}.svg", "r", encoding="utf8"
) as f:
    diagram_svg = f.read()

wia_dict = {
    "work_item_id": WORKITEM_ID,
    "title": "Diagram",
    "content_bytes": base64.b64encode(cairosvg.svg2png(diagram_svg)).decode(
        "utf8"
    ),
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
    mock_api_client = mock.MagicMock(spec=polarion_api.PolarionClient)
    monkeypatch.setattr(polarion_api, "PolarionClient", mock_api_client)
    mock_project_client = mock.MagicMock(spec=polarion_api.ProjectClient)
    monkeypatch.setattr(polarion_api, "ProjectClient", mock_project_client)
    return polarion_worker.CapellaPolarionWorker(
        polarion_worker.PolarionWorkerParams(
            "TEST",
            "http://localhost",
            "TESTPAT",
            False,
        )
    )


def set_attachment_ids(attachments: list[polarion_api.WorkItemAttachment]):
    counter = 0
    attachments = sorted(attachments, key=lambda a: a.file_name)
    for attachment in attachments:
        attachment.id = f"{counter}-{attachment.file_name}"
        counter += 1


def test_diagram_no_attachments(model: capellambse.MelodyModel):
    converter = model_converter.ModelConverter(model, "TEST")
    converter.converter_session[TEST_DIAG_UUID] = data_session.ConverterData(
        "",
        converter_config.CapellaTypeConfig("diagram", "diagram", []),
        model.diagrams.by_uuid(TEST_DIAG_UUID),
    )
    converter.generate_work_items(
        polarion_repo.PolarionDataRepository(), False, False
    )
    work_item = converter.converter_session[TEST_DIAG_UUID].work_item
    assert work_item is not None
    assert work_item.attachments == []


def test_diagram_has_attachments(model: capellambse.MelodyModel):
    converter = model_converter.ModelConverter(model, "TEST")
    converter.converter_session[TEST_DIAG_UUID] = data_session.ConverterData(
        "",
        converter_config.CapellaTypeConfig("diagram", "diagram", []),
        model.diagrams.by_uuid(TEST_DIAG_UUID),
    )
    converter.generate_work_items(
        polarion_repo.PolarionDataRepository(), False, True
    )

    work_item = converter.converter_session[TEST_DIAG_UUID].work_item
    assert work_item is not None
    assert len(work_item.attachments) == 2


# pylint: disable=redefined-outer-name
def test_diagram_attachments_new(
    model: capellambse.MelodyModel,
    worker: polarion_worker.CapellaPolarionWorker,
):
    converter = model_converter.ModelConverter(model, "TEST")
    worker.polarion_data_repo = polarion_repo.PolarionDataRepository(
        [data_models.CapellaWorkItem(WORKITEM_ID, uuid_capella=TEST_DIAG_UUID)]
    )

    worker.project_client.work_items.get.return_value = (
        data_models.CapellaWorkItem(WORKITEM_ID, uuid_capella=TEST_DIAG_UUID)
    )
    worker.project_client.work_items.attachments = mock.MagicMock()
    worker.project_client.work_items.attachments.create.side_effect = (
        set_attachment_ids
    )

    converter.converter_session[TEST_DIAG_UUID] = data_session.ConverterData(
        "",
        converter_config.CapellaTypeConfig("diagram", "diagram", []),
        model.diagrams.by_uuid(TEST_DIAG_UUID),
    )

    converter.generate_work_items(worker.polarion_data_repo, False, True)

    worker.compare_and_update_work_item(
        converter.converter_session[TEST_DIAG_UUID]
    )

    assert worker.project_client.work_items.update.call_count == 1
    assert worker.project_client.work_items.attachments.create.call_count == 1
    assert worker.project_client.work_items.attachments.get_all.call_count == 0

    created_attachments: list[polarion_api.WorkItemAttachment] = (
        worker.project_client.work_items.attachments.create.call_args.args[0]
    )
    work_item: data_models.CapellaWorkItem = (
        worker.project_client.work_items.update.call_args.args[0]
    )

    assert len(created_attachments) == 2
    assert created_attachments[0].title == created_attachments[1].title
    assert (
        created_attachments[0].file_name[:3]
        == created_attachments[0].file_name[:3]
    )

    assert work_item.description == TEST_DIAG_DESCR.format(
        title="Diagram",
        attachment_id="1-__C2P__diagram.svg",
        width=750,
        cls="diagram",
    )
    assert work_item.get_current_checksum() == DIAGRAM_CHECKSUM


# pylint: disable=redefined-outer-name
def test_new_diagram(
    model: capellambse.MelodyModel,
    worker: polarion_worker.CapellaPolarionWorker,
):
    converter = model_converter.ModelConverter(model, "TEST")

    checksum = json.dumps({"__C2P__WORK_ITEM": DIAGRAM_WI_CHECKSUM})

    worker.polarion_data_repo = polarion_repo.PolarionDataRepository(
        [
            data_models.CapellaWorkItem(
                WORKITEM_ID, uuid_capella=TEST_DIAG_UUID, checksum=checksum
            )
        ]
    )

    worker.project_client.work_items.get.return_value = (
        data_models.CapellaWorkItem(
            WORKITEM_ID, uuid_capella=TEST_DIAG_UUID, checksum=checksum
        )
    )
    worker.project_client.work_items.attachments.create = mock.MagicMock()
    worker.project_client.work_items.attachments.create.side_effect = (
        set_attachment_ids
    )

    converter.converter_session[TEST_DIAG_UUID] = data_session.ConverterData(
        "",
        converter_config.CapellaTypeConfig("diagram", "diagram", []),
        model.diagrams.by_uuid(TEST_DIAG_UUID),
    )

    converter.generate_work_items(worker.polarion_data_repo, False, True)

    worker.compare_and_update_work_item(
        converter.converter_session[TEST_DIAG_UUID]
    )

    assert worker.project_client.work_items.update.call_count == 1
    assert worker.project_client.work_items.attachments.create.call_count == 1
    assert worker.project_client.work_items.update.call_args.args[
        0
    ].description == TEST_DIAG_DESCR.format(
        title="Diagram",
        attachment_id="1-__C2P__diagram.svg",
        width=750,
        cls="diagram",
    )


def test_diagram_attachments_updated(
    model: capellambse.MelodyModel,
    worker: polarion_worker.CapellaPolarionWorker,
):
    converter = model_converter.ModelConverter(model, "TEST")
    worker.polarion_data_repo = polarion_repo.PolarionDataRepository(
        [data_models.CapellaWorkItem(WORKITEM_ID, uuid_capella=TEST_DIAG_UUID)]
    )
    existing_attachments = [
        polarion_api.WorkItemAttachment(
            WORKITEM_ID,
            "SVG-ATTACHMENT",
            "test",
            file_name="__C2P__diagram.svg",
        ),
        polarion_api.WorkItemAttachment(
            WORKITEM_ID,
            "PNG-ATTACHMENT",
            "test",
            file_name="__C2P__diagram.png",
        ),
    ]

    worker.project_client.work_items.get.return_value = (
        data_models.CapellaWorkItem(
            WORKITEM_ID,
            uuid_capella=TEST_DIAG_UUID,
            attachments=existing_attachments,
        )
    )

    worker.project_client.work_items.attachments.get_all = mock.MagicMock()
    worker.project_client.work_items.attachments.get_all.return_value = (
        existing_attachments
    )

    converter.converter_session[TEST_DIAG_UUID] = data_session.ConverterData(
        "",
        converter_config.CapellaTypeConfig("diagram", "diagram", []),
        model.diagrams.by_uuid(TEST_DIAG_UUID),
    )

    converter.generate_work_items(worker.polarion_data_repo, False, True)

    worker.compare_and_update_work_item(
        converter.converter_session[TEST_DIAG_UUID]
    )

    assert worker.project_client.work_items.update.call_count == 1
    assert worker.project_client.work_items.attachments.create.call_count == 0
    assert worker.project_client.work_items.attachments.update.call_count == 2
    assert worker.project_client.work_items.attachments.get_all.call_count == 1

    work_item: data_models.CapellaWorkItem = (
        worker.project_client.work_items.update.call_args.args[0]
    )

    assert work_item.description == TEST_DIAG_DESCR.format(
        title="Diagram",
        attachment_id="SVG-ATTACHMENT",
        width=750,
        cls="diagram",
    )


def test_diagram_attachments_unchanged_work_item_changed(
    model: capellambse.MelodyModel,
    worker: polarion_worker.CapellaPolarionWorker,
):
    converter = model_converter.ModelConverter(model, "TEST")
    worker.polarion_data_repo = polarion_repo.PolarionDataRepository(
        [
            data_models.CapellaWorkItem(
                WORKITEM_ID,
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
    worker.project_client.work_items.attachments.get_all = mock.MagicMock()
    worker.project_client.work_items.attachments.get_all.return_value = [
        polarion_api.WorkItemAttachment(
            WORKITEM_ID,
            "SVG-ATTACHMENT",
            "test",
            file_name="__C2P__diagram.svg",
        ),
        polarion_api.WorkItemAttachment(
            WORKITEM_ID,
            "PNG-ATTACHMENT",
            "test",
            file_name="__C2P__diagram.png",
        ),
    ]

    converter.converter_session[TEST_DIAG_UUID] = data_session.ConverterData(
        "",
        converter_config.CapellaTypeConfig("diagram", "diagram", []),
        model.diagrams.by_uuid(TEST_DIAG_UUID),
    )

    converter.generate_work_items(worker.polarion_data_repo, False, True)

    worker.compare_and_update_work_item(
        converter.converter_session[TEST_DIAG_UUID]
    )

    assert worker.project_client.work_items.update.call_count == 1
    assert worker.project_client.work_items.attachments.create.call_count == 0
    assert worker.project_client.work_items.attachments.update.call_count == 0

    work_item: data_models.CapellaWorkItem = (
        worker.project_client.work_items.update.call_args.args[0]
    )

    assert work_item.description == TEST_DIAG_DESCR.format(
        title="Diagram",
        attachment_id="SVG-ATTACHMENT",
        width=750,
        cls="diagram",
    )


def test_diagram_attachments_fully_unchanged(
    model: capellambse.MelodyModel,
    worker: polarion_worker.CapellaPolarionWorker,
):
    converter = model_converter.ModelConverter(model, "TEST")
    worker.polarion_data_repo = polarion_repo.PolarionDataRepository(
        [
            data_models.CapellaWorkItem(
                WORKITEM_ID,
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

    worker.compare_and_update_work_item(
        converter.converter_session[TEST_DIAG_UUID]
    )

    assert worker.project_client.work_items.update.call_count == 0
    assert worker.project_client.work_items.attachments.create.call_count == 0
    assert worker.project_client.work_items.attachments.update.call_count == 0
    assert worker.project_client.work_items.attachments.get_all.call_count == 0


def test_add_context_diagram(
    model: capellambse.MelodyModel,
    worker: polarion_worker.CapellaPolarionWorker,
):
    uuid = "11906f7b-3ae9-4343-b998-95b170be2e2b"
    converter = model_converter.ModelConverter(model, "TEST")
    worker.polarion_data_repo = polarion_repo.PolarionDataRepository(
        [data_models.CapellaWorkItem(WORKITEM_ID, uuid_capella=uuid)]
    )

    converter.converter_session[uuid] = data_session.ConverterData(
        "",
        converter_config.CapellaTypeConfig("test", "add_context_diagram", []),
        model.by_uuid(uuid),
    )

    worker.project_client.work_items.attachments.create = mock.MagicMock()
    worker.project_client.work_items.attachments.create.side_effect = (
        set_attachment_ids
    )

    converter.generate_work_items(worker.polarion_data_repo, False, True)

    worker.compare_and_update_work_item(converter.converter_session[uuid])

    assert worker.project_client.work_items.update.call_count == 1
    assert worker.project_client.work_items.attachments.create.call_count == 1

    created_attachments: list[polarion_api.WorkItemAttachment] = (
        worker.project_client.work_items.attachments.create.call_args.args[0]
    )
    work_item: data_models.CapellaWorkItem = (
        worker.project_client.work_items.update.call_args.args[0]
    )

    assert len(created_attachments) == 2
    assert created_attachments[0].title == created_attachments[1].title
    assert (
        created_attachments[0].file_name[:3]
        == created_attachments[0].file_name[:3]
    )

    assert str(
        work_item.additional_attributes["context_diagram"]["value"]
    ) == TEST_DIAG_DESCR.format(
        title="Context Diagram",
        attachment_id="1-__C2P__context_diagram.svg",
        width=650,
        cls="additional-attributes-diagram",
    )


def test_diagram_delete_attachments(
    model: capellambse.MelodyModel,
    worker: polarion_worker.CapellaPolarionWorker,
):
    converter = model_converter.ModelConverter(model, "TEST")
    worker.polarion_data_repo = polarion_repo.PolarionDataRepository(
        [
            data_models.CapellaWorkItem(
                WORKITEM_ID,
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
    worker.project_client.work_items.attachments.get_all = mock.MagicMock()
    worker.project_client.work_items.attachments.get_all.return_value = [
        polarion_api.WorkItemAttachment(
            WORKITEM_ID,
            "SVG-ATTACHMENT",
            "test",
            file_name="__C2P__diagram.svg",
        ),
        polarion_api.WorkItemAttachment(
            WORKITEM_ID,
            "PNG-ATTACHMENT",
            "test",
            file_name="__C2P__diagram.png",
        ),
        polarion_api.WorkItemAttachment(
            WORKITEM_ID, "SVG-DELETE", "test", file_name="delete_me.svg"
        ),
        polarion_api.WorkItemAttachment(
            WORKITEM_ID, "PNG-DELETE", "test", file_name="delete_me.png"
        ),
    ]

    converter.converter_session[TEST_DIAG_UUID] = data_session.ConverterData(
        "",
        converter_config.CapellaTypeConfig("diagram", "diagram", []),
        model.diagrams.by_uuid(TEST_DIAG_UUID),
    )

    converter.generate_work_items(worker.polarion_data_repo, False, True)

    worker.compare_and_update_work_item(
        converter.converter_session[TEST_DIAG_UUID]
    )

    assert worker.project_client.work_items.update.call_count == 1
    assert worker.project_client.work_items.attachments.create.call_count == 0
    assert worker.project_client.work_items.attachments.update.call_count == 0
    assert worker.project_client.work_items.attachments.delete.call_count == 2

    work_item: data_models.CapellaWorkItem = (
        worker.project_client.work_items.update.call_args.args[0]
    )

    assert work_item.description is None
    assert work_item.additional_attributes == {}
    assert work_item.title is None
    assert work_item.get_current_checksum() == DIAGRAM_CHECKSUM
