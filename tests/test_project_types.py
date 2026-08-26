"""S_build geometry formula, and the roof_height_factor slot that used to be
hardcoded to 1.0 everywhere because no caller (form or tool schema) ever
exposed it — see project_types.py's compute_house_floor_area docstring."""

from __future__ import annotations

import pytest

from app.core.chat.intent import FORM_SCHEMAS
from app.core.construction.project_types import compute_house_floor_area
from app.core.mcp.tools.cost_tool import COST_TOOL


class TestComputeHouseFloorArea:
    def test_default_roof_factor_is_1_flat_roof(self):
        area = compute_house_floor_area(
            foundation_area_m2=100,
            foundation_type="mong_bang",
            floor_areas_m2=[80, 80],
            roof_area_m2=100,
        )
        assert area == pytest.approx(100 * 0.5 + 80 + 80 + 100 * 1.0)

    def test_sloped_roof_factor_increases_area(self):
        flat = compute_house_floor_area(
            foundation_area_m2=100,
            foundation_type="mong_bang",
            floor_areas_m2=[80],
            roof_area_m2=100,
            roof_height_factor=1.0,
        )
        sloped = compute_house_floor_area(
            foundation_area_m2=100,
            foundation_type="mong_bang",
            floor_areas_m2=[80],
            roof_area_m2=100,
            roof_height_factor=1.2,
        )
        assert sloped > flat
        assert sloped - flat == pytest.approx(100 * 0.2)


class TestRoofFactorIsReachable:
    """Regression guard: roof_height_factor previously had a working
    implementation but no caller could ever set it away from the default —
    missing from both the human-form schema and the tool schema, so it was
    unreachable in practice."""

    def test_form_schema_exposes_a_roof_factor_field(self):
        fields = {f["name"] for f in FORM_SCHEMAS["construction_cost"]["fields"]}
        assert "roof_height_factor" in fields

    def test_form_field_is_optional_with_a_flat_roof_default(self):
        field = next(
            f
            for f in FORM_SCHEMAS["construction_cost"]["fields"]
            if f["name"] == "roof_height_factor"
        )
        assert field["required"] is False
        assert field["default"] == 1.0

    def test_tool_schema_exposes_a_roof_factor_property(self):
        assert "roof_height_factor" in COST_TOOL.inputSchema["properties"]
