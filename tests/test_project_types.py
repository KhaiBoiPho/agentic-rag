"""S_build geometry formula, and the roof_type slot that used to be
hardcoded to "flat roof" everywhere because no caller (form or tool schema)
ever exposed it — see project_types.py's compute_house_floor_area docstring.

roof_type (not a bare numeric factor) — a user has no way to know their
"roof coefficient", but everyone knows what kind of roof their house has,
same reasoning as foundation_type being picked by loại móng instead of a
number for H_móng."""

from __future__ import annotations

import pytest

from app.core.chat.intent import FORM_SCHEMAS
from app.core.construction.project_types import ROOF_TYPE_FACTOR, compute_house_floor_area
from app.core.mcp.tools.cost_tool import COST_TOOL


class TestComputeHouseFloorArea:
    def test_default_roof_type_is_flat_roof(self):
        area = compute_house_floor_area(
            foundation_area_m2=100,
            foundation_type="mong_bang",
            floor_areas_m2=[80, 80],
            roof_area_m2=100,
        )
        assert area == pytest.approx(100 * 0.5 + 80 + 80 + 100 * 1.0)

    def test_sloped_roof_type_increases_area(self):
        flat = compute_house_floor_area(
            foundation_area_m2=100,
            foundation_type="mong_bang",
            floor_areas_m2=[80],
            roof_area_m2=100,
            roof_type="mai_bang",
        )
        sloped = compute_house_floor_area(
            foundation_area_m2=100,
            foundation_type="mong_bang",
            floor_areas_m2=[80],
            roof_area_m2=100,
            roof_type="mai_ngoi",
        )
        assert sloped > flat
        assert sloped - flat == pytest.approx(100 * (ROOF_TYPE_FACTOR["mai_ngoi"] - 1.0))

    def test_invalid_roof_type_is_rejected(self):
        with pytest.raises(ValueError, match="roof_type"):
            compute_house_floor_area(
                foundation_area_m2=100,
                foundation_type="mong_bang",
                floor_areas_m2=[80],
                roof_area_m2=100,
                roof_type="mai_khong_ton_tai",
            )


class TestRoofTypeIsReachable:
    """Regression guard: this slot previously had a working implementation
    but no caller could ever set it away from the default — missing from
    both the human-form schema and the tool schema, so it was unreachable
    in practice."""

    def test_form_schema_exposes_a_roof_type_field(self):
        fields = {f["name"] for f in FORM_SCHEMAS["construction_cost"]["fields"]}
        assert "roof_type" in fields

    def test_form_field_is_an_optional_select_defaulting_to_flat_roof(self):
        field = next(
            f for f in FORM_SCHEMAS["construction_cost"]["fields"] if f["name"] == "roof_type"
        )
        assert field["required"] is False
        assert field["type"] == "select"
        assert field["default"] == "mai_bang"
        option_values = {o["value"] for o in field["options"]}
        assert option_values == set(ROOF_TYPE_FACTOR)

    def test_tool_schema_exposes_a_roof_type_property_with_matching_enum(self):
        prop = COST_TOOL.inputSchema["properties"]["roof_type"]
        assert set(prop["enum"]) == set(ROOF_TYPE_FACTOR)
