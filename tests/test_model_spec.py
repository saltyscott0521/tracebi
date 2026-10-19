"""Declarative model schema: the refusals a journey can't pin precisely."""


import pytest

from tracebi.model.model_spec import validate_model_file, validate_model_spec


def _doc(**over):
    doc = {
        "name": "m",
        "connectors": [{"name": "w", "type": "duckdb", "database": "data/w.duckdb"}],
        "tables": [{"name": "t", "connector": "w", "source": "t"}],
        "measures": [{"name": "n", "column": "x", "agg": "sum"}],
    }
    doc.update(over)
    return doc


@pytest.mark.parametrize("key", ["url", "password", "token", "credentials"])
def test_a_connector_cannot_carry_credentials(key):
    doc = _doc(connectors=[{"name": "w", "type": "duckdb", "database": "d.duckdb", key: "s3cret"}])
    errors = validate_model_spec(doc)
    assert any(f"connectors[0]: unknown key '{key}'" in e for e in errors)


@pytest.mark.parametrize("database", ["/etc/x.duckdb", "../x.duckdb", "data/../../x.duckdb", "C:\\x.duckdb"])
def test_a_database_must_stay_inside_the_project(database):
    doc = _doc(connectors=[{"name": "w", "type": "duckdb", "database": database}])
    assert any(e.startswith("connectors[0].database") for e in validate_model_spec(doc))


@pytest.mark.parametrize("key", ["database", "secret"])
def test_the_project_warehouse_connector_names_no_place_and_no_credential(key):
    # `type: warehouse` is wherever tracebi.yaml says; a path or a secret here
    # would be a second answer to that question.
    assert validate_model_spec(_doc(connectors=[{"name": "w", "type": "warehouse"}])) == []
    doc = _doc(connectors=[{"name": "w", "type": "warehouse", key: "x"}])
    errors = validate_model_spec(doc)
    assert errors and all(e.startswith("connectors[0]") for e in errors)
    assert any(key in e for e in errors)


def _yaml(tmp_path, text, stem="m"):
    (tmp_path / "models").mkdir(exist_ok=True)
    path = tmp_path / "models" / f"{stem}.yaml"
    path.write_text(text)
    return path


def test_a_repeated_yaml_key_is_an_error_not_last_wins(tmp_path):
    path = _yaml(tmp_path, "name: m\nmeasures:\n  - name: n\n    agg: sum\n    agg: mean\n")
    errors = validate_model_file(path)
    assert len(errors) == 1 and "duplicate key 'agg'" in errors[0]


def test_a_yaml_object_tag_is_refused_not_constructed(tmp_path):
    marker = tmp_path / "ran"
    path = _yaml(tmp_path, "name: !!python/object/apply:pathlib.Path.touch "
                           f"[!!python/object/apply:pathlib.Path [{marker}]]\n")
    errors = validate_model_file(path)
    assert errors and "not valid YAML" in errors[0]
    assert not marker.exists()
