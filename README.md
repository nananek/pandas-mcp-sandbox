# pandas-table-sandbox

Open WebUIからCSV/XLSXや会話中のレコードを安全に操作するための、宣言的なPandas Workerです。
LLM生成Pythonコードは受け付けず、操作JSONのホワイトリストだけを実行します。

## 構成

`openwebui_tool.py` は薄いHTTPクライアント、Pandas処理はDockerコンテナ内のWorkerです。
Workerはread-only filesystem、非root、全capability削除、内部ネットワークで起動します。

```bash
docker compose up --build -d
```

For a deployment where Open WebUI and the worker share an existing Docker
network, use the deployment overlay so no host port is exposed:

```bash
docker compose -f docker-compose.yml -f docker-compose.server.yml up -d --build
```

The overlay attaches the worker to the externally managed Open WebUI network.
Configure the Tool with the worker's service URL on that network. Do not publish
port 8080 to the host for this deployment mode.

Open WebUIのToolに `openwebui_tool.py` を貼り付け、Valvesの
`PANDAS_WORKER_URL`を設定します。Toolのアップロード入力はBase64形式です。
Webページから表を取得した場合は、LLMが行列を `create_table(records)` に直接渡せます。
ファイルアップロードのBase64変換は必須ではありません。

対応操作は `select_columns`, `drop_columns`, `filter`, `sort`, `rename_columns`,
`cast_type`, `fill_missing`, `drop_missing`, `drop_duplicates`, `add_column`,
`groupby_aggregate`, `pivot`, `merge` です。`add_column` には `percent_of_total`,
`rank_desc`, `rank_asc`, `cumsum`, `multiply`, `divide` の宣言的変換もあります。

## 制限

既定でファイル25MiB、20万行、200列、1操作リクエスト30操作までです。
入力元ファイルは変更せず、データはWorkerのメモリに保持します。Workerを公開ネットワークに
直接公開せず、認証付きのリバースプロキシ等を併用してください。

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

GitHub Actions runs the same test suite and a Python compilation check on every
push to `main` and every pull request.
