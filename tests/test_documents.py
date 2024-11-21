# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
import capellambse
import polarion_rest_api_client as polarion_api
import pytest
from lxml import etree, html

from capella2polarion import data_model as dm
from capella2polarion.connectors import polarion_repo, polarion_worker
from capella2polarion.converters import (
    document_config,
    document_renderer,
    text_work_item_provider,
)
from tests.conftest import (
    DOCUMENT_TEMPLATES,
    DOCUMENT_TEXT_WORK_ITEMS,
    DOCUMENT_WORK_ITEMS_CROSS_PROJECT,
    TEST_COMBINED_DOCUMENT_CONFIG,
    TEST_DOCUMENT_ROOT,
    TEST_PROJECT_ID,
)

CLASSES_TEMPLATE = "test-classes.html.j2"
JUPYTER_TEMPLATE_FOLDER = "jupyter-notebooks/document_templates"
DOCUMENT_SECTIONS = TEST_DOCUMENT_ROOT / "sections"
MIXED_CONFIG = TEST_DOCUMENT_ROOT / "mixed_config.yaml"
FULL_AUTHORITY_CONFIG = TEST_DOCUMENT_ROOT / "full_authority_config.yaml"
DOCUMENTS_CONFIG_JINJA = TEST_DOCUMENT_ROOT / "config.yaml.j2"
MIXED_AUTHORITY_DOCUMENT = TEST_DOCUMENT_ROOT / "mixed_authority_doc.html"
MIXED_AUTHORITY_DOCUMENT_WI = (
    TEST_DOCUMENT_ROOT / "mixed_authority_doc_workitem_inserted.html"
)
PROJECT_EXTERNAL_WORKITEM_SRC = (
    '<div id="polarion_wiki macro name=module-workitem;params=id=ATSY-1234'
    f'|layout=0|external=true|project={TEST_PROJECT_ID}"></div>'
)


def existing_documents() -> polarion_repo.DocumentRepository:
    return {
        (None, "_default", "id123"): (
            polarion_api.Document(
                module_folder="_default",
                module_name="id123",
                status="draft",
                home_page_content=polarion_api.TextContent(
                    type="text/html",
                    value=MIXED_AUTHORITY_DOCUMENT.read_text("utf-8"),
                ),
                rendering_layouts=[
                    polarion_api.RenderingLayout(
                        "text", "paragraph", type="text"
                    ),
                    polarion_api.RenderingLayout(
                        "Class", "paragraph", type="class"
                    ),
                ],
            ),
            [],
        ),
        (None, "_default", "id1237"): (
            polarion_api.Document(
                module_folder="_default",
                module_name="id1237",
                status="draft",
                home_page_content=polarion_api.TextContent(
                    type="text/html",
                    value=MIXED_AUTHORITY_DOCUMENT.read_text("utf-8"),
                ),
            ),
            [],
        ),
        ("TestProject", "_default", "id1239"): (
            polarion_api.Document(
                module_folder="_default",
                module_name="id1239",
                status="in_review",
                home_page_content=polarion_api.TextContent(
                    type="text/html",
                    value=MIXED_AUTHORITY_DOCUMENT.read_text("utf-8"),
                ),
            ),
            [],
        ),
        ("TestProject", "_default", "id1240"): (
            polarion_api.Document(
                module_folder="_default",
                module_name="id1240",
                status="draft",
                home_page_content=polarion_api.TextContent(
                    type="text/html",
                    value=MIXED_AUTHORITY_DOCUMENT.read_text("utf-8"),
                ),
            ),
            [],
        ),
    }


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
        empty_polarion_worker.polarion_data_repo, model, TEST_PROJECT_ID
    )

    document_data = renderer.render_document(
        JUPYTER_TEMPLATE_FOLDER,
        CLASSES_TEMPLATE,
        "_default",
        "TEST-DOC",
        cls="c710f1c2-ede6-444e-9e2b-0ff30d7fd040",
    )

    content: list[etree._Element] = html.fromstring(
        document_data.document.home_page_content.value
    )
    assert len(document_data.headings) == 0
    assert document_data.document.rendering_layouts == [
        polarion_api.RenderingLayout(
            label="Class", type="class", layouter="section"
        )
    ]
    assert len(content) == 4
    assert content[0].tag == "h1"
    assert content[0].text == "Class Document"
    assert content[2].tag == "div"
    assert content[2].get("id") == (
        "polarion_wiki macro name=module-workitem;"
        "params=id=ATSY-1234|layout=0|external=true"
    )
    assert content[3].tag == "div"
    assert content[3].get("id") == (
        "polarion_wiki macro name=module-workitem;"
        "params=id=ATSY-4321|layout=0|external=true"
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
        empty_polarion_worker.polarion_data_repo, model, TEST_PROJECT_ID
    )
    old_doc = polarion_api.Document(
        module_folder="_default",
        module_name="TEST-DOC",
        rendering_layouts=[
            polarion_api.RenderingLayout(
                label="Class",
                type="class",
                layouter="section",
                properties=[{"key": "fieldsAtStart", "value": "ID"}],
            )
        ],
        home_page_content=polarion_api.TextContent(
            type="text/html",
            value='<h2 id="polarion_wiki macro name='
            'module-workitem;params=id=ATSY-16062"/>',
        ),
    )

    document_data = renderer.render_document(
        JUPYTER_TEMPLATE_FOLDER,
        CLASSES_TEMPLATE,
        document=old_doc,
        text_work_items={},
        cls="c710f1c2-ede6-444e-9e2b-0ff30d7fd040",
    )

    content: list[etree._Element] = html.fromstring(
        document_data.document.home_page_content.value
    )
    assert len(document_data.document.rendering_layouts) == 1
    assert document_data.document.rendering_layouts[
        0
    ].properties == polarion_api.data_models.RenderingProperties(
        fields_at_start=["ID"]
    )
    assert content[0].get("id") == (
        "polarion_wiki macro name=module-workitem;params=id=ATSY-16062"
    )
    assert content[0].tag == "h1"
    assert content[1].text == "Data Classes"
    assert content[1].tag == "h2"
    assert len(document_data.headings) == 1
    assert document_data.headings[0].id == "ATSY-16062"
    assert document_data.headings[0].title == "Class Document"


def test_mixed_authority_document(
    empty_polarion_worker: polarion_worker.CapellaPolarionWorker,
    model: capellambse.MelodyModel,
):
    renderer = document_renderer.DocumentRenderer(
        empty_polarion_worker.polarion_data_repo, model, TEST_PROJECT_ID
    )
    old_doc = polarion_api.Document(
        module_folder="_default",
        module_name="TEST-DOC",
        home_page_content=polarion_api.TextContent(
            type="text/html", value=MIXED_AUTHORITY_DOCUMENT.read_text("utf-8")
        ),
    )

    document_data = renderer.update_mixed_authority_document(
        old_doc,
        DOCUMENT_SECTIONS,
        {
            "section1": "section1.html.j2",
            "section2": "section2.html.j2",
        },
        {"global_param": "Global Test"},
        {
            "section1": {"local_param": "Local Test section 1"},
            "section2": {
                "local_param": "Local Test section 2",
                "global_param": "Overwrite global param",
            },
        },
        text_work_item_provider=text_work_item_provider.TextWorkItemProvider(
            "MyField",
            "MyType",
            [
                polarion_api.WorkItem(
                    id="EXISTING", additional_attributes={"MyField": "id1"}
                )
            ],
        ),
    )

    content: list[etree._Element] = html.fromstring(
        document_data.document.home_page_content.value
    )

    assert len(document_data.text_work_item_provider.new_text_work_items) == 2
    assert (
        document_data.text_work_item_provider.new_text_work_items["id1"].id
        is None
    )
    assert (
        document_data.text_work_item_provider.new_text_work_items["id2"].id
        is None
    )
    assert len(content) == 17
    assert [c.tag for c in content[:3]] == ["h1", "p", "p"]
    assert (c4 := content[4]).tag == "h3" and c4.text == "New Heading"
    assert content[5].text == "Global Test"
    assert content[6].text == "Local Test section 1"
    assert content[9].text == "This will be kept."
    assert content[11].get("id") == (
        "polarion_wiki macro name=module-workitem;params=id=ATSY-18305"
    )
    assert content[11].tag == "h3"
    assert content[12].text == "Overwritten: Overwrite global param"
    assert content[13].text == "Local Test section 2"
    assert content[16].text == "Some postfix stuff"
    assert len(document_data.headings) == 1
    assert document_data.headings[0].id == "ATSY-18305"
    assert document_data.headings[0].title == "Keep Heading"


def test_mixed_authority_with_work_item(
    empty_polarion_worker: polarion_worker.CapellaPolarionWorker,
    model: capellambse.MelodyModel,
):
    empty_polarion_worker.polarion_data_repo.update_work_items(
        [
            dm.CapellaWorkItem(
                "ATSY-1234",
                uuid_capella="d8655737-39ab-4482-a934-ee847c7ff6bd",
                type="componentExchange",
            )
        ]
    )

    renderer = document_renderer.DocumentRenderer(
        empty_polarion_worker.polarion_data_repo, model, TEST_PROJECT_ID
    )
    old_doc = polarion_api.Document(
        module_folder="_default",
        module_name="TEST-DOC",
        home_page_content=polarion_api.TextContent(
            type="text/html",
            value=MIXED_AUTHORITY_DOCUMENT_WI.read_text("utf-8"),
        ),
    )

    def _find_links(content: list[etree._Element]) -> list[etree._Element]:
        links: list[etree._Element] = []
        for el in content:
            if el.tag != "p":
                continue

            for e in el:
                if e.tag == "span" and e.get("class") == "polarion-rte-link":
                    links.append(e)

        return links

    document_data = renderer.update_mixed_authority_document(
        old_doc,
        DOCUMENT_SECTIONS,
        {
            "section1": "section_with_work_items.html.j2",
            "section2": "section_with_work_items.html.j2",
        },
        {"element": "d8655737-39ab-4482-a934-ee847c7ff6bd"},
        {},
    )

    content: list[etree._Element] = html.fromstring(
        document_data.document.home_page_content.value
    )
    target_id = (
        "polarion_wiki macro name=module-workitem;"
        "params=id=ATSY-1234|layout=0|external=true"
    )
    wis = [
        el for el in content if el.tag == "div" and el.get("id") == target_id
    ]
    wi_links = _find_links(content)

    assert len(wis) == 1
    assert len(wi_links) == 2


def test_create_full_authority_document_text_work_items(
    empty_polarion_worker: polarion_worker.CapellaPolarionWorker,
    model: capellambse.MelodyModel,
):
    renderer = document_renderer.DocumentRenderer(
        empty_polarion_worker.polarion_data_repo, model, TEST_PROJECT_ID
    )

    document_data = renderer.render_document(
        DOCUMENT_TEMPLATES,
        DOCUMENT_TEXT_WORK_ITEMS,
        "_default",
        "TEST-DOC",
        text_work_item_provider=text_work_item_provider.TextWorkItemProvider(
            "MyField",
            "MyType",
        ),
    )

    assert len(document_data.text_work_item_provider.new_text_work_items) == 2
    assert (
        document_data.text_work_item_provider.new_text_work_items["id1"].id
        is None
    )
    assert (
        document_data.text_work_item_provider.new_text_work_items["id1"].type
        == "MyType"
    )
    assert (
        document_data.text_work_item_provider.new_text_work_items[
            "id1"
        ].additional_attributes["MyField"]
        == "id1"
    )
    assert (
        document_data.text_work_item_provider.new_text_work_items["id2"].id
        is None
    )
    assert (
        document_data.text_work_item_provider.new_text_work_items["id2"].type
        == "MyType"
    )
    assert (
        document_data.text_work_item_provider.new_text_work_items[
            "id2"
        ].additional_attributes["MyField"]
        == "id2"
    )


def test_update_full_authority_document_text_work_items(
    empty_polarion_worker: polarion_worker.CapellaPolarionWorker,
    model: capellambse.MelodyModel,
):
    renderer = document_renderer.DocumentRenderer(
        empty_polarion_worker.polarion_data_repo, model, TEST_PROJECT_ID
    )
    old_doc = polarion_api.Document(
        module_folder="_default",
        module_name="TEST-DOC",
        home_page_content=polarion_api.TextContent(
            type="text/html",
            value="",
        ),
    )

    document_data = renderer.render_document(
        DOCUMENT_TEMPLATES,
        DOCUMENT_TEXT_WORK_ITEMS,
        "_default",
        "TEST-DOC",
        document=old_doc,
        text_work_item_provider=text_work_item_provider.TextWorkItemProvider(
            "MyField",
            "MyType",
            [
                polarion_api.WorkItem(
                    id="EXISTING", additional_attributes={"MyField": "id1"}
                )
            ],
        ),
    )

    assert len(document_data.text_work_item_provider.new_text_work_items) == 2
    assert (
        document_data.text_work_item_provider.new_text_work_items["id1"].id
        == "EXISTING"
    )
    assert (
        document_data.text_work_item_provider.new_text_work_items["id1"].type
        is None
    )
    assert (
        document_data.text_work_item_provider.new_text_work_items[
            "id1"
        ].additional_attributes["MyField"]
        == "id1"
    )
    assert (
        document_data.text_work_item_provider.new_text_work_items["id2"].id
        is None
    )
    assert (
        document_data.text_work_item_provider.new_text_work_items["id2"].type
        == "MyType"
    )
    assert (
        document_data.text_work_item_provider.new_text_work_items[
            "id2"
        ].additional_attributes["MyField"]
        == "id2"
    )


def test_render_all_documents_partially_successfully(
    empty_polarion_worker: polarion_worker.CapellaPolarionWorker,
    model: capellambse.MelodyModel,
    caplog: pytest.LogCaptureFixture,
):
    empty_polarion_worker.polarion_data_repo.update_work_items(
        [
            dm.CapellaWorkItem(
                "ATSY-1234",
                uuid_capella="d8655737-39ab-4482-a934-ee847c7ff6bd",
                type="componentExchange",
            ),
        ]
    )
    with open(TEST_COMBINED_DOCUMENT_CONFIG, "r", encoding="utf-8") as f:
        conf = document_config.read_config_file(f)

    renderer = document_renderer.DocumentRenderer(
        empty_polarion_worker.polarion_data_repo, model, TEST_PROJECT_ID
    )

    projects_data = renderer.render_documents(conf, existing_documents())

    # There are 8 documents in the config, we expect 4 rendering to fail
    assert len(caplog.records) == 4
    # The first tree documents weren't rendered due to an error, the fourth
    # wasn't rendered because of status restrictions, which is a just warning
    assert [lr.levelno for lr in caplog.records] == [40, 40, 40, 30]
    # For one valid config we did not pass a document, so we expect a new one
    assert len(projects_data[None].new_docs) == 1
    # And three updated documents
    assert len(projects_data[None].updated_docs) == 2
    assert len(projects_data["TestProject"].updated_docs) == 1
    # In all existing documents we had 2 headings. In full authority mode
    # both should be updated and in mixed authority mode only one of them as
    # the other is outside the rendering area
    assert (
        sum(
            len(document_data.headings)
            for document_data in projects_data[None].updated_docs
        )
        == 3
    )
    assert (
        sum(
            len(document_data.headings)
            for document_data in projects_data["TestProject"].updated_docs
        )
        == 2
    )
    assert (
        PROJECT_EXTERNAL_WORKITEM_SRC
        in projects_data["TestProject"]
        .updated_docs[0]
        .document.home_page_content.value
    )
    assert (
        len(projects_data[None].updated_docs[0].document.rendering_layouts)
        == 0
    )
    assert (
        len(projects_data[None].updated_docs[1].document.rendering_layouts)
        == 2
    )
    assert (
        projects_data[None].updated_docs[0].document.outline_numbering is None
    )
    assert (
        projects_data[None].updated_docs[1].document.outline_numbering is None
    )


def test_insert_work_item_cross_project(
    empty_polarion_worker: polarion_worker.CapellaPolarionWorker,
    model: capellambse.MelodyModel,
):
    empty_polarion_worker.polarion_data_repo.update_work_items(
        [
            dm.CapellaWorkItem(
                "ATSY-1234",
                uuid_capella="d8655737-39ab-4482-a934-ee847c7ff6bd",
                type="componentExchange",
            )
        ]
    )
    renderer = document_renderer.DocumentRenderer(
        empty_polarion_worker.polarion_data_repo, model, TEST_PROJECT_ID
    )

    document_data_1 = renderer.render_document(
        DOCUMENT_TEMPLATES,
        DOCUMENT_WORK_ITEMS_CROSS_PROJECT,
        "test",
        "name",
        "title",
        document_project_id="DIFFERENT",
        element="d8655737-39ab-4482-a934-ee847c7ff6bd",
    )

    document_data_2 = renderer.render_document(
        DOCUMENT_TEMPLATES,
        DOCUMENT_WORK_ITEMS_CROSS_PROJECT,
        "test",
        "name",
        "title",
        element="d8655737-39ab-4482-a934-ee847c7ff6bd",
    )

    content_1: list[html.HtmlElement] = html.fragments_fromstring(
        document_data_1.document.home_page_content.value
    )
    content_2: list[html.HtmlElement] = html.fragments_fromstring(
        document_data_2.document.home_page_content.value
    )

    assert len(content_1) == 2
    assert content_1[0].attrib["id"].endswith(f"|project={TEST_PROJECT_ID}")
    assert content_1[1].attrib["data-scope"] == TEST_PROJECT_ID
    assert len(content_2) == 2
    assert content_2[0].attrib["id"].endswith("|external=true")


def test_render_all_documents_overwrite_headings_layouts(
    empty_polarion_worker: polarion_worker.CapellaPolarionWorker,
    model: capellambse.MelodyModel,
):
    with open(TEST_COMBINED_DOCUMENT_CONFIG, "r", encoding="utf-8") as f:
        conf = document_config.read_config_file(f)

    renderer = document_renderer.DocumentRenderer(
        empty_polarion_worker.polarion_data_repo,
        model,
        TEST_PROJECT_ID,
        True,
        True,
    )

    projects_data = renderer.render_documents(conf, existing_documents())
    updated_docs = projects_data[None].updated_docs

    assert len(updated_docs[0].document.rendering_layouts) == 2
    assert len(updated_docs[1].document.rendering_layouts) == 3
    assert updated_docs[1].document.rendering_layouts[0].type == "text"
    assert updated_docs[1].document.rendering_layouts[1].type == "class"
    assert (
        "tree_view_diagram"
        in updated_docs[1]
        .document.rendering_layouts[1]
        .properties.fields_at_end
    )
    assert updated_docs[0].document.outline_numbering is False
    assert updated_docs[1].document.outline_numbering is False


def test_full_authority_document_config():
    with open(FULL_AUTHORITY_CONFIG, "r", encoding="utf-8") as f:
        conf = document_config.read_config_file(f)

    assert len(conf.full_authority) == 2
    assert conf.full_authority[0].template_directory == JUPYTER_TEMPLATE_FOLDER
    assert conf.full_authority[0].template == "test-icd.html.j2"
    assert conf.full_authority[0].heading_numbering is False
    assert len(conf.full_authority[0].instances) == 2
    assert conf.full_authority[0].instances[0].polarion_space == "_default"
    assert conf.full_authority[0].instances[0].polarion_name == "id123"
    assert conf.full_authority[0].instances[0].polarion_title == "Interface23"
    assert conf.full_authority[0].instances[0].params == {
        "interface": "3d21ab4b-7bf6-428b-ba4c-a27bca4e86db"
    }
    assert conf.full_authority[0].project_id == "TestProject"
    assert conf.full_authority[0].status_allow_list == ["draft", "open"]
    assert conf.full_authority[1].project_id is None
    assert conf.full_authority[1].status_allow_list is None


def test_mixed_authority_document_config():
    with open(MIXED_CONFIG, "r", encoding="utf-8") as f:
        conf = document_config.read_config_file(f)

    assert len(conf.full_authority) == 0
    assert len(conf.mixed_authority) == 2
    assert (
        conf.mixed_authority[0].template_directory == JUPYTER_TEMPLATE_FOLDER
    )
    assert conf.mixed_authority[0].sections == {
        "section1": "test-icd.html.j2",
        "section2": "test-icd.html.j2",
    }
    assert conf.mixed_authority[0].heading_numbering is False
    assert len(conf.mixed_authority[0].instances) == 2
    assert conf.mixed_authority[0].instances[0].polarion_space == "_default"
    assert conf.mixed_authority[0].instances[0].polarion_name == "id123"
    assert conf.mixed_authority[0].project_id == "TestProject"
    assert conf.mixed_authority[0].status_allow_list == ["draft", "open"]
    assert conf.mixed_authority[0].instances[0].polarion_title == "Interface23"
    assert conf.mixed_authority[0].instances[0].params == {
        "interface": "3d21ab4b-7bf6-428b-ba4c-a27bca4e86db"
    }
    assert conf.mixed_authority[1].instances[0].section_params == {
        "section1": {"param_1": "Test"}
    }
    assert conf.mixed_authority[1].project_id is None
    assert conf.mixed_authority[1].status_allow_list is None
    assert conf.mixed_authority[0].text_work_item_type == "text"
    assert conf.mixed_authority[0].text_work_item_id_field == "__C2P__id"
    assert conf.mixed_authority[1].text_work_item_type == "myType"
    assert conf.mixed_authority[1].text_work_item_id_field == "myId"


def test_combined_config():
    with open(TEST_COMBINED_DOCUMENT_CONFIG, "r", encoding="utf-8") as f:
        conf = document_config.read_config_file(f)

    assert len(conf.full_authority) == 3
    assert len(conf.mixed_authority) == 3


def test_rendering_config():
    with open(
        FULL_AUTHORITY_CONFIG,
        "r",
        encoding="utf-8",
    ) as f:
        conf = document_config.read_config_file(f)

    no_rendering_layouts = document_config.generate_work_item_layouts(
        conf.full_authority[0].work_item_layouts
    )
    rendering_layouts = document_config.generate_work_item_layouts(
        conf.full_authority[1].work_item_layouts
    )

    assert len(no_rendering_layouts) == 0
    assert len(rendering_layouts) == 2
    assert rendering_layouts[0].label == "Component Exchange"
    assert rendering_layouts[0].type == "componentExchange"
    assert rendering_layouts[0].layouter.value == "section"
    assert rendering_layouts[0].properties.fields_at_start == ["ID"]
    assert rendering_layouts[0].properties.fields_at_end == ["context_diagram"]
    assert rendering_layouts[0].properties.sidebar_work_item_fields == [
        "ID",
        "context_diagram",
    ]
    assert rendering_layouts[0].properties.fields_at_end_as_table is True
    assert rendering_layouts[0].properties.hidden is True
    assert rendering_layouts[1].layouter.value == "paragraph"


def test_rendering_config_jinja(model: capellambse.MelodyModel):
    with open(
        DOCUMENTS_CONFIG_JINJA,
        "r",
        encoding="utf-8",
    ) as f:
        conf = document_config.read_config_file(f, model)

    assert len(conf.full_authority) == 1
    assert len(conf.full_authority[0].work_item_layouts) == 3
    assert len(conf.full_authority[0].instances) == 7
