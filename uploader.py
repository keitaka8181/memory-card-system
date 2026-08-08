#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
uploader.py  —  フォルダ監視型 R2 アップローダー（統合版）

OUTPUT_DIR を監視し、新しい/更新された画像（.png + 同名 .json のペア）が
出てきたら Cloudflare R2 へアップロードする。

【流れ】
  1. 監視フォルダに card.png と card.json（lat/lon入り）が揃う
  2. 画像本体を R2 にアップロード（images/ 以下）
  3. 最後に latest.json を上書き（最新キーと緯度経度を記録）
     ※ 必ず画像 -> manifest の順。逆だと取得側が存在しない画像を見にいく。

設定（監視フォルダ・接続情報）は config.py から読む。
run.py から start_observer() を呼べば、別スレッドで監視を動かせる。
"""

import json
import threading
import time
from pathlib import Path

import boto3
from botocore.config import Config
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import config

# 監視フォルダ（カード生成の出力先）と R2 上の接頭辞
WATCH_DIR = Path(config.OUTPUT_DIR).resolve()
KEY_PREFIX = getattr(config, "KEY_PREFIX", "images/")


def make_s3_client():
    """config.py の情報で R2(S3互換) クライアントを作る。"""
    return boto3.client(
        "s3",
        endpoint_url=config.ENDPOINT_URL,
        aws_access_key_id=config.ACCESS_KEY_ID,
        aws_secret_access_key=config.SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",  # R2 は auto 固定
    )


def load_latlon(png_path: Path):
    """画像と同名の .json（サイドカー）から緯度経度を読む。"""
    json_path = png_path.with_suffix(".json")
    if not json_path.exists():
        return None
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        return {"lat": data["lat"], "lon": data["lon"],
                "name": data.get("name", png_path.stem)}
    except (json.JSONDecodeError, KeyError):
        return None


def upload(s3, png_path: Path) -> bool:
    """画像1枚をアップロードし、latest.json を更新する。成功で True。"""
    meta = load_latlon(png_path)
    if meta is None:
        return False  # .json 未着 = ペア未成立。後で再試行。

    key = f"{KEY_PREFIX}{png_path.name}"

    # (1) 画像本体
    with open(png_path, "rb") as f:
        s3.put_object(Bucket=config.BUCKET_NAME, Key=key, Body=f, ContentType="image/png")

    # (2) 最後に manifest（順番が重要）
    manifest = {
        "latest": key,
        "lat": meta["lat"],
        "lon": meta["lon"],
        "name": meta["name"],
        "ts": int(time.time() * 1000),
    }
    s3.put_object(
        Bucket=config.BUCKET_NAME,
        Key="latest.json",
        Body=json.dumps(manifest, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )
    print(f"  アップロード完了: {key}  (lat={meta['lat']}, lon={meta['lon']})")
    return True


class PngHandler(FileSystemEventHandler):
    """新規/更新された .png を検知してアップロードするハンドラ。"""

    def __init__(self, s3):
        self.s3 = s3
        self.pending = set()          # .json 待ちで保留中の png
        self.last_mtime = {}          # path -> 最後にアップロードした時の mtime（重複抑止）
        self._lock = threading.Lock()

    def _try_upload(self, path: Path):
        if path.suffix.lower() != ".png" or not path.exists():
            return
        with self._lock:
            # 直近にアップ済みで中身が変わっていなければスキップ（重複イベント対策）
            try:
                mtime = path.stat().st_mtime
            except FileNotFoundError:
                return
            if self.last_mtime.get(str(path)) == mtime:
                return
            if upload(self.s3, path):
                self.last_mtime[str(path)] = mtime
                self.pending.discard(path)
            else:
                self.pending.add(path)

    def _handle(self, src_path):
        path = Path(src_path)
        suffix = path.suffix.lower()
        if suffix == ".png":
            time.sleep(0.2)  # 書き込み完了を少し待つ
            self._try_upload(path)
        elif suffix == ".json":
            png = path.with_suffix(".png")
            if png in self.pending:
                self._try_upload(png)

    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def on_modified(self, event):
        # 同名上書き（再生成）でも再アップロードできるように modified も拾う
        if not event.is_directory:
            self._handle(event.src_path)

    def on_moved(self, event):
        # エディタ等のアトミック保存（rename）対策
        if not event.is_directory:
            self._handle(event.dest_path)


def upload_existing(s3, handler: PngHandler):
    """起動時、すでにフォルダにある未処理の画像も一度処理しておく。"""
    for png in sorted(WATCH_DIR.glob("*.png")):
        handler._try_upload(png)


def start_observer(s3):
    """監視を開始して Observer と handler を返す（ノンブロッキング）。"""
    WATCH_DIR.mkdir(parents=True, exist_ok=True)
    handler = PngHandler(s3)
    upload_existing(s3, handler)
    observer = Observer()
    observer.schedule(handler, str(WATCH_DIR), recursive=False)
    observer.start()
    return observer, handler


def main():
    """単体起動（アップローダーのみ）。"""
    s3 = make_s3_client()
    print(f"監視フォルダ: {WATCH_DIR}")
    print("起動時の既存ファイルを確認中...")
    observer, _ = start_observer(s3)
    print("監視を開始しました。Ctrl+C で停止します。")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n停止します。")
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
