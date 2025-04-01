# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0

import io
import logging
import pathlib

import pydantic
import pytest
from capellambse_context_diagrams import filters as context_filters

from capella2polarion.converters.converter_config import ConverterConfig
from capella2polarion.data_model import (
    AddAttributesParams,
    DiagramParams,
    JinjaAsDescriptionParams,
    LinkConfigProcessed,
)

# pylint: disable=relative-beyond-top-level, useless-suppression
from .conftest import TEST_MODEL_ELEMENTS_CONFIG


@pytest.fixture
def dummy_jinja_structure(tmp_path: pathlib.Path) -> pathlib.Path:
    """Creates a dummy directory structure and file for Jinja tests."""
    template_dir = (
        tmp_path / "docs" / "source" / "examples" / "element_templates"
    )
    template_dir.mkdir(parents=True, exist_ok=True)
    template_file = template_dir / "class.html.j2"
    template_file.touch()
    return tmp_path


class TestConverterConfig:
    @staticmethod
    def test_read_config_context_diagram_with_params():
        expected_filter_func = getattr(
            context_filters, "EX_ITEMS_OR_EXCH", None
        )
        assert (
            expected_filter_func is not None
        ), "EX_ITEMS_OR_EXCH filter not found in context_filters"

        converter_key = "add_context_diagram-func"

        config = ConverterConfig()
        with open(TEST_MODEL_ELEMENTS_CONFIG, "r", encoding="utf8") as f:
            config.read_config_file(f)

        type_config = config.get_type_config("sa", "SystemFunction")

        assert type_config is not None
        assert isinstance(type_config.converters, dict)
        assert converter_key in type_config.converters
        converter_params = type_config.converters[converter_key]
        assert isinstance(converter_params, DiagramParams)
        assert len(converter_params.filters) == 1
        assert converter_params.filters[0].func == expected_filter_func
        assert converter_params.filters[0].args == {}

    @staticmethod
    def test_read_config_tree_view_with_params():
        converter_key = "add_tree_diagram"
        expected_render_params = {"depth": 1}

        config = ConverterConfig()
        with open(TEST_MODEL_ELEMENTS_CONFIG, "r", encoding="utf8") as f:
            config.read_config_file(f)

        type_config = config.get_type_config("*", "Class")

        assert type_config is not None
        assert isinstance(type_config.converters, dict)
        assert converter_key in type_config.converters
        converter_params = type_config.converters[converter_key]
        assert isinstance(converter_params, DiagramParams)
        assert converter_params.render_params == expected_render_params

    @staticmethod
    def test_read_config_links(caplog: pytest.LogCaptureFixture):
        """Tests link processing using actual capellambse find_wrapper."""
        expected_link1 = LinkConfigProcessed(
            capella_attr="inputs.exchanges",
            polarion_role="ROLE_input_exchanges",
            include={"Exchange Items": "exchange_items"},
            link_field="inputExchanges",
            reverse_field="inputExchangesReverse",
        )
        expected_link2 = LinkConfigProcessed(
            capella_attr="outputs.exchanges",
            polarion_role="ROLE_output_exchanges",
            include={"Exchange Items": "exchange_items"},
            link_field="output_exchanges",
            reverse_field="output_exchanges_reverse",
        )
        caplog.set_level(logging.WARNING)

        config = ConverterConfig()
        with open(TEST_MODEL_ELEMENTS_CONFIG, "r", encoding="utf8") as f:
            config.read_config_file(f, role_prefix="ROLE")

        system_fnc_config = config.get_type_config("sa", "SystemFunction")
        fe_config_sa = config.get_type_config("sa", "FunctionalExchange")
        actual_link1 = next(
            (
                link
                for link in system_fnc_config.links
                if link.capella_attr == "inputs.exchanges"
            ),
            None,
        )
        actual_link2 = next(
            (
                link
                for link in system_fnc_config.links
                if link.capella_attr == "outputs.exchanges"
            ),
            None,
        )
        link_present = any(
            link.capella_attr == "exchanged_items"
            for link in fe_config_sa.links
        )
        assert config.diagram_config is not None
        assert not any(
            link.capella_attr == "parent"
            for link in config.diagram_config.links
        )
        assert any(
            link.capella_attr == "diagram_elements"
            for link in config.diagram_config.links
        )
        assert any(
            rec.levelname == "WARNING"
            and "Link attribute 'parent' is not available on Capella type Diagram"
            in rec.message
            for rec in caplog.records
        ), "Missing warning for 'parent' link on Diagram"
        assert system_fnc_config is not None
        assert actual_link1 == expected_link1, f"Actual: {actual_link1}"
        assert actual_link2 == expected_link2, f"Actual: {actual_link2}"
        assert fe_config_sa is not None
        assert link_present, "'exchanged_items' link should be present"


class TestAddAttributesConverterConfig:
    @staticmethod
    def test_global_attributes_are_registered():
        """Verify global attributes are inherited."""
        config = ConverterConfig()
        global_converter_key = "add_attributes-global"
        tree_converter_key = "add_tree_diagram"
        expected_attribute = {"capella_attr": "layer", "polarion_id": "layer"}
        expected_tree_params = {"depth": 1}

        with open(TEST_MODEL_ELEMENTS_CONFIG, "r", encoding="utf8") as f:
            config.read_config_file(f)

        type_config = config.get_type_config("*", "Class")

        assert type_config is not None
        assert isinstance(type_config.converters, dict)
        assert global_converter_key in type_config.converters
        attr_params = type_config.converters[global_converter_key]
        assert isinstance(attr_params, AddAttributesParams)
        assert attr_params.attributes == [expected_attribute]
        assert tree_converter_key in type_config.converters
        tree_params_actual = type_config.converters[tree_converter_key]
        assert isinstance(tree_params_actual, DiagramParams)
        assert tree_params_actual.render_params == expected_tree_params

    @staticmethod
    def test_global_custom_suffixed_attributes_handling():
        """Test that suffixed converters are parsed correctly."""
        yaml_str = """\
        "*":
          "*":
            serializer:
              add_attributes-custom:
                attributes:
                  - capella_attr: layer
                    polarion_id: layer
        oa:
          TestType: {}
        """
        converter_key = "add_attributes-custom"
        expected_attributes = [
            {"capella_attr": "layer", "polarion_id": "layer"}
        ]
        config = ConverterConfig()
        config.read_config_file(io.StringIO(yaml_str))
        type_config = config.get_type_config("oa", "TestType")

        assert type_config is not None
        assert type_config.converters is not None
        assert converter_key in type_config.converters
        attr_params = type_config.converters[converter_key]
        assert isinstance(attr_params, AddAttributesParams)
        assert attr_params.attributes == expected_attributes

    @staticmethod
    def test_local_serializers_overwrite_global_serializers():
        """Verify local replaces global for the same key."""
        yaml_str = """\
        "*":
          "*":
            serializer:
              add_attributes-general:
                attributes:
                  - capella_attr: layer
                    polarion_id: layer
        oa:
          TestType:
            serializer:
              add_attributes-general:
                attributes:
                  - capella_attr: nature
                    polarion_id: nature
        """
        converter_key = "add_attributes-general"
        expected_attributes = [
            {"capella_attr": "nature", "polarion_id": "nature"}
        ]
        config = ConverterConfig()
        config.read_config_file(io.StringIO(yaml_str))
        type_config = config.get_type_config("oa", "TestType")

        assert type_config is not None
        assert type_config.converters is not None
        assert converter_key in type_config.converters
        attr_params = type_config.converters[converter_key]
        assert isinstance(attr_params, AddAttributesParams)
        assert attr_params.attributes == expected_attributes

    @staticmethod
    def test_reset_local_add_attributes_with_empty_list():
        yaml_str = """\
        "*":
          "*":
            serializer:
              add_attributes-general:
                attributes:
                  - capella_attr: layer
                    polarion_id: layer
          Class:
            serializer:
              add_attributes-general:
                 attributes: []
        oa:
          Class:
            serializer:
              add_attributes:
                attributes:
                  - capella_attr: local_oa
                    polarion_id: local_oa
        """
        global_reset_key = "add_attributes-general"
        local_new_key = "add_attributes"
        expected_local_attributes = [
            {"capella_attr": "local_oa", "polarion_id": "local_oa"}
        ]

        config = ConverterConfig()
        config.read_config_file(io.StringIO(yaml_str))
        type_config = config.get_type_config("oa", "Class")

        assert type_config is not None
        assert type_config.converters is not None
        assert global_reset_key in type_config.converters
        reset_params = type_config.converters[global_reset_key]
        assert isinstance(reset_params, AddAttributesParams)
        assert reset_params.attributes == []
        assert local_new_key in type_config.converters
        local_params = type_config.converters[local_new_key]
        assert isinstance(local_params, AddAttributesParams)
        assert local_params.attributes == expected_local_attributes

    @staticmethod
    def test_layer_reset_for_add_attributes_from_file():
        """Tests resetting attributes using the main config file."""
        global_key = "add_attributes-global"
        local_key = "add_attributes"
        expected_reset_attributes = []
        expected_local_attributes = [
            {"capella_attr": "nature", "polarion_id": "nature"}
        ]

        config = ConverterConfig()
        with open(TEST_MODEL_ELEMENTS_CONFIG, "r", encoding="utf8") as f:
            config.read_config_file(f)

        type_config = config.get_type_config("pa", "PhysicalComponent")

        assert type_config is not None
        assert type_config.converters is not None
        assert global_key in type_config.converters
        reset_params = type_config.converters[global_key]
        assert isinstance(reset_params, AddAttributesParams)
        assert reset_params.attributes == expected_reset_attributes
        assert local_key in type_config.converters
        local_params = type_config.converters[local_key]
        assert isinstance(local_params, AddAttributesParams)
        assert local_params.attributes == expected_local_attributes


class TestJinjaAsDescriptionConfig:
    @staticmethod
    def test_jinja_as_description_valid(dummy_jinja_structure: pathlib.Path):
        """Test valid jinja_as_description configuration."""
        template_folder_rel = "docs/source/examples/element_templates"
        template_path_rel = "class.html.j2"

        yaml_str = f"""\
        pa:
          LogicalArchitecture:
             serializer:
               jinja_as_description:
                 template_folder: "{dummy_jinja_structure / template_folder_rel}"
                 template_path: "{template_path_rel}"
        """
        converter_key = "jinja_as_description"
        config = ConverterConfig()

        config.read_config_file(io.StringIO(yaml_str))
        type_config = config.get_type_config("pa", "LogicalArchitecture")

        assert type_config is not None
        assert type_config.converters is not None
        assert converter_key in type_config.converters
        params = type_config.converters[converter_key]
        assert isinstance(params, JinjaAsDescriptionParams)
        assert (
            params.template_folder
            == dummy_jinja_structure / template_folder_rel
        )
        assert params.template_path == template_path_rel

    @staticmethod
    def test_jinja_as_description_invalid_path(
        dummy_jinja_structure: pathlib.Path,
    ):
        """Test invalid jinja_as_description config (file doesn't exist)."""
        template_folder_rel = "docs/source/examples/element_templates"
        template_path_rel = "non_existent_file.j2"
        yaml_str = f"""\
        pa:
          PhysicalComponent:
             serializer:
               jinja_as_description:
                 template_folder: "{dummy_jinja_structure / template_folder_rel}"
                 template_path: "{template_path_rel}"
        """
        config = ConverterConfig()

        with pytest.raises(
            pydantic.ValidationError,
            match=r"JinjaAsDescriptionParams[\s\S]*Value error, \('"
            "Resolved template path does not exist or is not a file:",
        ):
            config.read_config_file(io.StringIO(yaml_str))

    @staticmethod
    def test_jinja_as_description_missing_keys(
        dummy_jinja_structure: pathlib.Path,
    ):
        """Test jinja_as_description missing required keys."""
        template_folder_rel = "docs/source/examples/element_templates"
        yaml_str_missing_path = f"""\
        pa:
          PhysicalComponent:
             serializer:
               jinja_as_description:
                 template_folder: "{dummy_jinja_structure / template_folder_rel}"
                 # template_path missing
        """
        yaml_str_missing_folder = """\
        pa:
          PhysicalComponent:
             serializer:
               jinja_as_description:
                 template_path: "class.html.j2"
                 # template_folder missing
        """
        config = ConverterConfig()

        with pytest.raises(
            pydantic.ValidationError,
            match=r"JinjaAsDescriptionParams\s+template_path\s+Field required",
        ):
            config.read_config_file(io.StringIO(yaml_str_missing_path))

        with pytest.raises(
            pydantic.ValidationError,
            match=r"JinjaAsDescriptionParams\s+template_folder\s+Field required",
        ):
            config.read_config_file(io.StringIO(yaml_str_missing_folder))
