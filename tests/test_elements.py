# Copyright DB InfraGO AG and contributors
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

from capella2polarion import data_models
from capella2polarion.cli import Capella2PolarionCli
from capella2polarion.connectors import polarion_repo
from capella2polarion.connectors.polarion_worker import CapellaPolarionWorker
from capella2polarion.converters import (
    converter_config,
    data_session,
    element_converter,
    link_converter,
    model_converter,
)

# pylint: disable-next=relative-beyond-top-level, useless-suppression
from .conftest import (  # type: ignore[import]
    TEST_DIAGRAM_CACHE,
    TEST_HOST,
    TEST_MODEL_ELEMENTS_CONFIG,
)

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
    '<p><span class="polarion-rte-link" data-type="workItem" '
    'id="fake" data-item-id="TEST" data-option-id="long"/></p>\n'
)
TEST_ACTOR_UUID = "08e02248-504d-4ed8-a295-c7682a614f66"
TEST_PHYS_COMP = "b9f9a83c-fb02-44f7-9123-9d86326de5f1"
TEST_PHYS_NODE = "8a6d68c8-ac3d-4654-a07e-ada7adeed09f"
TEST_SCENARIO = "afdaa095-e2cd-4230-b5d3-6cb771a90f51"
TEST_CAP_REAL = "b80b3141-a7fc-48c7-84b2-1467dcef5fce"
TEST_CONSTRAINT = "95cbd4af-7224-43fe-98cb-f13dda540b8e"
TEST_DIAG_DESCR = '<html><p><img style="max-width: 100%" src="workitemimg:'
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
DIAGRAM_CONFIG = converter_config.CapellaTypeConfig("diagram", "diagram")


class BaseObjectContainer:
    def __init__(
        self,
        cli: Capella2PolarionCli,
        pw: CapellaPolarionWorker,
        mc: model_converter.ModelConverter,
    ) -> None:
        self.c2pcli: Capella2PolarionCli = cli
        self.pw: CapellaPolarionWorker = pw
        self.mc = mc


class TestDiagramElements:
    @staticmethod
    @pytest.fixture
    def base_object(
        diagram_cache_index: list[dict[str, t.Any]],
        model: capellambse.MelodyModel,
        monkeypatch: pytest.MonkeyPatch,
    ) -> BaseObjectContainer:
        import io

        class MyIO(io.StringIO):
            def write(self, text: str):
                pass

        uuid = diagram_cache_index[0]["uuid"]
        work_item = data_models.CapellaWorkItem(
            id="Diag-1", checksum="123", uuid_capella=uuid
        )
        c2p_cli = Capella2PolarionCli(
            debug=True,
            polarion_project_id="project_id",
            polarion_url=TEST_HOST,
            polarion_pat="PrivateAccessToken",
            polarion_delete_work_items=True,
            capella_model=model,
            synchronize_config_io=MyIO(),
        )
        c2p_cli.setup_logger()
        mock_api = mock.MagicMock(
            spec=polarion_api.OpenAPIPolarionProjectClient
        )
        monkeypatch.setattr(
            polarion_api, "OpenAPIPolarionProjectClient", mock_api
        )
        c2p_cli.config = mock.Mock(converter_config.ConverterConfig)

        mc = model_converter.ModelConverter(
            model, c2p_cli.polarion_params.project_id
        )

        mc.converter_session = {
            TEST_DIAG_UUID: data_session.ConverterData(
                "", DIAGRAM_CONFIG, model.diagrams.by_uuid(TEST_DIAG_UUID)
            )
        }

        pw = CapellaPolarionWorker(c2p_cli.polarion_params, c2p_cli.config)

        pw.polarion_data_repo = polarion_repo.PolarionDataRepository(
            [work_item]
        )
        return BaseObjectContainer(c2p_cli, pw, mc)

    @staticmethod
    def test_create_diagrams(base_object: BaseObjectContainer):
        pw = base_object.pw
        new_work_items: dict[str, data_models.CapellaWorkItem]
        new_work_items = base_object.mc.generate_work_items(
            pw.polarion_data_repo
        )
        assert len(new_work_items) == 1
        work_item = new_work_items[TEST_DIAG_UUID]
        assert isinstance(work_item, data_models.CapellaWorkItem)
        description = work_item.description
        work_item.description = None
        assert work_item == data_models.CapellaWorkItem(**TEST_SER_DIAGRAM)
        assert isinstance(description, str)
        assert description.startswith(TEST_DIAG_DESCR)

    @staticmethod
    def test_create_diagrams_filters_non_diagram_elements(
        base_object: BaseObjectContainer,
    ):
        # This test does not make any sense, but it also didn't before
        pw = base_object.pw
        base_object.mc.generate_work_items(pw.polarion_data_repo)
        assert pw.client.generate_work_items.call_count == 0

    @staticmethod
    def test_delete_diagrams(base_object: BaseObjectContainer):
        pw = base_object.pw
        base_object.mc.converter_session = {}
        base_object.mc.generate_work_items(pw.polarion_data_repo)
        pw.post_work_items(base_object.mc.converter_session)
        pw.delete_work_items(base_object.mc.converter_session)
        assert pw.client is not None
        assert pw.client.delete_work_items.call_count == 1
        assert pw.client.delete_work_items.call_args[0][0] == ["Diag-1"]
        assert pw.client.generate_work_items.call_count == 0


class FakeModelObject:
    """Mimicks a capellambse model objectyping."""

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
    @staticmethod
    @pytest.fixture
    def base_object(
        model: capellambse.MelodyModel | None, monkeypatch: pytest.MonkeyPatch
    ) -> BaseObjectContainer:
        import io

        class MyIO(io.StringIO):
            def write(self, text: str):
                pass

        work_item = data_models.CapellaWorkItem(
            id="Obj-1", uuid_capella="uuid1", status="open", checksum="123"
        )
        c2p_cli = Capella2PolarionCli(
            debug=True,
            polarion_project_id="project_id",
            polarion_url=TEST_HOST,
            polarion_pat="PrivateAccessToken",
            polarion_delete_work_items=True,
            capella_model=model,
            synchronize_config_io=MyIO(),
        )

        c2p_cli.setup_logger()
        mock_api = mock.MagicMock(
            spec=polarion_api.OpenAPIPolarionProjectClient
        )
        monkeypatch.setattr(
            polarion_api, "OpenAPIPolarionProjectClient", mock_api
        )
        c2p_cli.config = mock.Mock(converter_config.ConverterConfig)

        fake = FakeModelObject("uuid1", name="Fake 1")
        fake_model_type_config = converter_config.CapellaTypeConfig(
            "fakeModelObject", links=["attribute"]
        )

        mc = model_converter.ModelConverter(
            model, c2p_cli.polarion_params.project_id
        )

        mc.converter_session = {
            "uuid1": data_session.ConverterData(
                "oa",
                fake_model_type_config,
                fake,
                data_models.CapellaWorkItem(
                    id="Obj-1",
                    uuid_capella="uuid1",
                    status="open",
                    checksum="123",
                    type="fakeModelObject",
                ),
            ),
            "uuid2": data_session.ConverterData(
                "oa",
                fake_model_type_config,
                FakeModelObject("uuid2", name="Fake 2", attribute=fake),
            ),
        }

        pw = CapellaPolarionWorker(c2p_cli.polarion_params, c2p_cli.config)
        pw.polarion_data_repo = polarion_repo.PolarionDataRepository(
            [work_item]
        )
        return BaseObjectContainer(c2p_cli, pw, mc)

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
            "description_reference"
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
        links = link_serializer.create_links_for_work_item(
            "uuid2",
        )
        assert links == [expected]

    @staticmethod
    def test_create_links_custom_exchanges_resolver(
        base_object: BaseObjectContainer,
    ):
        function_uuid = "ceffa011-7b66-4b3c-9885-8e075e312ffa"
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
        base_object.mc.converter_session[
            function_uuid
        ] = data_session.ConverterData(
            "fa",
            converter_config.CapellaTypeConfig(
                type(funtion_obj).__name__, links=["input_exchanges"]
            ),
            funtion_obj,
            work_item_obj_1,
        )
        base_object.mc.converter_session[uuid] = data_session.ConverterData(
            "fa",
            converter_config.CapellaTypeConfig(
                "functionalExchange",
            ),
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
            "Unable to create work item link 'attribute' for [Obj-1]. "
            "There is no 'attribute' attribute on "
            "<FakeModelObject 'Fake 1' (uuid1)>"
        )
        with caplog.at_level(logging.DEBUG):
            link_serializer = link_converter.LinkSerializer(
                base_object.pw.polarion_data_repo,
                base_object.mc.converter_session,
                base_object.pw.polarion_params.project_id,
                base_object.c2pcli.capella_model,
            )
            links = link_serializer.create_links_for_work_item(
                "uuid1",
            )
        assert not links
        assert caplog.messages[0] == expected

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
            base_object.mc.converter_session[
                work_item.uuid_capella
            ] = data_session.ConverterData(
                "",
                base_object.mc.converter_session["uuid1"].type_config,
                fake_objects[work_item.uuid_capella],
                work_item,
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
        config = mock.Mock(converter_config.ConverterConfig)
        config.polarion_types = set()
        base_object.pw.config = config

        base_object.pw.load_polarion_work_item_map()

        base_object.mc.converter_session[
            "uuid1"
        ].work_item = data_models.CapellaWorkItem(
            id="Obj-1",
            uuid_capella="uuid1",
            title="Fake 1",
            type="type",
            description_type="text/html",
            description=markupsafe.Markup(""),
        )

        del base_object.mc.converter_session["uuid2"]

        get_work_item_mock = mock.MagicMock()
        get_work_item_mock.return_value = polarion_work_item_list[0]
        monkeypatch.setattr(
            base_object.pw.client,
            "get_work_item",
            get_work_item_mock,
        )

        base_object.pw.patch_work_items(base_object.mc.converter_session)
        assert base_object.pw.client is not None
        assert base_object.pw.client.get_all_work_item_links.call_count == 0
        assert base_object.pw.client.delete_work_item_links.call_count == 0
        assert base_object.pw.client.create_work_item_links.call_count == 0
        assert base_object.pw.client.update_work_item.call_count == 1
        assert base_object.pw.client.get_work_item.call_count == 1
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
        base_object.mc.converter_session[
            "uuid1"
        ].work_item = data_models.CapellaWorkItem(
            id="Obj-1",
            uuid_capella="uuid1",
            status="open",
            type="fakeModelObject",
        )

        del base_object.mc.converter_session["uuid2"]

        base_object.pw.patch_work_items(base_object.mc.converter_session)

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
        base_object.mc.converter_session[
            "uuid1"
        ].work_item = data_models.CapellaWorkItem(
            id="Obj-1",
            uuid_capella="uuid1",
            status="open",
            type="fakeModelObject",
        )

        del base_object.mc.converter_session["uuid2"]

        base_object.pw.patch_work_items(base_object.mc.converter_session)

        assert base_object.pw.client is not None
        assert base_object.pw.client.update_work_item.call_count == 1

    @staticmethod
    def test_update_links_with_no_elements(base_object: BaseObjectContainer):
        base_object.pw.polarion_data_repo = (
            polarion_repo.PolarionDataRepository()
        )
        base_object.mc.converter_session = {}
        base_object.pw.patch_work_items(base_object.mc.converter_session)

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
        base_object.mc.converter_session[
            "uuid1"
        ].work_item = data_models.CapellaWorkItem(
            id="Obj-1",
            uuid_capella="uuid1",
            status="open",
            type="fakeModelObject",
        )
        base_object.mc.converter_session[
            "uuid2"
        ].work_item = data_models.CapellaWorkItem(
            id="Obj-2",
            uuid_capella="uuid2",
            status="open",
            type="fakeModelObject",
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

        base_object.pw.patch_work_items(base_object.mc.converter_session)
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

        def mock_back_link(work_item, back_links):
            back_links[work_item.id] = [
                polarion_api.WorkItemLink(
                    "Obj-0", work_item.id, "attribute", True, "project_id"
                )
            ]

        mock_grouped_links = mock.MagicMock()
        monkeypatch.setattr(
            link_converter, "create_grouped_link_fields", mock_grouped_links
        )
        mock_grouped_links.side_effect = mock_back_link
        mock_grouped_links_reverse = mock.MagicMock()
        monkeypatch.setattr(
            link_converter,
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
        base_object.pw.patch_work_items(base_object.mc.converter_session)
        assert base_object.pw.client is not None
        update_work_item_calls = (
            base_object.pw.client.update_work_item.call_args_list
        )
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
    def test_maintain_grouped_links_attributes(
        dummy_work_items: dict[str, data_models.CapellaWorkItem]
    ):
        for work_item in dummy_work_items.values():
            link_converter.create_grouped_link_fields(work_item)
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
    def test_maintain_reverse_grouped_links_attributes(
        dummy_work_items: dict[str, data_models.CapellaWorkItem]
    ):
        reverse_polarion_id_map = {v: k for k, v in POLARION_ID_MAP.items()}
        back_links: dict[str, list[polarion_api.WorkItemLink]] = {}
        for work_item in dummy_work_items.values():
            link_converter.create_grouped_link_fields(work_item, back_links)
        for work_item_id, links in back_links.items():
            work_item = dummy_work_items[reverse_polarion_id_map[work_item_id]]
            link_converter.create_grouped_back_link_fields(work_item, links)
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
    work_item = data_models.CapellaWorkItem("id", "Dummy")
    links = [
        polarion_api.WorkItemLink("prim1", "id", "role1"),
        polarion_api.WorkItemLink("prim2", "id", "role1"),
    ]
    link_converter.create_grouped_back_link_fields(work_item, links)

    check_sum = work_item.calculate_checksum()

    links = [
        polarion_api.WorkItemLink("prim2", "id", "role1"),
        polarion_api.WorkItemLink("prim1", "id", "role1"),
    ]
    link_converter.create_grouped_back_link_fields(work_item, links)

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
        )

        serialized_diagram = serializer.serialize(TEST_DIAG_UUID)

        assert serialized_diagram == data_models.CapellaWorkItem(
            type="diagram",
            uuid_capella=TEST_DIAG_UUID,
            title="[CC] Capability",
            description_type="text/html",
            description='<html><p><img style="max-width: 100%" '
            'src="workitemimg:__C2P__diagram.svg" /></p></html>',
            status="open",
            linked_work_items=[],
        )

        attachment = serialized_diagram.attachments[0]
        attachment.content_bytes = None

        assert attachment == polarion_api.WorkItemAttachment(
            "", "", "Diagram", None, "image/svg+xml", "__C2P__diagram.svg"
        )

    @staticmethod
    @pytest.mark.parametrize(
        "layer,uuid,expected",
        [
            pytest.param(
                "la",
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
                "oa",
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
                        "preCondition": {"type": "text/html", "value": "hehe"},
                        "postCondition": {"type": "text/html", "value": ""},
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
                        "preCondition": {"type": "text/html", "value": ""},
                        "postCondition": {"type": "text/html", "value": ""},
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
        )

        work_item = serializer.serialize(uuid)
        assert work_item is not None
        status = work_item.status
        work_item.status = None

        assert work_item == data_models.CapellaWorkItem(**expected)
        assert status == "open"

    def test_add_context_diagram(self, model: capellambse.MelodyModel):
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
        )

        work_item = serializer.serialize(uuid)

        assert work_item is not None
        assert "context_diagram" in work_item.additional_attributes
        assert str(
            work_item.additional_attributes["context_diagram"]["value"]
        ).startswith(TEST_DIAG_DESCR)

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

    def test_multiple_serializers(self, model: capellambse.MelodyModel):
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
        )

        work_item = serializer.serialize(TEST_OCAP_UUID)

        assert work_item is not None
        assert "preCondition" in work_item.additional_attributes
        assert "postCondition" in work_item.additional_attributes
        assert "context_diagram" in work_item.additional_attributes
        assert str(
            work_item.additional_attributes["context_diagram"]["value"]
        ).startswith(TEST_DIAG_DESCR)
