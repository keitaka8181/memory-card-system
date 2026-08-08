# 思い出メッセージカード × R2 自動アップロード

ひとつの思い出JSONファイルを監視し、**更新されるたびに**新しい思い出の
メッセージカード(PNG)を自動生成して、**Cloudflare R2** に自動アップロードします。
カード生成とアップロードは `run.py` ひとつで同時に動きます。

```
思い出JSON(更新)  ->  カード生成(PNG + サイドカーJSON)  ->  R2 へアップロード
        ▲ 監視                  ▲ outputs/ に出力              ▲ outputs/ を監視
```

## 1. 準備

```bash
pip install -r requirements.txt          # pillow / boto3 / watchdog
cp config.example.py config.py           # 設定ファイルを作る（Windowsは copy）
```

`config.py` を開いて、以下を自分の値に書き換えます。

- `MEMORY_JSON` … 監視する思い出JSONのパス
- `OUTPUT_DIR` … カードの出力先（uploader が監視するフォルダ）
- `ENDPOINT_URL` / `ACCESS_KEY_ID` / `SECRET_ACCESS_KEY` / `BUCKET_NAME` … R2 の接続情報

## 2. 起動

```bash
python run.py
```

これだけで、

1. R2 アップローダーが `OUTPUT_DIR` の監視を開始
2. `MEMORY_JSON` の監視を開始
3. 起動時点の未生成の思い出をまとめてカード化
4. 以降、`MEMORY_JSON` を保存・更新するたびに、新しい思い出のカードを生成 → R2 へ送信

停止は `Ctrl+C`。カード生成とアップロードがまとめて止まります。

## 3. 思い出JSONの書き方

1ファイルに **1件のオブジェクト** でも **複数件の配列** でも書けます。

```json
[
  {
    "memory": "放課後の屋上で、二人で分けたメロンパンの味は今でも忘れられない。",
    "nickname": "ぽんた",
    "era": "2010年代",
    "genre": "友情",
    "latitude": 35.6812,
    "longitude": 139.7671
  }
]
```

| キー | 内容 | カード上の扱い |
|------|------|----------------|
| `memory` | 思い出の本文（長さ制限なし） | 中央。長文は自動縮小 |
| `nickname` | 書いた人のニックネーム | 左下 |
| `genre` | ジャンル（下記6種） | 右下のカラーピル＋端の装飾色 |
| `era` | 年代 | 画像には出さずファイル名へ |
| `latitude` / `longitude` | 緯度・経度 | 画像には出さず、ファイル名＋サイドカーへ |

ジャンルとイメージカラー: 恋愛=ピンク / 友情=水色 / 学業=緑 / 部活=黄 / 行事=紫 / その他=濃緑
（色は `message_card.py` の `GENRE_COLORS` で変更できます）

## 4. 出力されるもの

`OUTPUT_DIR` に、思い出1件につき2ファイル:

- `ジャンル_年代_ニックネーム_緯度_経度.png` … カード画像
- 同名 `.json` … サイドカー（`lat` / `lon` / `name`）。uploader が緯度経度を読むために使う

uploader は PNG を R2 の `images/` に置き、最後に `latest.json`
（`latest` / `lat` / `lon` / `name` / `ts`）を更新します。取得側はこの `latest.json` を見ます。

## 5. 仕組みの補足

- **二重生成しない**: 生成済みの思い出は `OUTPUT_DIR/.card_state.json` で記憶します。
  更新時は新しい/変更された思い出だけを作ります（本文等を編集すると別内容として作り直し）。
- **保存途中対策**: JSONが読めないタイミングは飛ばし、保存完了後のイベントで読み直します。
- **同名上書き対応**: 同じファイル名で作り直された場合も再アップロードします。

## 6. ファイル構成

```
run.py             統合ランチャー（これを起動する）
message_card.py    カード生成（描画・折り返し・サイドカー出力）
uploader.py        R2 監視アップローダー
config.example.py  設定テンプレート -> config.py を作る
memories.json      思い出JSONのサンプル
requirements.txt
```
