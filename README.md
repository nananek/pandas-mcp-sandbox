# pandas-table-sandbox

Open WebUIからCSV/XLSXを安全に操作するための、宣言的なPandas Workerです。
LLM生成Pythonコードは受け付けず、操作JSONのホワイトリストだけを実行します。

## 構成

`openwebui_tool.py` は薄いHTTPクライアント、Pandas処理はDockerコンテナ内のWorkerです。
Workerはread-only filesystem、非root、全capability削除、内部ネットワークで起動します。

```bash
docker compose up --build -d
```

Open WebUIのToolに `openwebui_tool.py` を貼り付け、Valvesの
`PANDAS_WORKER_URL`を設定します。Toolのアップロード入力はBase64形式です。
実運用ではOpen WebUIのファイルAPIから取得した内容をToolに渡す薄い連携を追加してください。

対応操作は `select_columns`, `drop_columns`, `filter`, `sort`, `rename_columns`,
`cast_type`, `fill_missing`, `drop_missing`, `drop_duplicates`, `add_column`,
`groupby_aggregate`, `pivot`, `merge` です。

## 制限

既定でファイル25MiB、20万行、200列、1操作リクエスト30操作までです。
入力元ファイルは変更せず、データはWorkerのメモリに保持します。Workerを公開ネットワークに
直接公開せず、認証付きのリバースプロキシ等を併用してください。
