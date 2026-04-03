import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
import uvicorn
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from tools.conversation_handler import handle_message
from tools.telegram_client import answer_callback

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# SCHEDULER — relatório mensal automático
# ─────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from tools.monthly_report import send_monthly_reports

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_monthly_reports,
        CronTrigger(day=1, hour=8, minute=0),  # Todo dia 1 às 08:00
        id="monthly_report",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler iniciado — relatório mensal agendado para dia 1 às 08:00")
    yield
    scheduler.shutdown()


app = FastAPI(title="Agente das Metas", lifespan=lifespan)


# ─────────────────────────────────────────────────────────
# WEBHOOK TELEGRAM
# ─────────────────────────────────────────────────────────

@app.post("/webhook")
async def receive_update(request: Request):
    body = await request.json()

    try:
        # Clique em botão inline
        if "callback_query" in body:
            cq = body["callback_query"]
            chat_id = cq["message"]["chat"]["id"]
            text = cq["data"]
            await answer_callback(cq["id"])
            await handle_message(chat_id, text, "callback")

        # Mensagem de texto, contato ou foto
        elif "message" in body:
            msg = body["message"]
            chat_id = msg["chat"]["id"]

            if "contact" in msg:
                phone = msg["contact"]["phone_number"]
                await handle_message(chat_id, f"__contact__{phone}", "contact")
            elif "photo" in msg:
                photo_file_id = msg["photo"][-1]["file_id"]
                caption = msg.get("caption", "").strip()
                await handle_message(chat_id, caption, "photo", photo_file_id=photo_file_id)
            elif "text" in msg:
                await handle_message(chat_id, msg["text"].strip(), "text")
            else:
                await handle_message(chat_id, "", "unsupported")

    except Exception as e:
        logger.error(f"Erro ao processar update: {e}", exc_info=True)

    return {"ok": True}


# ─────────────────────────────────────────────────────────
# ENDPOINTS UTILITÁRIOS
# ─────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "running", "service": "Agente das Metas (Telegram)"}


@app.post("/cron/monthly-report")
async def trigger_monthly_report():
    """Dispara o relatório mensal manualmente (para testes)."""
    from tools.monthly_report import send_monthly_reports
    count = await send_monthly_reports()
    return {"ok": True, "admins_notified": count}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
