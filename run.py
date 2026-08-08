#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run.py  —  統合ランチャー（これ1つを起動すれば全部動く）

  python run.py

やること:
  1. uploader の監視を別スレッドで開始（OUTPUT_DIR を見て R2 へ自動アップロード）
  2. config.MEMORY_JSON を監視
  3. MEMORY_JSON が更新されたら、まだカード化していない思い出を生成
     -> OUTPUT_DIR に PNG+サイドカーが出る -> uploader が拾って R2 へ送る

  Ctrl+C で両方まとめて停止。

  既に生成済みの思い出は state ファイル（OUTPUT_DIR/.card_state.json）で覚えていて、
  二重生成しない。思い出の本文等を編集すると「別の内容」として作り直す。

設定:
  config.py の MEMORY_JSON / OUTPUT_DIR / R2接続情報 を使う。
"""

import hashlib
import json
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

try:
    import config
except ModuleNotFoundError:
    import sys
    print("config.py が見つかりません。\n"
          "  config.example.py を config.py にコピーして、"
          "監視するJSONのパスとR2のAPIキーを記入してください。\n"
          "  例: cp config.example.py config.py", file=sys.stderr)
    sys.exit(1)

import message_card
import uploader

MEMORY_JSON = Path(config.MEMORY_JSON).resolve()
OUTPUT_DIR = Path(config.OUTPUT_DIR).resolve()
STATE_PATH = OUTPUT_DIR / ".card_state.json"

DEBOUNCE_SEC = 0.6  # 連続保存をまとめる待ち時間


# ------------------------------------------------------------
# 生成済みハッシュの記憶（二重生成防止）
# ------------------------------------------------------------

def load_state():
    if STATE_PATH.exists():
        try:
            return set(json.loads(STATE_PATH.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            return set()
    return set()


def save_state(state):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(sorted(state), ensure_ascii=False, indent=2),
                          encoding="utf-8")


def memory_hash(item: dict) -> str:
    """思い出1件の内容から安定したハッシュを作る。"""
    blob = json.dumps(item, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


# ------------------------------------------------------------
# 生成パス（更新検知のたびに走る）
# ------------------------------------------------------------

def generate_new_cards(state) -> int:
    """MEMORY_JSON を読み、未生成の思い出だけカード化する。生成枚数を返す。"""
    try:
        data = json.loads(MEMORY_JSON.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"  [待機] 監視対象がまだありません: {MEMORY_JSON}")
        return 0
    except json.JSONDecodeError:
        # 書き込み途中などで壊れて読めた場合は、次のイベントで読み直す
        print("  [スキップ] JSON を読めませんでした（保存途中かもしれません）")
        return 0

    items = data if isinstance(data, list) else [data]
    made = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        h = memory_hash(item)
        if h in state:
            continue
        try:
            png = message_card.generate(item, str(OUTPUT_DIR))
            state.add(h)
            made += 1
            print(f"  カード生成: {Path(png).name}")
        except Exception as e:  # 1件の失敗で全体を止めない
            print(f"  [エラー] 生成に失敗: {e}")
    if made:
        save_state(state)
    return made


# ------------------------------------------------------------
# MEMORY_JSON の監視（親フォルダを見て対象ファイルだけ反応・デバウンス）
# ------------------------------------------------------------

class MemoryFileHandler(FileSystemEventHandler):
    def __init__(self, state):
        self.state = state
        self._timer = None
        self._lock = threading.Lock()

    def _matches(self, path_str) -> bool:
        try:
            return Path(path_str).resolve() == MEMORY_JSON
        except OSError:
            return False

    def _schedule(self):
        # 連続イベントをまとめて、最後の1回だけ生成パスを走らせる
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(DEBOUNCE_SEC, self._run)
            self._timer.start()

    def _run(self):
        n = generate_new_cards(self.state)
        if n == 0:
            print("  （新しい思い出はありませんでした）")

    def on_modified(self, event):
        if not event.is_directory and self._matches(event.src_path):
            self._schedule()

    def on_created(self, event):
        if not event.is_directory and self._matches(event.src_path):
            self._schedule()

    def on_moved(self, event):
        # アトミック保存（一時ファイル -> rename）対策
        if not event.is_directory and self._matches(getattr(event, "dest_path", "")):
            self._schedule()


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()

    # (1) R2 アップローダーの監視を開始
    s3 = uploader.make_s3_client()
    up_observer, _ = uploader.start_observer(s3)
    print(f"[uploader] 監視フォルダ: {OUTPUT_DIR}  -> R2: {config.BUCKET_NAME}")

    # (2) 起動時に一度、既存の思い出を生成（未生成分のみ）
    print(f"[generator] 監視ファイル: {MEMORY_JSON}")
    print("起動時の内容を確認中...")
    generate_new_cards(state)

    # (3) MEMORY_JSON の監視を開始（親ディレクトリを監視）
    watch_dir = str(MEMORY_JSON.parent)
    Path(watch_dir).mkdir(parents=True, exist_ok=True)
    mem_handler = MemoryFileHandler(state)
    mem_observer = Observer()
    mem_observer.schedule(mem_handler, watch_dir, recursive=False)
    mem_observer.start()

    print("\n準備完了。思い出JSONを更新するとカード生成＆アップロードされます。")
    print("Ctrl+C で停止します。\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n停止します。")
    finally:
        mem_observer.stop()
        up_observer.stop()
        mem_observer.join()
        up_observer.join()


if __name__ == "__main__":
    main()
