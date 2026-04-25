import os
import hashlib
import hmac
import base64
from flask import Flask, request, abort
import anthropic
import requests
from supabase import create_client

app = Flask(__name__)

LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

SYSTEM_PROMPT = """あなたは事業アイデアの壁打ち相手として参加しているAIアシスタントです。
2人の起業家がLINEグループで事業について議論しており、あなたはその議論に参加しています。
建設的なフィードバック、鋭い質問、市場分析、リスク指摘などを行いながら、
事業アイデアをより良くする手助けをしてください。
日本語で回答してください。回答は簡潔にまとめてください。"""


@app.route("/")
def health():
    return "OK"


@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    hash_value = hmac.new(
        LINE_CHANNEL_SECRET.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256
    ).digest()
    expected = base64.b64encode(hash_value).decode("utf-8")

    if not hmac.compare_digest(signature, expected):
        abort(400)

    data = request.json
    for event in data.get("events", []):
        if event["type"] == "message" and event["message"]["type"] == "text":
            handle_message(event)

    return "OK"


def get_history(chat_id):
    result = supabase.table("conversations")\
        .select("role,content")\
        .eq("chat_id", chat_id)\
        .order("created_at")\
        .limit(20)\
        .execute()
    return [{"role": r["role"], "content": r["content"]} for r in result.data]


def save_message(chat_id, role, content):
    supabase.table("conversations").insert({
        "chat_id": chat_id,
        "role": role,
        "content": content
    }).execute()


def handle_message(event):
    reply_token = event["replyToken"]
    user_message = event["message"]["text"]
    chat_id = event["source"].get("groupId") or event["source"].get("userId")

    save_message(chat_id, "user", user_message)
    history = get_history(chat_id)

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=history
        )
        ai_reply = response.content[0].text
    except Exception as e:
        print(f"Claude APIエラー: {e}")
        ai_reply = f"エラーが発生しました: {e}"

    save_message(chat_id, "assistant", ai_reply)

    result = requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers={
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        },
        json={
            "replyToken": reply_token,
            "messages": [{"type": "text", "text": ai_reply}]
        }
    )
    print(f"LINE返信結果: {result.status_code} {result.text}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
