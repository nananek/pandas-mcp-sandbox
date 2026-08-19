from __future__ import annotations

from typing import Any

import pandas as pd


ALLOWED_OPS = {
    "select_columns", "drop_columns", "filter", "sort", "rename_columns",
    "cast_type", "fill_missing", "drop_missing", "drop_duplicates",
    "add_column", "groupby_aggregate", "pivot", "merge",
}
_FILTERS = {"=", "==", "!=", ">", ">=", "<", "<=", "contains", "in"}
_DTYPES = {"string", "Int64", "Float64", "boolean", "datetime64[ns]"}


class OperationError(ValueError):
    pass


def _columns(frame: pd.DataFrame, names: list[str], field: str = "columns") -> None:
    if not isinstance(names, list) or not names or any(not isinstance(x, str) for x in names):
        raise OperationError(f"{field} must be a non-empty list of column names")
    missing = [name for name in names if name not in frame.columns]
    if missing:
        raise OperationError(f"unknown column: {missing[0]}")


def apply_operations(
    frame: pd.DataFrame,
    operations: list[dict[str, Any]],
    datasets: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    result = frame.copy()
    for operation in operations:
        if not isinstance(operation, dict) or operation.get("op") not in ALLOWED_OPS:
            raise OperationError("unsupported operation")
        op = operation["op"]
        if op == "select_columns":
            names = operation.get("columns")
            _columns(result, names)
            result = result[names]
        elif op == "drop_columns":
            names = operation.get("columns")
            _columns(result, names)
            result = result.drop(columns=names)
        elif op == "filter":
            column, operator = operation.get("column"), operation.get("operator")
            if column not in result.columns or operator not in _FILTERS:
                raise OperationError("invalid filter column or operator")
            value = operation.get("value")
            series = result[column]
            if operator in {"=", "=="}: mask = series == value
            elif operator == "!=": mask = series != value
            elif operator == ">": mask = series > value
            elif operator == ">=": mask = series >= value
            elif operator == "<": mask = series < value
            elif operator == "<=": mask = series <= value
            elif operator == "contains": mask = series.astype("string").str.contains(str(value), na=False)
            else:
                if not isinstance(value, list): raise OperationError("in filter value must be a list")
                mask = series.isin(value)
            result = result[mask]
        elif op == "sort":
            names = operation.get("by")
            _columns(result, names, "by")
            ascending = operation.get("ascending", True)
            if not isinstance(ascending, (bool, list)): raise OperationError("ascending must be boolean or list")
            result = result.sort_values(by=names, ascending=ascending, kind="mergesort")
        elif op == "rename_columns":
            mapping = operation.get("mapping")
            if not isinstance(mapping, dict) or any(key not in result.columns for key in mapping):
                raise OperationError("invalid rename mapping")
            result = result.rename(columns=mapping)
        elif op == "cast_type":
            column, dtype = operation.get("column"), operation.get("dtype")
            if column not in result.columns or dtype not in _DTYPES: raise OperationError("invalid column or dtype")
            result[column] = pd.to_datetime(result[column]) if dtype == "datetime64[ns]" else result[column].astype(dtype)
        elif op == "fill_missing":
            column, value = operation.get("column"), operation.get("value")
            if column not in result.columns: raise OperationError("unknown column")
            result[column] = result[column].fillna(value)
        elif op == "drop_missing":
            names = operation.get("columns")
            if names is not None: _columns(result, names)
            result = result.dropna(subset=names)
        elif op == "drop_duplicates":
            names = operation.get("columns")
            if names is not None: _columns(result, names)
            result = result.drop_duplicates(subset=names, keep=operation.get("keep", "first"))
        elif op == "add_column":
            column, value = operation.get("column"), operation.get("value")
            if not isinstance(column, str) or not column or column in result.columns:
                raise OperationError("add_column requires a new column name")
            result[column] = value
        elif op == "groupby_aggregate":
            by, aggregations = operation.get("by"), operation.get("aggregations")
            _columns(result, by, "by")
            if not isinstance(aggregations, dict) or not aggregations: raise OperationError("aggregations is required")
            allowed = {"sum", "mean", "min", "max", "count", "nunique", "median"}
            if any(value not in allowed for value in aggregations.values()): raise OperationError("unsupported aggregation")
            _columns(result, list(aggregations), "aggregations")
            result = result.groupby(by, dropna=False, as_index=False).agg(aggregations)
        elif op == "pivot":
            index, columns, values = operation.get("index"), operation.get("columns"), operation.get("values")
            _columns(result, [index, columns, values], "pivot columns")
            result = pd.pivot_table(result, index=index, columns=columns, values=values, aggfunc=operation.get("aggfunc", "sum"), fill_value=operation.get("fill_value")).reset_index()
            result.columns = [str(column) for column in result.columns]
        elif op == "merge":
            right_id, on = operation.get("right_dataset_id"), operation.get("on")
            if not datasets or right_id not in datasets: raise OperationError("unknown right_dataset_id")
            _columns(result, on, "on")
            _columns(datasets[right_id], on, "on")
            result = result.merge(datasets[right_id], on=on, how=operation.get("how", "inner"), suffixes=("_left", "_right"))
    return result.reset_index(drop=True)
