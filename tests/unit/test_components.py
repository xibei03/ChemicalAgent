"""组分表和分子式解析。"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.components import (
    ComponentEntry,
    ComponentTable,
    atoms_by_component,
    find_component,
    load_component_table,
    parse_formula,
)
from reactor_agent.spec.enums import ComponentPhase

REPO = Path(__file__).resolve().parents[2]
TABLE_FILE = REPO / "config" / "components.yaml"
HYSYS_NAMES_FROM_THE_LEDGER = {
    "Methane",
    "H2O",
    "CO",
    "CO2",
    "Hydrogen",
    "Toluene",
    "Benzene",
    "p-Xylene",
    "m-Xylene",
    "o-Xylene",
    "Carbon",
}


def entry(name, formula="CH4", aliases=(), weight=16.0, phase=ComponentPhase.GAS):
    return ComponentEntry(
        name=name,
        aliases=aliases,
        formula=formula,
        molecular_weight_kg_per_kmol=weight,
        phase=phase,
    )


class TestParseFormula:
    @pytest.mark.parametrize(
        ("formula", "atoms"),
        [
            ("C7H8", {"C": 7, "H": 8}),
            ("H2O", {"H": 2, "O": 1}),
            ("C", {"C": 1}),
            ("H2", {"H": 2}),
            ("CO", {"C": 1, "O": 1}),
            ("Co", {"Co": 1}),
            ("Ca(OH)2", {"Ca": 1, "O": 2, "H": 2}),
            ("Al2(SO4)3", {"Al": 2, "S": 3, "O": 12}),
            ("(CH3)3C", {"C": 4, "H": 9}),
            ("C7H8         ", {"C": 7, "H": 8}),
        ],
    )
    def test_formula_becomes_element_counts(self, formula, atoms):
        assert dict(parse_formula(formula)) == atoms

    @pytest.mark.parametrize("formula", ["", "   ", "h2o", "C7 H8", "C7H8)", "(CH4", "H2O!", "2H"])
    def test_malformed_formula_is_rejected(self, formula):
        with pytest.raises(ValueError, match="分子式"):
            parse_formula(formula)


class TestComponentTable:
    def test_shipped_table_has_exactly_the_components_measured_in_hysys(self):
        table = load_component_table(TABLE_FILE)
        assert {item.name for item in table.components} == HYSYS_NAMES_FROM_THE_LEDGER

    def test_every_shipped_component_has_a_parsable_formula_and_a_weight(self):
        table = load_component_table(TABLE_FILE)
        atoms = atoms_by_component(table)
        assert set(atoms) == HYSYS_NAMES_FROM_THE_LEDGER
        assert atoms["Hydrogen"] == {"H": 2}
        assert atoms["p-Xylene"] == atoms["o-Xylene"] == {"C": 8, "H": 10}
        assert all(item.molecular_weight_kg_per_kmol > 0 for item in table.components)

    def test_only_carbon_is_a_solid(self):
        table = load_component_table(TABLE_FILE)
        solids = {item.name for item in table.components if item.phase is ComponentPhase.SOLID}
        assert solids == {"Carbon"}

    @pytest.mark.parametrize(
        ("text", "canonical"),
        [
            ("Methane", "Methane"),
            ("methane", "Methane"),
            ("甲烷", "Methane"),
            ("水蒸气", "H2O"),
            ("  steam ", "H2O"),
            ("ＣＯ２", "CO2"),
            ("H2", "Hydrogen"),
            ("对二甲苯", "p-Xylene"),
            ("煤", "Carbon"),
        ],
    )
    def test_component_is_found_by_name_or_alias_in_any_width_and_case(self, text, canonical):
        found = find_component(load_component_table(TABLE_FILE), text)
        assert found is not None
        assert found.name == canonical

    def test_unknown_component_is_not_found(self):
        assert find_component(load_component_table(TABLE_FILE), "Unobtainium") is None

    def test_alias_that_belongs_to_two_components_is_rejected(self):
        with pytest.raises(ValidationError, match="同时是"):
            ComponentTable(
                components=(entry("Methane", aliases=("gas",)), entry("Ethane", aliases=("GAS",)))
            )

    def test_formula_that_cannot_be_parsed_is_rejected(self):
        with pytest.raises(ValidationError, match="分子式"):
            entry("Methane", formula="CH4)")

    def test_non_positive_molecular_weight_is_rejected(self):
        with pytest.raises(ValidationError):
            entry("Methane", weight=0.0)


class TestLoading:
    def test_missing_file_is_an_io_error(self, tmp_path):
        with pytest.raises(ReactorAgentError) as caught:
            load_component_table(tmp_path / "nope.yaml")
        assert caught.value.code is ErrorCode.IO

    def test_broken_yaml_is_a_schema_error(self, tmp_path):
        path = tmp_path / "bad.yaml"
        path.write_text("components: [unclosed", encoding="utf-8")
        with pytest.raises(ReactorAgentError) as caught:
            load_component_table(path)
        assert caught.value.code is ErrorCode.SCHEMA

    def test_invalid_content_names_the_field_that_is_wrong(self, tmp_path):
        path = tmp_path / "bad.yaml"
        path.write_text(
            "components:\n"
            "  - {name: X, formula: H2, molecular_weight_kg_per_kmol: 2.0, phase: plasma}\n",
            encoding="utf-8",
        )
        with pytest.raises(ReactorAgentError) as caught:
            load_component_table(path)
        assert caught.value.code is ErrorCode.SCHEMA
        assert "components[0].phase" in caught.value.message
        assert "components[0].phase" in caught.value.details

    def test_json_files_are_read_too(self, tmp_path):
        path = tmp_path / "table.json"
        path.write_text(
            '{"components": [{"name": "H2", "formula": "H2", '
            '"molecular_weight_kg_per_kmol": 2.016, "phase": "gas"}]}',
            encoding="utf-8",
        )
        assert load_component_table(path).components[0].name == "H2"
