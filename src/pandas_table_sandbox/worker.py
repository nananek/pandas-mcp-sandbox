from __future__ import annotations

import io
import os
import secrets
import tempfile
import time
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field

from .operations import OperationError, apply_operations

MAX_BYTES = int(os.getenv("SANDBOX_MAX_FILE_BYTES", str(25 * 1024 * 1024)))
MAX_ROWS = int(os.getenv("SANDBOX_MAX_ROWS", "200000"))
MAX_COLUMNS = int(os.getenv("SANDBOX_MAX_COLUMNS", "200"))
MAX_PREVIEW = 100
MAX_OUTPUT_BYTES = int(os.getenv("SANDBOX_MAX_OUTPUT_BYTES", str(50 * 1024 * 1024)))
ROOT = Path(tempfile.gettempdir()) / "pandas-table-sandbox"
ROOT.mkdir(mode=0o700, exist_ok=True)
FILES: dict[str, pd.DataFrame] = {}
DATASETS: dict[str, pd.DataFrame] = {}
EXPORTS: dict[str, tuple[Path, float, str]] = {}

app = FastAPI(title="Pandas Table Sandbox", docs_url=None, redoc_url=None)


class OperationRequest(BaseModel):
    operations: list[dict[str, Any]] = Field(default_factory=list, max_length=30)
    preview_rows: int = Field(default=20, ge=1, le=MAX_PREVIEW)
    output_format: str | None = Field(default=None, pattern="^(csv|xlsx|json)$")


class ExportRequest(BaseModel):
    format: str = Field(pattern="^(csv|xlsx|json)$")
    filename: str = Field(default="result")


class RecordsRequest(BaseModel):
    records: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_ROWS)


def _safe_filename(name: str) -> str:
    clean = Path(name).name
    if clean != name or clean in {"", ".", ".."} or len(clean) > 100:
        raise HTTPException(400, "invalid filename")
    return clean


def _validate(frame: pd.DataFrame) -> None:
    if len(frame) > MAX_ROWS or len(frame.columns) > MAX_COLUMNS:
        raise OperationError("table exceeds configured row or column limit")


def _load(raw: bytes, filename: str) -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".csv", ".xlsx"}: raise HTTPException(415, "only CSV and XLSX files are supported")
    try:
        if suffix == ".xlsx": frame = pd.read_excel(io.BytesIO(raw), engine="openpyxl")
        else:
            try: frame = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig")
            except UnicodeDecodeError: frame = pd.read_csv(io.BytesIO(raw), encoding="cp932")
    except Exception as exc: raise HTTPException(400, "could not read table") from exc
    _validate(frame)
    return frame


def _register(frame: pd.DataFrame) -> str:
    _validate(frame)
    file_id = secrets.token_urlsafe(18)
    FILES[file_id] = frame
    return file_id


def _json_value(value: Any) -> Any:
    if pd.isna(value): return None
    if hasattr(value, "item"): return value.item()
    return str(value) if hasattr(value, "isoformat") else value


def preview(frame: pd.DataFrame, rows: int = 20) -> dict[str, Any]:
    return {
        "columns": [str(column) for column in frame.columns],
        "dtypes": {str(column): str(dtype) for column, dtype in frame.dtypes.items()},
        "row_count": len(frame), "column_count": len(frame.columns),
        "preview": [[_json_value(value) for value in row] for row in frame.head(rows).to_numpy().tolist()],
        "missing_values": {str(column): int(value) for column, value in frame.isna().sum().items()},
        "duplicate_rows": int(frame.duplicated().sum()),
    }


@app.get("/health")
def health() -> dict[str, str]: return {"status": "ok"}


@app.post("/v1/files")
async def upload(file: UploadFile = File(...)) -> dict[str, str]:
    filename = _safe_filename(file.filename or "table.csv")
    if file.content_type not in {"text/csv", "application/csv", "application/vnd.ms-excel",
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                "application/octet-stream"}:
        raise HTTPException(415, "unsupported MIME type")
    raw = await file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES: raise HTTPException(413, "file is too large")
    return {"file_id": _register(_load(raw, filename))}


@app.post("/v1/tables")
def create_table(request: RecordsRequest) -> dict[str, str]:
    """Register records supplied by an LLM or another trusted tool."""
    try:
        frame = pd.DataFrame.from_records(request.records)
        return {"file_id": _register(frame)}
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "could not create table from records") from exc


@app.get("/v1/files/{file_id}/inspect")
def inspect(file_id: str, preview_rows: int = 10) -> dict[str, Any]:
    if file_id not in FILES: raise HTTPException(404, "unknown file_id")
    if not 1 <= preview_rows <= MAX_PREVIEW: raise HTTPException(400, "invalid preview_rows")
    return preview(FILES[file_id], preview_rows)


@app.post("/v1/files/{file_id}/operations")
def operate(file_id: str, request: OperationRequest) -> dict[str, Any]:
    if file_id not in FILES: raise HTTPException(404, "unknown file_id")
    try: result = apply_operations(FILES[file_id], request.operations, DATASETS)
    except (OperationError, KeyError, TypeError, ValueError) as exc: raise HTTPException(400, str(exc)) from None
    _validate(result)
    dataset_id = secrets.token_urlsafe(18)
    DATASETS[dataset_id] = result
    response = preview(result, request.preview_rows) | {"dataset_id": dataset_id}
    if request.output_format:
        response["export"] = {"dataset_id": dataset_id, "format": request.output_format}
    return response


def _remove_export(path: Path, token: str) -> None:
    EXPORTS.pop(token, None)
    path.unlink(missing_ok=True)


def _cleanup_exports() -> None:
    now = time.time()
    for token, (path, expires_at, _) in list(EXPORTS.items()):
        if expires_at < now:
            _remove_export(path, token)


@app.post("/v1/datasets/{dataset_id}/export")
def export(dataset_id: str, request: ExportRequest) -> dict[str, str]:
    _cleanup_exports()
    if dataset_id not in DATASETS: raise HTTPException(404, "unknown dataset_id")
    filename = _safe_filename(request.filename)
    suffix = request.format
    path = ROOT / f"{secrets.token_hex(12)}.{suffix}"
    try:
        if suffix == "csv": DATASETS[dataset_id].to_csv(path, index=False, encoding="utf-8-sig")
        elif suffix == "json": DATASETS[dataset_id].to_json(path, orient="records", force_ascii=False)
        else: DATASETS[dataset_id].to_excel(path, index=False, engine="openpyxl")
    except Exception as exc: raise HTTPException(400, "could not export table") from exc
    if path.stat().st_size > MAX_OUTPUT_BYTES:
        path.unlink(missing_ok=True)
        raise HTTPException(413, "export is too large")
    token = secrets.token_urlsafe(18)
    EXPORTS[token] = (path, time.time() + 600, f"{filename}.{suffix}")
    return {"download_url": f"/v1/exports/{token}", "filename": f"{filename}.{suffix}"}


@app.get("/v1/exports/{token}")
def download_export(token: str) -> FileResponse:
    _cleanup_exports()
    export_info = EXPORTS.get(token)
    if export_info is None or export_info[1] < time.time():
        if export_info: _remove_export(export_info[0], token)
        raise HTTPException(404, "export expired")
    path, _, filename = export_info
    return FileResponse(path, filename=filename, media_type="application/octet-stream",
                        background=BackgroundTask(_remove_export, path, token))
