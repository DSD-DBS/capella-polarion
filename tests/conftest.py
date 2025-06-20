# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import copy
import importlib.metadata as imm
import json
import pathlib
import typing as t
from unittest import mock

import capellambse
import markupsafe
import polarion_rest_api_client as polarion_api
import pytest
from capellambse import model as m

from capella2polarion import cli, data_model
from capella2polarion.connectors import polarion_repo, polarion_worker
from capella2polarion.elements import (
    converter_config,
    data_session,
    model_converter,
)

TEST_DATA_ROOT = pathlib.Path(__file__).parent / "data"
TEST_DIAGRAM_CACHE = TEST_DATA_ROOT / "diagram_cache"
TEST_MODEL_ELEMENTS = TEST_DATA_ROOT / "model_elements"
TEST_MODEL_ELEMENTS_CONFIG = TEST_MODEL_ELEMENTS / "config.yaml"
TEST_DOCUMENT_ROOT = TEST_DATA_ROOT / "documents"
TEST_COMBINED_DOCUMENT_CONFIG = TEST_DOCUMENT_ROOT / "combined_config.yaml"
TEST_PLUGIN_CONFIG = TEST_DATA_ROOT / "plugins.yaml"
TEST_MODEL = {
    "path": str(TEST_DATA_ROOT / "model" / "Melody Model Test.aird"),
    "diagram_cache": str(TEST_DIAGRAM_CACHE),
}
TEST_HOST = "https://api.example.com"
TEST_PROJECT_ID = "project_id"
DOCUMENT_TEMPLATES = TEST_DOCUMENT_ROOT / "templates"
DOCUMENT_TEXT_WORK_ITEMS = "document_work_items.html.j2"
DOCUMENT_WORK_ITEMS_CROSS_PROJECT = "work_items_cross_project.html.j2"
LINK_CONFIG = converter_config.LinkConfig(
    capella_attr="attribute",
    polarion_role="attribute",
    link_field="attribute",
    reverse_field="attribute_reverse",
)
LINK_CONFIG2 = converter_config.LinkConfig(
    capella_attr="singleattr",
    polarion_role="singleattr",
    link_field="singleattr",
    reverse_field="singleattr_reverse",
)


TEST_NAMESPACE = m.Namespace(
    m.VIRTUAL_NAMESPACE_PREFIX + "capella2polarion_tests", "capella2polarion"
)


@pytest.fixture
def diagram_cache_index() -> list[dict[str, t.Any]]:
    """Return the test diagram cache index."""
    path = TEST_DIAGRAM_CACHE / "index.json"
    return json.loads(path.read_text(encoding="utf8"))


@pytest.fixture
def model() -> capellambse.MelodyModel:
    """Return the test model."""
    return capellambse.MelodyModel(**TEST_MODEL)


@pytest.fixture
def dummy_work_items() -> dict[str, data_model.CapellaWorkItem]:
    return {
        f"uuid{i}": data_model.CapellaWorkItem(
            id=f"Obj-{i}",
            uuid_capella=f"uuid{i}",
            title=f"Fake {i}",
            type="fakeModelObject",
            description=polarion_api.HtmlContent(markupsafe.Markup("")),
            linked_work_items=[
                polarion_api.WorkItemLink(
                    f"Obj-{i}", f"Obj-{j}", "attribute", True, TEST_PROJECT_ID
                )
                for j in range(3)
                if (i not in (j, 2))
            ],
            status="open",
        )
        for i in range(3)
    }


class FakeModelObject(m.ModelElement, ns=TEST_NAMESPACE):
    name = m.StringPOD("name")
    attribute = m.Association["FakeModelObject"](
        (TEST_NAMESPACE, "FakeModelObject"), "attribute"
    )
    singleattr = m.Single["FakeModelObject"](
        m.Association((TEST_NAMESPACE, "FakeModelObject"), "singleattr")
    )


class UnsupportedFakeModelObject(FakeModelObject, ns=TEST_NAMESPACE):
    """A ``FakeModelObject`` which shouldn't be migrated."""


@pytest.fixture(autouse=True)
def inject_test_classes(monkeypatch):
    class FakeEntryPoint:
        name: t.Final = "capella2polarion"
        group: t.Final = "capellambse.namespaces"
        value: t.Final = "conftest"

        def load(self) -> m.Namespace:
            return TEST_NAMESPACE

    def fake_entry_points(**kw):
        result = real_entry_points(**kw)
        if kw.get("group") == FakeEntryPoint.group:
            return (*result, FakeEntryPoint())
        return result

    real_entry_points = imm.entry_points
    monkeypatch.setattr(imm, "entry_points", fake_entry_points)
    capellambse.model.reset_entrypoint_caches()


class BaseObjectContainer(t.NamedTuple):
    c2pcli: cli.Capella2PolarionCli
    pw: polarion_worker.CapellaPolarionWorker
    mc: model_converter.ModelConverter


def _set_work_item_id(work_items: list[polarion_api.WorkItem]):
    for index, work_item in enumerate(work_items):
        work_item.id = f"AUTO-{index}"


def _setup_polarion_worker(
    monkeypatch: pytest.MonkeyPatch,
    params: polarion_worker.PolarionWorkerParams,
) -> polarion_worker.CapellaPolarionWorker:
    mock_api_client = mock.MagicMock(spec=polarion_api.PolarionClient)
    monkeypatch.setattr(polarion_api, "PolarionClient", mock_api_client)
    mock_project_client = mock.MagicMock(spec=polarion_api.ProjectClient)
    monkeypatch.setattr(polarion_api, "ProjectClient", mock_project_client)
    pw = polarion_worker.CapellaPolarionWorker(params)
    pw.project_client.work_items.create.side_effect = _set_work_item_id
    pw.project_client.work_items.delete_status = (
        None if params.delete_work_items else "deleted"
    )
    return pw


# pylint: disable=redefined-outer-name
@pytest.fixture
def base_object(
    model: capellambse.MelodyModel, monkeypatch: pytest.MonkeyPatch
) -> BaseObjectContainer:
    work_item = data_model.CapellaWorkItem(
        id="Obj-1", uuid_capella="uuid1", status="open"
    )
    c2p_cli = cli.Capella2PolarionCli(
        debug=True,
        polarion_project_id=TEST_PROJECT_ID,
        polarion_url=TEST_HOST,
        polarion_pat="PrivateAccessToken",
        polarion_delete_work_items=True,
        capella_model=model,
    )

    c2p_cli.setup_logger()
    c2p_cli.config = mock.Mock(converter_config.ConverterConfig)

    fake = model.la.extensions.create(
        "FakeModelObject", uuid="uuid1", name="Fake 1"
    )
    fake_model_type_config = converter_config.CapellaTypeConfig(
        "fakeModelObject",
        links=[copy.deepcopy(LINK_CONFIG), copy.deepcopy(LINK_CONFIG2)],
    )

    mc = model_converter.ModelConverter(
        model, c2p_cli.polarion_params.project_id
    )

    mc.converter_session = {
        "uuid1": data_session.ConverterData(
            "oa",
            fake_model_type_config,
            fake,
            data_model.CapellaWorkItem(
                id="Obj-1",
                uuid_capella="uuid1",
                status="open",
                type="fakeModelObject",
            ),
        ),
        "uuid2": data_session.ConverterData(
            "oa",
            fake_model_type_config,
            model.la.extensions.create(
                "FakeModelObject", uuid="uuid2", name="Fake 2", attribute=fake
            ),
        ),
    }

    pw = _setup_polarion_worker(monkeypatch, c2p_cli.polarion_params)
    pw.polarion_data_repo = polarion_repo.PolarionDataRepository([work_item])
    return BaseObjectContainer(c2p_cli, pw, mc)


@pytest.fixture
def empty_polarion_worker(monkeypatch: pytest.MonkeyPatch):
    polarion_params = polarion_worker.PolarionWorkerParams(
        project_id=TEST_PROJECT_ID,
        url=TEST_HOST,
        pat="PrivateAccessToken",
        delete_work_items=False,
    )
    return _setup_polarion_worker(monkeypatch, polarion_params)
