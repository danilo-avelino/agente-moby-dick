"""
WhatsApp Cloud API client.
Envia mensagens de texto, botões interativos e listas.

Limites da API:
  - Botões: máx 3 botões, título máx 20 chars
  - Lista: máx 10 itens total, título da linha máx 24 chars
  - Botão de abertura da lista: máx 20 chars
"""
import os
import logging
import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
_API_URL = f"https://graph.facebook.com/v19.0/{_PHONE_NUMBER_ID}/messages"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.getenv('WHATSAPP_TOKEN')}",
        "Content-Type": "application/json",
    }


async def send_text(to: str, text: str) -> None:
    """Envia mensagem de texto simples."""
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"body": text, "preview_url": False},
    }
    await _post(payload)


async def send_buttons(to: str, body: str, buttons: list[dict]) -> None:
    """
    Envia mensagem com botões de resposta rápida.
    buttons: [{"id": "btn_id", "title": "Texto"}]
    Máximo 3 botões, título truncado em 20 chars.
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": b["id"],
                            "title": b["title"][:20],
                        },
                    }
                    for b in buttons[:3]
                ]
            },
        },
    }
    await _post(payload)


async def send_list(
    to: str,
    body: str,
    button_text: str,
    sections: list[dict],
) -> None:
    """
    Envia mensagem com lista interativa.
    sections: [{"title": "Seção", "rows": [{"id": "...", "title": "...", "description": "..."}]}]
    Máximo 10 rows no total, título da row truncado em 24 chars.
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": body},
            "action": {
                "button": button_text[:20],
                "sections": sections,
            },
        },
    }
    await _post(payload)


async def _post(payload: dict) -> None:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(_API_URL, json=payload, headers=_headers())
        if response.status_code != 200:
            logger.error(
                f"WhatsApp API erro {response.status_code}: {response.text}"
            )
        else:
            logger.debug(f"Mensagem enviada para {payload.get('to')}")
