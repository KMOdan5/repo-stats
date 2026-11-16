"""GitHub のリポジトリの訪問数・来た元のサイト・リリースのダウンロード数・スター数などを集め、data/ の CSV に足す。

使い方: GITHUB_TOKEN に読み取り用のトークンを入れて、リポジトリの一番上で実行する。
    python3 scripts/collect.py

対象のリポジトリは repos.json に書く。

CSV の形(1 行に 1 つの数。DB にそのまま取り込める形):
- data/views.csv     … date, repo, views, uniques
    日ごとの閲覧数と訪問者数。GitHub は直近 14 日分を返すので、毎回その分を上書きする
    (その日の途中で取った数が、次の日に確定した数で置き換わる)。
- data/downloads.csv … date, repo, tag, asset, downloads
    記録した日の、添付ファイルごとのダウンロード数の合計。日ごとの増え方は、前の日との差で出す。
- data/referrers.csv … date, repo, referrer, views, uniques
    記録した日に GitHub が返す、直近 14 日の来た元のサイトの上位。
- data/repo.csv      … date, repo, stars, forks, watchers
    記録した日の、スター数・フォーク数・ウォッチ数。

日付は UTC。同じ日に何度実行しても、その日の行が置き換わるだけで、行は増えない。

data/updated.json には、CSV の中身が変わった日時(UTC)を書く。ページの「更新日時」に使う。
"""

import csv
import datetime
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
API = "https://api.github.com"

# CSV ごとの列
COLUMNS = {
    "views": ["date", "repo", "views", "uniques"],
    "downloads": ["date", "repo", "tag", "asset", "downloads"],
    "referrers": ["date", "repo", "referrer", "views", "uniques"],
    "repo": ["date", "repo", "stars", "forks", "watchers"],
}

# CSV ごとの、行を見分けるための列(この順に並べて書く)
KEYS = {
    "views": ["date", "repo"],
    "downloads": ["date", "repo", "tag", "asset"],
    "referrers": ["date", "repo", "referrer"],
    "repo": ["date", "repo"],
}


def get(path: str, token: str):
    """GitHub の API を呼び、JSON を返す。"""
    request = urllib.request.Request(
        API + path,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "tool-stats",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def get_all_releases(repo: str, token: str):
    """リリースをすべて返す(100 件ずつ取る)。"""
    releases, page = [], 1
    while True:
        chunk = get(f"/repos/{repo}/releases?per_page=100&page={page}", token)
        releases.extend(chunk)
        if len(chunk) < 100:
            return releases
        page += 1


def read_rows(name: str):
    path = DATA / f"{name}.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_rows(name: str, rows) -> bool:
    """行を日付・リポジトリなどの順に並べて書く。中身が変わらなければ書かない(余計なコミットを出さないため)。

    中身が変わって書いたら True を返す。
    """
    columns = COLUMNS[name]
    rows = sorted(rows, key=lambda row: [str(row[c]) for c in KEYS[name]])
    path = DATA / f"{name}.csv"
    DATA.mkdir(exist_ok=True)
    lines = [",".join(columns)]
    for row in rows:
        lines.append(",".join(csv_cell(row[c]) for c in columns))
    text = "\n".join(lines) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def csv_cell(value) -> str:
    text = str(value)
    if any(ch in text for ch in ',"\n'):
        return '"' + text.replace('"', '""') + '"'
    return text


def replace(rows, new_rows, is_old):
    """古い行のうち is_old に当たるものを捨て、新しい行を足す。"""
    return [row for row in rows if not is_old(row)] + new_rows


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("GITHUB_TOKEN is not set", file=sys.stderr)
        return 1
    repos = json.loads((ROOT / "repos.json").read_text(encoding="utf-8"))
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()

    views = read_rows("views")
    downloads = read_rows("downloads")
    referrers = read_rows("referrers")
    repo_rows = read_rows("repo")
    failed = 0

    for repo in repos:
        try:
            # 訪問数: 返ってきた日の分だけ、前の記録を置き換える
            traffic = get(f"/repos/{repo}/traffic/views", token)["views"]
            new = [
                {"date": v["timestamp"][:10], "repo": repo, "views": v["count"], "uniques": v["uniques"]}
                for v in traffic
            ]
            dates = {row["date"] for row in new}
            views = replace(views, new, lambda r: r["repo"] == repo and r["date"] in dates)

            # ダウンロード数: 今日の合計
            new = [
                {"date": today, "repo": repo, "tag": rel["tag_name"], "asset": a["name"], "downloads": a["download_count"]}
                for rel in get_all_releases(repo, token)
                for a in rel["assets"]
            ]
            downloads = replace(downloads, new, lambda r: r["repo"] == repo and r["date"] == today)

            # 来た元のサイト: 今日時点の直近 14 日の上位
            new = [
                {"date": today, "repo": repo, "referrer": r["referrer"], "views": r["count"], "uniques": r["uniques"]}
                for r in get(f"/repos/{repo}/traffic/popular/referrers", token)
            ]
            referrers = replace(referrers, new, lambda r: r["repo"] == repo and r["date"] == today)

            # スター数・フォーク数・ウォッチ数: 今日の数(ウォッチ数は API では subscribers_count)
            info = get(f"/repos/{repo}", token)
            new = [{
                "date": today, "repo": repo, "stars": info["stargazers_count"],
                "forks": info["forks_count"], "watchers": info["subscribers_count"],
            }]
            repo_rows = replace(repo_rows, new, lambda r: r["repo"] == repo and r["date"] == today)
            print(f"{repo}: ok")
        except Exception as error:  # 1 つのリポジトリで失敗しても、ほかのリポジトリは記録する
            failed += 1
            print(f"{repo}: failed ({error})", file=sys.stderr)

    changed = [
        write_rows("views", views),
        write_rows("downloads", downloads),
        write_rows("referrers", referrers),
        write_rows("repo", repo_rows),
    ]
    # 更新日時は、中身が変わったときだけ書き換える(変わらない日にコミットを出さないため)
    updated = DATA / "updated.json"
    if any(changed) or not updated.exists():
        now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
        updated.write_text(json.dumps({"updated": now.isoformat().replace("+00:00", "Z")}) + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
