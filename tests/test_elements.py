# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
import typing as t
from unittest import mock

import capellambse
import markupsafe
import polarion_rest_api_client as polarion_api
import pytest
from capellambse.model import common

from capella2polarion import elements
from capella2polarion.elements import element, helpers, serialize

# pylint: disable-next=relative-beyond-top-level, useless-suppression
from .conftest import TEST_DIAGRAM_CACHE, TEST_HOST  # type: ignore[import]

# pylint: disable=redefined-outer-name
TEST_DIAG_UUID = "_APMboAPhEeynfbzU12yy7w"
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
    '<p><span style="text-decoration: line-through;">Weather</span></p>\n'
)
TEST_ACTOR_UUID = "08e02248-504d-4ed8-a295-c7682a614f66"
TEST_PHYS_COMP = "b9f9a83c-fb02-44f7-9123-9d86326de5f1"
TEST_PHYS_NODE = "8a6d68c8-ac3d-4654-a07e-ada7adeed09f"
TEST_SCENARIO = "afdaa095-e2cd-4230-b5d3-6cb771a90f51"
TEST_CAP_REAL = "b80b3141-a7fc-48c7-84b2-1467dcef5fce"
TEST_CONSTRAINT = "95cbd4af-7224-43fe-98cb-f13dda540b8e"
TEST_POL_ID_MAP = {TEST_E_UUID: "TEST"}
TEST_POL_TYPE_MAP = {
    TEST_ELEMENT_UUID: "LogicalComponent",
    TEST_OCAP_UUID: "OperationalCapability",
    TEST_WE_UUID: "Entity",
}
TEST_DIAG_DESCR = (
    '<html><p><img style="max-width: 100%" src="data:image/svg+xml;base64,'
)
TEST_SER_DIAGRAM: dict[str, t.Any] = {
    "id": "Diag-1",
    "title": "[CC] Capability",
    "description_type": "text/html",
    "type": "diagram",
    "status": "open",
    "additional_attributes": {
        "uuid_capella": "_APMboAPhEeynfbzU12yy7w",
    },
}
TEST_WI_CHECKSUM = (
    "73508ec0c3048c5b33316dfa56ef5e5f4179ff69efaa209e47ab65b111415e82"
)
TEST_REQ_TEXT = (
    "<p>Test requirement 1 really l o n g text that is&nbsp;way too long to "
    "display here as that</p>\n\n<p>&lt; &gt; &quot; &#39;</p>\n\n<ul>\n\t<li>"
    "This&nbsp;is a list</li>\n\t<li>an unordered one</li>\n</ul>\n\n<ol>\n\t"
    "<li>Ordered list</li>\n\t<li>Ok</li>\n</ol>\n"
)
POLARION_ID_MAP = {f"uuid{i}": f"Obj-{i}" for i in range(3)}

HTML_LINK_0 = {
    "attribute": (
        "<ul><li>"
        '<span class="polarion-rte-link" data-type="workItem" id="fake" '
        'data-item-id="Obj-1" data-option-id="long"></span>'
        "</li>\n"
        "<li>"
        '<span class="polarion-rte-link" data-type="workItem" id="fake" '
        'data-item-id="Obj-2" data-option-id="long"></span>'
        "</li></ul>"
    ),
    "attribute_reverse": (
        "<ul><li>"
        '<span class="polarion-rte-link" data-type="workItem" id="fake" '
        'data-item-id="Obj-1" data-option-id="long"></span>'
        "</li></ul>"
    ),
}
HTML_LINK_1 = {
    "attribute": (
        "<ul><li>"
        '<span class="polarion-rte-link" data-type="workItem" id="fake" '
        'data-item-id="Obj-0" data-option-id="long"></span>'
        "</li>\n"
        "<li>"
        '<span class="polarion-rte-link" data-type="workItem" id="fake" '
        'data-item-id="Obj-2" data-option-id="long"></span>'
        "</li></ul>"
    ),
    "attribute_reverse": (
        "<ul><li>"
        '<span class="polarion-rte-link" data-type="workItem" id="fake" '
        'data-item-id="Obj-0" data-option-id="long"></span>'
        "</li></ul>"
    ),
}
HTML_LINK_2 = {
    "attribute_reverse": (
        "<ul><li>"
        '<span class="polarion-rte-link" data-type="workItem" id="fake" '
        'data-item-id="Obj-0" data-option-id="long"></span>'
        "</li>\n"
        "<li>"
        '<span class="polarion-rte-link" data-type="workItem" id="fake" '
        'data-item-id="Obj-1" data-option-id="long"></span>'
        "</li></ul>"
    )
}


class TestDiagramElements:
    @staticmethod
    @pytest.fixture
    def context(
        diagram_cache_index: list[dict[str, t.Any]],
        model: capellambse.MelodyModel,
    ) -> dict[str, t.Any]:
        api = mock.MagicMock(spec=polarion_api.OpenAPIPolarionProjectClient)
        uuid = diagram_cache_index[0]["uuid"]
        work_item = serialize.CapellaWorkItem(id="Diag-1", checksum="123")
        return {
            "API": api,
            "PROJECT_ID": "project_id",
            "CAPELLA_UUIDS": [d["uuid"] for d in diagram_cache_index],
            "MODEL": model,
            "POLARION_WI_MAP": {uuid: work_item},
            "POLARION_ID_MAP": {uuid: "Diag-1"},
            "DIAGRAM_IDX": diagram_cache_index,
            "DIAGRAM_CACHE": TEST_DIAGRAM_CACHE,
            "REST_API_URL": TEST_HOST,
        }

    @staticmethod
    def test_create_diagrams(context: dict[str, t.Any]):
        context["ELEMENTS"] = {"Diagram": context["MODEL"].diagrams}

        diagrams = element.create_work_items(context)

        assert len(diagrams) == 1
        work_item = diagrams[0]
        work_item.calculate_checksum()
        assert isinstance(work_item, serialize.CapellaWorkItem)
        assert {
            "id": work_item.id,
            "status": work_item.status,
            "description_type": work_item.description_type,
            "title": work_item.title,
            "type": work_item.type,
            "additional_attributes": work_item.additional_attributes,
        } == TEST_SER_DIAGRAM
        assert isinstance(work_item.description, str)
        assert work_item.description.startswith(TEST_DIAG_DESCR)

    @staticmethod
    def test_create_diagrams_filters_non_diagram_elements(
        monkeypatch: pytest.MonkeyPatch, context: dict[str, t.Any]
    ):
        context["ELEMENTS"] = {"Diagram": context["MODEL"].diagrams}
        attributes = mock.MagicMock()
        attributes.return_value = None
        monkeypatch.setattr(serialize, "element", attributes)

        element.create_work_items(context)

        assert context["API"].create_work_items.call_count == 0

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
        attribute: t.Any | None = None,
    ):
        self.uuid = uuid
        self.name = name
        self.attribute = attribute

    @classmethod
    def from_model(
        cls, _: capellambse.MelodyModel, element: FakeModelObject
    ) -> FakeModelObject:
        return element

    def _short_repr_(self) -> str:
        return f"<{type(self).__name__} {self.name!r} ({self.uuid})>"


class UnsupportedFakeModelObject(FakeModelObject):
    """A ``FakeModelObject`` which shouldn't be migrated."""


class TestModelElements:
    # TODO: Add tests for link creation of real model elements (special)

    @staticmethod
    @pytest.fixture
    def context(model: capellambse.MelodyModel) -> dict[str, t.Any]:
        api = mock.MagicMock(spec=polarion_api.OpenAPIPolarionProjectClient)
        fake = FakeModelObject("uuid1", name="Fake 1")
        work_item = serialize.CapellaWorkItem(
            id="Obj-1", uuid_capella="uuid1", status="open"
        )
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
            "MODEL": model,
            "POLARION_WI_MAP": {"uuid1": work_item},
            "POLARION_ID_MAP": {"uuid1": "Obj-1"},
            "POLARION_TYPE_MAP": {"uuid1": "FakeModelObject"},
            "CONFIG": {},
            "ROLES": {"FakeModelObject": ["attribute"]},
            "WORK_ITEMS": {},
        }

    @staticmethod
    def test_create_work_items(
        monkeypatch: pytest.MonkeyPatch, context: dict[str, t.Any]
    ):
        del context["ELEMENTS"]["UnsupportedFakeModelObject"]
        context["MODEL"] = model = mock.MagicMock()
        model.by_uuid.side_effect = context["ELEMENTS"]["FakeModelObject"]
        monkeypatch.setattr(
            serialize,
            "generic_work_item",
            mock_generic_work_item := mock.MagicMock(),
        )
        mock_generic_work_item.side_effect = [
            expected := serialize.CapellaWorkItem(
                uuid_capella="uuid1",
                title="Fake 1",
                type="fakeModelObject",
                description_type="text/html",
                description=markupsafe.Markup(""),
            ),
            expected1 := serialize.CapellaWorkItem(
                uuid_capella="uuid2",
                title="Fake 2",
                type="fakeModelObject",
                description_type="text/html",
                description=markupsafe.Markup(""),
            ),
        ]

        work_items = element.create_work_items(context)

        assert work_items == [expected, expected1]

    @staticmethod
    @pytest.mark.parametrize(
        "uuid,type,attrs",
        [
            pytest.param(
                "55b90f9a-c5af-47fc-9c1c-48090414d1f1",
                "OperationalInteraction",
                {"title": "Prepared food"},
                id="OperationalInteraction",
            )
        ],
    )
    def test_create_work_items_with_special_polarion_type(
        context: dict[str, t.Any],
        model: capellambse.MelodyModel,
        uuid: str,
        type: str,
        attrs: dict[str, t.Any],
    ):
        context["ELEMENTS"] = {type: [model.by_uuid(uuid)]}
        context["POLARION_TYPE_MAP"][uuid] = type
        context["MODEL"] = model

        expected = serialize.CapellaWorkItem(
            uuid_capella=uuid,
            type=type[0].lower() + type[1:],
            description_type="text/html",
            description=markupsafe.Markup(""),
            status="open",
            **attrs,
        )

        work_items = element.create_work_items(context)

        assert work_items == [expected]

    @staticmethod
    def test_create_links_custom_resolver(context: dict[str, t.Any]):
        obj = context["ELEMENTS"]["FakeModelObject"][1]
        context["POLARION_ID_MAP"]["uuid2"] = "Obj-2"
        context["WORK_ITEMS"]["uuid2"] = serialize.CapellaWorkItem(
            id="Obj-2",
            uuid_capella="uuid2",
            type="fakeModelObject",
            description_type="text/html",
            description=markupsafe.Markup(""),
            status="open",
        )
        context["ROLES"] = {"FakeModelObject": ["description_reference"]}
        context["DESCR_REFERENCES"] = {"uuid2": ["uuid1"]}
        expected = polarion_api.WorkItemLink(
            "Obj-2",
            "Obj-1",
            "description_reference",
            secondary_work_item_project="project_id",
        )

        links = element.create_links(obj, context)

        assert links == [expected]

    @staticmethod
    def test_create_links_custom_exchanges_resolver(context: dict[str, t.Any]):
        function_uuid = "ceffa011-7b66-4b3c-9885-8e075e312ffa"
        uuid = "1a414995-f4cd-488c-8152-486e459fb9de"
        obj = context["MODEL"].by_uuid(function_uuid)
        context["POLARION_ID_MAP"][function_uuid] = "Obj-1"
        context["WORK_ITEMS"][function_uuid] = serialize.CapellaWorkItem(
            id="Obj-1",
            uuid_capella=function_uuid,
            type=type(obj).__name__,
            description_type="text/html",
            description=markupsafe.Markup(""),
            status="open",
        )
        context["POLARION_ID_MAP"][uuid] = "Obj-2"
        context["WORK_ITEMS"][uuid] = serialize.CapellaWorkItem(
            id="Obj-2",
            uuid_capella=uuid,
            type="functionalExchange",
            description_type="text/html",
            description=markupsafe.Markup(""),
            status="open",
        )
        context["ROLES"] = {"SystemFunction": ["input_exchanges"]}
        expected = polarion_api.WorkItemLink(
            "Obj-1",
            "Obj-2",
            "input_exchanges",
            secondary_work_item_project="project_id",
        )

        links = element.create_links(obj, context)

        assert links == [expected]

    @staticmethod
    def test_create_links_missing_attribute(
        context: dict[str, t.Any], caplog: pytest.LogCaptureFixture
    ):
        obj = context["ELEMENTS"]["FakeModelObject"][0]
        expected = (
            "Unable to create work item link 'attribute' for [Obj-1]. "
            "There is no 'attribute' attribute on "
            "<FakeModelObject 'Fake 1' (uuid1)>"
        )
        context["WORK_ITEMS"] = {
            "uuid1": serialize.CapellaWorkItem(
                id="Obj-1",
                uuid_capella="uuid1",
                title="Fake 1",
                description_type="text/html",
                description=markupsafe.Markup(""),
                type="fakeModelObject",
            )
        }

        with caplog.at_level(logging.DEBUG):
            links = element.create_links(obj, context)

        assert not links
        assert caplog.messages[0] == expected

    @staticmethod
    def test_create_links_from_ElementList(context: dict[str, t.Any]):
        fake = FakeModelObject("uuid4", name="Fake 4")
        fake1 = FakeModelObject("uuid5", name="Fake 5")
        obj = FakeModelObject(
            "uuid6",
            name="Fake 6",
            attribute=common.ElementList(
                context["MODEL"], [fake, fake1], FakeModelObject
            ),
        )
        context["ELEMENTS"]["FakeModelObject"].append(obj)

        context["POLARION_ID_MAP"] |= {
            f"uuid{i}": f"Obj-{i}" for i in range(4, 7)
        }
        context["WORK_ITEMS"] |= {
            f"uuid{i}": serialize.CapellaWorkItem(
                id=f"Obj-{i}",
                uuid_capella=f"uuid{i}",
                type="fakeModelObject",
                description_type="text/html",
                description=markupsafe.Markup(""),
                status="open",
            )
            for i in range(4, 7)
        }
        expected_link = polarion_api.WorkItemLink(
            "Obj-6",
            "Obj-5",
            "attribute",
            secondary_work_item_project="project_id",
        )
        expected_link1 = polarion_api.WorkItemLink(
            "Obj-6",
            "Obj-4",
            "attribute",
            secondary_work_item_project="project_id",
        )

        links = element.create_links(obj, context)  # type: ignore[arg-type]

        assert expected_link in links
        assert expected_link1 in links

    @staticmethod
    def test_create_link_from_single_attribute(context: dict[str, t.Any]):
        obj = context["ELEMENTS"]["FakeModelObject"][1]
        context["POLARION_ID_MAP"]["uuid2"] = "Obj-2"
        context["WORK_ITEMS"]["uuid2"] = serialize.CapellaWorkItem(
            id="Obj-2",
            uuid_capella="uuid2",
            type="fakeModelObject",
            description_type="text/html",
            description=markupsafe.Markup(""),
            status="open",
        )
        expected = polarion_api.WorkItemLink(
            "Obj-2",
            "Obj-1",
            "attribute",
            secondary_work_item_project="project_id",
        )

        links = element.create_links(obj, context)

        assert links == [expected]

    @staticmethod
    def test_update_work_items(
        monkeypatch: pytest.MonkeyPatch, context: dict[str, t.Any]
    ):
        context["POLARION_WI_MAP"]["uuid1"] = serialize.CapellaWorkItem(
            id="Obj-1",
            type="type",
            uuid_capella="uuid1",
            status="open",
            title="Something",
            description_type="text/html",
            description=markupsafe.Markup("Test"),
            checksum="123",
        )
        mock_get_polarion_wi_map = mock.MagicMock()
        monkeypatch.setattr(
            elements, "get_polarion_wi_map", mock_get_polarion_wi_map
        )
        mock_get_polarion_wi_map.return_value = context["POLARION_WI_MAP"]
        context["WORK_ITEMS"] = {
            "uuid1": serialize.CapellaWorkItem(
                id="Obj-1",
                uuid_capella="uuid1",
                title="Fake 1",
                description_type="text/html",
                description=markupsafe.Markup(""),
                type="fakeModelObject",
            )
        }
        context["MODEL"] = mock_model = mock.MagicMock()
        mock_model.by_uuid.return_value = context["ELEMENTS"][
            "FakeModelObject"
        ][0]

        elements.patch_work_items(context)

        assert context["API"].get_all_work_item_links.call_count == 1
        assert context["API"].delete_work_item_links.call_count == 0
        assert context["API"].create_work_item_links.call_count == 0
        assert context["API"].update_work_item.call_count == 1
        work_item = context["API"].update_work_item.call_args[0][0]
        assert isinstance(work_item, serialize.CapellaWorkItem)
        assert work_item.id == "Obj-1"
        assert work_item.title == "Fake 1"
        assert work_item.description_type == "text/html"
        assert work_item.description == markupsafe.Markup("")
        assert work_item.type is None
        assert work_item.uuid_capella is None
        assert work_item.status == "open"

    @staticmethod
    def test_update_work_items_filters_work_items_with_same_checksum(
        context: dict[str, t.Any]
    ):
        context["POLARION_WI_MAP"]["uuid1"] = serialize.CapellaWorkItem(
            checksum=TEST_WI_CHECKSUM,
        )

        elements.patch_work_items(context)

        assert context["API"].update_work_item.call_count == 0

    @staticmethod
    def test_update_links_with_no_elements(context: dict[str, t.Any]):
        context["POLARION_WI_MAP"] = {}

        elements.patch_work_items(context)

        assert context["API"].get_all_work_item_links.call_count == 0

    @staticmethod
    def test_update_links(
        monkeypatch: pytest.MonkeyPatch, context: dict[str, t.Any]
    ):
        link = polarion_api.WorkItemLink(
            "Obj-1", "Obj-2", "attribute", True, "project_id"
        )
        context["POLARION_WI_MAP"]["uuid1"].linked_work_items = [link]
        context["POLARION_WI_MAP"]["uuid2"] = serialize.CapellaWorkItem(
            id="Obj-2", uuid_capella="uuid2", status="open"
        )
        context["WORK_ITEMS"] = {
            "uuid1": serialize.CapellaWorkItem(
                id="Obj-1",
                uuid_capella="uuid1",
                status="open",
                type="fakeModelObject",
            ),
            "uuid2": serialize.CapellaWorkItem(
                id="Obj-2",
                uuid_capella="uuid2",
                status="open",
                type="fakeModelObject",
            ),
        }
        mock_get_polarion_wi_map = mock.MagicMock()
        monkeypatch.setattr(
            elements, "get_polarion_wi_map", mock_get_polarion_wi_map
        )
        mock_get_polarion_wi_map.return_value = context["POLARION_WI_MAP"]
        context["API"].get_all_work_item_links.side_effect = (
            [link],
            [],
        )
        context["MODEL"] = mock_model = mock.MagicMock()
        mock_model.by_uuid.side_effect = context["ELEMENTS"]["FakeModelObject"]
        expected_new_link = polarion_api.WorkItemLink(
            "Obj-2", "Obj-1", "attribute", None, "project_id"
        )

        elements.patch_work_items(context)

        links = context["API"].get_all_work_item_links.call_args_list
        assert context["API"].get_all_work_item_links.call_count == 2
        assert [links[0][0][0], links[1][0][0]] == ["Obj-1", "Obj-2"]
        new_links = context["API"].create_work_item_links.call_args[0][0]
        assert context["API"].create_work_item_links.call_count == 1
        assert new_links == [expected_new_link]
        assert context["API"].delete_work_item_links.call_count == 1
        assert context["API"].delete_work_item_links.call_args[0][0] == [link]

    @staticmethod
    def test_patch_work_item_grouped_links(
        monkeypatch: pytest.MonkeyPatch,
        context: dict[str, t.Any],
        dummy_work_items,
    ):
        context["WORK_ITEMS"] = dummy_work_items

        context["POLARION_WI_MAP"] = {
            "uuid0": serialize.CapellaWorkItem(
                id="Obj-0", uuid_capella="uuid0", status="open"
            ),
            "uuid1": serialize.CapellaWorkItem(
                id="Obj-1", uuid_capella="uuid1", status="open"
            ),
            "uuid2": serialize.CapellaWorkItem(
                id="Obj-2", uuid_capella="uuid2", status="open"
            ),
        }
        mock_create_links = mock.MagicMock()
        monkeypatch.setattr(element, "create_links", mock_create_links)
        mock_create_links.side_effect = lambda obj, ctx: dummy_work_items[
            obj.uuid
        ].linked_work_items

        def mock_back_link(work_item, back_links):
            back_links[work_item.id] = []

        mock_grouped_links = mock.MagicMock()
        monkeypatch.setattr(
            element, "create_grouped_link_fields", mock_grouped_links
        )
        mock_grouped_links.side_effect = mock_back_link

        mock_grouped_links_reverse = mock.MagicMock()
        monkeypatch.setattr(
            element,
            "create_grouped_back_link_fields",
            mock_grouped_links_reverse,
        )

        context["MODEL"] = mock_model = mock.MagicMock()
        mock_model.by_uuid.side_effect = [
            FakeModelObject(f"uuid{i}", name=f"Fake {i}") for i in range(3)
        ]

        elements.patch_work_items(context)

        update_work_item_calls = context["API"].update_work_item.call_args_list
        assert len(update_work_item_calls) == 3

        mock_grouped_links_calls = mock_grouped_links.call_args_list

        assert len(mock_grouped_links_calls) == 3
        assert mock_grouped_links_reverse.call_count == 3

        assert mock_grouped_links_calls[0][0][0] == dummy_work_items["uuid0"]
        assert mock_grouped_links_calls[1][0][0] == dummy_work_items["uuid1"]
        assert mock_grouped_links_calls[2][0][0] == dummy_work_items["uuid2"]

        work_item_0 = update_work_item_calls[0][0][0]
        work_item_1 = update_work_item_calls[1][0][0]
        work_item_2 = update_work_item_calls[2][0][0]

        assert work_item_0.additional_attributes == {}
        assert work_item_1.additional_attributes == {}
        assert work_item_2.additional_attributes == {}

    @staticmethod
    def test_maintain_grouped_links_attributes(dummy_work_items):
        for work_item in dummy_work_items.values():
            element.create_grouped_link_fields(work_item)

        del dummy_work_items["uuid0"].additional_attributes["uuid_capella"]
        del dummy_work_items["uuid1"].additional_attributes["uuid_capella"]
        del dummy_work_items["uuid2"].additional_attributes["uuid_capella"]

        assert (
            dummy_work_items["uuid0"].additional_attributes.pop("attribute")[
                "value"
            ]
            == HTML_LINK_0["attribute"]
        )

        assert (
            dummy_work_items["uuid1"].additional_attributes.pop("attribute")[
                "value"
            ]
            == HTML_LINK_1["attribute"]
        )

        assert dummy_work_items["uuid0"].additional_attributes == {}
        assert dummy_work_items["uuid1"].additional_attributes == {}
        assert dummy_work_items["uuid2"].additional_attributes == {}

    @staticmethod
    def test_maintain_reverse_grouped_links_attributes(dummy_work_items):
        reverse_polarion_id_map = {v: k for k, v in POLARION_ID_MAP.items()}
        back_links: dict[str, list[polarion_api.WorkItemLink]] = {}

        for work_item in dummy_work_items.values():
            element.create_grouped_link_fields(work_item, back_links)

        for work_item_id, links in back_links.items():
            work_item = dummy_work_items[reverse_polarion_id_map[work_item_id]]
            element.create_grouped_back_link_fields(work_item, links)

        del dummy_work_items["uuid0"].additional_attributes["uuid_capella"]
        del dummy_work_items["uuid1"].additional_attributes["uuid_capella"]
        del dummy_work_items["uuid2"].additional_attributes["uuid_capella"]

        del dummy_work_items["uuid0"].additional_attributes["attribute"]
        del dummy_work_items["uuid1"].additional_attributes["attribute"]

        assert (
            dummy_work_items["uuid0"].additional_attributes.pop(
                "attribute_reverse"
            )["value"]
            == HTML_LINK_0["attribute_reverse"]
        )

        assert (
            dummy_work_items["uuid1"].additional_attributes.pop(
                "attribute_reverse"
            )["value"]
            == HTML_LINK_1["attribute_reverse"]
        )

        assert (
            dummy_work_items["uuid2"].additional_attributes.pop(
                "attribute_reverse"
            )["value"]
            == HTML_LINK_2["attribute_reverse"]
        )

        assert dummy_work_items["uuid0"].additional_attributes == {}
        assert dummy_work_items["uuid1"].additional_attributes == {}
        assert dummy_work_items["uuid2"].additional_attributes == {}


def test_grouped_linked_work_items_order_consistency():
    work_item = serialize.CapellaWorkItem("id", "Dummy")
    links = [
        polarion_api.WorkItemLink("prim1", "id", "role1"),
        polarion_api.WorkItemLink("prim2", "id", "role1"),
    ]
    element.create_grouped_back_link_fields(work_item, links)

    check_sum = work_item.calculate_checksum()

    links = [
        polarion_api.WorkItemLink("prim2", "id", "role1"),
        polarion_api.WorkItemLink("prim1", "id", "role1"),
    ]
    element.create_grouped_back_link_fields(work_item, links)

    assert check_sum == work_item.calculate_checksum()


class TestHelpers:
    @staticmethod
    def test_resolve_element_type():
        xtype = "LogicalComponent"

        type = helpers.resolve_element_type(xtype)

        assert type == "logicalComponent"


class TestSerializers:
    @staticmethod
    def test_diagram(model: capellambse.MelodyModel):
        diag = model.diagrams.by_uuid(TEST_DIAG_UUID)

        serialized_diagram = serialize.diagram(
            diag, {"DIAGRAM_CACHE": TEST_DIAGRAM_CACHE}
        )
        serialized_diagram.description = None

        assert serialized_diagram == serialize.CapellaWorkItem(
            type="diagram",
            uuid_capella=TEST_DIAG_UUID,
            title="[CC] Capability",
            description_type="text/html",
            status="open",
            linked_work_items=[],
        )

    @staticmethod
    def test__decode_diagram():
        diagram_path = TEST_DIAGRAM_CACHE / "_APMboAPhEeynfbzU12yy7w.svg"

        diagram = serialize._decode_diagram(diagram_path)

        assert diagram.startswith("data:image/svg+xml;base64,")

    @staticmethod
    @pytest.mark.parametrize(
        "uuid,expected",
        [
            pytest.param(
                TEST_ELEMENT_UUID,
                {
                    "type": "logicalComponent",
                    "title": "Hogwarts",
                    "uuid_capella": TEST_ELEMENT_UUID,
                    "description_type": "text/html",
                    "description": markupsafe.Markup(TEST_DESCR),
                    "reqtype": {
                        "type": "text/html",
                        "value": markupsafe.Markup(TEST_REQ_TEXT),
                    },
                },
                id="logicalComponent",
            ),
            pytest.param(
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
                id="operationalCapability",
            ),
            pytest.param(
                TEST_WE_UUID,
                {
                    "type": "entity",
                    "title": "Environment",
                    "uuid_capella": TEST_WE_UUID,
                    "description_type": "text/html",
                    "description": markupsafe.Markup(TEST_WE_DESCR),
                },
                id="entity",
            ),
            pytest.param(
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
                id="logicalActor",
            ),
            pytest.param(
                TEST_PHYS_COMP,
                {
                    "type": "physicalComponent",
                    "title": "Physical System",
                    "uuid_capella": TEST_PHYS_COMP,
                    "description_type": "text/html",
                    "description": markupsafe.Markup(""),
                },
                id="physicalComponent",
            ),
            pytest.param(
                TEST_PHYS_NODE,
                {
                    "type": "physicalComponentNode",
                    "title": "PC 1",
                    "uuid_capella": TEST_PHYS_NODE,
                    "description_type": "text/html",
                    "description": markupsafe.Markup(""),
                },
                id="physicalComponentNode",
            ),
            pytest.param(
                TEST_SCENARIO,
                {
                    "type": "scenario",
                    "title": "Scenario",
                    "uuid_capella": TEST_SCENARIO,
                    "description_type": "text/html",
                    "description": markupsafe.Markup(""),
                    "additional_attributes": {
                        "preCondition": {"type": "text/html", "value": "hehe"},
                        "postCondition": {"type": "text/html", "value": ""},
                    },
                },
                id="scenario",
            ),
            pytest.param(
                TEST_CAP_REAL,
                {
                    "type": "capabilityRealization",
                    "title": "Capability Realization",
                    "uuid_capella": TEST_CAP_REAL,
                    "description_type": "text/html",
                    "description": markupsafe.Markup(""),
                    "additional_attributes": {
                        "preCondition": {"type": "text/html", "value": ""},
                        "postCondition": {"type": "text/html", "value": ""},
                    },
                },
                id="capabilityRealization",
            ),
            pytest.param(
                TEST_CONSTRAINT,
                {
                    "type": "constraint",
                    "title": "",
                    "uuid_capella": TEST_CONSTRAINT,
                    "description_type": "text/html",
                    "description": markupsafe.Markup(
                        "This is a test context.Make Food"
                    ),
                },
                id="constraint",
            ),
        ],
    )
    def test_generic_work_item(
        model: capellambse.MelodyModel, uuid: str, expected: dict[str, t.Any]
    ):
        obj = model.by_uuid(uuid)

        work_item = serialize.generic_work_item(
            obj,
            {
                "POLARION_ID_MAP": TEST_POL_ID_MAP,
                "POLARION_TYPE_MAP": TEST_POL_TYPE_MAP,
            },
        )
        status = work_item.status
        work_item.status = None

        assert work_item == serialize.CapellaWorkItem(**expected)
        assert status == "open"
