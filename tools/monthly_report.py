"""
Gerador de relatório mensal de metas.
Enviado automaticamente no dia 1 de cada mês para todos os admins com telegram_chat_id.
Também pode ser disparado manualmente via POST /cron/monthly-report.
"""
import logging
from calendar import monthrange
from datetime import date

from tools.supabase_client import (
    get_all_users, get_all_stores, get_meta_configs,
    get_sectors_for_meta, get_meta_summary,
)
from tools.telegram_client import send_text

logger = logging.getLogger(__name__)


def _prev_month(ref: date) -> tuple[date, date, str]:
    """Retorna (start, end, label) do mês anterior a ref."""
    month = ref.month - 1
    year = ref.year
    if month == 0:
        month = 12
        year -= 1
    last_day = monthrange(year, month)[1]
    start = date(year, month, 1)
    end = date(year, month, last_day)
    label = start.strftime("%B/%Y").capitalize()
    return start, end, label


def _build_store_report(store: dict, start_date: str, end_date: str, label: str) -> str:
    """Monta o bloco de texto do relatório para uma loja."""
    meta_configs = get_meta_configs(store["id"])
    if not meta_configs:
        return f"🏪 *{store['name']}*\nNenhuma meta configurada.\n"

    # Coleta todos os setores únicos das metas da loja
    sector_map: dict[int, dict] = {}
    for meta in meta_configs:
        for sector in get_sectors_for_meta(meta["id"]):
            sector_map[sector["id"]] = sector

    lines = [f"🏪 *{store['name']}* — {label}\n"]

    for sector in sorted(sector_map.values(), key=lambda s: s["name"]):
        lines.append(f"📍 *{sector['name']}*")
        has_any_meta = False
        for meta in meta_configs:
            # Verifica vínculo setor-meta
            from tools.supabase_client import get_client
            link = (
                get_client().table("bot_meta_sectors")
                .select("id")
                .eq("meta_config_id", meta["id"])
                .eq("sector_id", sector["id"])
                .execute()
            )
            if not link.data:
                continue
            has_any_meta = True
            records = get_meta_summary(meta["table_name"], meta["id"], start_date, end_date)
            count = sum(1 for r in records if r["sector_id"] == sector["id"])
            status = "✅" if count <= meta["target_value"] else "❌"
            plural = "ocorrência" if count == 1 else "ocorrências"
            lines.append(f"   {status} {meta['display_name']} (≤{meta['target_value']}): {count} {plural}")
        if not has_any_meta:
            lines.append("   _Sem metas vinculadas_")
        lines.append("")

    return "\n".join(lines)


async def send_monthly_reports(target_month: date | None = None) -> int:
    """
    Gera e envia o relatório do mês anterior para todos os admins.
    target_month: primeiro dia do mês a relatar (default: mês anterior ao atual).
    Retorna o número de admins notificados.
    """
    ref = target_month or date.today()
    start, end, label = _prev_month(ref)
    start_str = start.isoformat()
    end_str = end.isoformat()

    admins = [u for u in get_all_users() if u.get("is_admin") and u.get("telegram_chat_id")]
    if not admins:
        logger.warning("Nenhum admin com telegram_chat_id encontrado para o relatório mensal.")
        return 0

    stores = get_all_stores()

    header = f"📊 *Relatório Mensal — {label}*\nGerado automaticamente no dia 1.\n\n"

    for admin in admins:
        chat_id = admin["telegram_chat_id"]
        try:
            await send_text(chat_id, header)
            for store in stores:
                block = _build_store_report(store, start_str, end_str, label)
                await send_text(chat_id, block)
            logger.info(f"Relatório mensal enviado para {admin['name']} (chat_id={chat_id})")
        except Exception as e:
            logger.error(f"Erro ao enviar relatório para {admin['name']}: {e}")

    return len(admins)
