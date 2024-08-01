# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
import capellambse
import polarion_rest_api_client as polarion_api
from lxml import etree, html

from capella2polarion import data_models as dm
from capella2polarion.connectors import polarion_worker
from capella2polarion.converters import document_config, document_renderer
from tests.conftest import TEST_DATA_ROOT

DOCUMENT_ROOT = TEST_DATA_ROOT / "documents"
DOCUMENT_SECTIONS = DOCUMENT_ROOT / "sections"
MIXED_CONFIG = DOCUMENT_ROOT / "mixed_config.yaml"
COMBINED_CONFIG = DOCUMENT_ROOT / "combined_config.yaml"
FULL_AUTHORITY_CONFIG = DOCUMENT_ROOT / "full_authority_config.yaml"
DOCUMENTS_CONFIG_JINJA = DOCUMENT_ROOT / "config.yaml.j2"
MIXED_AUTHORITY_DOCUMENT = DOCUMENT_ROOT / "mixed_authority_doc.html"


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

    content: list[etree._Element] = html.fromstring(
        new_doc.home_page_content.value
    )
    assert len(wis) == 0
    assert new_doc.rendering_layouts == [
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
                properties=[{"key": "fieldsAtStart", "value": "ID"}],
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

    content: list[etree._Element] = html.fromstring(
        new_doc.home_page_content.value
    )
    assert len(new_doc.rendering_layouts) == 1
    assert new_doc.rendering_layouts[
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
    assert len(wis) == 1
    assert wis[0].id == "ATSY-16062"
    assert wis[0].title == "Class Document"


def test_mixed_authority_document(
    empty_polarion_worker: polarion_worker.CapellaPolarionWorker,
    model: capellambse.MelodyModel,
):
    renderer = document_renderer.DocumentRenderer(
        empty_polarion_worker.polarion_data_repo, model
    )
    old_doc = polarion_api.Document(
        module_folder="_default",
        module_name="TEST-DOC",
        home_page_content=polarion_api.TextContent(
            type="text/html", value=MIXED_AUTHORITY_DOCUMENT.read_text("utf-8")
        ),
    )

    new_doc, wis = renderer.update_mixed_authority_document(
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
    )

    content: list[etree._Element] = html.fromstring(
        new_doc.home_page_content.value
    )

    assert len(content) == 15
    assert [c.tag for c in content[:3]] == ["h1", "p", "p"]
    assert (c4 := content[4]).tag == "h3" and c4.text == "New Heading"
    assert content[5].text == "Global Test"
    assert content[6].text == "Local Test section 1"
    assert content[8].text == "This will be kept."
    assert content[10].get("id") == (
        "polarion_wiki macro name=module-workitem;params=id=ATSY-18305"
    )
    assert content[10].tag == "h3"
    assert content[11].text == "Overwritten: Overwrite global param"
    assert content[12].text == "Local Test section 2"
    assert content[14].text == "Some postfix stuff"
    assert len(wis) == 1
    assert wis[0].id == "ATSY-18305"
    assert wis[0].title == "Keep Heading"


def test_full_authority_document_config():
    with open(
        "tests/data/documents/full_authority_config.yaml",
        "r",
        encoding="utf-8",
    ) as f:
        conf = document_config.read_config_file(f)

    assert len(conf.full_authority) == 2
    assert (
        conf.full_authority[0].template_directory
        == "jupyter-notebooks/document_templates"
    )
    assert conf.full_authority[0].template == "test-icd.html.j2"
    assert conf.full_authority[0].heading_numbering is False
    assert len(conf.full_authority[0].instances) == 2
    assert conf.full_authority[0].instances[0].polarion_space == "_default"
    assert conf.full_authority[0].instances[0].polarion_name == "id123"
    assert conf.full_authority[0].instances[0].polarion_title == "Interface23"
    assert conf.full_authority[0].instances[0].params == {
        "interface": "3d21ab4b-7bf6-428b-ba4c-a27bca4e86db"
    }


def test_mixed_authority_document_config():
    with open(MIXED_CONFIG, "r", encoding="utf-8") as f:
        conf = document_config.read_config_file(f)

    assert len(conf.full_authority) == 0
    assert len(conf.mixed_authority) == 2
    assert (
        conf.mixed_authority[0].template_directory
        == "jupyter-notebooks/document_templates"
    )
    assert conf.mixed_authority[0].sections == {
        "section1": "test-icd.html.j2",
        "section2": "test-icd.html.j2",
    }
    assert conf.mixed_authority[0].heading_numbering is False
    assert len(conf.mixed_authority[0].instances) == 2
    assert conf.mixed_authority[0].instances[0].polarion_space == "_default"
    assert conf.mixed_authority[0].instances[0].polarion_name == "id123"
    assert conf.mixed_authority[0].instances[0].polarion_title == "Interface23"
    assert conf.mixed_authority[0].instances[0].params == {
        "interface": "3d21ab4b-7bf6-428b-ba4c-a27bca4e86db"
    }
    assert conf.mixed_authority[1].instances[0].section_params == {
        "section1": {"param_1": "Test"}
    }


def test_combined_config():
    with open(COMBINED_CONFIG, "r", encoding="utf-8") as f:
        conf = document_config.read_config_file(f)

    assert len(conf.full_authority) == 2
    assert len(conf.mixed_authority) == 2


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
