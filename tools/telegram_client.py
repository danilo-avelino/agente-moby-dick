"""
Cliente Telegram Bot API.
Substitui o whatsapp_client.py — mesma interface de send_text/send_buttons/send_list.
"""
import os
import logging
import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
_API = f"https://api.telegram.org/bot{_TOKEN}"


async def send_text(chat_id: int, text: str) -> None:
    await _post("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    })


async def send_buttons(chat_id: int, text: str, buttons: list[dict]) -> None:
    """
    buttons: [{"id": "btn_id", "title": "Texto"}]
    Exibe 2 botões por linha no teclado inline.
    """
    keyboard = []
    row = []
    for b in buttons:
        row.append({"text": b["title"], "callback_data": b["id"]})
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    await _post("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": {"inline_keyboard": keyboard},
    })


async def send_list(
    chat_id: int,
    text: str,
    button_text: str,
    sections: list[dict],
) -> None:
    """
    sections: [{"title": "...", "rows": [{"id": "...", "title": "..."}]}]
    Converte para teclado inline com um botão por linha.
    """
    keyboard = []
    for section in sections:
        for row in section.get("rows", []):
            keyboard.append([{"text": row["title"], "callback_data": row["id"]}])

    await _post("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": {"inline_keyboard": keyboard},
    })


async def request_phone(chat_id: int) -> None:
    """Solicita que o usuário compartilhe o número de telefone."""
    await _post("sendMessage", {
        "chat_id": chat_id,
        "text": "👋 Olá! Para acessar o sistema, compartilhe seu número de telefone:",
        "reply_markup": {
            "keyboard": [[{"text": "📱 Compartilhar meu número", "request_contact": True}]],
            "one_time_keyboard": True,
            "resize_keyboard": True,
        },
    })


async def remove_keyboard(chat_id: int) -> None:
    """Remove o teclado de resposta."""
    await _post("sendMessage", {
        "chat_id": chat_id,
        "text": "​",  # Zero-width space — mensagem invisível só para remover o teclado
        "reply_markup": {"remove_keyboard": True},
    })


async def answer_callback(callback_query_id: str) -> None:
    """Confirma o clique em botão inline (evita loading no Telegram)."""
    await _post("answerCallbackQuery", {"callback_query_id": callback_query_id})


def set_webhook(url: str) -> dict:
    """Configura o webhook do bot (chamada síncrona, usada no start.py)."""
    import httpx as _httpx
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    r = _httpx.post(
        f"https://api.telegram.org/bot{token}/setWebhook",
        json={"url": url, "allowed_updates": ["message", "callback_query"]},
        timeout=10,
    )
    return r.json()


async def _post(method: str, data: dict) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(f"{_API}/{method}", json=data)
        if response.status_code != 200:
            logger.error(f"Telegram API erro [{method}]: {response.text}")
        return response.json()
