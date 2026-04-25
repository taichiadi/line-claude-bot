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

conversation_history = {}

SYSTEM_PROMPT = """あなたは事業アイデアの壁打ち相手として参加しているAIアシスタントです。
2人の起業家がLINEグループで事業について議論しており、あなたはその議論に参加しています。
建設的なフィードバック、鋭い質問、市場分析、リスク指摘などを行いながら、
事業アイデアをより良くする手助けをしてください。
日本語で回答してください。回答は簡潔にまとめてください。"""


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
    reply_token = event["replyToken"]
    user_message = event["message"]["text"]
    chat_id = event["source"].get("groupId") or event["source"].get("userId")

    if chat_id not in conversation_history:
        conversation_history[chat_id] = []

    conversation_history[chat_id].append({
        "role": "user",
        "content": user_message
    })

    if len(conversation_history[chat_id]) > 20:
        conversation_history[chat_id] = conversation_history[chat_id][-20:]

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=conversation_history[chat_id]
    )

    ai_reply = response.content[0].text

    conversation_history[chat_id].append({
        "role": "assistant",
        "content": ai_reply
    })

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
