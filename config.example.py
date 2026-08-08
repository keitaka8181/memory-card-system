"""
config.example.py  —  設定テンプレート

【使い方】
1. このファイルを同じフォルダに config.py という名前でコピーする
       cp config.example.py config.py      (Windowsなら copy)
2. config.py を開いて、下の値を自分のものに書き換える
3. config.py は秘密情報を含むので、他人に見せたり Git にあげたりしないこと
   （.gitignore に config.py を入れてあります）
"""

# ============================================================
# 監視する思い出JSONファイル（このファイルが更新されたらカードを生成）
# ============================================================
# 1ファイルに「1件のオブジェクト」または「複数件の配列」を書ける。
# このファイルが保存・更新されるたびに、新しい思い出のカードが作られる。
MEMORY_JSON = "./memories.json"

# 生成したカード(PNG+サイドカーJSON)の出力先。
# uploader はこのフォルダを監視して R2 に送る。
OUTPUT_DIR = "./outputs"


# ============================================================
# R2(Cloudflare) 接続情報
# すべて「R2 API トークンを作成」時に表示された値を使う。
# ============================================================
# 形式: https://<アカウントID>.r2.cloudflarestorage.com
ENDPOINT_URL = "https://xxxxxxxxxxxxxxxx.r2.cloudflarestorage.com"

# アクセスキーID（トークン作成完了画面に表示）
ACCESS_KEY_ID = "ここにAccess Key IDを貼る"

# シークレットアクセスキー（作成直後の一度だけ表示。控え忘れたら再発行）
SECRET_ACCESS_KEY = "ここにSecret Access Keyを貼る"

# 自分で付けたバケット名（例: plateau-images）
BUCKET_NAME = "plateau-images"

# R2 上で画像を置くキーの接頭辞（変えなくてよい）
KEY_PREFIX = "images/"
