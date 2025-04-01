# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Module providing pydantic classes for the converter config."""

from __future__ import annotations

import pathlib
import typing as t

import pydantic
from capellambse_context_diagrams import filters as context_filters
from pydantic import DirectoryPath, RootModel, field_validator, model_validator

__all__ = [
    "AddAttributesParams",
    "AddJinjaFieldsParams",
    "BaseModel",
    "CapellaTypeConfigInput",
    "CapellaTypeConfigProcessed",
    "DiagramFilter",
    "DiagramParams",
    "FullConfigInput",
    "JinjaAsDescriptionParams",
    "LinkConfigInput",
    "LinkConfigProcessed",
    "LinkIncludeConfig",
    "SERIALIZER_PARAM_MODELS",
    "SimpleParams",
]


class BaseModel(pydantic.BaseModel):
    """Custom base model for common configuration."""

    class Config:
        """Config for BaseModel."""

        extra = "forbid"


class LinkIncludeConfig(RootModel[dict[str, str]]):
    """Represents the 'include' dictionary: {DisplayName: capella_attr}."""

    root: dict[str, str] = {}


class LinkConfigInput(BaseModel):
    """Raw input structure for a link config (dict format from YAML)."""

    capella_attr: str
    polarion_role: str | None = None
    include: LinkIncludeConfig = pydantic.Field(
        default_factory=LinkIncludeConfig
    )
    link_field: str | None = None
    reverse_field: str | None = None


class LinkConfigProcessed(LinkConfigInput):
    """Processed Link Config.

    Defaults are applied and prefixes potentially added.

    Attributes
    ----------
    capella_attr
        The attribute name on the capellambse model object.
    polarion_role
        The identifier used in Polarion for the link role (guaranteed).
    include
        Dictionary mapping display names to included attributes from linked objects.
    link_field
        The Polarion field name for the forward link (guaranteed).
    reverse_field
        The Polarion field name for the reverse link (guaranteed).
    """

    @model_validator(mode="before")
    @classmethod
    def apply_link_defaults(cls, values: dict[str, t.Any]) -> dict[str, t.Any]:
        """Derive role, link_field, reverse_field if not provided."""
        capella_attr = values.get("capella_attr")
        if not capella_attr:
            raise ValueError("LinkConfigInput requires 'capella_attr'")

        base_id = values.get("polarion_role", capella_attr)
        if not values.get("polarion_role"):
            values["polarion_role"] = base_id
        if not values.get("link_field"):
            values["link_field"] = base_id
        if not values.get("reverse_field"):
            link_field_val = values.get("link_field", base_id)
            values["reverse_field"] = f"{link_field_val}_reverse"
        return values


class AddAttributesParams(BaseModel):
    """Parameters for 'add_attributes' serializer."""

    attributes: list[dict[str, str]] = []

    @field_validator("attributes", mode="before", check_fields=False)
    @classmethod
    def normalize_attribute_items(
        cls, attributes: list[str | dict[str, t.Any]]
    ) -> list[dict[str, str]]:
        """Normalize string entries to the dictionary format during input."""
        if not isinstance(attributes, list):
            raise TypeError(
                "AddAttributesParams must be either a list of capella "
                "attribute IDs or dictionaries"
            )

        normalized_list: list[dict[str, str]] = []
        for item in attributes:
            if isinstance(item, str):
                normalized_list.append(
                    {"capella_attr": item, "polarion_id": item}
                )
            elif isinstance(item, dict):
                if "capella_attr" not in item:
                    raise ValueError(
                        "AddAttributesParams is missing 'capella_attr', %r",
                        item,
                    )

                item.setdefault(
                    "polarion_id",
                    item.get("polarion_id", item["capella_attr"]),
                )

                normalized_list.append(
                    {
                        "capella_attr": str(item["capella_attr"]),
                        "polarion_id": str(item["polarion_id"]),
                    }
                )
            else:
                raise TypeError(
                    "AddAttributesParams doesn't support attribute type in "
                    "list: %r",
                    type(item).__name__,
                )
        return normalized_list


class DiagramFilter(BaseModel):
    """Represents a single filter function reference."""

    func: t.Callable
    args: dict[str, t.Any] = {}

    @field_validator("func", mode="before")
    @classmethod
    def resolve_filter_func(cls, filter_id: str) -> t.Callable:
        """Resolve filter function name string to callable."""
        try:
            func = getattr(context_filters, filter_id)
            if not callable(func):
                raise TypeError(
                    "Filter in context_filters isn't callable, %r", func
                )
            return func
        except AttributeError:
            raise ValueError("Unknown diagram filter ID: %r", filter_id)

    class Config:
        """Config for DiagramFilter."""

        arbitrary_types_allowed = True


class DiagramParams(BaseModel):
    """Parameters for diagram serializers like 'add_context_diagram'."""

    filters: list[DiagramFilter] = []
    render_params: dict[str, t.Any] = {}

    @field_validator("filters", mode="before", check_fields=False)
    @classmethod
    def normalize_filter_input(
        cls, items: list[str | dict[str, t.Any]]
    ) -> list[dict[str, t.Any]] | t.Any:
        """Handle diagram filters."""
        normalized_list: list[dict[str, t.Any]] = []
        for item in items:
            if isinstance(item, str):
                normalized_list.append({"func": item})
            elif isinstance(item, dict):
                if "func" in item:
                    normalized_list.append(item)
                else:
                    raise ValueError(
                        "Filter item missing 'func' key, %r", item
                    )
        return normalized_list


class AddJinjaFieldsParams(BaseModel):
    """Parameters for 'add_jinja_fields', expects a dict of fields."""

    fields: dict[str, t.Any] = {}

    @model_validator(mode="before")
    @classmethod
    def ensure_input_is_fields_dict(
        cls, values: dict[str, t.Any]
    ) -> dict[str, t.Any]:
        """Ensure the input dict has the 'fields' key."""
        if isinstance(values, dict):
            if "fields" in values and isinstance(values["fields"], dict):
                return values
            elif "fields" not in values:
                return {"fields": values}
        else:
            raise TypeError(
                "AddJinjaFieldsParams must be a dictionary, got: %r", values
            )
        return values


class JinjaAsDescriptionParams(BaseModel):
    """Parameters for 'jinja_as_description' serializer."""

    template_folder: DirectoryPath
    template_path: str
    resolved_template_path: pathlib.Path | None = pydantic.Field(
        None, exclude=True
    )

    @model_validator(mode="after")
    def check_full_template_path(self) -> JinjaAsDescriptionParams:
        """Check existence of resolved template path."""
        full_path = (self.template_folder / self.template_path).resolve()
        if not full_path.is_file():
            raise ValueError(
                "Resolved template path does not exist or is not a file: %r",
                full_path,
            )

        self.resolved_template_path = full_path
        return self


class SimpleParams(BaseModel):
    """Parameters for simple serializers (accepts any dict or empty)."""

    class Config:
        """Config for SimpleParams."""

        extra = "allow"


SERIALIZER_PARAM_MODELS: dict[str, type[BaseModel]] = {
    "include_pre_and_post_condition": SimpleParams,
    "linked_text_as_description": SimpleParams,
    "add_attributes": AddAttributesParams,
    "add_context_diagram": DiagramParams,
    "add_tree_diagram": DiagramParams,
    "add_jinja_fields": AddJinjaFieldsParams,
    "jinja_as_description": JinjaAsDescriptionParams,
    "diagram": SimpleParams,
}


class CapellaTypeConfigInput(BaseModel):
    """Represents a single entry for a Capella type config from YAML."""

    polarion_type: str | None = None
    links: list[str | LinkConfigInput] = []
    serializer: None | str | list[str] | dict[str, t.Any] = None
    is_actor: bool | None = None
    nature: str | None = None

    @field_validator("links", mode="before", check_fields=False)
    @classmethod
    def normalize_link_input(cls, v: t.Any) -> list[dict[str, t.Any]] | t.Any:
        """Allow link input list items as string or dict."""
        if not isinstance(v, list):
            return v

        normalized_list: list[dict[str, t.Any]] = []
        for item_idx, item in enumerate(v):
            if isinstance(item, str):
                normalized_list.append({"capella_attr": item})
            elif isinstance(item, dict):
                # Assume it's compatible with LinkConfigInput
                normalized_list.append(item)
            else:
                raise TypeError(
                    f"Link item {item_idx} must be string or dict, got {type(item).__name__}"
                )
        return normalized_list

    @field_validator("serializer", mode="before")
    @classmethod
    def normalize_serializer_input(cls, v: t.Any) -> dict[str, t.Any] | t.Any:
        """Normalize various serializer input formats to a dictionary."""
        if v is None:
            return {}
        if isinstance(v, str):
            return {v: {}}
        if isinstance(v, list):
            if not all(isinstance(i, str) for i in v):
                raise ValueError("Serializer list must contain only strings")
            return {name: None for name in v}
        if isinstance(v, dict):
            normalized_dict: dict[str, t.Any] = {}
            for name, params in v.items():
                base_name = name.split("-", 1)[0]
                if base_name not in SERIALIZER_PARAM_MODELS:
                    raise ValueError(
                        f"Unknown serializer ID: {base_name!r} derived "
                        f"from {name!r}"
                    )

                param_model = SERIALIZER_PARAM_MODELS[base_name]
                processed_params = params
                if param_model is AddAttributesParams and isinstance(
                    params, list
                ):
                    processed_params = {"attributes": params}
                elif not isinstance(params, (dict, type(None))):
                    raise ValueError(
                        f"Parameters for serializer {name!r} ({base_name!r}) "
                        f"must be dict or null, got {type(params).__name__}"
                    )

                normalized_dict.setdefault(name, processed_params or {})
            return normalized_dict
        return v


class CapellaTypeConfigProcessed(BaseModel):
    """Represents a fully validated and processed type configuration."""

    p_type: str
    converters: dict[str, BaseModel] = {}
    links: list[LinkConfigProcessed] = []
    is_actor_specifier: bool | None = None
    nature_specifier: str | None = None

    class Config:
        """Config for CapellaTypeConfigProcessed."""

        arbitrary_types_allowed = True


class FullConfigInput(
    RootModel[dict[str, dict[str, list[CapellaTypeConfigInput]]]]
):
    """Parses the entire YAML structure, ensuring types map to lists."""

    root: dict[str, dict[str, list[CapellaTypeConfigInput]]]

    @model_validator(mode="before")
    @classmethod
    def ensure_type_configs_are_lists(cls, values: t.Any) -> t.Any:
        """Ensure that each Capella type maps to a list of configs."""
        if not isinstance(values, dict):
            raise TypeError("YAML root must be a dictionary (layers mapping)")

        processed_root: dict[str, dict[str, list[CapellaTypeConfigInput]]] = {}
        for layer, layer_config in values.items():
            if not isinstance(layer_config, dict):
                if layer_config is None:
                    processed_root[layer] = {}
                    continue
                raise TypeError(
                    f"Layer '{layer}' configuration must be a dictionary, got {type(layer_config).__name__}"
                )

            processed_layer: dict[str, list[CapellaTypeConfigInput]] = {}
            for c_type, type_config in layer_config.items():
                try:
                    if type_config is None:
                        processed_layer[c_type] = [CapellaTypeConfigInput()]
                    elif isinstance(type_config, dict):
                        processed_layer[c_type] = [
                            CapellaTypeConfigInput.model_validate(type_config)
                        ]
                    elif isinstance(type_config, list):
                        parsed_list: list[CapellaTypeConfigInput] = []
                        for item_idx, item in enumerate(type_config):
                            if isinstance(item, dict):
                                parsed_list.append(
                                    CapellaTypeConfigInput.model_validate(item)
                                )
                            else:
                                raise TypeError(
                                    f"Item {item_idx} must be a dictionary, got {type(item).__name__}"
                                )
                        processed_layer[c_type] = parsed_list
                    else:
                        raise TypeError(
                            f"Config must be a dictionary, list, or null, got {type(type_config).__name__}"
                        )
                except (pydantic.ValidationError, TypeError, ValueError) as e:
                    raise ValueError(
                        f"Validation error in config for {layer}/{c_type}: {e}"
                    ) from e
            processed_root[layer] = processed_layer
        return processed_root
