"""
title: Pandas Table Sandbox
author: nananek
version: 0.1.0
license: MIT
description: Safely inspect and transform uploaded CSV/XLSX tables through a sandbox worker.
requirements: pydantic
"""

import base64
import json
import urllib.error
import urllib.request
from typing import Any

from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        PANDAS_WORKER_URL: str = Field(default="http://pandas-worker:8080", description="Sandbox worker URL")

    def __init__(self) -> None:
        self.valves = self.Valves()

    def _request(self, method: str, path: str, body: bytes | None = None, content_type: str = "application/json") -> Any:
        url = self.valves.PANDAS_WORKER_URL.rstrip("/") + path
        request = urllib.request.Request(url, data=body, method=method, headers={"Content-Type": content_type})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError("Pandas Workerへの接続または処理に失敗しました") from exc

    async def upload_table(self, filename: str, content_base64: str) -> str:
        """CSV/XLSXをWorkerに登録し、後続処理用のfile_idを返す。"""
        try:
            content = base64.b64decode(content_base64, validate=True)
        except Exception as exc:
            return f"入力エラー: Base64データが不正です ({type(exc).__name__})"
        boundary = "----pandas-sandbox-boundary"
        payload = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
                   "Content-Type: application/octet-stream\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
        try:
            result = self._request("POST", "/v1/files", payload, f"multipart/form-data; boundary={boundary}")
            return f"登録しました。file_id: {result['file_id']}"
        except (RuntimeError, KeyError) as exc:
            return f"エラー: {exc}"

    async def inspect_table(self, file_id: str, preview_rows: int = 10) -> str:
        """表の列、型、件数、欠損、重複、先頭行を確認する。"""
        try:
            return json.dumps(self._request("GET", f"/v1/files/{file_id}/inspect?preview_rows={preview_rows}"), ensure_ascii=False, indent=2)
        except RuntimeError as exc:
            return f"エラー: {exc}"

    async def run_table_operation(self, file_id: str, operations: list[dict[str, Any]], preview_rows: int = 20) -> str:
        """許可されたJSON操作だけで表を変換し、結果のプレビューを返す。"""
        try:
            result = self._request("POST", f"/v1/files/{file_id}/operations", json.dumps({"operations": operations, "preview_rows": preview_rows}).encode())
            return json.dumps(result, ensure_ascii=False, indent=2)
        except RuntimeError as exc:
            return f"エラー: {exc}"

    async def export_table(self, dataset_id: str, format: str, filename: str = "result") -> str:
        """処理結果をCSV、XLSX、JSONとしてWorkerから出力する。"""
        if format not in {"csv", "xlsx", "json"}:
            return "入力エラー: formatはcsv、xlsx、jsonのいずれかです"
        try:
            result = self._request("POST", f"/v1/datasets/{dataset_id}/export", json.dumps({"format": format, "filename": filename}).encode())
            base = self.valves.PANDAS_WORKER_URL.rstrip("/")
            result["download_url"] = base + result["download_url"]
            return json.dumps(result, ensure_ascii=False, indent=2)
        except RuntimeError as exc:
            return f"エラー: {exc}"
