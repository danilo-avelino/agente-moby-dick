"""
Camada de acesso ao Supabase.
Todas as operações de banco de dados passam por aqui.
"""
import os
import re
import logging
from datetime import date
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL e SUPABASE_SERVICE_KEY são obrigatórios no .env")
        _client = create_client(url, key)
    return _client


# ─────────────────────────────────────────────────────────
# USUÁRIOS
# ─────────────────────────────────────────────────────────

def get_user(phone: str) -> dict | None:
    """Retorna usuário pelo telefone ou None se não autorizado."""
    result = get_client().table("bot_users").select("*").eq("phone", phone).execute()
    return result.data[0] if result.data else None


def get_all_users() -> list:
    result = get_client().table("bot_users").select("*").order("name").execute()
    return result.data


def add_user(phone: str, name: str, is_admin: bool, created_by: str) -> dict:
    result = (
        get_client()
        .table("bot_users")
        .insert({"phone": phone, "name": name, "is_admin": is_admin, "created_by": created_by})
        .execute()
    )
    return result.data[0]


def grant_store_access(phone: str, store_id: int) -> None:
    try:
        get_client().table("bot_user_store_access").insert(
            {"user_phone": phone, "store_id": store_id}
        ).execute()
    except Exception:
        pass  # Já tem acesso — ignora conflito


# ─────────────────────────────────────────────────────────
# LOJAS
# ─────────────────────────────────────────────────────────

def get_all_stores() -> list:
    result = get_client().table("bot_stores").select("*").order("name").execute()
    return result.data


def get_user_stores(phone: str) -> list:
    """Lojas que um usuário não-admin pode acessar."""
    result = (
        get_client()
        .table("bot_user_store_access")
        .select("store_id, bot_stores(id, name)")
        .eq("user_phone", phone)
        .execute()
    )
    return [r["bot_stores"] for r in result.data if r.get("bot_stores")]


def add_store(name: str) -> dict:
    result = get_client().table("bot_stores").insert({"name": name}).execute()
    return result.data[0]


# ─────────────────────────────────────────────────────────
# SETORES
# ─────────────────────────────────────────────────────────

def add_sectors(store_id: int, names: list[str]) -> list[dict]:
    """Cria vários setores de uma vez e retorna os registros inseridos."""
    rows = [{"store_id": store_id, "name": n.strip()} for n in names if n.strip()]
    if not rows:
        return []
    result = get_client().table("bot_sectors").insert(rows).execute()
    return result.data


def get_sectors_for_store(store_id: int) -> list:
    result = (
        get_client()
        .table("bot_sectors")
        .select("*")
        .eq("store_id", store_id)
        .order("name")
        .execute()
    )
    return result.data


def get_sectors_for_meta(meta_config_id: int) -> list:
    result = (
        get_client()
        .table("bot_meta_sectors")
        .select("sector_id, bot_sectors(id, name)")
        .eq("meta_config_id", meta_config_id)
        .execute()
    )
    return [r["bot_sectors"] for r in result.data if r.get("bot_sectors")]


# ─────────────────────────────────────────────────────────
# METAS
# ─────────────────────────────────────────────────────────

def get_meta_configs(store_id: int) -> list:
    result = (
        get_client()
        .table("bot_meta_configs")
        .select("*")
        .eq("store_id", store_id)
        .order("display_name")
        .execute()
    )
    return result.data


def get_meta_summary(table_name: str, meta_config_id: int, start_date: str, end_date: str | None = None) -> list:
    """Retorna todos os registros do período para contagem por setor."""
    q = (
        get_client()
        .table(table_name)
        .select("sector_id")
        .eq("meta_config_id", meta_config_id)
        .gte("occurrence_date", start_date)
    )
    if end_date:
        q = q.lte("occurrence_date", end_date)
    return q.execute().data


def get_sector_report(
    sector_id: int,
    meta_configs: list[dict],
    start_date: str,
    end_date: str,
) -> list[dict]:
    """
    Para um setor, retorna contagem de ocorrências de cada meta no período.
    Retorna: [{display_name, target_value, count, ok}, ...]
    """
    results = []
    client = get_client()
    for meta in meta_configs:
        # Verifica se este setor está vinculado à meta
        link = (
            client.table("bot_meta_sectors")
            .select("id")
            .eq("meta_config_id", meta["id"])
            .eq("sector_id", sector_id)
            .execute()
        )
        if not link.data:
            continue
        # Conta ocorrências do setor neste período
        records = (
            client.table(meta["table_name"])
            .select("id")
            .eq("meta_config_id", meta["id"])
            .eq("sector_id", sector_id)
            .gte("occurrence_date", start_date)
            .lte("occurrence_date", end_date)
            .execute()
        )
        count = len(records.data)
        results.append({
            "display_name": meta["display_name"],
            "target_value": meta["target_value"],
            "count": count,
            "ok": count <= meta["target_value"],
        })
    return results


def add_occurrence(
    table_name: str,
    meta_config_id: int,
    sector_id: int,
    reported_by: str,
    notes: str | None = None,
    photo_file_id: str | None = None,
) -> None:
    get_client().table(table_name).insert(
        {
            "meta_config_id": meta_config_id,
            "sector_id": sector_id,
            "reported_by": reported_by,
            "occurrence_date": date.today().isoformat(),
            "notes": notes,
            "photo_file_id": photo_file_id,
        }
    ).execute()


def update_user_chat_id(phone: str, chat_id: int) -> None:
    """Salva o telegram_chat_id do usuário para envio de relatórios."""
    get_client().table("bot_users").update(
        {"telegram_chat_id": chat_id}
    ).eq("phone", phone).execute()


# ─────────────────────────────────────────────────────────
# EXCLUSÕES (Admin)
# ─────────────────────────────────────────────────────────

def link_sector_to_meta(meta_config_id: int, sector_id: int) -> None:
    try:
        get_client().table("bot_meta_sectors").insert(
            {"meta_config_id": meta_config_id, "sector_id": sector_id}
        ).execute()
    except Exception:
        pass  # Já vinculado — ignora conflito


def unlink_sector_from_meta(meta_config_id: int, sector_id: int) -> None:
    get_client().table("bot_meta_sectors").delete()\
        .eq("meta_config_id", meta_config_id)\
        .eq("sector_id", sector_id)\
        .execute()


def update_meta_target(meta_config_id: int, new_target: int) -> None:
    get_client().table("bot_meta_configs").update(
        {"target_value": new_target}
    ).eq("id", meta_config_id).execute()


def delete_user(phone: str) -> None:
    get_client().table("bot_user_store_access").delete().eq("user_phone", phone).execute()
    get_client().table("bot_users").delete().eq("phone", phone).execute()


def delete_meta_config(meta_config_id: int, table_name: str) -> None:
    import psycopg
    get_client().table("bot_meta_sectors").delete().eq("meta_config_id", meta_config_id).execute()
    get_client().table("bot_meta_configs").delete().eq("id", meta_config_id).execute()
    db_url = os.getenv("SUPABASE_DB_URL")
    if db_url and table_name.startswith("bot_records_"):
        with psycopg.connect(db_url) as conn:
            conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
            conn.commit()


def delete_store(store_id: int) -> None:
    metas = get_client().table("bot_meta_configs").select("id").eq("store_id", store_id).execute().data
    for meta in metas:
        get_client().table("bot_meta_sectors").delete().eq("meta_config_id", meta["id"]).execute()
    get_client().table("bot_meta_configs").delete().eq("store_id", store_id).execute()
    sectors = get_client().table("bot_sectors").select("id").eq("store_id", store_id).execute().data
    for sector in sectors:
        get_client().table("bot_meta_sectors").delete().eq("sector_id", sector["id"]).execute()
    get_client().table("bot_sectors").delete().eq("store_id", store_id).execute()
    get_client().table("bot_user_store_access").delete().eq("store_id", store_id).execute()
    get_client().table("bot_stores").delete().eq("id", store_id).execute()


def delete_sector(sector_id: int) -> None:
    get_client().table("bot_meta_sectors").delete().eq("sector_id", sector_id).execute()
    get_client().table("bot_sectors").delete().eq("id", sector_id).execute()


def get_recent_occurrences(table_name: str, meta_config_id: int, sector_id: int, limit: int = 10) -> list[dict]:
    result = (
        get_client()
        .table(table_name)
        .select("id, occurrence_date, reported_by, notes")
        .eq("meta_config_id", meta_config_id)
        .eq("sector_id", sector_id)
        .order("occurrence_date", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


def delete_occurrence(table_name: str, record_id: int) -> None:
    get_client().table(table_name).delete().eq("id", record_id).execute()


def get_all_meta_configs_with_store() -> list[dict]:
    result = (
        get_client()
        .table("bot_meta_configs")
        .select("*, bot_stores(id, name)")
        .order("display_name")
        .execute()
    )
    return result.data


def create_new_meta(
    store_id: int,
    name: str,
    target_value: int,
    created_by: str,
    sector_ids: list[int],
) -> tuple[bool, str, str | None]:
    """
    Cria configuração de meta e tabela de registros.
    Retorna (sucesso, nome_da_tabela, mensagem_de_erro).
    """
    slug = re.sub(r"[^a-z0-9]", "_", name.lower()).strip("_")
    table_name = f"bot_records_{slug}"

    try:
        # Cria tabela via função armazenada no Postgres
        get_client().rpc("create_records_table", {"p_table_name": table_name}).execute()

        # Salva configuração
        result = (
            get_client()
            .table("bot_meta_configs")
            .insert(
                {
                    "store_id": store_id,
                    "name": slug,
                    "display_name": name,
                    "target_value": target_value,
                    "comparison": "lte",
                    "table_name": table_name,
                    "created_by": created_by,
                }
            )
            .execute()
        )
        meta_id = result.data[0]["id"]

        # Associa setores
        if sector_ids:
            get_client().table("bot_meta_sectors").insert(
                [{"meta_config_id": meta_id, "sector_id": sid} for sid in sector_ids]
            ).execute()

        return True, table_name, None

    except Exception as e:
        logger.error(f"Erro ao criar meta '{name}': {e}")
        return False, "", str(e)
