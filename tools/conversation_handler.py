"""
Máquina de estados para conversas do Telegram.
Sessões indexadas por chat_id (int). Telefone obtido via contato compartilhado.

Estados:
  awaiting_phone
  main_menu
  view_select_store | view_select_meta
  apontar_select_store | apontar_select_meta | apontar_select_sector | apontar_confirm
  admin_menu
  add_user_phone | add_user_name | add_user_role | add_user_store
  add_meta_store | add_meta_name | add_meta_target | add_meta_sectors
  add_store_name
"""
import logging
from datetime import datetime, date

from tools.telegram_client import (
    send_text, send_buttons, send_list,
    request_phone, remove_keyboard,
)
from tools.supabase_client import (
    get_user, get_all_users, get_all_stores, get_user_stores,
    get_meta_configs, get_sectors_for_meta, get_sectors_for_store,
    get_meta_summary, get_sector_report, add_occurrence,
    add_user, grant_store_access, create_new_meta, add_store, add_sectors,
    update_user_chat_id,
    delete_user, delete_meta_config, delete_store, delete_sector,
    get_recent_occurrences, delete_occurrence, get_all_meta_configs_with_store,
)

logger = logging.getLogger(__name__)

# Sessões: chat_id -> {state, data, updated_at}
_sessions: dict[int, dict] = {}
SESSION_TIMEOUT_SECONDS = 30 * 60

_RESET_KEYWORDS = {"/start", "/menu", "menu", "início", "inicio", "oi", "olá", "ola"}


# ─────────────────────────────────────────────────────────
# GESTÃO DE SESSÃO
# ─────────────────────────────────────────────────────────

def _get_session(chat_id: int) -> dict:
    session = _sessions.get(chat_id)
    if not session:
        return {}
    elapsed = (datetime.now() - session["updated_at"]).total_seconds()
    if elapsed > SESSION_TIMEOUT_SECONDS:
        del _sessions[chat_id]
        return {}
    return session


def _set_session(chat_id: int, state: str, data: dict | None = None) -> None:
    prev_data = _sessions.get(chat_id, {}).get("data", {})
    merged = {**prev_data, **(data or {})}
    _sessions[chat_id] = {"state": state, "data": merged, "updated_at": datetime.now()}


def _set_session_clean(chat_id: int, state: str, data: dict | None = None) -> None:
    """Versão que NÃO herda dados anteriores (para transições limpas)."""
    phone = _sessions.get(chat_id, {}).get("data", {}).get("phone")
    base = {"phone": phone} if phone else {}
    _sessions[chat_id] = {
        "state": state,
        "data": {**base, **(data or {})},
        "updated_at": datetime.now(),
    }


def _clear_session(chat_id: int) -> None:
    _sessions.pop(chat_id, None)


# ─────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────

async def handle_message(chat_id: int, text: str, msg_type: str, photo_file_id: str | None = None) -> None:
    try:
        # Contato compartilhado → verificação de telefone
        if text.startswith("__contact__"):
            phone = text.replace("__contact__", "").replace("+", "").replace(" ", "")
            await _handle_phone_verification(chat_id, phone)
            return

        session = _get_session(chat_id)
        state = session.get("state", "start")
        data = session.get("data", {})
        phone = data.get("phone")

        # Sem telefone verificado → solicitar
        if not phone:
            if state != "awaiting_phone":
                await request_phone(chat_id)
                _set_session_clean(chat_id, "awaiting_phone")
            else:
                await send_text(chat_id, "Por favor, use o botão abaixo para compartilhar seu número.")
                await request_phone(chat_id)
            return

        # Telefone verificado → buscar usuário
        user = get_user(phone)
        if not user:
            await send_text(
                chat_id,
                "⛔ *Acesso restrito.*\n\n"
                "Seu número não está autorizado.\n"
                "Entre em contato com um administrador.",
            )
            _clear_session(chat_id)
            return

        # Escape universal
        if text.lower() in _RESET_KEYWORDS:
            await show_main_menu(chat_id, user)
            return

        # Tipos não suportados
        if msg_type == "unsupported":
            await send_text(chat_id, "⚠️ Use apenas texto ou os botões do menu.")
            return

        # Roteamento por estado
        handlers = {
            "start":                 lambda: show_main_menu(chat_id, user),
            "main_menu":             lambda: handle_main_menu(chat_id, user, text),
            "view_select_store":     lambda: handle_view_select_store(chat_id, user, text, data),
            "view_select_meta":      lambda: handle_view_select_meta(chat_id, user, text, data),
            "apontar_select_store":  lambda: handle_apontar_select_store(chat_id, user, text, data),
            "apontar_select_meta":   lambda: handle_apontar_select_meta(chat_id, user, text, data),
            "apontar_select_sector": lambda: handle_apontar_select_sector(chat_id, user, text, data),
            "apontar_confirm":         lambda: handle_apontar_confirm(chat_id, user, text, data),
            "apontar_extras":          lambda: handle_apontar_extras(chat_id, user, text, data),
            "apontar_extras_waiting":  lambda: handle_apontar_extras_waiting(chat_id, user, text, data, msg_type, photo_file_id),
            "report_select_store":     lambda: handle_report_select_store(chat_id, user, text, data),
            "report_select_period":    lambda: handle_report_select_period(chat_id, user, text, data),
            "report_select_sector":    lambda: handle_report_select_sector(chat_id, user, text, data),
            "admin_menu":              lambda: handle_admin_menu(chat_id, user, text),
            "general_report_period": lambda: handle_general_report_period(chat_id, user, text, data),
            "del_user_select":       lambda: handle_delete_user_select(chat_id, user, text, data),
            "del_user_confirm":      lambda: handle_delete_user_confirm(chat_id, user, text, data),
            "del_meta_select":       lambda: handle_delete_meta_select(chat_id, user, text, data),
            "del_meta_confirm":      lambda: handle_delete_meta_confirm(chat_id, user, text, data),
            "del_store_select":      lambda: handle_delete_store_select(chat_id, user, text, data),
            "del_store_confirm":     lambda: handle_delete_store_confirm(chat_id, user, text, data),
            "del_sector_store":      lambda: handle_delete_sector_store(chat_id, user, text, data),
            "del_sector_select":     lambda: handle_delete_sector_select(chat_id, user, text, data),
            "del_sector_confirm":    lambda: handle_delete_sector_confirm(chat_id, user, text, data),
            "del_occ_store":         lambda: handle_delete_occ_store(chat_id, user, text, data),
            "del_occ_meta":          lambda: handle_delete_occ_meta(chat_id, user, text, data),
            "del_occ_sector":        lambda: handle_delete_occ_sector(chat_id, user, text, data),
            "del_occ_list":          lambda: handle_delete_occ_list(chat_id, user, text, data),
            "del_occ_confirm":       lambda: handle_delete_occ_confirm(chat_id, user, text, data),
            "add_user_phone":        lambda: handle_add_user_phone(chat_id, user, text, data),
            "add_user_name":         lambda: handle_add_user_name(chat_id, user, text, data),
            "add_user_role":         lambda: handle_add_user_role(chat_id, user, text, data),
            "add_user_store":        lambda: handle_add_user_store(chat_id, user, text, data),
            "add_meta_store":        lambda: handle_add_meta_store(chat_id, user, text, data),
            "add_meta_name":         lambda: handle_add_meta_name(chat_id, user, text, data),
            "add_meta_target":       lambda: handle_add_meta_target(chat_id, user, text, data),
            "add_meta_sectors":      lambda: handle_add_meta_sectors(chat_id, user, text, data),
            "add_meta_new_sectors":  lambda: handle_add_meta_new_sectors(chat_id, user, text, data),
            "add_store_name":        lambda: handle_add_store_name(chat_id, user, text, data),
            "awaiting_phone":        lambda: request_phone(chat_id),
        }

        handler = handlers.get(state)
        if handler:
            await handler()
        else:
            await show_main_menu(chat_id, user)

    except Exception as e:
        logger.error(f"Erro ao processar mensagem de chat_id={chat_id}: {e}", exc_info=True)
        await send_text(chat_id, "❌ Ocorreu um erro inesperado. Digite /menu para recomeçar.")
        _clear_session(chat_id)


async def _handle_phone_verification(chat_id: int, phone: str) -> None:
    user = get_user(phone)
    if not user:
        await send_text(
            chat_id,
            "⛔ *Acesso restrito.*\n\n"
            "Seu número não está autorizado.\n"
            "Entre em contato com um administrador.",
        )
        return
    # Salva chat_id para envio de relatórios mensais
    update_user_chat_id(phone, chat_id)
    _set_session_clean(chat_id, "start", {"phone": phone})
    await show_main_menu(chat_id, user)


# ─────────────────────────────────────────────────────────
# MENU PRINCIPAL
# ─────────────────────────────────────────────────────────

async def show_main_menu(chat_id: int, user: dict) -> None:
    first_name = user.get("name", "").split()[0] or "!"
    is_admin = user.get("is_admin", False)

    greeting = (
        f"Olá, *{first_name}*! 👋\n\n"
        "O que deseja fazer?"
        + ("\n\n_Você tem acesso de administrador._" if is_admin else "")
    )

    # Menu como lista para suportar todas as opções sem limite de 3 botões
    rows = [
        {"id": "ver_metas",  "title": "📊 Ver Metas",          "description": "Resumo por meta e setor"},
        {"id": "relatorio",  "title": "📋 Relatório por Setor", "description": "Histórico dos últimos meses"},
    ]
    if is_admin:
        rows += [
            {"id": "apontar",    "title": "📝 Apontar",     "description": "Registrar ocorrência"},
            {"id": "admin_menu", "title": "⚙️ Admin",       "description": "Usuários, metas e lojas"},
        ]

    await send_list(chat_id, greeting, "Ver opções", [{"title": "Menu", "rows": rows}])
    _set_session_clean(chat_id, "main_menu")


async def handle_main_menu(chat_id: int, user: dict, text: str) -> None:
    is_admin = user.get("is_admin", False)
    if text == "ver_metas":
        await start_view_metas(chat_id, user)
    elif text == "relatorio":
        await start_report(chat_id, user)
    elif text == "apontar" and is_admin:
        await start_apontar(chat_id, user)
    elif text == "admin_menu" and is_admin:
        await show_admin_menu(chat_id, user)
    else:
        await show_main_menu(chat_id, user)


# ─────────────────────────────────────────────────────────
# FLUXO: VER METAS
# ─────────────────────────────────────────────────────────

async def start_view_metas(chat_id: int, user: dict) -> None:
    stores = get_all_stores() if user.get("is_admin") else get_user_stores(user["phone"])
    if not stores:
        await send_text(chat_id, "⚠️ Você não tem acesso a nenhuma loja ainda.")
        await show_main_menu(chat_id, user)
        return
    if len(stores) == 1:
        await _show_meta_type_list(chat_id, user, stores[0], "view")
        return
    rows = [{"id": f"store_{s['id']}", "title": s["name"]} for s in stores]
    await send_list(chat_id, "📊 *Verificar Metas*\n\nSelecione a loja:", "Ver lojas",
                    [{"title": "Lojas", "rows": rows}])
    _set_session_clean(chat_id, "view_select_store", {"stores": stores})


async def handle_view_select_store(chat_id: int, user: dict, text: str, data: dict) -> None:
    store = _find_store(text, data.get("stores", []))
    if not store:
        await send_text(chat_id, "Por favor, selecione uma loja.")
        return
    await _show_meta_type_list(chat_id, user, store, "view")


async def handle_view_select_meta(chat_id: int, user: dict, text: str, data: dict) -> None:
    meta = _find_item(text, data.get("meta_configs", []), "meta_")
    if not meta:
        await send_text(chat_id, "Por favor, selecione uma meta.")
        return
    await _send_meta_summary(chat_id, user, data.get("store", {}), meta)


async def _send_meta_summary(chat_id: int, user: dict, store: dict, meta: dict) -> None:
    sectors = get_sectors_for_meta(meta["id"])
    today = date.today()
    start_of_month = date(today.year, today.month, 1).isoformat()
    records = get_meta_summary(meta["table_name"], meta["id"], start_of_month)

    count_map: dict[int, int] = {}
    for r in records:
        sid = r["sector_id"]
        count_map[sid] = count_map.get(sid, 0) + 1

    target = meta["target_value"]
    month_label = today.strftime("%B/%Y").capitalize()

    lines = [
        f"📊 *{meta['display_name']} — {store['name']}*",
        f"Período: {month_label}  |  Meta: ≤{target} ocorrência(s)\n",
    ]
    for sector in sectors:
        count = count_map.get(sector["id"], 0)
        status = "✅" if count <= target else "❌"
        lines.append(f"{status} {sector['name']}: *{count}*")

    await send_text(chat_id, "\n".join(lines))
    await send_buttons(chat_id, "O que deseja fazer agora?", [
        {"id": "ver_metas",      "title": "📊 Ver outra meta"},
        {"id": "menu_principal", "title": "🏠 Menu principal"},
    ])
    _set_session_clean(chat_id, "main_menu")


# ─────────────────────────────────────────────────────────
# FLUXO: APONTAR INDICADOR (admin)
# ─────────────────────────────────────────────────────────

async def start_apontar(chat_id: int, user: dict) -> None:
    stores = get_all_stores()
    if len(stores) == 1:
        await _show_meta_type_list(chat_id, user, stores[0], "apontar")
        return
    rows = [{"id": f"store_{s['id']}", "title": s["name"]} for s in stores]
    await send_list(chat_id, "📝 *Apontar Indicador*\n\nSelecione a loja:", "Ver lojas",
                    [{"title": "Lojas", "rows": rows}])
    _set_session_clean(chat_id, "apontar_select_store", {"stores": stores})


async def handle_apontar_select_store(chat_id: int, user: dict, text: str, data: dict) -> None:
    store = _find_store(text, data.get("stores", []))
    if not store:
        await send_text(chat_id, "Por favor, selecione uma loja.")
        return
    await _show_meta_type_list(chat_id, user, store, "apontar")


async def handle_apontar_select_meta(chat_id: int, user: dict, text: str, data: dict) -> None:
    meta = _find_item(text, data.get("meta_configs", []), "meta_")
    if not meta:
        await send_text(chat_id, "Por favor, selecione uma meta.")
        return
    sectors = get_sectors_for_meta(meta["id"])
    if not sectors:
        await send_text(chat_id, "⚠️ Esta meta não tem setores configurados.")
        await show_main_menu(chat_id, user)
        return
    rows = [{"id": f"sector_{s['id']}", "title": s["name"]} for s in sectors]
    store = data.get("store", {})
    await send_list(chat_id,
                    f"📝 *{meta['display_name']} — {store['name']}*\n\nEm qual setor ocorreu?",
                    "Ver setores", [{"title": "Setores", "rows": rows}])
    _set_session_clean(chat_id, "apontar_select_sector",
                       {"store": store, "meta": meta, "sectors": sectors})


async def handle_apontar_select_sector(chat_id: int, user: dict, text: str, data: dict) -> None:
    sector = _find_item(text, data.get("sectors", []), "sector_")
    if not sector:
        await send_text(chat_id, "Por favor, selecione um setor.")
        return
    meta = data.get("meta", {})
    store = data.get("store", {})
    await send_buttons(chat_id,
        f"📝 *Confirmar apontamento*\n\n"
        f"Loja: {store['name']}\n"
        f"Meta: {meta['display_name']}\n"
        f"Setor: {sector['name']}\n"
        f"Data: {date.today().strftime('%d/%m/%Y')}\n\n"
        f"Confirma o registro?",
        [{"id": "confirm_yes", "title": "✅ Confirmar"},
         {"id": "confirm_no",  "title": "❌ Cancelar"}])
    _set_session_clean(chat_id, "apontar_confirm", {"store": store, "meta": meta, "sector": sector})


async def handle_apontar_confirm(chat_id: int, user: dict, text: str, data: dict) -> None:
    if text == "confirm_yes":
        await send_buttons(chat_id,
            "Deseja adicionar foto ou observação?",
            [{"id": "extras_sim", "title": "📎 Sim"},
             {"id": "extras_nao", "title": "❌ Não"}])
        _set_session_clean(chat_id, "apontar_extras")
    else:
        await send_text(chat_id, "❌ Apontamento cancelado.")
        await show_main_menu(chat_id, user)


async def handle_apontar_extras(chat_id: int, user: dict, text: str, data: dict) -> None:
    if text == "extras_sim":
        await send_text(chat_id,
            "📎 Envie a *foto* e/ou *observação* em uma mensagem.\n"
            "_(Pode ser só texto, só foto ou foto com legenda)_")
        _set_session_clean(chat_id, "apontar_extras_waiting")
    else:
        meta, sector = data["meta"], data["sector"]
        add_occurrence(meta["table_name"], meta["id"], sector["id"], user["phone"])
        await _apontar_success(chat_id, user, meta, sector)


async def handle_apontar_extras_waiting(
    chat_id: int, user: dict, text: str, data: dict,
    msg_type: str, photo_file_id: str | None,
) -> None:
    if msg_type not in ("text", "photo"):
        await send_text(chat_id, "⚠️ Envie texto e/ou foto.")
        return
    meta, sector = data["meta"], data["sector"]
    notes = text if text else None
    add_occurrence(
        meta["table_name"], meta["id"], sector["id"], user["phone"],
        notes=notes, photo_file_id=photo_file_id,
    )
    await _apontar_success(chat_id, user, meta, sector, notes=notes, has_photo=bool(photo_file_id))


async def _apontar_success(
    chat_id: int, user: dict, meta: dict, sector: dict,
    notes: str | None = None, has_photo: bool = False,
) -> None:
    extras = ""
    if notes:
        extras += f"\nObservação: _{notes}_"
    if has_photo:
        extras += "\nFoto: ✅ salva"
    await send_text(chat_id,
        f"✅ *Apontamento registrado!*\n\n"
        f"Meta: {meta['display_name']}\n"
        f"Setor: {sector['name']}\n"
        f"Data: {date.today().strftime('%d/%m/%Y')}{extras}")
    await send_buttons(chat_id, "O que deseja fazer agora?", [
        {"id": "apontar",        "title": "📝 Apontar outro"},
        {"id": "ver_metas",      "title": "📊 Ver Metas"},
        {"id": "menu_principal", "title": "🏠 Menu principal"},
    ])
    _set_session_clean(chat_id, "main_menu")


# ─────────────────────────────────────────────────────────
# MENU ADMIN
# ─────────────────────────────────────────────────────────

async def show_admin_menu(chat_id: int, user: dict) -> None:
    await send_list(chat_id, "⚙️ *Menu Administrativo*\n\nSelecione uma opção:", "Ver opções", [
        {"title": "Usuários", "rows": [
            {"id": "add_user",   "title": "👤 Cadastrar usuário"},
            {"id": "list_users", "title": "📋 Listar usuários"},
            {"id": "del_user",   "title": "🗑️ Excluir usuário"},
        ]},
        {"title": "Metas e Lojas", "rows": [
            {"id": "add_meta",   "title": "➕ Nova meta"},
            {"id": "add_store",  "title": "🏪 Nova loja"},
            {"id": "del_meta",   "title": "🗑️ Excluir meta"},
            {"id": "del_store",  "title": "🗑️ Excluir loja"},
        ]},
        {"title": "Setores e Apontamentos", "rows": [
            {"id": "del_sector",     "title": "🗑️ Excluir setor"},
            {"id": "del_occurrence", "title": "🗑️ Excluir apontamento"},
        ]},
        {"title": "Relatórios", "rows": [
            {"id": "general_report", "title": "📊 Relatório Geral"},
        ]},
        {"title": "Navegação", "rows": [
            {"id": "menu_principal", "title": "🏠 Menu principal"},
        ]},
    ])
    _set_session_clean(chat_id, "admin_menu")


async def handle_admin_menu(chat_id: int, user: dict, text: str) -> None:
    routes = {
        "add_user":       lambda: start_add_user(chat_id, user),
        "list_users":     lambda: show_users_list(chat_id, user),
        "add_meta":       lambda: start_add_meta(chat_id, user),
        "add_store":      lambda: start_add_store(chat_id, user),
        "del_user":       lambda: start_delete_user(chat_id, user),
        "del_meta":       lambda: start_delete_meta(chat_id, user),
        "del_store":      lambda: start_delete_store(chat_id, user),
        "del_sector":     lambda: start_delete_sector(chat_id, user),
        "del_occurrence": lambda: start_delete_occurrence(chat_id, user),
        "general_report": lambda: start_general_report(chat_id, user),
        "menu_principal": lambda: show_main_menu(chat_id, user),
    }
    handler = routes.get(text)
    if handler:
        await handler()
    else:
        await show_admin_menu(chat_id, user)


# ─────────────────────────────────────────────────────────
# FLUXO: CADASTRAR USUÁRIO
# ─────────────────────────────────────────────────────────

async def start_add_user(chat_id: int, user: dict) -> None:
    await send_text(chat_id,
        "👤 *Cadastrar novo usuário*\n\n"
        "Digite o número de telefone com código do país e DDD:\n"
        "Exemplo: *5586999999999*\n\n"
        "Digite *cancelar* para voltar.")
    _set_session_clean(chat_id, "add_user_phone")


async def handle_add_user_phone(chat_id: int, user: dict, text: str, data: dict) -> None:
    if text.lower() == "cancelar":
        await show_admin_menu(chat_id, user)
        return
    clean = text.strip().replace("+", "").replace(" ", "").replace("-", "")
    if not clean.isdigit() or len(clean) < 10:
        await send_text(chat_id, "❌ Número inválido. Use o formato: *5586999999999*")
        return
    existing = get_user(clean)
    if existing:
        await send_text(chat_id, f"⚠️ O número *{clean}* já está cadastrado como *{existing['name']}*.")
        await show_admin_menu(chat_id, user)
        return
    await send_text(chat_id, f"✅ Número: *{clean}*\n\nQual é o *nome completo* deste usuário?")
    _set_session_clean(chat_id, "add_user_name", {"new_phone": clean})


async def handle_add_user_name(chat_id: int, user: dict, text: str, data: dict) -> None:
    if text.lower() == "cancelar":
        await show_admin_menu(chat_id, user)
        return
    name = text.strip()
    if len(name) < 2:
        await send_text(chat_id, "❌ Nome muito curto. Digite o nome completo:")
        return
    await send_buttons(chat_id, f"👤 *{name}*\n\nEste usuário será administrador?", [
        {"id": "role_admin", "title": "✅ Sim, admin"},
        {"id": "role_user",  "title": "👤 Não, usuário"},
    ])
    _set_session_clean(chat_id, "add_user_role", {**data, "new_name": name})


async def handle_add_user_role(chat_id: int, user: dict, text: str, data: dict) -> None:
    if text not in ("role_admin", "role_user"):
        await send_text(chat_id, "Por favor, selecione uma das opções.")
        return
    is_admin = text == "role_admin"
    stores = get_all_stores()
    rows = [{"id": f"store_{s['id']}", "title": s["name"]} for s in stores]
    rows.append({"id": "store_all", "title": "🏪 Todas as lojas"})
    role_label = "Administrador" if is_admin else "Usuário"
    await send_list(chat_id,
        f"👤 *{data['new_name']}* ({role_label})\n\nQual loja este usuário pode acessar?",
        "Ver lojas", [{"title": "Lojas", "rows": rows}])
    _set_session_clean(chat_id, "add_user_store", {**data, "is_admin": is_admin, "stores": stores})


async def handle_add_user_store(chat_id: int, user: dict, text: str, data: dict) -> None:
    stores = data.get("stores", [])
    new_phone = data["new_phone"]
    new_name = data["new_name"]
    is_admin = data["is_admin"]

    if text == "store_all":
        store_ids = [s["id"] for s in stores]
        stores_label = "Todas as lojas"
    elif text.startswith("store_"):
        store = _find_store(text, stores)
        if not store:
            await send_text(chat_id, "Por favor, selecione uma loja da lista.")
            return
        store_ids = [store["id"]]
        stores_label = store["name"]
    else:
        await send_text(chat_id, "Por favor, selecione uma loja da lista.")
        return

    add_user(new_phone, new_name, is_admin, user["phone"])
    for sid in store_ids:
        grant_store_access(new_phone, sid)

    role_label = "administrador" if is_admin else "usuário"
    await send_text(chat_id,
        f"✅ *Usuário cadastrado!*\n\n"
        f"Nome: {new_name}\n"
        f"Telefone: {new_phone}\n"
        f"Perfil: {role_label}\n"
        f"Lojas: {stores_label}")
    await show_admin_menu(chat_id, user)


async def show_users_list(chat_id: int, user: dict) -> None:
    users = get_all_users()
    if not users:
        await send_text(chat_id, "📋 Nenhum usuário cadastrado ainda.")
    else:
        lines = ["📋 *Usuários cadastrados:*\n"]
        for u in users:
            role = "👑 Admin" if u.get("is_admin") else "👤 Usuário"
            lines.append(f"• *{u['name']}* — {u['phone']} — {role}")
        await send_text(chat_id, "\n".join(lines))
    await show_admin_menu(chat_id, user)


# ─────────────────────────────────────────────────────────
# FLUXO: ADICIONAR NOVA META
# ─────────────────────────────────────────────────────────

async def start_add_meta(chat_id: int, user: dict) -> None:
    stores = get_all_stores()
    rows = [{"id": f"store_{s['id']}", "title": s["name"]} for s in stores]
    await send_list(chat_id, "➕ *Nova Meta*\n\nPara qual loja?", "Ver lojas",
                    [{"title": "Lojas", "rows": rows}])
    _set_session_clean(chat_id, "add_meta_store", {"stores": stores})


async def handle_add_meta_store(chat_id: int, user: dict, text: str, data: dict) -> None:
    store = _find_store(text, data.get("stores", []))
    if not store:
        await send_text(chat_id, "Por favor, selecione uma loja.")
        return
    await send_text(chat_id,
        f"➕ *Nova Meta — {store['name']}*\n\n"
        "Qual é o *nome* desta meta?\n_(Ex: Limpeza, Atendimento)_\n\n"
        "Digite *cancelar* para voltar.")
    _set_session_clean(chat_id, "add_meta_name", {"store": store})


async def handle_add_meta_name(chat_id: int, user: dict, text: str, data: dict) -> None:
    if text.lower() == "cancelar":
        await show_admin_menu(chat_id, user)
        return
    name = text.strip()
    if len(name) < 2:
        await send_text(chat_id, "❌ Nome muito curto. Tente novamente:")
        return
    await send_text(chat_id,
        f"✅ Meta: *{name}*\n\n"
        "Qual é o *número máximo* de ocorrências permitidas?\n_(Ex: *2*)_")
    _set_session_clean(chat_id, "add_meta_target", {**data, "meta_name": name})


async def handle_add_meta_target(chat_id: int, user: dict, text: str, data: dict) -> None:
    if text.lower() == "cancelar":
        await show_admin_menu(chat_id, user)
        return
    try:
        target = int(text.strip())
        if target < 0:
            raise ValueError
    except ValueError:
        await send_text(chat_id, "❌ Digite apenas um número inteiro positivo. Ex: *2*")
        return

    store = data["store"]
    sectors = get_sectors_for_store(store["id"])

    if not sectors:
        # Loja sem setores → perguntar quais criar
        await send_text(chat_id,
            f"✅ Meta: *{data['meta_name']}* (≤{target} ocorrências)\n\n"
            f"A loja *{store['name']}* ainda não tem setores.\n\n"
            "Digite os *nomes dos setores* separados por vírgula para criá-los agora:\n"
            "_(Ex: Salão, Cozinha, Delivery)_\n\n"
            "Digite *cancelar* para voltar.")
        _set_session_clean(chat_id, "add_meta_new_sectors", {**data, "target": target})
        return

    sector_list = "\n".join(f"*{i+1}.* {s['name']}" for i, s in enumerate(sectors))
    await send_text(chat_id,
        f"✅ Meta: *{data['meta_name']}* (≤{target} ocorrências)\n\n"
        f"*Setores disponíveis em {store['name']}:*\n{sector_list}\n\n"
        "Digite os *números* dos setores separados por vírgula.\n"
        "_(Ex: *1,2,4* ou *todos* para todos)_")
    _set_session_clean(chat_id, "add_meta_sectors", {**data, "target": target, "sectors": sectors})


async def handle_add_meta_sectors(chat_id: int, user: dict, text: str, data: dict) -> None:
    if text.lower() == "cancelar":
        await show_admin_menu(chat_id, user)
        return
    sectors = data.get("sectors", [])
    if text.lower() == "todos":
        selected = sectors
    else:
        try:
            indices = [int(x.strip()) - 1 for x in text.split(",") if x.strip()]
            selected = [sectors[i] for i in indices if 0 <= i < len(sectors)]
        except (ValueError, IndexError):
            await send_text(chat_id, "❌ Formato inválido. Use números separados por vírgula. Ex: *1,2,4*")
            return
    if not selected:
        await send_text(chat_id, "❌ Nenhum setor válido selecionado. Tente novamente.")
        return

    store = data["store"]
    success, table_name, error = create_new_meta(
        store_id=store["id"],
        name=data["meta_name"],
        target_value=data["target"],
        created_by=user["phone"],
        sector_ids=[s["id"] for s in selected],
    )
    if success:
        sector_names = ", ".join(s["name"] for s in selected)
        await send_text(chat_id,
            f"✅ *Meta criada!*\n\n"
            f"Loja: {store['name']}\n"
            f"Meta: {data['meta_name']}\n"
            f"Limite: ≤{data['target']} ocorrências\n"
            f"Setores: {sector_names}")
    else:
        await send_text(chat_id, f"❌ Erro ao criar meta: {error}")
    await show_admin_menu(chat_id, user)


async def handle_add_meta_new_sectors(chat_id: int, user: dict, text: str, data: dict) -> None:
    """Cria setores e meta quando a loja ainda não tem setores cadastrados."""
    if text.lower() == "cancelar":
        await show_admin_menu(chat_id, user)
        return

    names = [n.strip() for n in text.split(",") if n.strip()]
    if not names:
        await send_text(chat_id, "❌ Digite pelo menos um setor. Ex: *Salão, Cozinha, Delivery*")
        return

    store = data["store"]
    created = add_sectors(store["id"], names)
    if not created:
        await send_text(chat_id, "❌ Erro ao criar setores. Tente novamente.")
        return

    success, table_name, error = create_new_meta(
        store_id=store["id"],
        name=data["meta_name"],
        target_value=data["target"],
        created_by=user["phone"],
        sector_ids=[s["id"] for s in created],
    )

    if success:
        await send_text(chat_id,
            f"✅ *Meta e setores criados!*\n\n"
            f"Loja: {store['name']}\n"
            f"Meta: {data['meta_name']}\n"
            f"Limite: ≤{data['target']} ocorrências\n"
            f"Setores: {', '.join(names)}")
    else:
        await send_text(chat_id, f"⚠️ Setores criados, mas erro ao criar meta: {error}")
    await show_admin_menu(chat_id, user)


# ─────────────────────────────────────────────────────────
# FLUXO: ADICIONAR LOJA
# ─────────────────────────────────────────────────────────

async def start_add_store(chat_id: int, user: dict) -> None:
    await send_text(chat_id,
        "🏪 *Nova Loja*\n\nQual é o *nome* do restaurante?\n\nDigite *cancelar* para voltar.")
    _set_session_clean(chat_id, "add_store_name")


async def handle_add_store_name(chat_id: int, user: dict, text: str, data: dict) -> None:
    if text.lower() == "cancelar":
        await show_admin_menu(chat_id, user)
        return
    name = text.strip()
    if len(name) < 2:
        await send_text(chat_id, "❌ Nome muito curto. Tente novamente:")
        return
    store = add_store(name)
    for admin in [u for u in get_all_users() if u.get("is_admin")]:
        grant_store_access(admin["phone"], store["id"])
    await send_text(chat_id,
        f"✅ *Loja cadastrada!*\n\nNome: {name}\n"
        "_(Acesso concedido automaticamente a todos os administradores)_")
    await show_admin_menu(chat_id, user)


# ─────────────────────────────────────────────────────────
# FLUXO: RELATÓRIOS POR SETOR
# ─────────────────────────────────────────────────────────

def _month_range(months_ago: int):
    """Retorna (start_date, end_date, label) para N meses atrás."""
    from calendar import monthrange
    today = date.today()
    month = today.month - months_ago
    year = today.year
    while month <= 0:
        month += 12
        year -= 1
    last_day = monthrange(year, month)[1]
    label = date(year, month, 1).strftime("%B/%Y").capitalize()
    return date(year, month, 1).isoformat(), date(year, month, last_day).isoformat(), label


async def start_report(chat_id: int, user: dict) -> None:
    stores = get_all_stores() if user.get("is_admin") else get_user_stores(user["phone"])
    if not stores:
        await send_text(chat_id, "⚠️ Você não tem acesso a nenhuma loja.")
        await show_main_menu(chat_id, user)
        return
    if len(stores) == 1:
        await _report_select_period(chat_id, user, stores[0])
        return
    rows = [{"id": f"store_{s['id']}", "title": s["name"]} for s in stores]
    await send_list(chat_id, "📋 *Relatório por Setor*\n\nSelecione a loja:", "Ver lojas",
                    [{"title": "Lojas", "rows": rows}])
    _set_session_clean(chat_id, "report_select_store", {"stores": stores})


async def handle_report_select_store(chat_id: int, user: dict, text: str, data: dict) -> None:
    store = _find_store(text, data.get("stores", []))
    if not store:
        await send_text(chat_id, "Por favor, selecione uma loja.")
        return
    await _report_select_period(chat_id, user, store)


async def _report_select_period(chat_id: int, user: dict, store: dict) -> None:
    periods = [_month_range(i) for i in range(4)]
    rows = [{"id": f"period_{i}", "title": p[2]} for i, p in enumerate(periods)]
    rows[0]["title"] = f"📅 {rows[0]['title']} (atual)"
    await send_list(chat_id,
        f"📋 *{store['name']}*\n\nSelecione o período:",
        "Ver períodos", [{"title": "Períodos", "rows": rows}])
    _set_session_clean(chat_id, "report_select_period", {"store": store, "periods": periods})


async def handle_report_select_period(chat_id: int, user: dict, text: str, data: dict) -> None:
    if not text.startswith("period_"):
        await send_text(chat_id, "Por favor, selecione um período.")
        return
    idx = int(text.replace("period_", ""))
    periods = data.get("periods", [])
    if idx >= len(periods):
        await show_main_menu(chat_id, user)
        return
    start_date, end_date, label = periods[idx]
    store = data["store"]

    sectors = get_sectors_for_store(store["id"])
    if not sectors:
        await send_text(chat_id, f"⚠️ Nenhum setor cadastrado para *{store['name']}*.")
        await show_main_menu(chat_id, user)
        return

    rows = [{"id": f"sector_{s['id']}", "title": s["name"]} for s in sectors]
    await send_list(chat_id,
        f"📋 *{store['name']}* — {label}\n\nSelecione o setor:",
        "Ver setores", [{"title": "Setores", "rows": rows}])
    _set_session_clean(chat_id, "report_select_sector",
                       {"store": store, "sectors": sectors,
                        "start_date": start_date, "end_date": end_date, "label": label})


async def handle_report_select_sector(chat_id: int, user: dict, text: str, data: dict) -> None:
    sector = _find_item(text, data.get("sectors", []), "sector_")
    if not sector:
        await send_text(chat_id, "Por favor, selecione um setor.")
        return

    store = data["store"]
    start_date = data["start_date"]
    end_date = data["end_date"]
    label = data["label"]

    meta_configs = get_meta_configs(store["id"])
    report = get_sector_report(sector["id"], meta_configs, start_date, end_date)

    if not report:
        await send_text(chat_id,
            f"📋 *{sector['name']}* — {label}\n\n"
            "Nenhuma meta configurada para este setor.")
    else:
        lines = [
            f"📋 *Relatório — {sector['name']}*",
            f"Loja: {store['name']}  |  Período: {label}\n",
        ]
        for m in report:
            status = "✅" if m["ok"] else "❌"
            plural = "ocorrência" if m["count"] == 1 else "ocorrências"
            lines.append(
                f"{status} *{m['display_name']}* (≤{m['target_value']})  →  "
                f"{m['count']} {plural}"
            )
        await send_text(chat_id, "\n".join(lines))

    await send_buttons(chat_id, "O que deseja fazer?", [
        {"id": "relatorio",      "title": "📋 Outro relatório"},
        {"id": "menu_principal", "title": "🏠 Menu principal"},
    ])
    _set_session_clean(chat_id, "main_menu")


# ─────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────

def _find_store(text: str, stores: list) -> dict | None:
    if not text.startswith("store_"):
        return None
    try:
        sid = int(text.replace("store_", ""))
        return next((s for s in stores if s["id"] == sid), None)
    except ValueError:
        return None


def _find_item(text: str, items: list, prefix: str) -> dict | None:
    if not text.startswith(prefix):
        return None
    try:
        iid = int(text.replace(prefix, ""))
        return next((i for i in items if i["id"] == iid), None)
    except ValueError:
        return None


async def _show_meta_type_list(chat_id: int, user: dict, store: dict, action: str) -> None:
    meta_configs = get_meta_configs(store["id"])
    if not meta_configs:
        await send_text(chat_id, f"⚠️ Nenhuma meta configurada para *{store['name']}*.")
        await show_main_menu(chat_id, user)
        return
    rows = [{"id": f"meta_{m['id']}", "title": m["display_name"]} for m in meta_configs]
    icon = "📊" if action == "view" else "📝"
    verb = "Ver resumo de:" if action == "view" else "Apontar ocorrência em:"
    next_state = "view_select_meta" if action == "view" else "apontar_select_meta"
    await send_list(chat_id, f"{icon} *{store['name']}*\n\n{verb}", "Ver metas",
                    [{"title": "Metas", "rows": rows}])
    _set_session_clean(chat_id, next_state, {"store": store, "meta_configs": meta_configs})


# ─────────────────────────────────────────────────────────
# RELATÓRIO GERAL (Admin)
# ─────────────────────────────────────────────────────────

async def start_general_report(chat_id: int, user: dict) -> None:
    periods = [_month_range(i) for i in range(4)]
    rows = [{"id": f"period_{i}", "title": p[2]} for i, p in enumerate(periods)]
    rows[0]["title"] = f"📅 {rows[0]['title']} (atual)"
    await send_list(chat_id, "📊 *Relatório Geral*\n\nSelecione o período:", "Ver períodos",
                    [{"title": "Períodos", "rows": rows}])
    _set_session_clean(chat_id, "general_report_period", {"periods": periods})


async def handle_general_report_period(chat_id: int, user: dict, text: str, data: dict) -> None:
    if not text.startswith("period_"):
        await send_text(chat_id, "Por favor, selecione um período.")
        return
    idx = int(text.replace("period_", ""))
    periods = data.get("periods", [])
    if idx >= len(periods):
        await show_admin_menu(chat_id, user)
        return
    start_date, end_date, label = periods[idx]

    from tools.monthly_report import _build_store_report
    stores = get_all_stores()
    await send_text(chat_id, f"📊 *Relatório Geral — {label}*\n")
    for store in stores:
        block = _build_store_report(store, start_date, end_date, label)
        await send_text(chat_id, block)
    await show_admin_menu(chat_id, user)


# ─────────────────────────────────────────────────────────
# EXCLUIR USUÁRIO
# ─────────────────────────────────────────────────────────

async def start_delete_user(chat_id: int, user: dict) -> None:
    users = get_all_users()
    if not users:
        await send_text(chat_id, "Nenhum usuário cadastrado.")
        await show_admin_menu(chat_id, user)
        return
    rows = [{"id": f"deluser_{u['phone']}", "title": u["name"],
             "description": u["phone"] + (" (admin)" if u.get("is_admin") else "")}
            for u in users]
    await send_list(chat_id, "🗑️ *Excluir Usuário*\n\nSelecione o usuário:", "Ver usuários",
                    [{"title": "Usuários", "rows": rows}])
    _set_session_clean(chat_id, "del_user_select", {"users": users})


async def handle_delete_user_select(chat_id: int, user: dict, text: str, data: dict) -> None:
    if not text.startswith("deluser_"):
        await send_text(chat_id, "Por favor, selecione um usuário.")
        return
    phone = text.replace("deluser_", "")
    users = data.get("users", [])
    target = next((u for u in users if u["phone"] == phone), None)
    if not target:
        await send_text(chat_id, "Usuário não encontrado.")
        await show_admin_menu(chat_id, user)
        return
    await send_buttons(chat_id,
        f"🗑️ *Excluir usuário?*\n\nNome: {target['name']}\nTelefone: {target['phone']}\n\n"
        "⚠️ Esta ação não pode ser desfeita.",
        [{"id": "del_confirm_yes", "title": "✅ Confirmar exclusão"},
         {"id": "del_confirm_no",  "title": "❌ Cancelar"}])
    _set_session_clean(chat_id, "del_user_confirm", {"target_phone": phone, "target_name": target["name"]})


async def handle_delete_user_confirm(chat_id: int, user: dict, text: str, data: dict) -> None:
    if text == "del_confirm_yes":
        delete_user(data["target_phone"])
        await send_text(chat_id, f"✅ Usuário *{data['target_name']}* excluído.")
    else:
        await send_text(chat_id, "❌ Exclusão cancelada.")
    await show_admin_menu(chat_id, user)


# ─────────────────────────────────────────────────────────
# EXCLUIR META
# ─────────────────────────────────────────────────────────

async def start_delete_meta(chat_id: int, user: dict) -> None:
    metas = get_all_meta_configs_with_store()
    if not metas:
        await send_text(chat_id, "Nenhuma meta cadastrada.")
        await show_admin_menu(chat_id, user)
        return
    rows = [{"id": f"delmeta_{m['id']}", "title": m["display_name"],
             "description": m.get("bot_stores", {}).get("name", "") if m.get("bot_stores") else ""}
            for m in metas]
    await send_list(chat_id, "🗑️ *Excluir Meta*\n\nSelecione a meta:", "Ver metas",
                    [{"title": "Metas", "rows": rows}])
    _set_session_clean(chat_id, "del_meta_select", {"metas": metas})


async def handle_delete_meta_select(chat_id: int, user: dict, text: str, data: dict) -> None:
    if not text.startswith("delmeta_"):
        await send_text(chat_id, "Por favor, selecione uma meta.")
        return
    meta_id = int(text.replace("delmeta_", ""))
    metas = data.get("metas", [])
    target = next((m for m in metas if m["id"] == meta_id), None)
    if not target:
        await send_text(chat_id, "Meta não encontrada.")
        await show_admin_menu(chat_id, user)
        return
    store_name = target.get("bot_stores", {}).get("name", "") if target.get("bot_stores") else ""
    await send_buttons(chat_id,
        f"🗑️ *Excluir meta?*\n\nMeta: {target['display_name']}\nLoja: {store_name}\n\n"
        "⚠️ Todos os apontamentos desta meta serão excluídos permanentemente.",
        [{"id": "del_confirm_yes", "title": "✅ Confirmar exclusão"},
         {"id": "del_confirm_no",  "title": "❌ Cancelar"}])
    _set_session_clean(chat_id, "del_meta_confirm",
                       {"target_id": meta_id, "target_name": target["display_name"],
                        "table_name": target["table_name"]})


async def handle_delete_meta_confirm(chat_id: int, user: dict, text: str, data: dict) -> None:
    if text == "del_confirm_yes":
        delete_meta_config(data["target_id"], data["table_name"])
        await send_text(chat_id, f"✅ Meta *{data['target_name']}* excluída.")
    else:
        await send_text(chat_id, "❌ Exclusão cancelada.")
    await show_admin_menu(chat_id, user)


# ─────────────────────────────────────────────────────────
# EXCLUIR LOJA
# ─────────────────────────────────────────────────────────

async def start_delete_store(chat_id: int, user: dict) -> None:
    stores = get_all_stores()
    if not stores:
        await send_text(chat_id, "Nenhuma loja cadastrada.")
        await show_admin_menu(chat_id, user)
        return
    rows = [{"id": f"delstore_{s['id']}", "title": s["name"]} for s in stores]
    await send_list(chat_id, "🗑️ *Excluir Loja*\n\nSelecione a loja:", "Ver lojas",
                    [{"title": "Lojas", "rows": rows}])
    _set_session_clean(chat_id, "del_store_select", {"stores": stores})


async def handle_delete_store_select(chat_id: int, user: dict, text: str, data: dict) -> None:
    if not text.startswith("delstore_"):
        await send_text(chat_id, "Por favor, selecione uma loja.")
        return
    store_id = int(text.replace("delstore_", ""))
    stores = data.get("stores", [])
    target = next((s for s in stores if s["id"] == store_id), None)
    if not target:
        await send_text(chat_id, "Loja não encontrada.")
        await show_admin_menu(chat_id, user)
        return
    await send_buttons(chat_id,
        f"🗑️ *Excluir loja?*\n\nLoja: {target['name']}\n\n"
        "⚠️ Todos os setores, metas e acessos desta loja serão excluídos.",
        [{"id": "del_confirm_yes", "title": "✅ Confirmar exclusão"},
         {"id": "del_confirm_no",  "title": "❌ Cancelar"}])
    _set_session_clean(chat_id, "del_store_confirm",
                       {"target_id": store_id, "target_name": target["name"]})


async def handle_delete_store_confirm(chat_id: int, user: dict, text: str, data: dict) -> None:
    if text == "del_confirm_yes":
        delete_store(data["target_id"])
        await send_text(chat_id, f"✅ Loja *{data['target_name']}* excluída.")
    else:
        await send_text(chat_id, "❌ Exclusão cancelada.")
    await show_admin_menu(chat_id, user)


# ─────────────────────────────────────────────────────────
# EXCLUIR SETOR
# ─────────────────────────────────────────────────────────

async def start_delete_sector(chat_id: int, user: dict) -> None:
    stores = get_all_stores()
    if not stores:
        await send_text(chat_id, "Nenhuma loja cadastrada.")
        await show_admin_menu(chat_id, user)
        return
    rows = [{"id": f"store_{s['id']}", "title": s["name"]} for s in stores]
    await send_list(chat_id, "🗑️ *Excluir Setor*\n\nSelecione a loja:", "Ver lojas",
                    [{"title": "Lojas", "rows": rows}])
    _set_session_clean(chat_id, "del_sector_store", {"stores": stores})


async def handle_delete_sector_store(chat_id: int, user: dict, text: str, data: dict) -> None:
    store = _find_store(text, data.get("stores", []))
    if not store:
        await send_text(chat_id, "Por favor, selecione uma loja.")
        return
    sectors = get_sectors_for_store(store["id"])
    if not sectors:
        await send_text(chat_id, f"⚠️ Nenhum setor cadastrado em *{store['name']}*.")
        await show_admin_menu(chat_id, user)
        return
    rows = [{"id": f"delsector_{s['id']}", "title": s["name"]} for s in sectors]
    await send_list(chat_id, f"🗑️ *{store['name']}*\n\nSelecione o setor a excluir:", "Ver setores",
                    [{"title": "Setores", "rows": rows}])
    _set_session_clean(chat_id, "del_sector_select", {"store": store, "sectors": sectors})


async def handle_delete_sector_select(chat_id: int, user: dict, text: str, data: dict) -> None:
    if not text.startswith("delsector_"):
        await send_text(chat_id, "Por favor, selecione um setor.")
        return
    sector_id = int(text.replace("delsector_", ""))
    sectors = data.get("sectors", [])
    target = next((s for s in sectors if s["id"] == sector_id), None)
    if not target:
        await send_text(chat_id, "Setor não encontrado.")
        await show_admin_menu(chat_id, user)
        return
    store = data.get("store", {})
    await send_buttons(chat_id,
        f"🗑️ *Excluir setor?*\n\nSetor: {target['name']}\nLoja: {store.get('name', '')}\n\n"
        "⚠️ O setor será removido de todas as metas vinculadas.",
        [{"id": "del_confirm_yes", "title": "✅ Confirmar exclusão"},
         {"id": "del_confirm_no",  "title": "❌ Cancelar"}])
    _set_session_clean(chat_id, "del_sector_confirm",
                       {"target_id": sector_id, "target_name": target["name"]})


async def handle_delete_sector_confirm(chat_id: int, user: dict, text: str, data: dict) -> None:
    if text == "del_confirm_yes":
        delete_sector(data["target_id"])
        await send_text(chat_id, f"✅ Setor *{data['target_name']}* excluído.")
    else:
        await send_text(chat_id, "❌ Exclusão cancelada.")
    await show_admin_menu(chat_id, user)


# ─────────────────────────────────────────────────────────
# EXCLUIR APONTAMENTO
# ─────────────────────────────────────────────────────────

async def start_delete_occurrence(chat_id: int, user: dict) -> None:
    stores = get_all_stores()
    if not stores:
        await send_text(chat_id, "Nenhuma loja cadastrada.")
        await show_admin_menu(chat_id, user)
        return
    rows = [{"id": f"store_{s['id']}", "title": s["name"]} for s in stores]
    await send_list(chat_id, "🗑️ *Excluir Apontamento*\n\nSelecione a loja:", "Ver lojas",
                    [{"title": "Lojas", "rows": rows}])
    _set_session_clean(chat_id, "del_occ_store", {"stores": stores})


async def handle_delete_occ_store(chat_id: int, user: dict, text: str, data: dict) -> None:
    store = _find_store(text, data.get("stores", []))
    if not store:
        await send_text(chat_id, "Por favor, selecione uma loja.")
        return
    metas = get_meta_configs(store["id"])
    if not metas:
        await send_text(chat_id, f"⚠️ Nenhuma meta em *{store['name']}*.")
        await show_admin_menu(chat_id, user)
        return
    rows = [{"id": f"meta_{m['id']}", "title": m["display_name"]} for m in metas]
    await send_list(chat_id, f"🗑️ *{store['name']}*\n\nSelecione a meta:", "Ver metas",
                    [{"title": "Metas", "rows": rows}])
    _set_session_clean(chat_id, "del_occ_meta", {"store": store, "meta_configs": metas})


async def handle_delete_occ_meta(chat_id: int, user: dict, text: str, data: dict) -> None:
    meta = _find_item(text, data.get("meta_configs", []), "meta_")
    if not meta:
        await send_text(chat_id, "Por favor, selecione uma meta.")
        return
    sectors = get_sectors_for_meta(meta["id"])
    if not sectors:
        await send_text(chat_id, "⚠️ Nenhum setor vinculado a esta meta.")
        await show_admin_menu(chat_id, user)
        return
    rows = [{"id": f"sector_{s['id']}", "title": s["name"]} for s in sectors]
    await send_list(chat_id, f"🗑️ *{meta['display_name']}*\n\nSelecione o setor:", "Ver setores",
                    [{"title": "Setores", "rows": rows}])
    _set_session_clean(chat_id, "del_occ_sector",
                       {"store": data.get("store"), "meta": meta, "sectors": sectors})


async def handle_delete_occ_sector(chat_id: int, user: dict, text: str, data: dict) -> None:
    sector = _find_item(text, data.get("sectors", []), "sector_")
    if not sector:
        await send_text(chat_id, "Por favor, selecione um setor.")
        return
    meta = data["meta"]
    occurrences = get_recent_occurrences(meta["table_name"], meta["id"], sector["id"], limit=10)
    if not occurrences:
        await send_text(chat_id, "⚠️ Nenhum apontamento encontrado para este setor/meta.")
        await show_admin_menu(chat_id, user)
        return
    rows = []
    for occ in occurrences:
        title = occ["occurrence_date"]
        desc = occ.get("notes") or occ.get("reported_by") or ""
        rows.append({"id": f"occ_{occ['id']}", "title": title, "description": desc[:30] if desc else ""})
    await send_list(chat_id,
        f"🗑️ *{meta['display_name']} — {sector['name']}*\n\nSelecione o apontamento a excluir:",
        "Ver apontamentos", [{"title": "Apontamentos recentes", "rows": rows}])
    _set_session_clean(chat_id, "del_occ_list",
                       {"meta": meta, "sector": sector, "occurrences": occurrences})


async def handle_delete_occ_list(chat_id: int, user: dict, text: str, data: dict) -> None:
    if not text.startswith("occ_"):
        await send_text(chat_id, "Por favor, selecione um apontamento.")
        return
    occ_id = int(text.replace("occ_", ""))
    occurrences = data.get("occurrences", [])
    target = next((o for o in occurrences if o["id"] == occ_id), None)
    if not target:
        await send_text(chat_id, "Apontamento não encontrado.")
        await show_admin_menu(chat_id, user)
        return
    meta = data["meta"]
    sector = data["sector"]
    notes_line = f"\nObservação: {target['notes']}" if target.get("notes") else ""
    await send_buttons(chat_id,
        f"🗑️ *Excluir apontamento?*\n\n"
        f"Meta: {meta['display_name']}\nSetor: {sector['name']}\n"
        f"Data: {target['occurrence_date']}{notes_line}\n\n"
        "⚠️ Esta ação não pode ser desfeita.",
        [{"id": "del_confirm_yes", "title": "✅ Confirmar exclusão"},
         {"id": "del_confirm_no",  "title": "❌ Cancelar"}])
    _set_session_clean(chat_id, "del_occ_confirm",
                       {"occ_id": occ_id, "table_name": meta["table_name"],
                        "date": target["occurrence_date"]})


async def handle_delete_occ_confirm(chat_id: int, user: dict, text: str, data: dict) -> None:
    if text == "del_confirm_yes":
        delete_occurrence(data["table_name"], data["occ_id"])
        await send_text(chat_id, f"✅ Apontamento de *{data['date']}* excluído.")
    else:
        await send_text(chat_id, "❌ Exclusão cancelada.")
    await show_admin_menu(chat_id, user)
