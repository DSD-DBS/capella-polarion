# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
import capellambse
import polarion_rest_api_client as polarion_api
from lxml import etree, html

from capella2polarion import data_models as dm
from capella2polarion.connectors import polarion_worker
from capella2polarion.converters import document_renderer


def test_create_new_document(
    empty_polarion_worker: polarion_worker.CapellaPolarionWorker,
    model: capellambse.MelodyModel,
):
    empty_polarion_worker.polarion_data_repo.update_work_items(
        [
            dm.CapellaWorkItem(
                "ATSY-1234",
                uuid_capella="c710f1c2-ede6-444e-9e2b-0ff30d7fd040",
                type="class",
            ),
            dm.CapellaWorkItem(
                "ATSY-4321",
                uuid_capella="2b34c799-769c-42f2-8a1b-4533dba209a0",
                type="class",
            ),
        ]
    )
    renderer = document_renderer.DocumentRenderer(
        empty_polarion_worker.polarion_data_repo, model
    )

    new_doc, wis = renderer.render_document(
        "jupyter-notebooks/document_templates",
        "test-classes.html.j2",
        "_default",
        "TEST-DOC",
        cls="c710f1c2-ede6-444e-9e2b-0ff30d7fd040",
    )

    content = html.fromstring(new_doc.home_page_content.value)
    assert len(wis) == 0
    assert new_doc.rendering_layouts == [
        polarion_api.RenderingLayout(
            label="Class", type="class", layouter="section"
        )
    ]
    assert len(content) == 4
    assert (
        etree.tostring(content[0])
        .decode("utf-8")
        .startswith("<h1>Class Document</h1>")
    )
    assert (
        etree.tostring(content[2])
        .decode("utf-8")
        .startswith(
            '<div id="polarion_wiki macro name=module-workitem;'
            'params=id=ATSY-1234|layout=0|external=true"/>'
        )
    )
    assert (
        etree.tostring(content[3])
        .decode("utf-8")
        .startswith(
            '<div id="polarion_wiki macro name=module-workitem;'
            'params=id=ATSY-4321|layout=0|external=true"/>'
        )
    )


def test_update_document(
    empty_polarion_worker: polarion_worker.CapellaPolarionWorker,
    model: capellambse.MelodyModel,
):
    empty_polarion_worker.polarion_data_repo.update_work_items(
        [
            dm.CapellaWorkItem(
                "ATSY-1234",
                uuid_capella="c710f1c2-ede6-444e-9e2b-0ff30d7fd040",
                type="class",
            ),
            dm.CapellaWorkItem(
                "ATSY-4321",
                uuid_capella="2b34c799-769c-42f2-8a1b-4533dba209a0",
                type="class",
            ),
        ]
    )
    renderer = document_renderer.DocumentRenderer(
        empty_polarion_worker.polarion_data_repo, model
    )
    old_doc = polarion_api.Document(
        module_folder="_default",
        module_name="TEST-DOC",
        rendering_layouts=[
            polarion_api.RenderingLayout(
                label="Class",
                type="class",
                layouter="section",
                properties=[{"key": "value"}],
            )
        ],
        home_page_content=polarion_api.TextContent(
            type="text/html",
            value='<h2 id="polarion_wiki macro name='
            'module-workitem;params=id=ATSY-16062"/>',
        ),
    )

    new_doc, wis = renderer.render_document(
        "jupyter-notebooks/document_templates",
        "test-classes.html.j2",
        document=old_doc,
        cls="c710f1c2-ede6-444e-9e2b-0ff30d7fd040",
    )

    content = html.fromstring(new_doc.home_page_content.value)
    assert len(new_doc.rendering_layouts) == 1
    assert new_doc.rendering_layouts[0].properties == [{"key": "value"}]
    assert (
        etree.tostring(content[0])
        .decode("utf-8")
        .startswith(
            '<h1 id="polarion_wiki macro name='
            'module-workitem;params=id=ATSY-16062"'
        )
    )
    assert (
        etree.tostring(content[1])
        .decode("utf-8")
        .startswith("<h2>Data Classes</h2>")
    )
    assert len(wis) == 1
    assert wis[0].id == "ATSY-16062"
    assert wis[0].title == "Class Document"
