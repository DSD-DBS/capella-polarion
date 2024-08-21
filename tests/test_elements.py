# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
import typing as t
from unittest import mock

import capellambse
import capellambse_context_diagrams.context
import markupsafe
import polarion_rest_api_client as polarion_api
import pytest
from capellambse.model import common

from capella2polarion import data_models
from capella2polarion.connectors import polarion_repo
from capella2polarion.converters import (
    converter_config,
    data_session,
    element_converter,
    link_converter,
    model_converter,
)

# pylint: disable-next=relative-beyond-top-level, useless-suppression
from .conftest import (  # type: ignore[import]
    TEST_MODEL_ELEMENTS_CONFIG,
    BaseObjectContainer,
    FakeModelObject,
)

TEST_DIAG_UUID = "_APOQ0QPhEeynfbzU12yy7w"
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
TEST_SCENARIO = "afdaa095-e2cd-4230-b5d3-6cb771a90f51"
TEST_CAP_REAL = "b80b3141-a7fc-48c7-84b2-1467dcef5fce"
TEST_CONSTRAINT = "95cbd4af-7224-43fe-98cb-f13dda540b8e"
TEST_SYS_FNC = "ceffa011-7b66-4b3c-9885-8e075e312ffa"
TEST_SYS_FNC_EX = "1a414995-f4cd-488c-8152-486e459fb9de"
TEST_DIAG_DESCR = (
    '<span><img title="{title}" class="{cls}" '
    'src="workitemimg:{attachment_id}" '
    'style="max-width: {width}px;"/></span>'
)
TEST_SER_DIAGRAM: dict[str, t.Any] = {
    "id": "Diag-1",
    "title": "[CC] Capability",
    "description_type": "text/html",
    "type": "diagram",
    "status": "open",
    "additional_attributes": {
        "uuid_capella": TEST_DIAG_UUID,
    },
}
TEST_WI_CHECKSUM = (
    '{"__C2P__WORK_ITEM": '
    '"be783ea9b9144856394222dde865ebc925f31e497e8aabb93aa53b97adf22035"}'
)
TEST_REQ_TEXT = (
    "<p>Test requirement 1 really l o n g text that is&nbsp;way too long to "
    "display here as that</p>\n\n<p>&lt; &gt; &quot; &#39;</p>\n\n<ul>\n\t<li>"
    "This&nbsp;is a list</li>\n\t<li>an unordered one</li>\n</ul>\n\n<ol>\n\t"
    "<li>Ordered list</li>\n\t<li>Ok</li>\n</ol>\n"
)
POLARION_ID_MAP = {f"uuid{i}": f"Obj-{i}" for i in range(3)}
TEST_LOGICAL_COMPONENT = {
    "type": "logicalComponent",
    "title": "Hogwarts",
    "description_type": "text/html",
    "description": markupsafe.Markup(TEST_DESCR),
}
TEST_CONDITION = {
    "type": "text/html",
    "value": '<div style="text-align: center;"></div>',
}
TEST_OPERATIONAL_CAPABILITY = {
    "type": "operationalCapability",
    "title": "Stay alive",
    "description_type": "text/html",
    "description": markupsafe.Markup(""),
}

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
HTML_LINK_3 = {
    "input_exchanges": (
        "<ul><li>"
        '<span class="polarion-rte-link" data-type="workItem" id="fake" '
        'data-item-id="WI-1" data-option-id="long"></span>'
        "</li>\n"
        "<ul><div>Exchange Items:</div>\n"
        '<li><span class="polarion-rte-link" data-type="workItem" id="fake" '
        'data-item-id="WI-2" data-option-id="long"></span>'
        "</li>\n"
        '<li><span class="polarion-rte-link" data-type="workItem" id="fake" '
        'data-item-id="WI-3" data-option-id="long"></span>'
        "</li></ul></ul>"
    )
}
DIAGRAM_CONFIG = converter_config.CapellaTypeConfig("diagram", "diagram")


class GroupedLinksBaseObject(t.TypedDict):
    link_serializer: link_converter.LinkSerializer
    work_items: dict[str, data_models.CapellaWorkItem]
    back_links: dict[str, list[polarion_api.WorkItemLink]]
    reverse_polarion_id_map: dict[str, str]
    config: converter_config.CapellaTypeConfig


# pylint: disable=redefined-outer-name
@pytest.fixture()
def grouped_links_base_object(
    base_object: BaseObjectContainer,
    dummy_work_items: dict[str, data_models.CapellaWorkItem],
) -> GroupedLinksBaseObject:
    reverse_polarion_id_map = {v: k for k, v in POLARION_ID_MAP.items()}
    back_links: dict[str, list[polarion_api.WorkItemLink]] = {}
    config = converter_config.CapellaTypeConfig(
        "fakeModelObject",
        links=[
            converter_config.LinkConfig(
                capella_attr="attribute", polarion_role="attribute"
            )
        ],
    )
    mock_model = mock.MagicMock()
    fake_2 = FakeModelObject("uuid2", "Fake 2")
    fake_1 = FakeModelObject("uuid1", "Fake 1")
    fake_0 = FakeModelObject("uuid0", "Fake 0", attribute=[fake_1, fake_2])
    fake_1.attribute = [fake_0, fake_2]
    mock_model.by_uuid.side_effect = lambda uuid: {
        "uuid0": fake_0,
        "uuid1": fake_1,
        "uuid2": fake_2,
    }[uuid]
    link_serializer = link_converter.LinkSerializer(
        base_object.pw.polarion_data_repo,
        base_object.mc.converter_session,
        base_object.pw.polarion_params.project_id,
        mock_model,
    )
    return {
        "link_serializer": link_serializer,
        "work_items": dummy_work_items,
        "back_links": back_links,
        "reverse_polarion_id_map": reverse_polarion_id_map,
        "config": config,
    }


class TestDiagramElements:
    @staticmethod
    @pytest.fixture
    def diagr_base_object(
        diagram_cache_index: list[dict[str, t.Any]],
        model: capellambse.MelodyModel,
        base_object: BaseObjectContainer,
    ) -> BaseObjectContainer:
        uuid = diagram_cache_index[0]["uuid"]
        work_item = data_models.CapellaWorkItem(
            id="Diag-1", checksum="123", uuid_capella=uuid
        )

        base_object.mc.converter_session = {
            TEST_DIAG_UUID: data_session.ConverterData(
                "", DIAGRAM_CONFIG, model.diagrams.by_uuid(TEST_DIAG_UUID)
            )
        }

        base_object.pw.polarion_data_repo = (
            polarion_repo.PolarionDataRepository([work_item])
        )
        return base_object

    @staticmethod
    def test_create_diagrams(diagr_base_object: BaseObjectContainer):
        pw = diagr_base_object.pw
        new_work_items: dict[str, data_models.CapellaWorkItem]
        new_work_items = diagr_base_object.mc.generate_work_items(
            pw.polarion_data_repo, generate_attachments=True
        )
        assert len(new_work_items) == 1
        work_item = new_work_items[TEST_DIAG_UUID]
        assert isinstance(work_item, data_models.CapellaWorkItem)
        description = work_item.description
        work_item.description = None
        work_item.attachments = []
        assert work_item == data_models.CapellaWorkItem(**TEST_SER_DIAGRAM)
        assert isinstance(description, str)
        assert description == TEST_DIAG_DESCR.format(
            title="Diagram",
            attachment_id="__C2P__diagram.svg",
            width=750,
            cls="diagram",
        )

    @staticmethod
    def test_create_diagrams_filters_non_diagram_elements(
        diagr_base_object: BaseObjectContainer,
    ):
        # This test does not make any sense, but it also didn't before
        pw = diagr_base_object.pw
        diagr_base_object.mc.generate_work_items(pw.polarion_data_repo)
        assert pw.client.generate_work_items.call_count == 0

    @staticmethod
    def test_delete_diagrams(diagr_base_object: BaseObjectContainer):
        pw = diagr_base_object.pw
        diagr_base_object.mc.converter_session = {}
        diagr_base_object.mc.generate_work_items(pw.polarion_data_repo)
        pw.create_missing_work_items(diagr_base_object.mc.converter_session)
        pw.delete_orphaned_work_items(diagr_base_object.mc.converter_session)
        assert pw.client is not None
        assert pw.client.delete_work_items.call_count == 1
        assert pw.client.delete_work_items.call_args[0][0] == ["Diag-1"]
        assert pw.client.generate_work_items.call_count == 0


class TestModelElements:
    @staticmethod
    def test_create_work_items(
        monkeypatch: pytest.MonkeyPatch, base_object: BaseObjectContainer
    ):
        base_object.c2pcli.capella_model = mock.MagicMock()
        monkeypatch.setattr(
            element_converter.CapellaWorkItemSerializer,
            "serialize",
            mock_generic_work_item := mock.MagicMock(),
        )
        mock_generic_work_item.side_effect = [
            expected := data_models.CapellaWorkItem(
                uuid_capella="uuid1",
                title="Fake 1",
                type="fakeModelObject",
                description_type="text/html",
                description=markupsafe.Markup(""),
            ),
            expected1 := data_models.CapellaWorkItem(
                uuid_capella="uuid2",
                title="Fake 2",
                type="fakeModelObject",
                description_type="text/html",
                description=markupsafe.Markup(""),
            ),
        ]
        work_items = base_object.mc.generate_work_items(
            base_object.pw.polarion_data_repo
        )
        assert list(work_items.values()) == [expected, expected1]

    @staticmethod
    @pytest.mark.parametrize(
        "uuid,_type,attrs",
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
        base_object: BaseObjectContainer,
        model: capellambse.MelodyModel,
        uuid: str,
        _type: str,
        attrs: dict[str, t.Any],
    ):
        base_object.mc.converter_session = {
            uuid: data_session.ConverterData(
                "oa",
                converter_config.CapellaTypeConfig(
                    _type[0].lower() + _type[1:]
                ),
                model.by_uuid(uuid),
            )
        }
        base_object.c2pcli.capella_model = model

        expected = data_models.CapellaWorkItem(
            uuid_capella=uuid,
            type=_type[0].lower() + _type[1:],
            description_type="text/html",
            description=markupsafe.Markup(""),
            status="open",
            **attrs,
        )

        work_items = base_object.mc.generate_work_items(
            base_object.pw.polarion_data_repo
        )

        assert len(work_items) == 1
        assert work_items[uuid] == expected

    @staticmethod
    def test_create_links_custom_resolver(base_object: BaseObjectContainer):
        work_item_obj_2 = data_models.CapellaWorkItem(
            id="Obj-2",
            uuid_capella="uuid2",
            type="fakeModelObject",
            description_type="text/html",
            description=markupsafe.Markup(""),
            status="open",
        )
        base_object.pw.polarion_data_repo.update_work_items([work_item_obj_2])
        base_object.mc.converter_session["uuid2"].work_item = work_item_obj_2
        base_object.mc.converter_session["uuid2"].type_config.links = [
            converter_config.LinkConfig(
                capella_attr="description_reference",
                polarion_role="description_reference",
            )
        ]
        base_object.mc.converter_session["uuid2"].description_references = [
            "uuid1"
        ]
        expected = polarion_api.WorkItemLink(
            "Obj-2",
            "Obj-1",
            "description_reference",
            secondary_work_item_project="project_id",
        )
        link_serializer = link_converter.LinkSerializer(
            base_object.pw.polarion_data_repo,
            base_object.mc.converter_session,
            base_object.pw.polarion_params.project_id,
            base_object.c2pcli.capella_model,
        )

        links = link_serializer.create_links_for_work_item("uuid2")

        assert links == [expected]

    @staticmethod
    def test_create_links_custom_exchanges_resolver(
        base_object: BaseObjectContainer,
    ):
        function_uuid = TEST_SYS_FNC
        uuid = "1a414995-f4cd-488c-8152-486e459fb9de"

        funtion_obj = base_object.c2pcli.capella_model.by_uuid(function_uuid)
        obj = base_object.c2pcli.capella_model.by_uuid(uuid)

        work_item_obj_1 = data_models.CapellaWorkItem(
            id="Obj-1",
            uuid_capella=function_uuid,
            type=type(funtion_obj).__name__,
            description_type="text/html",
            description=markupsafe.Markup(""),
            status="open",
        )
        work_item_obj_2 = data_models.CapellaWorkItem(
            id="Obj-2",
            uuid_capella=uuid,
            type="functionalExchange",
            description_type="text/html",
            description=markupsafe.Markup(""),
            status="open",
        )

        base_object.pw.polarion_data_repo.update_work_items(
            [work_item_obj_1, work_item_obj_2]
        )
        link_config = converter_config.LinkConfig(
            capella_attr="inputs.exchanges", polarion_role="input_exchanges"
        )
        base_object.mc.converter_session[function_uuid] = (
            data_session.ConverterData(
                "fa",
                converter_config.CapellaTypeConfig(
                    type(funtion_obj).__name__, links=[link_config]
                ),
                funtion_obj,
                work_item_obj_1,
            )
        )
        base_object.mc.converter_session[uuid] = data_session.ConverterData(
            "fa",
            converter_config.CapellaTypeConfig("functionalExchange"),
            obj,
            work_item_obj_2,
        )
        expected = polarion_api.WorkItemLink(
            "Obj-1",
            "Obj-2",
            "input_exchanges",
            secondary_work_item_project="project_id",
        )
        link_serializer = link_converter.LinkSerializer(
            base_object.pw.polarion_data_repo,
            base_object.mc.converter_session,
            base_object.pw.polarion_params.project_id,
            base_object.c2pcli.capella_model,
        )

        links = link_serializer.create_links_for_work_item(function_uuid)

        assert links == [expected]

    @staticmethod
    def test_create_links_missing_attribute(
        base_object: BaseObjectContainer, caplog: pytest.LogCaptureFixture
    ):
        expected = (
            "Link creation for \"<FakeModelObject 'Fake 1' (uuid1)>\" failed:"
            "\n\tRequested attribute: attribute"
            "\n\tAssertionError No 'uuid' on value"
            "\n\t--------"
        )

        with caplog.at_level(logging.DEBUG):
            link_serializer = link_converter.LinkSerializer(
                base_object.pw.polarion_data_repo,
                base_object.mc.converter_session,
                base_object.pw.polarion_params.project_id,
                base_object.c2pcli.capella_model,
            )
            links = link_serializer.create_links_for_work_item("uuid1")

        assert not links
        assert caplog.messages[0] == expected

    @staticmethod
    def test_create_links_no_new_links_with_errors(
        base_object: BaseObjectContainer, caplog: pytest.LogCaptureFixture
    ):
        expected = (
            "Link creation for \"<FakeModelObject 'Fake 2' (uuid2)>\" failed:"
            "\n\tRequested attribute: non_existent_attr"
            "\n\t"
        )

        work_item_obj_2 = data_models.CapellaWorkItem(
            id="Obj-2",
            uuid_capella="uuid2",
            type="fakeModelObject",
            description_type="text/html",
            description=markupsafe.Markup(""),
            status="open",
        )
        base_object.pw.polarion_data_repo.update_work_items([work_item_obj_2])
        base_object.mc.converter_session["uuid2"].work_item = work_item_obj_2
        base_object.mc.converter_session["uuid2"].type_config.links = [
            converter_config.LinkConfig(
                capella_attr="non_existent_attr",
                polarion_role="invalid_role",
            )
        ]
        base_object.mc.converter_session["uuid2"].errors = set()

        link_serializer = link_converter.LinkSerializer(
            base_object.pw.polarion_data_repo,
            base_object.mc.converter_session,
            base_object.pw.polarion_params.project_id,
            base_object.c2pcli.capella_model,
        )

        def error():
            assert False

        link_serializer.serializers["invalid_role"] = (
            lambda obj, work_item_id, role_id, links: error()
        )

        with caplog.at_level(logging.ERROR):
            links = link_serializer.create_links_for_work_item("uuid2")

        assert not links
        assert len(caplog.messages) == 1
        assert caplog.messages[0].startswith(expected)
        assert len(base_object.mc.converter_session["uuid2"].errors) == 3

    @staticmethod
    def test_create_links_with_new_links_and_errors(
        base_object: BaseObjectContainer, caplog: pytest.LogCaptureFixture
    ):
        expected = (
            "Link creation for \"<FakeModelObject 'Fake 2' (uuid2)>\" "
            "partially successful. Some links were not created:"
            "\n\tRequested attribute: non_existent_attr"
            "\n\t"
        )

        work_item_obj_2 = data_models.CapellaWorkItem(
            id="Obj-2",
            uuid_capella="uuid2",
            type="fakeModelObject",
            description_type="text/html",
            description=markupsafe.Markup(""),
            status="open",
        )
        work_item_obj_1 = data_models.CapellaWorkItem(
            id="Obj-1",
            uuid_capella="uuid1",
            type="fakeModelObject",
            description_type="text/html",
            description=markupsafe.Markup(""),
            status="open",
        )
        base_object.pw.polarion_data_repo.update_work_items(
            [work_item_obj_2, work_item_obj_1]
        )
        base_object.mc.converter_session["uuid2"].work_item = work_item_obj_2
        base_object.mc.converter_session["uuid1"].work_item = work_item_obj_1
        base_object.mc.converter_session["uuid2"].type_config.links = [
            converter_config.LinkConfig(
                capella_attr="description_reference",
                polarion_role="description_reference",
            ),
            converter_config.LinkConfig(
                capella_attr="non_existent_attr",
                polarion_role="invalid_role",
            ),
        ]
        base_object.mc.converter_session["uuid2"].description_references = [
            "uuid1"
        ]
        base_object.mc.converter_session["uuid2"].errors = set()

        expected_link = polarion_api.WorkItemLink(
            "Obj-2",
            "Obj-1",
            "description_reference",
            secondary_work_item_project="project_id",
        )

        link_serializer = link_converter.LinkSerializer(
            base_object.pw.polarion_data_repo,
            base_object.mc.converter_session,
            base_object.pw.polarion_params.project_id,
            base_object.c2pcli.capella_model,
        )

        def error():
            assert False

        link_serializer.serializers["invalid_role"] = (
            lambda obj, work_item_id, role_id, links: error()
        )

        with caplog.at_level(logging.WARNING):
            links = link_serializer.create_links_for_work_item("uuid2")

        assert links == [expected_link]
        assert len(caplog.messages) == 1
        assert caplog.messages[0].startswith(expected)

    @staticmethod
    def test_create_links_from_ElementList(base_object: BaseObjectContainer):
        fake = FakeModelObject("uuid4", name="Fake 4")
        fake1 = FakeModelObject("uuid5", name="Fake 5")
        obj = FakeModelObject(
            "uuid6",
            name="Fake 6",
            attribute=common.ElementList(
                base_object.c2pcli.capella_model,
                [fake, fake1],
                FakeModelObject,
            ),
        )
        fake_objects = {"uuid4": fake, "uuid5": fake1, "uuid6": obj}

        work_items = [
            data_models.CapellaWorkItem(
                id=f"Obj-{i}",
                uuid_capella=f"uuid{i}",
                type="fakeModelObject",
                description_type="text/html",
                description=markupsafe.Markup(""),
                status="open",
            )
            for i in range(4, 7)
        ]
        base_object.pw.polarion_data_repo.update_work_items(work_items)
        for work_item in work_items:
            base_object.mc.converter_session[work_item.uuid_capella] = (
                data_session.ConverterData(
                    "",
                    base_object.mc.converter_session["uuid1"].type_config,
                    fake_objects[work_item.uuid_capella],
                    work_item,
                )
            )

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
        link_serializer = link_converter.LinkSerializer(
            base_object.pw.polarion_data_repo,
            base_object.mc.converter_session,
            base_object.pw.polarion_params.project_id,
            base_object.c2pcli.capella_model,
        )
        links = link_serializer.create_links_for_work_item(
            "uuid6",
        )
        # type: ignore[arg-type]
        assert expected_link in links
        assert expected_link1 in links

    @staticmethod
    def test_create_link_from_single_attribute(
        base_object: BaseObjectContainer,
    ):
        work_item_2 = data_models.CapellaWorkItem(
            id="Obj-2",
            uuid_capella="uuid2",
            type="fakeModelObject",
            description_type="text/html",
            description=markupsafe.Markup(""),
            status="open",
        )

        base_object.pw.polarion_data_repo.update_work_items([work_item_2])
        base_object.mc.converter_session["uuid2"].work_item = work_item_2

        expected = polarion_api.WorkItemLink(
            "Obj-2",
            "Obj-1",
            "attribute",
            secondary_work_item_project="project_id",
        )
        link_serializer = link_converter.LinkSerializer(
            base_object.pw.polarion_data_repo,
            base_object.mc.converter_session,
            base_object.pw.polarion_params.project_id,
            base_object.c2pcli.capella_model,
        )
        links = link_serializer.create_links_for_work_item(
            "uuid2",
        )
        assert links == [expected]

    @staticmethod
    def test_create_link_from_single_attribute_with_role_prefix(
        base_object: BaseObjectContainer,
    ):
        work_item_2 = data_models.CapellaWorkItem(
            id="Obj-2",
            type="_C2P_fakeModelObject",
            description_type="text/html",
            description=markupsafe.Markup(""),
            status="open",
            uuid_capella="uuid2",
        )

        base_object.pw.polarion_data_repo.update_work_items([work_item_2])
        base_object.mc.converter_session["uuid2"].work_item = work_item_2

        expected = polarion_api.WorkItemLink(
            "Obj-2",
            "Obj-1",
            "_C2P_attribute",
            secondary_work_item_project="project_id",
        )
        link_serializer = link_converter.LinkSerializer(
            base_object.pw.polarion_data_repo,
            base_object.mc.converter_session,
            base_object.pw.polarion_params.project_id,
            base_object.c2pcli.capella_model,
            role_prefix="_C2P",
        )
        links = link_serializer.create_links_for_work_item("uuid2")

        assert links == [expected]

    @staticmethod
    def test_update_work_items(
        monkeypatch: pytest.MonkeyPatch, base_object: BaseObjectContainer
    ):
        polarion_work_item_list: list[data_models.CapellaWorkItem] = [
            data_models.CapellaWorkItem(
                id="Obj-1",
                type="type",
                uuid_capella="uuid1",
                status="open",
                title="Something",
                description_type="text/html",
                description=markupsafe.Markup("Test"),
                checksum="123",
            )
        ]
        polarion_api_get_all_work_items = mock.MagicMock()
        polarion_api_get_all_work_items.return_value = polarion_work_item_list
        monkeypatch.setattr(
            base_object.pw.client,
            "get_all_work_items",
            polarion_api_get_all_work_items,
        )

        base_object.pw.load_polarion_work_item_map()

        base_object.mc.converter_session["uuid1"].work_item = (
            data_models.CapellaWorkItem(
                id="Obj-1",
                uuid_capella="uuid1",
                title="Fake 1",
                type="type",
                description_type="text/html",
                description=markupsafe.Markup(""),
            )
        )

        del base_object.mc.converter_session["uuid2"]

        get_work_item_mock = mock.MagicMock()
        get_work_item_mock.return_value = polarion_work_item_list[0]
        monkeypatch.setattr(
            base_object.pw.client,
            "get_work_item",
            get_work_item_mock,
        )

        base_object.pw.compare_and_update_work_items(
            base_object.mc.converter_session
        )
        assert base_object.pw.client is not None
        assert base_object.pw.client.get_all_work_item_links.call_count == 0
        assert base_object.pw.client.delete_work_item_links.call_count == 0
        assert base_object.pw.client.create_work_item_links.call_count == 0
        assert base_object.pw.client.update_work_item.call_count == 1
        assert base_object.pw.client.get_work_item.call_count == 1
        assert (
            base_object.pw.client.get_all_work_item_attachments.call_count == 0
        )
        work_item = base_object.pw.client.update_work_item.call_args[0][0]
        assert isinstance(work_item, data_models.CapellaWorkItem)
        assert work_item.id == "Obj-1"
        assert work_item.title == "Fake 1"
        assert work_item.description_type == "text/html"
        assert work_item.description == markupsafe.Markup("")
        assert work_item.type is None
        assert work_item.status == "open"
        assert work_item.uuid_capella is None

    @staticmethod
    def test_update_deleted_work_item(
        monkeypatch: pytest.MonkeyPatch, base_object: BaseObjectContainer
    ):
        polarion_work_item_list: list[data_models.CapellaWorkItem] = [
            data_models.CapellaWorkItem(
                id="Obj-1",
                type="type",
                uuid_capella="uuid1",
                status="deleted",
                checksum="123",
            )
        ]
        polarion_api_get_all_work_items = mock.MagicMock()
        polarion_api_get_all_work_items.return_value = polarion_work_item_list
        monkeypatch.setattr(
            base_object.pw.client,
            "get_all_work_items",
            polarion_api_get_all_work_items,
        )

        base_object.pw.load_polarion_work_item_map()

        base_object.mc.converter_session["uuid1"].work_item = (
            data_models.CapellaWorkItem(
                id="Obj-1",
                type="type",
                uuid_capella="uuid1",
                status="open",
                title="Something",
                description_type="text/html",
                description=markupsafe.Markup("Test"),
                checksum="123",
            )
        )

        del base_object.mc.converter_session["uuid2"]

        get_work_item_mock = mock.MagicMock()
        get_work_item_mock.return_value = polarion_work_item_list[0]
        monkeypatch.setattr(
            base_object.pw.client,
            "get_work_item",
            get_work_item_mock,
        )
        base_object.pw.delete_orphaned_work_items(
            base_object.mc.converter_session
        )
        assert base_object.pw.client.update_work_item.called is False

        base_object.pw.create_missing_work_items(
            base_object.mc.converter_session
        )
        assert base_object.pw.client.create_work_items.called is False

        base_object.pw.compare_and_update_work_items(
            base_object.mc.converter_session
        )
        work_item = base_object.pw.client.update_work_item.call_args[0][0]
        assert isinstance(work_item, data_models.CapellaWorkItem)
        assert work_item.status == "open"

    @staticmethod
    def test_update_work_items_filters_work_items_with_same_checksum(
        base_object: BaseObjectContainer,
    ):
        base_object.pw.polarion_data_repo.update_work_items(
            [
                data_models.CapellaWorkItem(
                    id="Obj-1",
                    uuid_capella="uuid1",
                    status="open",
                    checksum=TEST_WI_CHECKSUM,
                    type="fakeModelObject",
                )
            ]
        )
        base_object.mc.converter_session["uuid1"].work_item = (
            data_models.CapellaWorkItem(
                id="Obj-1",
                uuid_capella="uuid1",
                status="open",
                type="fakeModelObject",
            )
        )

        del base_object.mc.converter_session["uuid2"]

        base_object.pw.compare_and_update_work_items(
            base_object.mc.converter_session
        )

        assert base_object.pw.client is not None
        assert base_object.pw.client.update_work_item.call_count == 0

    @staticmethod
    def test_update_work_items_same_checksum_force(
        base_object: BaseObjectContainer,
    ):
        base_object.pw.force_update = True
        base_object.pw.polarion_data_repo.update_work_items(
            [
                data_models.CapellaWorkItem(
                    id="Obj-1",
                    uuid_capella="uuid1",
                    status="open",
                    checksum=TEST_WI_CHECKSUM,
                    type="fakeModelObject",
                )
            ]
        )
        base_object.mc.converter_session["uuid1"].work_item = (
            data_models.CapellaWorkItem(
                id="Obj-1",
                uuid_capella="uuid1",
                status="open",
                type="fakeModelObject",
            )
        )

        del base_object.mc.converter_session["uuid2"]

        base_object.pw.compare_and_update_work_items(
            base_object.mc.converter_session
        )

        assert base_object.pw.client is not None
        assert base_object.pw.client.update_work_item.call_count == 1

    @staticmethod
    def test_update_links_with_no_elements(base_object: BaseObjectContainer):
        base_object.pw.polarion_data_repo = (
            polarion_repo.PolarionDataRepository()
        )
        base_object.mc.converter_session = {}
        base_object.pw.compare_and_update_work_items(
            base_object.mc.converter_session
        )

        assert base_object.pw.client.get_all_work_item_links.call_count == 0

    @staticmethod
    def test_update_links(base_object: BaseObjectContainer):
        link = polarion_api.WorkItemLink(
            "Obj-1", "Obj-2", "attribute", True, "project_id"
        )
        _, work_item = base_object.pw.polarion_data_repo["uuid1"]
        work_item.linked_work_items = [link]
        base_object.pw.polarion_data_repo.update_work_items(
            [
                data_models.CapellaWorkItem(
                    id="Obj-2",
                    uuid_capella="uuid2",
                    status="open",
                    type="fakeModelObject",
                )
            ]
        )
        base_object.mc.converter_session["uuid1"].work_item = (
            data_models.CapellaWorkItem(
                id="Obj-1",
                uuid_capella="uuid1",
                status="open",
                type="fakeModelObject",
            )
        )
        base_object.mc.converter_session["uuid2"].work_item = (
            data_models.CapellaWorkItem(
                id="Obj-2",
                uuid_capella="uuid2",
                status="open",
                type="fakeModelObject",
            )
        )

        assert base_object.pw.client is not None
        base_object.pw.client.get_all_work_item_links.side_effect = (
            [link],
            [],
        )
        expected_new_link = polarion_api.WorkItemLink(
            "Obj-2", "Obj-1", "attribute", None, "project_id"
        )
        base_object.mc.generate_work_item_links(
            base_object.pw.polarion_data_repo
        )

        work_item_1 = data_models.CapellaWorkItem(
            **base_object.pw.polarion_data_repo["uuid1"][1].to_dict()
        )
        work_item_2 = data_models.CapellaWorkItem(
            **base_object.pw.polarion_data_repo["uuid2"][1].to_dict()
        )
        work_item_1.linked_work_items_truncated = True
        work_item_2.linked_work_items_truncated = True

        base_object.pw.client.get_work_item.side_effect = (
            work_item_1,
            work_item_2,
        )

        base_object.pw.compare_and_update_work_items(
            base_object.mc.converter_session
        )
        assert base_object.pw.client is not None
        links = base_object.pw.client.get_all_work_item_links.call_args_list
        assert base_object.pw.client.get_all_work_item_links.call_count == 2
        assert [links[0][0][0], links[1][0][0]] == ["Obj-1", "Obj-2"]
        new_links = base_object.pw.client.create_work_item_links.call_args[0][
            0
        ]
        assert base_object.pw.client.create_work_item_links.call_count == 1
        assert new_links == [expected_new_link]
        assert base_object.pw.client.delete_work_item_links.call_count == 1
        assert base_object.pw.client.delete_work_item_links.call_args[0][
            0
        ] == [link]

    @staticmethod
    def test_patch_work_item_grouped_links(
        monkeypatch: pytest.MonkeyPatch,
        base_object: BaseObjectContainer,
        dummy_work_items: dict[str, data_models.CapellaWorkItem],
    ):
        base_object.mc.converter_session = {
            work_item.uuid_capella: data_session.ConverterData(
                "",
                converter_config.CapellaTypeConfig("fakeModelObject"),
                FakeModelObject("uuid4", name="Fake 4"),
                work_item,
            )
            for work_item in dummy_work_items.values()
        }
        base_object.pw.polarion_data_repo = (
            polarion_repo.PolarionDataRepository(
                [
                    data_models.CapellaWorkItem(
                        id="Obj-0", uuid_capella="uuid0", status="open"
                    ),
                    data_models.CapellaWorkItem(
                        id="Obj-1", uuid_capella="uuid1", status="open"
                    ),
                    data_models.CapellaWorkItem(
                        id="Obj-2", uuid_capella="uuid2", status="open"
                    ),
                ]
            )
        )
        mock_create_links = mock.MagicMock()
        monkeypatch.setattr(
            link_converter.LinkSerializer,
            "create_links_for_work_item",
            mock_create_links,
        )
        mock_create_links.side_effect = lambda uuid, *args: dummy_work_items[
            uuid
        ].linked_work_items

        def mock_back_link(converter_data, back_links):
            work_item = converter_data.work_item
            back_links[work_item.id] = [
                polarion_api.WorkItemLink(
                    "Obj-0", work_item.id, "attribute", True, "project_id"
                )
            ]

        mock_grouped_links = mock.MagicMock()
        monkeypatch.setattr(
            link_converter.LinkSerializer,
            "create_grouped_link_fields",
            mock_grouped_links,
        )
        mock_grouped_links.side_effect = mock_back_link
        mock_grouped_links_reverse = mock.MagicMock()
        monkeypatch.setattr(
            link_converter.LinkSerializer,
            "create_grouped_back_link_fields",
            mock_grouped_links_reverse,
        )
        base_object.c2pcli.capella_model = mock_model = mock.MagicMock()
        mock_model.by_uuid.side_effect = [
            FakeModelObject(f"uuid{i}", name=f"Fake {i}") for i in range(3)
        ]
        base_object.mc.model = mock_model
        base_object.mc.generate_work_item_links(
            base_object.pw.polarion_data_repo
        )
        base_object.pw.compare_and_update_work_items(
            base_object.mc.converter_session
        )
        assert base_object.pw.client is not None
        update_work_item_calls = (
            base_object.pw.client.update_work_item.call_args_list
        )
        assert len(update_work_item_calls) == 3
        mock_grouped_links_calls = mock_grouped_links.call_args_list
        assert len(mock_grouped_links_calls) == 3
        assert mock_grouped_links_reverse.call_count == 3
        assert (
            mock_grouped_links_calls[0][0][0].work_item
            == dummy_work_items["uuid0"]
        )
        assert (
            mock_grouped_links_calls[1][0][0].work_item
            == dummy_work_items["uuid1"]
        )
        assert (
            mock_grouped_links_calls[2][0][0].work_item
            == dummy_work_items["uuid2"]
        )
        work_item_0 = update_work_item_calls[0][0][0]
        work_item_1 = update_work_item_calls[1][0][0]
        work_item_2 = update_work_item_calls[2][0][0]
        assert work_item_0.additional_attributes == {}
        assert work_item_1.additional_attributes == {}
        assert work_item_2.additional_attributes == {}

    @staticmethod
    def test_maintain_grouped_links_attributes(
        base_object: BaseObjectContainer,
        dummy_work_items: dict[str, data_models.CapellaWorkItem],
    ):
        config = converter_config.CapellaTypeConfig(
            "fakeModelObject",
            links=[
                converter_config.LinkConfig(
                    capella_attr="attribute", polarion_role="attribute"
                )
            ],
        )
        mock_model = mock.MagicMock()
        fake_2 = FakeModelObject("uuid2", "Fale 2")
        fake_1 = FakeModelObject("uuid1", "Fake 1")
        fake_0 = FakeModelObject("uuid0", "Fake 0", attribute=[fake_1, fake_2])
        fake_1.attribute = [fake_0, fake_2]
        mock_model.by_uuid.side_effect = lambda uuid: {
            "uuid0": fake_0,
            "uuid1": fake_1,
            "uuid2": fake_2,
        }[uuid]
        link_serializer = link_converter.LinkSerializer(
            base_object.pw.polarion_data_repo,
            base_object.mc.converter_session,
            base_object.pw.polarion_params.project_id,
            mock_model,
        )
        for work_item in dummy_work_items.values():
            converter_data = data_session.ConverterData(
                "test", config, [], work_item
            )
            link_serializer.create_grouped_link_fields(converter_data)
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
    def test_maintain_grouped_links_attributes_with_role_prefix(
        base_object: BaseObjectContainer,
        dummy_work_items: dict[str, data_models.CapellaWorkItem],
    ):
        config = converter_config.CapellaTypeConfig(
            "fakeModelObject",
            links=[
                converter_config.LinkConfig(
                    capella_attr="attribute", polarion_role="attribute"
                )
            ],
        )
        mock_model = mock.MagicMock()
        fake_2 = FakeModelObject("uuid2", "Fale 2")
        fake_1 = FakeModelObject("uuid1", "Fake 1")
        fake_0 = FakeModelObject("uuid0", "Fake 0", attribute=[fake_1, fake_2])
        fake_1.attribute = [fake_0, fake_2]
        mock_model.by_uuid.side_effect = lambda uuid: {
            "uuid0": fake_0,
            "uuid1": fake_1,
            "uuid2": fake_2,
        }[uuid]
        for link in dummy_work_items["uuid0"].linked_work_items:
            link.role = f"_C2P_{link.role}"
        link_serializer = link_converter.LinkSerializer(
            base_object.pw.polarion_data_repo,
            base_object.mc.converter_session,
            base_object.pw.polarion_params.project_id,
            mock_model,
            role_prefix="_C2P",
        )

        for work_item in dummy_work_items.values():
            converter_data = data_session.ConverterData(
                "test", config, [], work_item
            )
            link_serializer.create_grouped_link_fields(converter_data)

        assert "attribute" in dummy_work_items["uuid0"].additional_attributes
        assert "attribute" in dummy_work_items["uuid1"].additional_attributes

    @staticmethod
    def test_grouped_links_attributes_with_includes(
        base_object: BaseObjectContainer, model: capellambse.MelodyModel
    ):
        fnc = model.by_uuid(TEST_SYS_FNC)
        ex = model.by_uuid(TEST_SYS_FNC_EX)
        fnc_config = converter_config.CapellaTypeConfig(
            "systemFunction",
            links=[
                converter_config.LinkConfig(
                    "inputs.exchanges",
                    "input_exchanges",
                    include={"Exchange Items": "exchange_items"},
                )
            ],
        )
        ex_config = converter_config.CapellaTypeConfig(
            "systemFunctionalExchange",
            links=[
                converter_config.LinkConfig("exchange_items", "exchange_items")
            ],
        )
        ex_item_config = converter_config.CapellaTypeConfig("exchangeItem")
        base_object.mc.converter_session = {
            TEST_SYS_FNC: data_session.ConverterData(
                "sa", fnc_config, fnc, None
            ),
            TEST_SYS_FNC_EX: data_session.ConverterData(
                "sa", ex_config, ex, None
            ),
        }
        for ex_item in ex.exchange_items:
            base_object.mc.converter_session[ex_item.uuid] = (
                data_session.ConverterData("sa", ex_item_config, ex_item, None)
            )

        converter = model_converter.ModelConverter(
            base_object.c2pcli.capella_model,
            base_object.c2pcli.polarion_params.project_id,
        )
        converter.converter_session = base_object.mc.converter_session
        work_items = converter.generate_work_items(
            base_object.pw.polarion_data_repo
        )
        work_item: data_models.CapellaWorkItem | None
        for i, work_item in enumerate(work_items.values()):
            work_item.id = f"WI-{i}"

        base_object.pw.polarion_data_repo.update_work_items(
            list(work_items.values())
        )
        link_serializer = link_converter.LinkSerializer(
            base_object.pw.polarion_data_repo,
            base_object.mc.converter_session,
            base_object.pw.polarion_params.project_id,
            base_object.c2pcli.capella_model,
        )
        backlinks: dict[str, list[polarion_api.WorkItemLink]] = {}
        work_item = (
            base_object.pw.polarion_data_repo.get_work_item_by_capella_uuid(
                fnc.uuid
            )
        )

        for converter_data in base_object.mc.converter_session.values():
            links = link_serializer.create_links_for_work_item(fnc.uuid)
            assert converter_data.work_item is not None
            converter_data.work_item.linked_work_items = links

            link_serializer.create_grouped_link_fields(
                converter_data, backlinks
            )

        assert work_item is not None
        assert (
            work_item.additional_attributes["input_exchanges"]["value"]
            == HTML_LINK_3["input_exchanges"]
        )
        assert backlinks

    @staticmethod
    def test_maintain_reverse_grouped_links_attributes(
        grouped_links_base_object: GroupedLinksBaseObject,
    ):
        link_serializer = grouped_links_base_object["link_serializer"]
        dummy_work_items = grouped_links_base_object["work_items"]
        reverse_polarion_id_map = grouped_links_base_object[
            "reverse_polarion_id_map"
        ]
        back_links = grouped_links_base_object["back_links"]
        config = grouped_links_base_object["config"]

        for work_item in dummy_work_items.values():
            converter_data = data_session.ConverterData(
                "test", config, [], work_item
            )
            link_serializer.create_grouped_link_fields(
                converter_data, back_links
            )
        for work_item_id, links in back_links.items():
            work_item = dummy_work_items[reverse_polarion_id_map[work_item_id]]
            link_serializer.create_grouped_back_link_fields(work_item, links)

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

    @staticmethod
    def test_maintain_reverse_grouped_links_attributes_with_role_prefix(
        grouped_links_base_object: GroupedLinksBaseObject,
    ):
        link_serializer = grouped_links_base_object["link_serializer"]
        dummy_work_items = grouped_links_base_object["work_items"]
        reverse_polarion_id_map = grouped_links_base_object[
            "reverse_polarion_id_map"
        ]
        back_links = grouped_links_base_object["back_links"]
        config = grouped_links_base_object["config"]
        for link in dummy_work_items["uuid0"].linked_work_items:
            link.role = f"_C2P_{link.role}"
        link_serializer.role_prefix = "_C2P"

        for work_item in dummy_work_items.values():
            converter_data = data_session.ConverterData(
                "test", config, [], work_item
            )
            link_serializer.create_grouped_link_fields(
                converter_data, back_links
            )
        for work_item_id, links in back_links.items():
            work_item = dummy_work_items[reverse_polarion_id_map[work_item_id]]
            link_serializer.create_grouped_back_link_fields(work_item, links)

        assert (
            "attribute_reverse"
            in dummy_work_items["uuid0"].additional_attributes
        )
        assert (
            "attribute_reverse"
            in dummy_work_items["uuid1"].additional_attributes
        )


def test_grouped_linked_work_items_order_consistency(
    base_object: BaseObjectContainer,
):
    link_serializer = link_converter.LinkSerializer(
        base_object.pw.polarion_data_repo,
        base_object.mc.converter_session,
        base_object.pw.polarion_params.project_id,
        base_object.c2pcli.capella_model,
    )
    work_item = data_models.CapellaWorkItem("id", "Dummy")
    links = [
        polarion_api.WorkItemLink("prim1", "id", "role1"),
        polarion_api.WorkItemLink("prim2", "id", "role1"),
    ]
    link_serializer.create_grouped_back_link_fields(work_item, links)

    check_sum = work_item.calculate_checksum()

    links = [
        polarion_api.WorkItemLink("prim2", "id", "role1"),
        polarion_api.WorkItemLink("prim1", "id", "role1"),
    ]
    link_serializer.create_grouped_back_link_fields(work_item, links)

    assert check_sum == work_item.calculate_checksum()


class TestHelpers:
    @staticmethod
    def test_resolve_element_type():
        xtype = "LogicalComponent"

        type = element_converter.resolve_element_type(xtype)

        assert type == "logicalComponent"


class TestSerializers:
    @staticmethod
    def test_diagram(model: capellambse.MelodyModel):
        diag = model.diagrams.by_uuid(TEST_DIAG_UUID)

        serializer = element_converter.CapellaWorkItemSerializer(
            model,
            polarion_repo.PolarionDataRepository(),
            {
                TEST_DIAG_UUID: data_session.ConverterData(
                    "", DIAGRAM_CONFIG, diag
                )
            },
            True,
        )

        serialized_diagram = serializer.serialize(TEST_DIAG_UUID)

        assert serialized_diagram is not None

        attachment = serialized_diagram.attachments[0]
        attachment.content_bytes = None

        assert attachment == polarion_api.WorkItemAttachment(
            "", "", "Diagram", None, "image/svg+xml", "__C2P__diagram.svg"
        )

        serialized_diagram.attachments = []

        assert serialized_diagram == data_models.CapellaWorkItem(
            type="diagram",
            uuid_capella=TEST_DIAG_UUID,
            title="[CC] Capability",
            description_type="text/html",
            description=TEST_DIAG_DESCR.format(
                title="Diagram",
                attachment_id="__C2P__diagram.svg",
                width=750,
                cls="diagram",
            ),
            status="open",
            linked_work_items=[],
        )

    @staticmethod
    @pytest.mark.parametrize(
        "layer,uuid,expected",
        [
            pytest.param(
                "la",
                TEST_ELEMENT_UUID,
                {
                    **TEST_LOGICAL_COMPONENT,
                    "uuid_capella": TEST_ELEMENT_UUID,
                    "reqtype": {
                        "type": "text/html",
                        "value": markupsafe.Markup(TEST_REQ_TEXT),
                    },
                },
                id="logicalComponent",
            ),
            pytest.param(
                "oa",
                TEST_OCAP_UUID,
                {
                    **TEST_OPERATIONAL_CAPABILITY,
                    "uuid_capella": TEST_OCAP_UUID,
                    "additional_attributes": {
                        "preCondition": TEST_CONDITION,
                        "postCondition": TEST_CONDITION,
                    },
                },
                id="operationalCapability",
            ),
            pytest.param(
                "oa",
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
                "la",
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
                "pa",
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
                "pa",
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
                "oa",
                TEST_SCENARIO,
                {
                    "type": "scenario",
                    "title": "Scenario",
                    "uuid_capella": TEST_SCENARIO,
                    "description_type": "text/html",
                    "description": markupsafe.Markup(""),
                    "additional_attributes": {
                        "preCondition": {
                            "type": "text/html",
                            "value": (
                                '<div style="text-align: center;">hehe'
                                "<br/></div>"
                            ),
                        },
                        "postCondition": {
                            "type": "text/html",
                            "value": '<div style="text-align: center;"></div>',
                        },
                    },
                },
                id="scenario",
            ),
            pytest.param(
                "la",
                TEST_CAP_REAL,
                {
                    "type": "capabilityRealization",
                    "title": "Capability Realization",
                    "uuid_capella": TEST_CAP_REAL,
                    "description_type": "text/html",
                    "description": markupsafe.Markup(""),
                    "additional_attributes": {
                        "preCondition": {
                            "type": "text/html",
                            "value": '<div style="text-align: center;"></div>',
                        },
                        "postCondition": {
                            "type": "text/html",
                            "value": '<div style="text-align: center;"></div>',
                        },
                    },
                },
                id="capabilityRealization",
            ),
            pytest.param(
                "oa",
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
        model: capellambse.MelodyModel,
        layer: str,
        uuid: str,
        expected: dict[str, t.Any],
    ):
        obj = model.by_uuid(uuid)
        config = converter_config.ConverterConfig()
        with open(TEST_MODEL_ELEMENTS_CONFIG, "r", encoding="utf8") as f:
            config.read_config_file(f)

        c_type = type(obj).__name__
        attributes = {
            "is_actor": getattr(obj, "is_actor", None),
            "nature": getattr(obj, "nature", None),
        }
        type_config = config.get_type_config(layer, c_type, **attributes)
        assert type_config is not None

        serializer = element_converter.CapellaWorkItemSerializer(
            model,
            polarion_repo.PolarionDataRepository(
                [
                    data_models.CapellaWorkItem(
                        id="TEST", uuid_capella=TEST_E_UUID
                    )
                ]
            ),
            {
                uuid: data_session.ConverterData(
                    layer,
                    type_config,
                    obj,
                )
            },
            False,
        )

        work_item = serializer.serialize(uuid)
        assert work_item is not None
        status = work_item.status
        work_item.status = None

        assert work_item == data_models.CapellaWorkItem(**expected)
        assert status == "open"

    @staticmethod
    def test_add_context_diagram(model: capellambse.MelodyModel):
        uuid = "11906f7b-3ae9-4343-b998-95b170be2e2b"
        type_config = converter_config.CapellaTypeConfig(
            "test", "add_context_diagram", []
        )
        serializer = element_converter.CapellaWorkItemSerializer(
            model,
            polarion_repo.PolarionDataRepository(),
            {
                uuid: data_session.ConverterData(
                    "pa",
                    type_config,
                    model.by_uuid(uuid),
                )
            },
            True,
        )

        work_item = serializer.serialize(uuid)

        assert work_item is not None
        assert "context_diagram" in work_item.additional_attributes
        assert str(
            work_item.additional_attributes["context_diagram"]["value"]
        ) == TEST_DIAG_DESCR.format(
            title="Context Diagram",
            attachment_id="__C2P__context_diagram.svg",
            width=650,
            cls="additional-attributes-diagram",
        )

        attachment = work_item.attachments[0]
        attachment.content_bytes = None

        assert attachment == polarion_api.WorkItemAttachment(
            "",
            "",
            "Context Diagram",
            None,
            "image/svg+xml",
            "__C2P__context_diagram.svg",
        )

    def test_add_jinja_to_description(self, model: capellambse.MelodyModel):
        uuid = "c710f1c2-ede6-444e-9e2b-0ff30d7fd040"
        type_config = converter_config.CapellaTypeConfig(
            "test",
            {
                "jinja_as_description": {
                    "template_folder": "jupyter-notebooks/element_templates",
                    "template_path": "class.html.j2",
                }
            },
            [],
        )
        serializer = element_converter.CapellaWorkItemSerializer(
            model,
            polarion_repo.PolarionDataRepository(),
            {
                uuid: data_session.ConverterData(
                    "la",
                    type_config,
                    model.by_uuid(uuid),
                )
            },
            False,
        )

        work_item = serializer.serialize(uuid)

        assert work_item is not None

    @staticmethod
    @pytest.mark.parametrize("prefix", ["", "_C2P"])
    def test_multiple_serializers(model: capellambse.MelodyModel, prefix: str):
        cap = model.by_uuid(TEST_OCAP_UUID)
        type_config = converter_config.CapellaTypeConfig(
            "test",
            ["include_pre_and_post_condition", "add_context_diagram"],
            [],
        )
        serializer = element_converter.CapellaWorkItemSerializer(
            model,
            polarion_repo.PolarionDataRepository(),
            {
                TEST_OCAP_UUID: data_session.ConverterData(
                    "pa", type_config, cap
                )
            },
            True,
            prefix,
        )

        work_item = serializer.serialize(TEST_OCAP_UUID)

        assert work_item is not None
        assert work_item.type.startswith(prefix)
        assert "preCondition" in work_item.additional_attributes
        assert "postCondition" in work_item.additional_attributes
        assert "context_diagram" in work_item.additional_attributes
        assert str(
            work_item.additional_attributes["context_diagram"]["value"]
        ) == TEST_DIAG_DESCR.format(
            title="Context Diagram",
            attachment_id="__C2P__context_diagram.svg",
            width=650,
            cls="additional-attributes-diagram",
        )

    @staticmethod
    @pytest.mark.parametrize(
        "layer,uuid,expected",
        [
            pytest.param(
                "la",
                TEST_ELEMENT_UUID,
                {
                    **TEST_LOGICAL_COMPONENT,
                    "type": "_C2P_logicalComponent",
                    "uuid_capella": TEST_ELEMENT_UUID,
                    "reqtype": {
                        "type": "text/html",
                        "value": markupsafe.Markup(TEST_REQ_TEXT),
                    },
                },
                id="logicalComponent",
            ),
            pytest.param(
                "oa",
                TEST_OCAP_UUID,
                {
                    **TEST_OPERATIONAL_CAPABILITY,
                    "type": "_C2P_operationalCapability",
                    "uuid_capella": TEST_OCAP_UUID,
                    "additional_attributes": {
                        "preCondition": TEST_CONDITION,
                        "postCondition": TEST_CONDITION,
                    },
                },
                id="operationalCapability",
            ),
        ],
    )
    def test_generic_work_item_with_type_prefix(
        model: capellambse.MelodyModel,
        layer: str,
        uuid: str,
        expected: dict[str, t.Any],
    ):
        prefix = "_C2P"
        obj = model.by_uuid(uuid)
        config = converter_config.ConverterConfig()
        with open(TEST_MODEL_ELEMENTS_CONFIG, "r", encoding="utf8") as f:
            config.read_config_file(f)

        c_type = type(obj).__name__
        attributes = {
            "is_actor": getattr(obj, "is_actor", None),
            "nature": getattr(obj, "nature", None),
        }
        type_config = config.get_type_config(layer, c_type, **attributes)
        assert type_config is not None
        ework_item = data_models.CapellaWorkItem(id=f"{prefix}_TEST")
        serializer = element_converter.CapellaWorkItemSerializer(
            model,
            polarion_repo.PolarionDataRepository([ework_item]),
            {uuid: data_session.ConverterData(layer, type_config, obj)},
            False,
            prefix,
        )

        work_item = serializer.serialize(uuid)

        assert work_item is not None
        work_item.status = None
        assert work_item == data_models.CapellaWorkItem(**expected)

    @staticmethod
    def test_read_config_with_custom_params(model: capellambse.MelodyModel):
        cap = model.by_uuid("c710f1c2-ede6-444e-9e2b-0ff30d7fd040")
        config = converter_config.ConverterConfig()
        with open(TEST_MODEL_ELEMENTS_CONFIG, "r", encoding="utf8") as f:
            config.read_config_file(f)

        type_config = config.get_type_config("la", "Class")
        assert type_config is not None
        assert isinstance(type_config.converters, dict)
        assert "add_tree_diagram" in type_config.converters
        assert type_config.converters["add_tree_diagram"]["render_params"] == {
            "depth": 1
        }

        serializer = element_converter.CapellaWorkItemSerializer(
            model,
            polarion_repo.PolarionDataRepository(),
            {
                TEST_OCAP_UUID: data_session.ConverterData(
                    "pa", type_config, cap
                )
            },
            True,
        )

        with mock.patch.object(
            capellambse_context_diagrams.context.ContextDiagram, "render"
        ) as wrapped_render:
            serializer.serialize_all()
            assert wrapped_render.call_count == 1
            assert wrapped_render.call_args_list[0][1] == {"depth": 1}

    @staticmethod
    def test_read_config_links(caplog: pytest.LogCaptureFixture):
        caplog.set_level("DEBUG")
        config = converter_config.ConverterConfig()
        expected = (
            "capella2polarion.converters.converter_config",
            20,
            "Global link parent is not available on Capella type diagram",
            "capella2polarion.converters.converter_config",
            40,
            "Link exchanged_items is not available on Capella type "
            "FunctionalExchange",
        )
        with open(TEST_MODEL_ELEMENTS_CONFIG, "r", encoding="utf8") as f:
            config.read_config_file(f)

        assert config.diagram_config
        assert not any(
            link
            for link in config.diagram_config.links
            if link.capella_attr == "parent"
        )
        assert caplog.record_tuples[0] + caplog.record_tuples[1] == expected
