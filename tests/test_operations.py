import pandas as pd
import pytest

from pandas_table_sandbox.operations import OperationError, apply_operations


def test_filter_sort_and_select():
    frame = pd.DataFrame({"name": ["a", "b", "c"], "sales": [100, 300, 200]})
    result = apply_operations(frame, [
        {"op": "filter", "column": "sales", "operator": ">=", "value": 200},
        {"op": "sort", "by": ["sales"], "ascending": False},
        {"op": "select_columns", "columns": ["name", "sales"]},
    ])
    assert result.to_dict("records") == [{"name": "b", "sales": 300}, {"name": "c", "sales": 200}]


def test_groupby_and_merge():
    left = pd.DataFrame({"key": ["a", "a", "b"], "value": [1, 2, 3]})
    right = pd.DataFrame({"key": ["a", "b"], "label": ["A", "B"]})
    grouped = apply_operations(left, [{"op": "groupby_aggregate", "by": ["key"], "aggregations": {"value": "sum"}}])
    merged = apply_operations(grouped, [{"op": "merge", "right_dataset_id": "right", "on": ["key"]}], {"right": right})
    assert merged.to_dict("records") == [{"key": "a", "value": 3, "label": "A"}, {"key": "b", "value": 3, "label": "B"}]


def test_groupby_alias_and_list_aggregation():
    frame = pd.DataFrame({"region": ["east", "east", "west"], "population": [10, 20, 5]})
    result = apply_operations(frame, [{
        "op": "groupby",
        "groupby": ["region"],
        "aggregation": [{"column": "population", "function": "sum"}],
    }])
    assert result.to_dict("records") == [
        {"region": "east", "population": 30}, {"region": "west", "population": 5}
    ]


def test_invalid_operation_is_rejected():
    with pytest.raises(OperationError):
        apply_operations(pd.DataFrame({"x": [1]}), [{"op": "execute_python", "code": "__import__('os')"}])


def test_population_helpers_are_declarative():
    frame = pd.DataFrame({"prefecture": ["A", "B", "C"], "population": [300, 100, 200]})
    result = apply_operations(frame, [
        {"op": "add_column", "column": "rank", "source_column": "population", "transform": "rank_desc"},
        {"op": "add_column", "column": "share", "source_column": "population", "transform": "percent_of_total", "decimal_places": 2},
        {"op": "sort", "by": ["rank"]},
    ])
    assert result["rank"].tolist() == [1, 2, 3]
    assert result["share"].tolist() == [50.0, 33.33, 16.67]


def test_calculation_alias_is_supported_and_missing_calculation_fails():
    frame = pd.DataFrame({"population": [3, 1]})
    result = apply_operations(frame, [{
        "op": "add_column", "column": "share", "source": "population",
        "calculation": "percentage_of_total", "decimal_places": 1,
    }])
    assert result["share"].tolist() == [75.0, 25.0]
    with pytest.raises(OperationError, match="supported calculation"):
        apply_operations(frame, [{"op": "add_column", "column": "empty"}])
