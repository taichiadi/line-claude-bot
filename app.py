import os
import hashlib
import hmac
import base64
from flask import Flask, request, abort
import anthropic
import requests

app = Flask(__name__)

LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
BOT_NAME = "事業相談Bot"

SYSTEM_PROMPT = """あなたは事業アイデアの壁打ち相手として参加しているAIアシスタントです。
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


def handle_message(event):
    user_message = event["message"]["text"]
    source_type = event["source"]["type"]

    if source_type == "group":
        if BOT_NAME not in user_message:
            return
        user_message = user_message.replace("@" + BOT_NAME, "").replace(BOT_NAME, "").strip()

    if not user_message:
        return

    reply_token = event["replyToken"]

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}]
        )
        ai_reply = response.content[0].text.strip()
    except Exception as e:
        print(f"Claude APIエラー: {e}")
        ai_reply = "エラーが発生しました。もう一度お試しください。"

    requests.post(
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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
