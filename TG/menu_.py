# TG.menu_.py
from __future__ import annotations

import asyncio
from typing import *
import copy
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

from a_config import (
    COPY_NUMBER,
)

from c_utils import now
from .helpers_ import (
    parse_id_range, validate_master,
    validate_copy, format_status,
    can_push_cmd, validate_unique_accounts, parse_mx_credentials)

from b_context import COPY_TEMPLATE

if TYPE_CHECKING:
    from c_log import UnifiedLogger
    from b_context import MainContext
    from COPY.state_ import CopyState


# =====================================================================
#                          MAIN UI CLASS
# =====================================================================

class UIMenu:
    """
    Полный Telegram UI для:
    • Master (ID=0)
    • Copies (1..COPY_NUMBER)

    Всё залочено на self.admin_id — бот монопользовательский.
    """

    def __init__(
            self,
            bot: Bot,
            dp: Dispatcher,
            ctx: "MainContext",
            logger: "UnifiedLogger",
            copy_state: "CopyState",
            admin_id: int,
            on_close: Callable[[List[int]], Awaitable[None]]
        ):
        self.bot = bot
        self.dp = dp
        self.ctx = ctx
        self.log = logger
        self.copy_state = copy_state
        self.admin_id = admin_id
        self.on_close = on_close

        # runtime input state: chat → {...}
        self.await_input: Dict[int, Optional[Dict[str, Any]]] = {}

        # регистрируем handlers
        self._register_handlers()

    # =====================================================================
    #                     MENU TEMPLATES
    # =====================================================================

    def menu_main(self):
        kb = [
            [types.KeyboardButton(text="▶️ START"), types.KeyboardButton(text="⏹ STOP")],
            [types.KeyboardButton(text="🧩 MASTER"), types.KeyboardButton(text="👥 COPIES")],
        ]
        return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

    def menu_master(self):
        kb = [
            [types.KeyboardButton(text="📑 Status")],
            [types.KeyboardButton(text="🔑 API & Proxy")],            
            [types.KeyboardButton(text="🔄 Change Master")],
            [types.KeyboardButton(text="⬅ Back")],
        ]
        return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

    def menu_copies(self):
        kb = [
            [types.KeyboardButton(text="📑 Copy Status"), types.KeyboardButton(text="📋 List Copies")],
            [types.KeyboardButton(text="🔑 Copy API & Proxy"), types.KeyboardButton(text="🛠 Custom Settings")],
            [types.KeyboardButton(text="▶ Activate Copy"), types.KeyboardButton(text="🗑 Deactivate Copy")],
            [types.KeyboardButton(text="🔒 CLOSE")],
            [types.KeyboardButton(text="⬅ Back")],
        ]
        return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    
    def menu_copy_settings(self):
        kb = [
            [types.KeyboardButton(text="📐 Coef")],
            [types.KeyboardButton(text="🎚 Leverage")],
            [types.KeyboardButton(text="🧱 Margin Mode")],
            [types.KeyboardButton(text="💰 Max Position Size")],
            [types.KeyboardButton(text="🎲 Random Size %")],
            [types.KeyboardButton(text="⏱ Delay (ms)")],
            [types.KeyboardButton(text="⬅ Back to Copies")],   # ← ВАЖНО
        ]
        return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

    # =====================================================================
    #                       INTERNAL HELPERS
    # =====================================================================

    async def _check_admin(self, msg: types.Message) -> bool:
        if msg.chat.id != self.admin_id:
            await msg.answer("❗ Нет доступа")
            return False
        return True

    def _enter_input(self, chat_id: int, **kwargs):
        self.await_input[chat_id] = kwargs

    def _exit_input(self, chat_id: int):
        self.await_input[chat_id] = None

    # =====================================================================
    #                     REGISTER HANDLERS
    # =====================================================================

    def _register_handlers(self):
        dp = self.dp

        dp.message.register(self.cmd_start, Command("start"))
        dp.message.register(self.cmd_status, Command("status"))

        # MAIN menu
        dp.message.register(self.btn_start, lambda m: m.text == "▶️ START")
        dp.message.register(self.btn_stop, lambda m: m.text == "⏹ STOP")
        dp.message.register(self.btn_master, lambda m: m.text == "🧩 MASTER")
        dp.message.register(self.btn_copies, lambda m: m.text == "👥 COPIES")
        dp.message.register(self.btn_close, lambda m: m.text == "🔒 CLOSE")

        # MASTER submenu
        dp.message.register(self.btn_mx_settings, lambda m: m.text == "🔑 API & Proxy")
        dp.message.register(self.btn_mx_status, lambda m: m.text == "📑 Status")
        dp.message.register(self.btn_mx_change, lambda m: m.text == "🔄 Change Master")
        dp.message.register(self.btn_back, lambda m: m.text == "⬅ Back")

        # COPIES submenu
        dp.message.register(self.btn_copy_list, lambda m: m.text == "📋 List Copies")
        dp.message.register(self.btn_copy_mx_settings, lambda m: m.text == "🔑 Copy API & Proxy")
        dp.message.register(self.btn_copy_settings, lambda m: m.text == "🛠 Custom Settings")
        dp.message.register(self.btn_copy_activate, lambda m: m.text == "▶ Activate Copy")
        dp.message.register(self.btn_copy_deactivate, lambda m: m.text == "🗑 Deactivate Copy")
        dp.message.register(self.btn_copy_status, lambda m: m.text == "📑 Copy Status")

        # universal input handler
        dp.message.register(self.handle_text_input)

    # =====================================================================
    #                          BASIC COMMANDS
    # =====================================================================

    async def cmd_start(self, msg: types.Message):
        if not await self._check_admin(msg):
            return
        await msg.answer("Добро пожаловать!", reply_markup=self.menu_main())

    async def cmd_status(self, msg: types.Message):
        if not await self._check_admin(msg):
            return
        await self._ask_status_id(msg)

    # =====================================================================
    #                          MAIN BUTTONS
    # =====================================================================

    async def btn_start(self, msg: types.Message):
        if not await self._check_admin(msg):
            return

        cfg = self.ctx.copy_configs.get(0)
        rt = cfg.setdefault("cmd_state", {})

        # ❗ STOP ожидает подтверждения -> запрещаем START
        if rt.get("stop_confirm"):
            await msg.answer("❗ Остановка не завершена. Нажмите STOP ещё раз для подтверждения.")
            return
        
        # # ❗ проверка уникальности аккаунтов
        dup_reason = validate_unique_accounts(self.ctx)
        if dup_reason:
            await msg.answer(dup_reason)
            return

        # ❗ валидация
        reason = validate_master(cfg)
        if reason:
            await msg.answer(f"❗ Мастер конфиг неполный:\n{reason}")
            return
        
        # ❗ проверка: есть ли хотя бы один активный copy
        has_active_copy = any(
            cid != 0 and cfg and cfg.get("enabled")
            for cid, cfg in self.ctx.copy_configs.items()
        )

        if not has_active_copy:
            await msg.answer(
                "❗ Убедитесь, что активирован хотя бы один копи-аккаунт.\n"
                "После этого нажмите START ещё раз."
            )
            return

        # 🔥 ПОЛНЫЙ RESET всех служебных флагов + старт
        rt["stop_flag"] = False
        rt["stop_confirm"] = False
        rt["trading_enabled"] = True

        await msg.answer("▶️ Мастер запущен", reply_markup=self.menu_main())

    async def btn_stop(self, msg: types.Message):
        if not await self._check_admin(msg):
            return

        cfg = self.ctx.copy_configs[0]
        rt = cfg.setdefault("cmd_state", {})

        if not rt.get("trading_enabled"):
            await msg.answer("⏹ Мастер уже остановлен.")
            return

        if not rt.get("stop_confirm"):
            rt["stop_confirm"] = True
            await msg.answer("❗ Нажмите STOP ещё раз для подтверждения.")
            return

        rt["trading_enabled"] = False
        rt["stop_flag"] = True
        rt["stop_confirm"] = False

        await msg.answer("⏹ Остановка мастера активирована.")

    async def btn_status(self, msg: types.Message):
        if not await self._check_admin(msg):
            return
        await self._ask_status_id(msg)

    async def btn_master(self, msg: types.Message):
        if not await self._check_admin(msg):
            return
        await msg.answer("MASTER MENU:", reply_markup=self.menu_master())

    async def btn_copies(self, msg: types.Message):
        if not await self._check_admin(msg):
            return
        await msg.answer("COPIES MENU:", reply_markup=self.menu_copies())

    async def btn_close(self, msg: types.Message):
        if not await self._check_admin(msg):
            return

        # 🔒 CLOSE разрешён только после старта мастера
        master_cfg = self.ctx.copy_configs.get(0, {})
        cmd_state = master_cfg.get("cmd_state", {})

        if not cmd_state.get("trading_enabled"):
            await msg.answer(
                "❗ CLOSE недоступен.\n"
                "Мастер ещё не запущен.\n"
                "Сначала нажмите ▶️ START."
            )
            return

        self._enter_input(msg.chat.id, mode="close_ids")
        await msg.answer(
            "Введите ID аккаунтов для ЗАКРЫТИЯ ПОЗИЦИЙ.\n"
            "Поддерживается список и диапазоны.\n"
            "❗ МАСТЕР (ID=0) ЗАКРЫВАТЬ НЕЛЬЗЯ.\n\n"
            "Примеры:\n"
            "• 1\n"
            "• 1 3\n"
            "• 1-3\n"
            "• 2-5 7-4"
        )

    async def btn_back(self, msg: types.Message):
        if not await self._check_admin(msg):
            return
        await msg.answer("Главное меню:", reply_markup=self.menu_main())

    # =====================================================================
    #                           STATUS BY ID
    # =====================================================================
    async def _ask_status_id(self, msg: types.Message):
        cid = msg.chat.id
        self._enter_input(cid, mode="copy_status_id")
        await msg.answer(
            "Введите ID аккаунтов для ПРОСМОТРА СТАТУСА.\n"
            "Поддерживается список и диапазоны.\n\n"
            "Примеры:\n"
            "• 1\n"
            "• 1 3 5\n"
            "• 2-6"
        )

    async def _send_status(self, msg: types.Message, acc_id: int, reply_kb=None):
        cfg = self.ctx.copy_configs.get(acc_id)
        if not cfg:
            await msg.answer("❗ Нет такого аккаунта.")
            return

        if reply_kb is None:
            await msg.answer(format_status(cfg))
        else:
            await msg.answer(format_status(cfg), reply_markup=reply_kb)

    # =====================================================================
    #                         MASTER SETTINGS
    # =====================================================================
    async def btn_mx_settings(self, msg: types.Message):
        if not await self._check_admin(msg):
            return

        self._enter_input(msg.chat.id, mode="master_mx_input")
        await msg.answer(
            "🔐 MASTER • API & Proxy\n\n"
            "Введите MX креденции MASTER построчно:\n"
            "api_key\n"
            "api_secret\n"
            "uid\n"
            "proxy (опционально)\n\n"
            "Пример:\n"
            "mx0...\n"
            "83df...\n"
            "WEB...\n"
            "154.219.71.17:64008:user:pass"
        )

    async def btn_mx_status(self, msg: types.Message):
        if not await self._check_admin(msg):
            return
        await self._send_status(msg, 0)

    async def btn_mx_change(self, msg: types.Message):
        if not await self._check_admin(msg):
            return
        self._enter_input(msg.chat.id, mode="change_master")
        await msg.answer("Введите ID копи, с которым нужно поменяться ролями:")

    # =====================================================================
    #                          COPIES MENU
    # =====================================================================
    async def btn_copy_mx_settings(self, msg: types.Message):
        if not await self._check_admin(msg):
            return

        self._enter_input(msg.chat.id, mode="copy_mx_select")
        await msg.answer("Введите ID копи-аккаунта для настройки API & Proxy:")

    async def btn_copy_settings(self, msg: types.Message):
        if not await self._check_admin(msg):
            return

        self._enter_input(msg.chat.id, mode="copy_settings_select")
        await msg.answer("Введите ID копи-аккаунта для настройки параметров:")

    async def btn_copy_list(self, msg: types.Message):
        if not await self._check_admin(msg):
            return

        text = "Список копи-аккаунтов:\n\n"
        for cid, cfg in self.ctx.copy_configs.items():
            if cid == 0:
                continue

            if cfg is None:
                status = "⚫ EMPTY"
            else:
                status = "🟢 ON" if cfg.get("enabled") else "⚪ OFF"

            text += f"{cid}: {status}\n"

        await msg.answer(text)

    async def btn_copy_activate(self, msg: types.Message):
        if not await self._check_admin(msg):
            return

        self._enter_input(msg.chat.id, mode="copy_activate")
        await msg.answer(
            "Введите ID копи-аккаунтов для АКТИВАЦИИ.\n"
            "Поддерживается список и диапазоны.\n\n"
            "Примеры:\n"
            "• 1\n"
            "• 1 3 5\n"
            "• 2-6\n"
            "• 1-3 5 8-6\n\n"
            "❗ Аккаунты должны быть предварительно настроены."
        )

    async def btn_copy_deactivate(self, msg: types.Message):
        if not await self._check_admin(msg):
            return

        self._enter_input(msg.chat.id, mode="copy_deactivate")
        await msg.answer(
            "Введите ID копи-аккаунтов для ДЕАКТИВАЦИИ.\n"
            "Поддерживается список и диапазоны.\n\n"
            "Примеры:\n"
            "• 1\n"
            "• 1 3 5\n"
            "• 2-6\n"
            "• 1-3 5 8-6"
        )

    async def btn_copy_status(self, msg: types.Message):
        if not await self._check_admin(msg):
            return

        self._enter_input(msg.chat.id, mode="copy_status_id")
        await msg.answer(
            "Введите ID копи-аккаунтов для ПРОСМОТРА СТАТУСА.\n"
            "Поддерживается список и диапазоны.\n\n"
            "Примеры:\n"
            "• 1\n"
            "• 1 3 5\n"
            "• 2-6\n"
            "• 1-3 5 8-4"
        )

    # =====================================================================
    #                   UNIVERSAL TEXT INPUT HANDLER
    # =====================================================================
    async def handle_text_input(self, msg: types.Message):
        chat_id = msg.chat.id
        if chat_id != self.admin_id:
            return

        wait = self.await_input.get(chat_id)
        if not wait:
            return

        raw = msg.text.strip()
        mode = wait["mode"]

        # ============================
        # CANCEL / BACK
        # ============================
        if raw.lower() in ("cancel", "отмена", "назад"):
            self._exit_input(chat_id)
            await msg.answer("❕ Ввод отменён.", reply_markup=self.menu_main())
            return

        if raw == "⬅ Back":
            self._exit_input(chat_id)
            await msg.answer("Главное меню:", reply_markup=self.menu_main())
            return
        
        # ============================
        # BACK FROM COPY SETTINGS
        # ============================
        if raw == "⬅ Back to Copies":
            self._exit_input(chat_id)
            await msg.answer("COPIES MENU:", reply_markup=self.menu_copies())
            return

        # ============================
        # CLOSE (range) — DANGEROUS
        # ============================
        if mode == "close_ids":
            try:
                ids = parse_id_range(raw, allow_zero=False)

                if not can_push_cmd(self.ctx):
                    await msg.answer("⏳ Подождите секунду...")
                    return

                asyncio.create_task(self.on_close(ids))
                self._exit_input(chat_id)

                await msg.answer(
                    f"✔ Команда CLOSE отправлена для: {ids}",
                    reply_markup=self.menu_main(),
                )
            except Exception as e:
                await msg.answer(f"❗ Ошибка формата.\n{e}")
            return

        # ============================
        # CHANGE MASTER
        # ============================
        elif mode == "change_master":
            try:
                cid = int(raw)
                if cid == 0 or cid not in self.ctx.copy_configs:
                    await msg.answer("❗ Неверный ID.")
                    return

                master = self.ctx.copy_configs[0]
                copy_acc = self.ctx.copy_configs[cid]
                if copy_acc is None:
                    await msg.answer("❗ COPY не инициализирован.")
                    return

                ex = copy_acc.get("exchange", {})
                if not ex.get("api_key") or not ex.get("api_secret"):
                    await msg.answer(
                        "❗ У этого копи нет необходимых кредов для роли MASTER.\n"
                        "Нужны api_key и api_secret."
                    )
                    return

                master["exchange"], copy_acc["exchange"] = (
                    copy_acc["exchange"],
                    master["exchange"],
                )

                await self.ctx.save_users()
                self._exit_input(chat_id)
                await msg.answer("✔ Мастер успешно сменён!", reply_markup=self.menu_main())
            except:
                await msg.answer("❗ Ошибка ID.")
            return

        # ============================
        # MASTER MX INPUT
        # ============================
        elif mode == "master_mx_input":
            try:
                data, err = parse_mx_credentials(raw)
                if err:
                    await msg.answer(f"❗ {err}")
                    return

                cfg = self.ctx.copy_configs[0]
                cfg.setdefault("exchange", {}).update(data)

                await self.ctx.save_users()
                self._exit_input(chat_id)

                await msg.answer(
                    "✔ MASTER API & Proxy сохранены.",
                    reply_markup=self.menu_master(),
                )
            except Exception as e:
                await msg.answer(f"❗ Ошибка обработки.\n{e}")
            return

        # ============================
        # COPY ACTIVATE
        # ============================
        elif mode == "copy_activate":
            try:
                ids = parse_id_range(raw)

                for cid in ids:
                    if cid <= 0 or cid > COPY_NUMBER:
                        await msg.answer(f"❗ Недопустимый ID: {cid}")
                        return

                    # 🔥 МАТЕРИАЛИЗАЦИЯ
                    if self.ctx.copy_configs.get(cid) is None:
                        fresh = copy.deepcopy(COPY_TEMPLATE)
                        fresh["id"] = cid
                        self.ctx.copy_configs[cid] = fresh

                    missing = validate_copy(self.ctx.copy_configs[cid])
                    if missing:
                        await msg.answer(
                            f"❗ Нельзя активировать ID={cid} — конфиг неполный:\n{missing}"
                        )
                        return

                for cid in ids:
                    cfg = self.ctx.copy_configs[cid]
                    cfg["enabled"] = True
                    cfg["created_at"] = now()

                    ok = await self.copy_state.activate_copy(cid)
                    if not ok:
                        await msg.answer(f"❌ ID={cid} — ошибка активации")
                        return

                await self.ctx.save_users()
                self._exit_input(chat_id)

                await msg.answer(
                    f"✔ Копи-аккаунты {ids} активированы.",
                    reply_markup=self.menu_copies(),
                )
            except:
                await msg.answer("❗ Ошибка формата.")


        # ============================
        # COPY DEACTIVATE
        # ============================
        elif mode == "copy_deactivate":
            try:
                ids = parse_id_range(raw)

                for cid in ids:
                    if cid <= 0:
                        await msg.answer("❗ ID=0 — это мастер.")
                        return

                    await self.copy_state.deactivate_copy(cid)

                    self.ctx.copy_configs[cid]["enabled"] = False
                    self.ctx.copy_configs[cid]["created_at"] = None

                await self.ctx.save_users()
                self._exit_input(chat_id)

                await msg.answer(
                    f"✔ Копи-аккаунты {ids} деактивированы.",
                    reply_markup=self.menu_copies(),
                )
            except:
                await msg.answer("❗ Ошибка формата.")
            return

        # ============================
        # COPY STATUS
        # ============================
        elif mode == "copy_status_id":
            try:
                ids = parse_id_range(raw)

                blocks: list[str] = []

                for cid in ids:
                    if cid <= 0 or cid not in self.ctx.copy_configs:
                        await msg.answer(f"❗ Неверный ID: {cid}")
                        return

                    cfg = self.ctx.copy_configs[cid]
                    if cfg is None:
                        blocks.append(f"⚫ COPY ID={cid}\nСтатус: не инициализирован")
                    else:
                        blocks.append(format_status(cfg))

                self._exit_input(chat_id)

                # минимальный и читаемый разделитель
                separator = "\n\n"

                text = separator.join(blocks)

                await msg.answer(
                    text,
                    reply_markup=self.menu_copies(),
                )

            except Exception:
                await msg.answer("❗ Ошибка формата.")
            return

        # ============================
        # COPY API & PROXY
        # ============================
        elif mode == "copy_mx_select":
            try:
                cid = int(raw)
                cfg = self.ctx.copy_configs.get(cid)
                if cid <= 0 or cfg is None:
                    await msg.answer("❗ COPY не инициализирован. Сначала Activate Copy.")
                    return

                self._enter_input(chat_id, mode="copy_mx_input", cid=cid)
                await msg.answer(
                    "Введите креденции построчно:\n"
                    "api_key\napi_secret\nuid\nproxy (опционально)"
                )
            except:
                await msg.answer("❗ Ошибка ID.")
            return

        elif mode == "copy_mx_input":
            cid = wait["cid"]
            data, err = parse_mx_credentials(raw)
            if err:
                await msg.answer(f"❗ {err}")
                return

            self.ctx.copy_configs[cid].setdefault("exchange", {}).update(data)
            await self.ctx.save_users()
            self._exit_input(chat_id)

            await msg.answer("✔ API & Proxy сохранены.", reply_markup=self.menu_copies())
            return

        # ============================
        # COPY CUSTOM SETTINGS
        # ============================
        elif mode == "copy_settings_select":
            try:
                cid = int(raw)
                cfg = self.ctx.copy_configs.get(cid)
                if cid <= 0 or cfg is None:
                    await msg.answer("❗ COPY не инициализирован. Сначала Activate Copy.")
                    return

                self._enter_input(chat_id, mode="copy_settings_menu", cid=cid)
                await msg.answer(
                    f"🛠 Настройки COPY ID={cid}:",
                    reply_markup=self.menu_copy_settings(),
                )
            except:
                await msg.answer("❗ Ошибка ID.")
            return

        elif mode == "copy_settings_menu":
            cid = wait["cid"]

            mapping = {
                "📐 Coef": ("coef", "Пример: 0.5 / 1 / 2"),
                "🎚 Leverage": ("leverage", "0 — брать из мастера"),
                "🧱 Margin Mode": ("margin_mode", "1 — ISOLATED\n2 — CROSSED"),
                "💰 Max Position Size": ("max_position_size", "USDT"),
                "🎲 Random Size %": ("random_size_pct", "Формат: 90 110"),
                "⏱ Delay (ms)": ("delay_ms", "Формат: 300 1200"),
            }

            if raw not in mapping:
                await msg.answer("❗ Неизвестная настройка.")
                return

            field, hint = mapping[raw]
            self._enter_input(chat_id, mode="copy_settings_input", cid=cid, field=field)
            await msg.answer(hint)
            return

        elif mode == "copy_settings_input":
            cid = wait["cid"]
            field = wait["field"]
            cfg = self.ctx.copy_configs[cid]

            try:
                if field == "coef":
                    cfg["coef"] = float(raw)
                elif field == "leverage":
                    v = int(raw)
                    cfg["leverage"] = None if v == 0 else v
                elif field == "margin_mode":
                    if raw not in ("1", "2"):
                        raise ValueError
                    cfg["margin_mode"] = int(raw)
                elif field == "max_position_size":
                    cfg["max_position_size"] = float(raw)
                elif field == "random_size_pct":
                    a, b = map(float, raw.split())
                    cfg["random_size_pct"] = [a, b]
                elif field == "delay_ms":
                    a, b = map(int, raw.split())
                    if a > b or a < 0:
                        raise ValueError
                    cfg["delay_ms"] = [a, b]
            except:
                await msg.answer("❗ Некорректное значение.")
                return

            await self.ctx.save_users()
            self._enter_input(chat_id, mode="copy_settings_menu", cid=cid)
            await msg.answer("✔ Сохранено.", reply_markup=self.menu_copy_settings())
            return