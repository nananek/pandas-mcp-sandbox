import io
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from pandas_table_sandbox import worker


@pytest.fixture
def client():
    worker.FILES.clear()
    worker.DATASETS.clear()
    worker.EXPORTS.clear()
    with TestClient(worker.app) as test_client:
        yield test_client
    worker.FILES.clear()
    worker.DATASETS.clear()
    for path, _, _ in list(worker.EXPORTS.values()):
        path.unlink(missing_ok=True)
    worker.EXPORTS.clear()


def test_upload_and_inspect_utf8_csv(client):
    response = client.post(
        "/v1/files",
        files={"file": ("people.csv", "name,population\nA,10\nB,20\n", "text/csv")},
    )
    assert response.status_code == 200
    file_id = response.json()["file_id"]
    inspected = client.get(f"/v1/files/{file_id}/inspect").json()
    assert inspected["columns"] == ["name", "population"]
    assert inspected["row_count"] == 2
    assert inspected["dtypes"]["population"] == "int64"


def test_upload_shift_jis_csv(client):
    content = "都道府県,人口\n東京都,14000000\n".encode("cp932")
    response = client.post(
        "/v1/files",
        files={"file": ("population.csv", content, "text/csv")},
    )
    assert response.status_code == 200
    file_id = response.json()["file_id"]
    assert client.get(f"/v1/files/{file_id}/inspect").json()["preview"][0][0] == "東京都"


def test_upload_xlsx(client):
    buffer = io.BytesIO()
    pd.DataFrame({"name": ["A"], "value": [1]}).to_excel(buffer, index=False)
    response = client.post(
        "/v1/files",
        files={
            "file": (
                "table.xlsx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 200
    assert response.json()["file_id"]


def test_records_groupby_and_dataset_chaining(client):
    created = client.post(
        "/v1/tables",
        json={
            "records": [
                {"region": "関東", "population": 10},
                {"region": "関東", "population": 20},
                {"region": "関西", "population": 5},
            ]
        },
    )
    assert created.status_code == 200
    file_id = created.json()["file_id"]
    ranked = client.post(
        f"/v1/files/{file_id}/operations",
        json={
            "operations": [
                {
                    "op": "add_column",
                    "column": "rank",
                    "source_column": "population",
                    "transform": "rank_desc",
                }
            ]
        },
    ).json()
    grouped = client.post(
        f"/v1/files/{ranked['dataset_id']}/operations",
        json={
            "operations": [
                {
                    "op": "groupby",
                    "groupby": ["region"],
                    "aggregation": [{"column": "population", "function": "sum"}],
                }
            ]
        },
    )
    assert grouped.status_code == 200
    assert grouped.json()["row_count"] == 2


def test_invalid_column_returns_safe_error(client):
    file_id = client.post(
        "/v1/tables", json={"records": [{"name": "A", "population": 1}]}
    ).json()["file_id"]
    response = client.post(
        f"/v1/files/{file_id}/operations",
        json={"operations": [{"op": "sort", "by": ["missing"]}]},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "unknown column: missing"}


def test_export_can_be_downloaded_once(client):
    file_id = client.post(
        "/v1/tables", json={"records": [{"name": "A", "value": 1}]}
    ).json()["file_id"]
    dataset_id = client.post(
        f"/v1/files/{file_id}/operations", json={"operations": []}
    ).json()["dataset_id"]
    exported = client.post(
        f"/v1/datasets/{dataset_id}/export",
        json={"format": "json", "filename": "result"},
    )
    assert exported.status_code == 200
    download = client.get(exported.json()["download_url"])
    assert download.status_code == 200
    assert json.loads(download.content)[0]["name"] == "A"
    assert client.get(exported.json()["download_url"]).status_code == 404
