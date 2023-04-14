# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import typing as t
from unittest import mock

import capellambse
import markupsafe
import pytest

from capella2polarion import elements, polarion_api
from capella2polarion.elements import diagram, element, helpers, serialize

# pylint: disable-next=relative-beyond-top-level, useless-suppression
from .conftest import TEST_DIAGRAM_CACHE, TEST_HOST  # type: ignore[import]

# pylint: disable=redefined-outer-name
TEST_DIAG_UUID = "_6Td1kOQ8Ee2tXvmHzHzXCA"
TEST_ELEMENT_UUID = "0d2edb8f-fa34-4e73-89ec-fb9a63001440"
TEST_OCAP_UUID = "83d1334f-6180-46c4-a80d-6839341df688"
TEST_DESCR = (
    "<p>This instance is the mighty Hogwarts. Do you really need a "
    "description? Then maybe read the books or watch atleast the epic movies."
    "</p>\n"
)
TEST_WE_UUID = "e37510b9-3166-4f80-a919-dfaac9b696c7"
TEST_E_UUID = "4bf0356c-89dd-45e9-b8a6-e0332c026d33"
TEST_WE_DESCR = (
    '<p><span class="polarion-rte-link" data-type="workItem" '
    'id="fake" data-item-id="TEST" data-option-id="long"/></p>\n'
)
TEST_ACTOR_UUID = "08e02248-504d-4ed8-a295-c7682a614f66"
TEST_PHYS_COMP = "b9f9a83c-fb02-44f7-9123-9d86326de5f1"
TEST_PHYS_NODE = "8a6d68c8-ac3d-4654-a07e-ada7adeed09f"
TEST_POL_ID_MAP = {TEST_E_UUID: "TEST"}
TEST_POL_TYPE_MAP = {
    TEST_ELEMENT_UUID: "LogicalComponent",
    TEST_OCAP_UUID: "OperationalCapability",
    TEST_WE_UUID: "Entity",
}
TEST_SER_DIAGRAM: dict[str, t.Any] = {
    "id": None,
    "title": "[CDB] Class tests",
    "description_type": "text/html",
    "type": "diagram",
    "uuid_capella": "_Eiw7IOQ9Ee2tXvmHzHzXCA",
    "status": None,
    "additional_attributes": {},
}
TEST_DIAG_DESCR = (
    '<html><p><img style="max-width=100%" src="data:image/svg+xml;base64,'
)


class TestDiagramElements:
    @staticmethod
    @pytest.fixture
    def context(
        diagram_cache_index: list[dict[str, t.Any]]
    ) -> dict[str, t.Any]:
        api = mock.MagicMock(spec=polarion_api.OpenAPIPolarionProjectClient)
        return {
            "API": api,
            "PROJECT_ID": "project_id",
            "CAPELLA_UUIDS": [d["uuid"] for d in diagram_cache_index],
            "POLARION_ID_MAP": {diagram_cache_index[0]["uuid"]: "Diag-1"},
            "DIAGRAM_IDX": diagram_cache_index,
            "DIAGRAM_CACHE": TEST_DIAGRAM_CACHE,
            "REST_API_URL": TEST_HOST,
        }

    @staticmethod
    def test_create_diagrams(context: dict[str, t.Any]):
        diagram.create_diagrams(context)

        work_item = context["API"].create_work_items.call_args[0][0][0]
        assert context["API"].create_work_items.call_count == 1
        assert isinstance(work_item, polarion_api.WorkItem)
        assert {
            "id": work_item.id,
            "status": work_item.status,
            "description_type": work_item.description_type,
            "title": work_item.title,
            "type": work_item.type,
            "uuid_capella": work_item.uuid_capella,
            "additional_attributes": work_item.additional_attributes,
        } == TEST_SER_DIAGRAM
        assert isinstance(work_item.description, str)
        assert work_item.description.startswith(TEST_DIAG_DESCR)

    @staticmethod
    def test_create_diagrams_filters_non_diagram_elements(
        monkeypatch: pytest.MonkeyPatch, context: dict[str, t.Any]
    ):
        attributes = mock.MagicMock()
        attributes.return_value = None
        monkeypatch.setattr(serialize, "element", attributes)

        diagram.create_diagrams(context)

        assert context["API"].create_work_items.call_count == 0

    @staticmethod
    def test_update_diagrams(context: dict[str, t.Any]):
        diagram.update_diagrams(context)

        work_item = context["API"].update_work_item.call_args[0][0]
        assert context["API"].update_work_item.call_count == 1
        assert isinstance(work_item.description, str)
        assert work_item.id == "Diag-1"
        assert work_item.status == "open"
        assert work_item.title == "[CC] Capability"
        assert work_item.type is None
        assert work_item.uuid_capella is None
        assert work_item.description.startswith(TEST_DIAG_DESCR)

    @staticmethod
    def test_update_diagrams_filter_non_diagram_elements(
        monkeypatch: pytest.MonkeyPatch, context: dict[str, t.Any]
    ):
        attributes = mock.MagicMock()
        attributes.return_value = None
        monkeypatch.setattr(serialize, "element", attributes)

        diagram.update_diagrams(context)

        assert context["API"].update_work_item.call_count == 0

    @staticmethod
    def test_delete_diagrams(context: dict[str, t.Any]):
        context["CAPELLA_UUIDS"] = []

        elements.delete_work_items(context)

        assert context["API"].delete_work_items.call_count == 1
        assert context["API"].delete_work_items.call_args[0][0] == ["Diag-1"]


class FakeModelObject:
    """Mimicks a capellambse model object."""

    def __init__(
        self,
        uuid: str,
        name: str = "",
        attribute: FakeModelObject | None = None,
    ):
        self.uuid = uuid
        self.name = name
        self.attribute = attribute

    def _short_repr_(self) -> str:
        return f"<{type(self).__name__} {self.name!r} ({self.uuid})>"


class UnsupportedFakeModelObject(FakeModelObject):
    """A ``FakeModelObject`` which shouldn't be migrated."""


class TestModelElements:
    @staticmethod
    @pytest.fixture
    def context() -> dict[str, t.Any]:
        api = mock.MagicMock(spec=polarion_api.OpenAPIPolarionProjectClient)
        fake = FakeModelObject("uuid1", name="Fake 1")
        return {
            "API": api,
            "PROJECT_ID": "project_id",
            "ELEMENTS": {
                "FakeModelObject": [
                    fake,
                    FakeModelObject("uuid2", name="Fake 2", attribute=fake),
                ],
                "UnsupportedFakeModelObject": [
                    UnsupportedFakeModelObject("uuid3")
                ],
            },
            "POLARION_ID_MAP": {"uuid1": "Obj-1"},
            "CONFIG": {},
            "ROLES": {"FakeModelObject": ["attribute"]},
        }

    @staticmethod
    def test_create_work_items(
        monkeypatch: pytest.MonkeyPatch, context: dict[str, t.Any]
    ):
        monkeypatch.setattr(
            serialize,
            "generic_attributes",
            mock_generic_attributes := mock.MagicMock(),
        )
        mock_generic_attributes.side_effect = [
            wi_ := {
                "uuid_capella": "uuid1",
                "title": "Fake 1",
                "type": "fakeModelObject",
                "description_type": "text/html",
                "description": markupsafe.Markup(""),
            },
            wi_1 := {
                "uuid_capella": "uuid2",
                "title": "Fake 2",
                "type": "fakeModelObject",
                "description_type": "text/html",
                "description": markupsafe.Markup(""),
            },
        ]

        element.create_work_items(context)

        wi, wi1 = context["API"].create_work_items.call_args[0][0]
        assert context["API"].create_work_items.call_count == 1
        assert wi == polarion_api.WorkItem(**wi_)  # type: ignore[arg-type]
        assert wi1 == polarion_api.WorkItem(**wi_1)  # type: ignore[arg-type]

    @staticmethod
    def test_update_work_items(
        monkeypatch: pytest.MonkeyPatch, context: dict[str, t.Any]
    ):
        monkeypatch.setattr(
            serialize,
            "generic_attributes",
            mock_generic_attributes := mock.MagicMock(),
        )
        mock_generic_attributes.return_value = {
            "type": "type",
            "uuid_capella": "uuid1",
            "title": "Something",
            "description_type": "text/html",
            "description": (expected_markup := markupsafe.Markup("Test")),
        }

        element.update_work_items(context)

        work_item = context["API"].update_work_item.call_args[0][0]
        assert context["API"].update_work_item.call_count == 1
        assert isinstance(work_item, polarion_api.WorkItem)
        assert work_item.id == "Obj-1"
        assert work_item.title == "Something"
        assert work_item.description_type == "text/html"
        assert work_item.description == expected_markup
        assert work_item.type is None
        assert work_item.uuid_capella is None
        assert work_item.status == "open"

    @staticmethod
    def test_update_links_with_no_elements(context: dict[str, t.Any]):
        context["POLARION_ID_MAP"] = {}

        element.update_links(context)

        assert context["API"].get_all_work_item_links.call_count == 0

    @staticmethod
    def test_update_links(context: dict[str, t.Any]):
        context["POLARION_ID_MAP"]["uuid2"] = "Obj-2"
        context["API"].get_all_work_item_links.return_value = [
            link := polarion_api.WorkItemLink(
                "Obj-1", "Obj-2", "attribute", True, "project_id"
            )
        ]
        expected_new_link = polarion_api.WorkItemLink(
            "Obj-2", "Obj-1", "attribute", None, "project_id"
        )

        element.update_links(context)

        links = context["API"].get_all_work_item_links.call_args_list
        assert context["API"].get_all_work_item_links.call_count == 2
        assert [links[0][0][0], links[1][0][0]] == ["Obj-1", "Obj-2"]
        new_links = context["API"].create_work_item_links.call_args[0][0]
        assert context["API"].create_work_item_links.call_count == 1
        assert new_links == [expected_new_link]
        assert context["API"].delete_work_item_links.call_count == 1
        assert context["API"].delete_work_item_links.call_args[0][0] == [link]


class TestHelpers:
    @staticmethod
    def test_resolve_element_type():
        xtype = "LogicalComponent"

        type = helpers.resolve_element_type(xtype)

        assert type == "logicalComponent"


class TestSerializers:
    @staticmethod
    def test_diagram():
        diag = {"uuid": TEST_DIAG_UUID, "name": "test_diagram"}

        serialized_diagram = serialize.diagram(
            diag, {"DIAGRAM_CACHE": TEST_DIAGRAM_CACHE}
        )
        del serialized_diagram["description"]

        assert serialized_diagram == {
            "type": "diagram",
            "uuid_capella": TEST_DIAG_UUID,
            "title": "test_diagram",
            "description_type": "text/html",
        }

    @staticmethod
    def test__decode_diagram():
        diagram_path = TEST_DIAGRAM_CACHE / "_6Td1kOQ8Ee2tXvmHzHzXCA.svg"

        diagram = serialize._decode_diagram(diagram_path)

        assert diagram.startswith("data:image/svg+xml;base64,")

    @staticmethod
    @pytest.mark.parametrize(
        "uuid,expected",
        [
            (
                TEST_ELEMENT_UUID,
                {
                    "type": "logicalComponent",
                    "title": "Hogwarts",
                    "uuid_capella": TEST_ELEMENT_UUID,
                    "description_type": "text/html",
                    "description": markupsafe.Markup(TEST_DESCR),
                },
            ),
            (
                TEST_OCAP_UUID,
                {
                    "type": "operationalCapability",
                    "title": "Stay alive",
                    "uuid_capella": TEST_OCAP_UUID,
                    "description_type": "text/html",
                    "description": markupsafe.Markup(""),
                    "additional_attributes": {
                        "preCondition": {"type": "text/html", "value": ""},
                        "postCondition": {"type": "text/html", "value": ""},
                    },
                },
            ),
            (
                TEST_WE_UUID,
                {
                    "type": "entity",
                    "title": "Environment",
                    "uuid_capella": TEST_WE_UUID,
                    "description_type": "text/html",
                    "description": markupsafe.Markup(TEST_WE_DESCR),
                },
            ),
            (
                TEST_ACTOR_UUID,
                {
                    "type": "logicalActor",
                    "title": "Prof. A. P. W. B. Dumbledore",
                    "uuid_capella": TEST_ACTOR_UUID,
                    "description_type": "text/html",
                    "description": markupsafe.Markup(
                        "<p>Principal of Hogwarts, wearer of the elder wand "
                        "and greatest mage of all time.</p>\n"
                    ),
                },
            ),
            (
                TEST_PHYS_COMP,
                {
                    "type": "physicalComponent",
                    "title": "Physical System",
                    "uuid_capella": TEST_PHYS_COMP,
                    "description_type": "text/html",
                    "description": markupsafe.Markup(""),
                },
            ),
            (
                TEST_PHYS_NODE,
                {
                    "type": "physicalComponentNode",
                    "title": "PC 1",
                    "uuid_capella": TEST_PHYS_NODE,
                    "description_type": "text/html",
                    "description": markupsafe.Markup(""),
                },
            ),
        ],
    )
    def test_generic_attributes(
        model: capellambse.MelodyModel, uuid: str, expected: dict[str, t.Any]
    ):
        obj = model.by_uuid(uuid)

        attributes = serialize.generic_attributes(
            obj,
            {
                "POLARION_ID_MAP": TEST_POL_ID_MAP,
                "POLARION_TYPE_MAP": TEST_POL_TYPE_MAP,
            },
        )

        assert attributes == expected
