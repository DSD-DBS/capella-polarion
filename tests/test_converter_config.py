# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0

import io

import pytest
import yaml

from capella2polarion.converters import converter_config

# pylint: disable-next=relative-beyond-top-level, useless-suppression
from .conftest import TEST_MODEL_ELEMENTS_CONFIG  # type: ignore[import]


class TestConverterConfig:
    @staticmethod
    def test_read_config_context_diagram_with_params():
        expected_filter = (
            "capellambse_context_diagrams-show.exchanges.or.exchange.items."
            "filter"
        )
        config = converter_config.ConverterConfig()
        with open(TEST_MODEL_ELEMENTS_CONFIG, encoding="utf8") as f:
            config.read_config_file(f)

        type_config = config.get_type_config("sa", "SystemFunction")

        assert type_config is not None
        assert isinstance(type_config.converters, dict)
        assert "add_context_diagram" in type_config.converters
        assert type_config.converters["add_context_diagram"]["filters"] == [
            expected_filter
        ]

    @staticmethod
    def test_read_config_tree_view_with_params():
        config = converter_config.ConverterConfig()
        with open(TEST_MODEL_ELEMENTS_CONFIG, encoding="utf8") as f:
            config.read_config_file(f)

        type_config = config.get_type_config("la", "Class")

        assert type_config is not None
        assert isinstance(type_config.converters, dict)
        assert "add_tree_diagram" in type_config.converters
        assert type_config.converters["add_tree_diagram"]["render_params"] == {
            "depth": 1
        }

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
            "Link broken_attribute_name is not available on Capella type "
            "FunctionalExchange",
        )
        with open(TEST_MODEL_ELEMENTS_CONFIG, encoding="utf8") as f:
            config.read_config_file(f)

        assert config.diagram_config
        assert not any(
            link
            for link in config.diagram_config.links
            if link.capella_attr == "parent"
        )
        assert caplog.record_tuples[0] + caplog.record_tuples[1] == expected
        assert (
            system_fnc_config := config.get_type_config("sa", "SystemFunction")
        )
        assert system_fnc_config.links[0] == converter_config.LinkConfig(
            capella_attr="inputs.exchanges",
            polarion_role="input_exchanges",
            include={"Exchange Items": "exchange_items"},
            link_field="inputExchanges",
            reverse_field="inputExchangesReverse",
        )
        assert system_fnc_config.links[1] == converter_config.LinkConfig(
            capella_attr="outputs.exchanges",
            polarion_role="output_exchanges",
            include={"Exchange Items": "exchange_items"},
            link_field="output_exchanges",
            reverse_field="output_exchanges_reverse",
        )

    @staticmethod
    def test_add_read_config_global_serializers_are_registered():
        config = converter_config.ConverterConfig()
        expected_attribute_params = {
            "capella_attr": "layer",
            "polarion_id": "layer",
        }
        expected_tree_view_params = {"render_params": {"depth": 1}}
        with open(TEST_MODEL_ELEMENTS_CONFIG, encoding="utf8") as f:
            config.read_config_file(f)

        type_config = config.get_type_config("la", "Class")

        assert type_config is not None
        assert isinstance(type_config.converters, dict)
        assert "add_attributes" in type_config.converters
        assert type_config.converters["add_attributes"] == {
            "attributes": [expected_attribute_params]
        }
        assert "add_tree_diagram" in type_config.converters
        assert (
            type_config.converters["add_tree_diagram"]
            == expected_tree_view_params
        )

    @staticmethod
    def test_add_read_config_global_serializers_are_kept():
        config = converter_config.ConverterConfig()
        expected_attribute_params = [
            {"capella_attr": "layer", "polarion_id": "layer"},
            {"capella_attr": "nature", "polarion_id": "nature"},
        ]
        with open(TEST_MODEL_ELEMENTS_CONFIG, encoding="utf8") as f:
            config.read_config_file(f)

        type_config = config.get_type_config("pa", "PhysicalComponent")

        assert type_config is not None
        assert isinstance(type_config.converters, dict)
        assert "add_attributes" in type_config.converters
        assert (
            type_config.converters["add_attributes"]["attributes"]
            == expected_attribute_params
        )

    @staticmethod
    def test_add_jinja_fields_config():
        """Test that suffixed converters are parsed correctly."""
        converter_key = "add_jinja_fields"
        expected_attributes = {
            "field_id": {
                "template_folder": "folder/path",
                "template_path": "template.html.j2",
                "render_parameters": {"key": "value"},
            },
            "field_id_1": {
                "template_folder": "folder/path",
                "template_path": "template_1.html.j2",
            },
        }
        config = {
            "la": {
                "LogicalComponent": {
                    "serializer": {converter_key: expected_attributes}
                }
            }
        }
        yaml_str = yaml.dump(config, indent=2)
        config = converter_config.ConverterConfig()

        config.read_config_file(io.StringIO(yaml_str))
        type_config = config.get_type_config("la", "LogicalComponent")

        assert type_config is not None
        assert type_config.converters is not None
        assert converter_key in type_config.converters
        assert type_config.converters[converter_key] == expected_attributes
