# repo-stats

GitHub のリポジトリの訪問数・来た元のサイト・リリースのダウンロード数・スター数などを毎日記録し、閲覧数・訪問者数・ダウンロード数をグラフで見るためのリポジトリです。

GitHub の「Insights」→「Traffic」は直近 14 日分しか残らず、リリースのダウンロード数も合計しか分かりません。GitHub Actions で毎日 1 回記録し、推移を残します。

## 記録しているもの
| ファイル | 中身 |
|---|---|
| `data/views.csv` | 日ごとの閲覧数と訪問者数 |
| `data/downloads.csv` | 記録した日の、リリースの添付ファイルごとのダウンロード数の合計 |
| `data/referrers.csv` | 記録した日の、直近 14 日の来た元のサイトの上位 |
| `data/repo.csv` | 記録した日の、スター数・フォーク数・ウォッチ数 |
| `data/updated.json` | 記録の中身が最後に変わった日時(UTC)。ページでは日本時間で表示します |

どれも「日付・リポジトリ・項目・数」を 1 行ずつ並べた CSV です。日付は UTC です。

## 仕組み
- `.github/workflows/collect.yaml` が毎日 UTC 0:37(日本時間 9:37)に `scripts/collect.py` を動かし、`data/` に記録します。中身が変わったときだけコミットします
- `index.html` が `data/` の CSV を読み、閲覧数・訪問者数・ダウンロード数を GitHub Pages で折れ線グラフにします(来た元のサイトとスター数などは、記録だけしています)
- 記録するリポジトリは `repos.json` に並べます

## 設定
- Secrets の `STATS_TOKEN`: きめ細かいトークン(fine-grained personal access token)。対象は記録するリポジトリだけにして、権限は Repository permissions の「Administration」の読み取りだけにします。訪問数の API にこの権限が要り、Actions の標準のトークンには付けられないためです
- GitHub Pages: `main` の `/ (root)` から公開します

## ライセンス
MIT License。グラフの描画には [Chart.js](https://www.chartjs.org/)(MIT License)を CDN から読み込んでいます。
