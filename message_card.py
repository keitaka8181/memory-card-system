#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
message_card.py  —  思い出メッセージカード生成

思い出データ(dict) 1件 -> 正方形 PNG カード 1枚 + サイドカー .json を生成する。
サイドカー .json は uploader.py が緯度経度を読むために使う（同名・lat/lon入り）。

思い出データのスキーマ（1件分）:
{
    "memory":    "思い出の本文。長さ制限なし。",
    "nickname":  "ニックネーム",
    "era":       "2010年代",
    "genre":     "友情",
    "latitude":  35.6812,
    "longitude": 139.7671
}

カード上のレイアウト:
    思い出本文 = 中央 / ニックネーム = 左下 / ジャンル = 右下(カラーピル)
    年代・緯度経度は画像には載せず、ファイル名とサイドカーに反映。

単体での使い方:
    python message_card.py memory.json -o ./outputs
"""

import argparse
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

# ============================================================
# 設定（見た目はここで調整）
# ============================================================

CANVAS_SIZE = 1080
MARGIN = 70
FRAME_INSET = 48

FONT_SERIF = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"
FONT_SANS = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_SANS_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

BODY_FONT_MAX = 60
BODY_FONT_MIN = 22
NICKNAME_FONT = 34
GENRE_FONT = 30

BODY_COLOR = (51, 51, 51)
NICKNAME_COLOR = (90, 90, 90)
BG_COLOR = (255, 255, 255)

# ジャンル -> イメージカラー(RGB)
GENRE_COLORS = {
    "恋愛": (236, 140, 170),   # ピンク
    "友情": (126, 196, 222),   # 水色
    "学業": (111, 191, 115),   # 緑
    "部活": (242, 193, 78),    # 黄色
    "行事": (156, 127, 201),   # 紫
    "その他": (46, 94, 78),    # 濃緑
}
DEFAULT_COLOR = (150, 150, 150)


# ============================================================
# 日本語向けテキスト処理
# ============================================================

KINSOKU_HEAD = set("、。，．・：；）」』】〕〉》｝］!?！？ー―〜～…ゝゞヽヾ々")
KINSOKU_TAIL = set("（「『【〔〈《｛［")


def _measure(draw, text, font):
    if not text:
        return 0
    b = draw.textbbox((0, 0), text, font=font)
    return b[2] - b[0]


def wrap_japanese(draw, text, font, max_width):
    """幅計測ベースで折り返し、簡易禁則処理を施す。明示改行も尊重。"""
    lines = []
    for paragraph in text.split("\n"):
        if paragraph == "":
            lines.append("")
            continue
        line = ""
        for ch in paragraph:
            if _measure(draw, line + ch, font) <= max_width or line == "":
                line += ch
            else:
                lines.append(line)
                line = ch
        if line:
            lines.append(line)
    return _apply_kinsoku(lines)


def _apply_kinsoku(lines):
    changed = True
    guard = 0
    while changed and guard < 50:
        changed = False
        guard += 1
        for i in range(len(lines)):
            line = lines[i]
            if i > 0 and line and line[0] in KINSOKU_HEAD:
                lines[i - 1] += line[0]
                lines[i] = line[1:]
                changed = True
            line = lines[i]
            if line and line[-1] in KINSOKU_TAIL and i + 1 < len(lines):
                lines[i + 1] = line[-1] + lines[i + 1]
                lines[i] = line[:-1]
                changed = True
    return lines


def fit_body_text(draw, text, max_width, max_height, line_spacing=1.5):
    """領域に収まる最大フォントで折り返す。長文は自動縮小。"""
    for size in range(BODY_FONT_MAX, BODY_FONT_MIN - 1, -2):
        font = ImageFont.truetype(FONT_SERIF, size)
        lines = wrap_japanese(draw, text, font, max_width)
        a, d = font.getmetrics()
        lh = int((a + d) * line_spacing)
        if lh * len(lines) <= max_height:
            return font, lines, lh * len(lines), lh
    font = ImageFont.truetype(FONT_SERIF, BODY_FONT_MIN)
    lines = wrap_japanese(draw, text, font, max_width)
    a, d = font.getmetrics()
    lh = int((a + d) * line_spacing)
    return font, lines, lh * len(lines), lh


# ============================================================
# 色ユーティリティ
# ============================================================

def _mix(c, o, r):
    return tuple(int(a * r + b * (1 - r)) for a, b in zip(c, o))


def _luminance(c):
    return (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) / 255


def _readable_text_on(c):
    return (40, 40, 40) if _luminance(c) > 0.6 else (255, 255, 255)


# ============================================================
# 描画
# ============================================================

def draw_decoration(draw, color):
    tint = _mix(color, (255, 255, 255), 0.10)
    draw.rectangle([MARGIN, MARGIN, CANVAS_SIZE - MARGIN, CANVAS_SIZE - MARGIN], fill=tint)
    fx0, fy0 = MARGIN + FRAME_INSET, MARGIN + FRAME_INSET
    fx1, fy1 = CANVAS_SIZE - MARGIN - FRAME_INSET, CANVAS_SIZE - MARGIN - FRAME_INSET
    draw.rectangle([fx0, fy0, fx1, fy1], outline=color, width=2)
    acc, w = 34, 5
    for cx, cy, dx, dy in [(fx0, fy0, 1, 1), (fx1, fy0, -1, 1), (fx0, fy1, 1, -1), (fx1, fy1, -1, -1)]:
        draw.line([(cx, cy), (cx + dx * acc, cy)], fill=color, width=w)
        draw.line([(cx, cy), (cx, cy + dy * acc)], fill=color, width=w)
    cx, cy, s = CANVAS_SIZE // 2, fy0, 9
    draw.polygon([(cx, cy - s), (cx + s, cy), (cx, cy + s), (cx - s, cy)], fill=color)


def draw_genre_label(draw, genre, color):
    font = ImageFont.truetype(FONT_SANS_BOLD, GENRE_FONT)
    tw = _measure(draw, genre, font)
    pad_x, pad_y = 24, 12
    th = sum(font.getmetrics())
    x1 = CANVAS_SIZE - MARGIN - FRAME_INSET - 10
    y1 = CANVAS_SIZE - MARGIN - FRAME_INSET - 10
    x0, y0 = x1 - (tw + pad_x * 2), y1 - (th + pad_y * 2)
    draw.rounded_rectangle([x0, y0, x1, y1], radius=(y1 - y0) // 2, fill=color)
    draw.text((x0 + pad_x, y0 + pad_y), genre, font=font, fill=_readable_text_on(color))


def draw_nickname(draw, nickname, color):
    font = ImageFont.truetype(FONT_SANS, NICKNAME_FONT)
    x0 = MARGIN + FRAME_INSET + 14
    th = sum(font.getmetrics())
    y1 = CANVAS_SIZE - MARGIN - FRAME_INSET - 22
    draw.text((x0, y1 - th), f"— {nickname}", font=font, fill=NICKNAME_COLOR)
    draw.text((x0, y1 - th), "—", font=font, fill=color)


def render_card(data):
    """思い出データ(dict) -> PIL Image"""
    genre = str(data.get("genre", "その他"))
    color = GENRE_COLORS.get(genre, DEFAULT_COLOR)
    memory = str(data.get("memory", "")).strip()
    nickname = str(data.get("nickname", "")).strip()

    img = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), BG_COLOR)
    draw = ImageDraw.Draw(img)
    draw_decoration(draw, color)

    text_left = MARGIN + FRAME_INSET + 60
    text_right = CANVAS_SIZE - MARGIN - FRAME_INSET - 60
    text_top = MARGIN + FRAME_INSET + 70
    text_bottom = CANVAS_SIZE - MARGIN - FRAME_INSET - 90
    area_w, area_h = text_right - text_left, text_bottom - text_top

    font, lines, total_h, line_h = fit_body_text(draw, memory, area_w, area_h)
    y = text_top + max(0, (area_h - total_h) // 2)
    for line in lines:
        x = text_left + (area_w - _measure(draw, line, font)) // 2
        draw.text((x, y), line, font=font, fill=BODY_COLOR)
        y += line_h

    draw_nickname(draw, nickname, color)
    draw_genre_label(draw, genre, color)
    return img


# ============================================================
# ファイル名 / サイドカー
# ============================================================

def _sanitize(s):
    s = str(s)
    for bad in '/\\:*?"<>|_ ':
        s = s.replace(bad, "")
    return s or "none"


def build_filename(data):
    """ジャンル_年代_ニックネーム_緯度_経度.png（緯度経度は末尾固定）"""
    genre = _sanitize(data.get("genre", "その他"))
    era = _sanitize(data.get("era", "不明"))
    nick = _sanitize(data.get("nickname", "noname"))
    lat = data.get("latitude", "")
    lng = data.get("longitude", "")
    return f"{genre}_{era}_{nick}_{lat}_{lng}.png"


def write_sidecar(png_path, data):
    """uploader.py が読むサイドカー .json（同名・lat/lon/name）を書く。"""
    sidecar = {
        "lat": data.get("latitude"),
        "lon": data.get("longitude"),
        "name": str(data.get("nickname", "")).strip() or os.path.splitext(os.path.basename(png_path))[0],
        "genre": data.get("genre"),
        "era": data.get("era"),
    }
    json_path = os.path.splitext(png_path)[0] + ".json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(sidecar, f, ensure_ascii=False, indent=2)
    return json_path


def generate(data, out_dir):
    """
    思い出データ(dict) からカードPNG＋サイドカーJSONを out_dir に生成。
    生成した PNG のパスを返す。
    サイドカーを先に書いてから PNG を書く（uploaderが取りこぼさない順序）。
    """
    os.makedirs(out_dir, exist_ok=True)
    png_path = os.path.join(out_dir, build_filename(data))
    write_sidecar(png_path, data)          # 先にサイドカー
    render_card(data).save(png_path, "PNG")  # 次にPNG（これが監視のトリガになる）
    return png_path


# ============================================================
# 単体CLI
# ============================================================

def main():
    p = argparse.ArgumentParser(description="思い出メッセージカード生成（単体）")
    p.add_argument("json", help="思い出JSON（1件のオブジェクト、または配列）")
    p.add_argument("-o", "--out", default="./outputs", help="出力ディレクトリ")
    args = p.parse_args()

    if not os.path.exists(args.json):
        print(f"ファイルが見つかりません: {args.json}", file=sys.stderr)
        sys.exit(1)

    with open(args.json, encoding="utf-8") as f:
        data = json.load(f)
    items = data if isinstance(data, list) else [data]
    for item in items:
        path = generate(item, args.out)
        print(f"生成しました: {path}")


if __name__ == "__main__":
    main()
