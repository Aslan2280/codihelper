import asyncio
import json
import os
import random
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from pathlib import Path

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from aiogram.utils.markdown import hbold, hcode

# ==================== КОНФИГУРАЦИЯ ====================

BOT_TOKEN = "8919148715:AAF1TL1-EyCZS_EeBVPh3z0Vj9ISpMkTdOc"  # ЗАМЕНИТЕ НА СВОЙ
BOT_NAME = "CodiHelper"

# Пути к файлам
USERS_FILE = "users.json"
GROUPS_FILE = "groups.json"
SHOP_FILE = "shop.json"
MARKET_FILE = "market.json"

# Настройки
DAILY_REWARD = 50
VIP_PRICE_PER_DAY = 20
MAX_WARNS = 3
MUTE_DEFAULT_MINUTES = 60
REFERRAL_REWARD = 25
FARM_BASE_PRODUCTION = 10

# Плохие слова
BAD_WORDS = ['хуй', 'пизда', 'блядь', 'сука', 'ебать', 'нахуй', 'пиздец', 'залупа', 'мудак', 'гандон', 'еблан']

# Цвета для VIP
COLORS = {
    "red": "Красный",
    "gold": "Золотой",
    "blue": "Синий",
    "pink": "Розовый",
    "white": "Белый"
}

# ==================== РАБОТА С БАЗОЙ ДАННЫХ ====================

def ensure_data_dir():
    """Создает папку для данных"""
    DATA_DIR.mkdir(exist_ok=True)

def load_data(file_path) -> Dict[str, Any]:
    """Загружает данные из JSON"""
    ensure_data_dir()
    if not file_path.exists():
        return {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def save_data(file_path, data: Dict[str, Any]):
    """Сохраняет данные в JSON"""
    ensure_data_dir()
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ============ ПОЛЬЗОВАТЕЛИ ============

def get_user(user_id: int) -> Dict[str, Any]:
    """Получает данные пользователя, создает если нет"""
    users = load_data(USERS_FILE)
    user_id = str(user_id)
    
    if user_id not in users:
        users[user_id] = {
            "balance": 0,
            "gold_balance": 0,
            "vip": False,
            "vip_until": None,
            "warns": 0,
            "mutes": [],
            "reputation": 0,
            "medals": [],
            "nickname": None,
            "nick_color": "white",
            "level": 1,
            "exp": 0,
            "exp_to_next": 100,
            "referrals": [],
            "referrer": None,
            "daily_last": None,
            "farm": {
                "level": 1,
                "last_collect": None,
                "production": FARM_BASE_PRODUCTION
            },
            "created_at": datetime.now().isoformat(),
            "messages_count": 0,
            "last_message_time": None
        }
        save_data(USERS_FILE, users)
    
    user_data = users[user_id]
    current_time = datetime.now()
    
    # Очистка просроченных мутов
    if 'mutes' in user_data:
        user_data['mutes'] = [
            mute for mute in user_data.get('mutes', []) 
            if datetime.fromisoformat(mute) > current_time
        ]
    
    # Проверка VIP
    if user_data.get('vip_until'):
        vip_until = datetime.fromisoformat(user_data['vip_until'])
        if vip_until < current_time:
            user_data['vip'] = False
            user_data['vip_until'] = None
    
    save_data(USERS_FILE, users)
    return users[user_id]

def update_user(user_id: int, data: Dict[str, Any]):
    """Обновляет данные пользователя"""
    users = load_data(USERS_FILE)
    users[str(user_id)] = data
    save_data(USERS_FILE, users)

def add_balance(user_id: int, amount: int) -> int:
    """Добавляет ириски"""
    user = get_user(user_id)
    user['balance'] += amount
    update_user(user_id, user)
    return user['balance']

def add_gold(user_id: int, amount: int) -> int:
    """Добавляет золото"""
    user = get_user(user_id)
    user['gold_balance'] += amount
    update_user(user_id, user)
    return user['gold_balance']

def add_exp(user_id: int, exp: int) -> int:
    """Добавляет опыт"""
    user = get_user(user_id)
    user['exp'] += exp
    
    while user['exp'] >= user.get('exp_to_next', 100):
        user['exp'] -= user.get('exp_to_next', 100)
        user['level'] += 1
        user['exp_to_next'] = int(user.get('exp_to_next', 100) * 1.5)
    
    update_user(user_id, user)
    return user['level']

def add_warn(user_id: int) -> bool:
    """Добавляет предупреждение, возвращает True если достигнут лимит"""
    user = get_user(user_id)
    user['warns'] += 1
    
    if user['warns'] >= MAX_WARNS:
        user['warns'] = 0
        update_user(user_id, user)
        return True
    
    update_user(user_id, user)
    return False

def is_muted(user_id: int) -> bool:
    """Проверяет, замьючен ли пользователь"""
    user = get_user(user_id)
    current_time = datetime.now()
    for mute_time in user.get('mutes', []):
        if datetime.fromisoformat(mute_time) > current_time:
            return True
    return False

# ============ ГРУППЫ ============

def get_group(group_id: int) -> Dict[str, Any]:
    """Получает данные группы"""
    groups = load_data(GROUPS_FILE)
    group_id = str(group_id)
    
    if group_id not in groups:
        groups[group_id] = {
            "settings": {
                "welcome": "Добро пожаловать в чат",
                "welcome_enabled": False,
                "rules": "Правила чата:\n1. Без мата\n2. Без спама\n3. Будьте вежливы",
                "bad_words_filter": True,
                "antispam": True,
                "spam_interval": 5,
                "max_messages": 5
            },
            "admins": [],
            "banned_users": []
        }
        save_data(GROUPS_FILE, groups)
    
    return groups[group_id]

def update_group(group_id: int, data: Dict[str, Any]):
    """Обновляет данные группы"""
    groups = load_data(GROUPS_FILE)
    groups[str(group_id)] = data
    save_data(GROUPS_FILE, groups)

def is_admin(user_id: int, chat_id: int) -> bool:
    """Проверяет, является ли пользователь администратором"""
    group = get_group(chat_id)
    return user_id in group.get('admins', [])

# ============ МАГАЗИН ============

def get_shop_items() -> Dict[str, Any]:
    """Получает товары магазина"""
    items = load_data(SHOP_FILE)
    if not items:
        items = {
            "vip_7": {
                "name": "VIP на 7 дней",
                "price": 140,
                "type": "vip",
                "days": 7,
                "emoji": "👑"
            },
            "vip_30": {
                "name": "VIP на 30 дней",
                "price": 500,
                "type": "vip",
                "days": 30,
                "emoji": "👑"
            },
            "vip_90": {
                "name": "VIP на 90 дней",
                "price": 1200,
                "type": "vip",
                "days": 90,
                "emoji": "👑"
            },
            "vip_365": {
                "name": "VIP на год",
                "price": 4000,
                "type": "vip",
                "days": 365,
                "emoji": "👑"
            },
            "color_red": {
                "name": "Красный цвет ника",
                "price": 200,
                "type": "color",
                "color": "red",
                "emoji": "🔴"
            },
            "color_gold": {
                "name": "Золотой цвет ника",
                "price": 500,
                "type": "color",
                "color": "gold",
                "emoji": "🌟"
            },
            "color_blue": {
                "name": "Синий цвет ника",
                "price": 150,
                "type": "color",
                "color": "blue",
                "emoji": "🔵"
            },
            "color_pink": {
                "name": "Розовый цвет ника",
                "price": 200,
                "type": "color",
                "color": "pink",
                "emoji": "🩷"
            }
        }
        save_data(SHOP_FILE, items)
    return items

# ============ БИРЖА ============

def get_market_orders() -> Dict[str, Any]:
    """Получает ордера биржи"""
    orders = load_data(MARKET_FILE)
    if not orders:
        orders = {"buy": [], "sell": []}
        save_data(MARKET_FILE, orders)
    return orders

def save_market_orders(orders: Dict[str, Any]):
    """Сохраняет ордера биржи"""
    save_data(MARKET_FILE, orders)

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def has_bad_words(text: str) -> List[str]:
    """Проверяет наличие плохих слов"""
    found = []
    text_lower = text.lower()
    for word in BAD_WORDS:
        if word in text_lower:
            found.append(word)
    return found

def format_user(user) -> str:
    """Форматирует имя пользователя"""
    if user.username:
        return f"@{user.username}"
    return user.first_name or "Пользователь"

def format_time(seconds: int) -> str:
    """Форматирует секунды в читаемый вид"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}ч")
    if minutes > 0:
        parts.append(f"{minutes}м")
    if secs > 0 and hours == 0:
        parts.append(f"{secs}с")
    
    return " ".join(parts) if parts else "0с"

def get_color_name(color: str) -> str:
    """Возвращает название цвета"""
    return COLORS.get(color, "Белый")

def format_medals(medals: List[str]) -> str:
    """Форматирует список медалей"""
    if not medals:
        return "Нет"
    return ", ".join(medals)

def get_progress_bar(current: int, total: int, length: int = 20) -> str:
    """Создает прогресс-бар"""
    progress = int((current / total) * length)
    return "█" * progress + "░" * (length - progress)

# ==================== МИДЛВАРЬ ДЛЯ АНТИСПАМА ====================

user_messages = {}

class AntiSpamMiddleware(BaseMiddleware):
    """Мидлварь для антиспама и фильтра мата"""
    
    async def __call__(
        self,
        handler,
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        if not event.text or event.from_user.is_bot:
            return await handler(event, data)
        
        # Проверка на мут
        if is_muted(event.from_user.id):
            await event.delete()
            await event.answer(
                f"{event.from_user.first_name}, вы замьючены",
                show_alert=False
            )
            return
        
        # Только для групп
        if event.chat.type in ['group', 'supergroup']:
            group = get_group(event.chat.id)
            
            # Фильтр плохих слов
            if group['settings'].get('bad_words_filter', True):
                bad_words = has_bad_words(event.text)
                if bad_words:
                    await event.delete()
                    if add_warn(event.from_user.id):
                        until = datetime.now() + timedelta(minutes=MUTE_DEFAULT_MINUTES)
                        user = get_user(event.from_user.id)
                        user['mutes'].append(until.isoformat())
                        update_user(event.from_user.id, user)
                        await event.answer(
                            f"{event.from_user.first_name} замучен за мат (автоматически)"
                        )
                    else:
                        user = get_user(event.from_user.id)
                        await event.answer(
                            f"{event.from_user.first_name}, не используйте плохие слова ({user['warns']}/{MAX_WARNS})"
                        )
                    return
            
            # Антиспам
            if group['settings'].get('antispam', True):
                user_id = event.from_user.id
                current_time = datetime.now()
                interval = group['settings'].get('spam_interval', 5)
                
                if user_id not in user_messages:
                    user_messages[user_id] = []
                
                user_messages[user_id] = [
                    t for t in user_messages[user_id] 
                    if (current_time - t).total_seconds() < interval
                ]
                
                user_messages[user_id].append(current_time)
                
                max_messages = group['settings'].get('max_messages', 5)
                if len(user_messages[user_id]) > max_messages:
                    await event.delete()
                    await event.answer(
                        f"{event.from_user.first_name}, не спамьте",
                        show_alert=False
                    )
                    return
        
        # Добавление опыта за сообщение
        if random.random() < 0.3:
            exp = random.randint(1, 5)
            new_level = add_exp(event.from_user.id, exp)
            if new_level > get_user(event.from_user.id)['level']:
                user = get_user(event.from_user.id)
                bonus = user['level'] * 10
                user['balance'] += bonus
                update_user(event.from_user.id, user)
                await event.reply(
                    f"Поздравляю! Вы достигли уровня {user['level']}\n"
                    f"Бонус: {bonus} ирисок"
                )
        
        return await handler(event, data)

# ==================== ИНИЦИАЛИЗАЦИЯ БОТА ====================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Подключаем мидлварь
dp.message.middleware(AntiSpamMiddleware())

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ КОМАНД ====================

async def find_user(message: Message) -> tuple[Optional[int], Optional[types.User]]:
    """
    Находит пользователя тремя способами:
    1. Ответ на сообщение
    2. @username
    3. Telegram ID
    """
    # Способ 1: Ответ на сообщение
    if message.reply_to_message:
        return message.reply_to_message.from_user.id, message.reply_to_message.from_user
    
    # Способ 2 и 3: Парсим текст
    args = message.text.split()
    if len(args) < 2:
        return None, None
    
    target = args[1]
    
    # Способ 2: @username
    if target.startswith('@'):
        username = target[1:]
        try:
            user = await bot.get_chat(username)
            return user.id, user
        except:
            return None, None
    
    # Способ 3: Telegram ID
    if target.isdigit():
        try:
            user = await bot.get_chat(int(target))
            return int(target), user
        except:
            return int(target), None
    
    return None, None

def create_shop_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру магазина"""
    items = get_shop_items()
    keyboard = []
    row = []
    for i, (item_id, item) in enumerate(items.items()):
        row.append(InlineKeyboardButton(
            text=f"{item['emoji']} {item['name']}",
            callback_data=f"buy_{item_id}"
        ))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ==================== ОСНОВНЫЕ КОМАНДЫ ====================

@dp.message(CommandStart())
async def start_command(message: Message):
    """Команда /start"""
    user_id = message.from_user.id
    user = get_user(user_id)
    
    # Реферальная система
    args = message.text.split()
    if len(args) > 1 and args[1].isdigit() and int(args[1]) != user_id:
        referrer_id = int(args[1])
        referrer = get_user(referrer_id)
        if user_id not in referrer.get('referrals', []):
            referrer['referrals'].append(user_id)
            referrer['balance'] += REFERRAL_REWARD
            update_user(referrer_id, referrer)
            user['referrer'] = referrer_id
            update_user(user_id, user)
            try:
                await bot.send_message(
                    referrer_id,
                    f"Пользователь {format_user(message.from_user)} перешел по вашей реферальной ссылке\n"
                    f"Вы получили {REFERRAL_REWARD} ирисок"
                )
            except:
                pass
    
    welcome_text = (
        f"Привет, {message.from_user.first_name}!\n\n"
        f"Это {BOT_NAME} - бот-менеджер для чатов\n"
        f"Вот что я умею:\n"
        f"баланс - баланс ирисок\n"
        f"вип - информация о VIP статусе\n"
        f"инфо - информация о пользователе\n"
        f"ежедневно - ежедневный бонус\n"
        f"магазин - магазин\n"
        f"реферал - ваша реферальная ссылка\n"
        f"ферма - ферма для заработка\n"
        f"помощь - все команды\n\n"
        f"Удачи в использовании"
    )
    await message.reply(welcome_text)

@dp.message(Command("помощь"))
async def help_command(message: Message):
    """Команда /помощь"""
    help_text = (
        f"Список всех команд {BOT_NAME}:\n\n"
        "Экономика:\n"
        "баланс - показать баланс\n"
        "передать пользователь сумма - передать ириски\n"
        "ежедневно - ежедневный бонус\n"
        "магазин - магазин\n"
        "купить ID - купить товар\n"
        "ферма - ферма для заработка\n"
        "собрать - собрать урожай с фермы\n"
        "улучшитьферму - улучшить ферму\n"
        "биржа - биржа\n"
        "продать количество цена - выставить на продажу\n"
        "купитьбиржу количество цена - купить\n\n"
        "VIP:\n"
        "вип - информация о VIP\n"
        "купитьвип дни - купить VIP\n\n"
        "Профиль:\n"
        "инфо пользователь - информация о пользователе\n"
        "уровень - уровень и опыт\n"
        "реферал - реферальная ссылка\n\n"
        "Модерация:\n"
        "предупредить пользователь - выдать предупреждение\n"
        "мут пользователь минуты - замутить\n"
        "размут пользователь - размутить\n"
        "кик пользователь - кикнуть\n"
        "бан пользователь - забанить\n"
        "разбан пользователь - разбанить\n"
        "приветствие текст - установить приветствие\n"
        "правила текст - установить правила\n"
        "включитьприветствие - включить приветствие\n"
        "выключитьприветствие - выключить приветствие\n"
        "добавитьадмина пользователь - добавить админа\n"
        "удалитьадмина пользователь - удалить админа\n\n"
        "Развлечения:\n"
        "медаль пользователь название - выдать медаль\n"
        "медали - список медалей\n"
        "монетка - подбросить монетку\n"
        "кости - игра в кости"
    )
    await message.reply(help_text)

# ==================== ЭКОНОМИКА ====================

@dp.message(Command("баланс"))
async def balance_command(message: Message):
    """Команда /баланс"""
    user_id, user_obj = await find_user(message)
    
    if user_id:
        target = get_user(user_id)
        name = format_user(user_obj) if user_obj else f"ID: {user_id}"
        await message.reply(
            f"Баланс пользователя {name}:\n"
            f"Ириски: {target['balance']}\n"
            f"Золото: {target['gold_balance']}\n"
            f"Репутация: {target['reputation']}"
        )
    else:
        user = get_user(message.from_user.id)
        await message.reply(
            f"Ваш баланс:\n"
            f"Ириски: {user['balance']}\n"
            f"Золото: {user['gold_balance']}\n"
            f"Репутация: {user['reputation']}\n"
            f"Уровень: {user['level']}"
        )

@dp.message(Command("передать"))
async def give_command(message: Message):
    """Команда /передать"""
    args = message.text.split()
    if len(args) < 3:
        await message.reply("Использование: передать пользователь сумма")
        return
    
    try:
        amount = int(args[-1])
        if amount <= 0:
            await message.reply("Сумма должна быть положительной")
            return
    except ValueError:
        await message.reply("Укажите корректное число")
        return
    
    target_id, target_obj = await find_user(message)
    if not target_id:
        await message.reply("Пользователь не найден. Укажите @username, ID или ответьте на сообщение")
        return
    
    if target_id == message.from_user.id:
        await message.reply("Нельзя передать ириски самому себе")
        return
    
    sender = get_user(message.from_user.id)
    target = get_user(target_id)
    
    if sender['balance'] < amount:
        await message.reply(f"Недостаточно средств. Ваш баланс: {sender['balance']}")
        return
    
    sender['balance'] -= amount
    target['balance'] += amount
    update_user(message.from_user.id, sender)
    update_user(target_id, target)
    
    name = format_user(target_obj) if target_obj else f"ID: {target_id}"
    await message.reply(
        f"Передано {amount} ирисок пользователю {name}\n"
        f"Ваш новый баланс: {sender['balance']}"
    )

@dp.message(Command("ежедневно"))
async def daily_command(message: Message):
    """Команда /ежедневно"""
    user = get_user(message.from_user.id)
    last_daily = user.get('daily_last')
    
    if last_daily:
        last_time = datetime.fromisoformat(last_daily)
        if datetime.now() - last_time < timedelta(hours=24):
            remaining = timedelta(hours=24) - (datetime.now() - last_time)
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            await message.reply(
                f"Вы уже получили ежедневный бонус\nСледующий через {hours}ч {minutes}м"
            )
            return
    
    # VIP получает в 2 раза больше
    bonus = DAILY_REWARD + (user['level'] - 1) * 5
    if user['vip']:
        bonus *= 2
    
    user['balance'] += bonus
    user['daily_last'] = datetime.now().isoformat()
    update_user(message.from_user.id, user)
    
    await message.reply(
        f"Вы получили {bonus} ирисок\n"
        f"Баланс: {user['balance']} ирисок"
    )

# ==================== VIP ====================

@dp.message(Command("вип"))
async def vip_command(message: Message):
    """Команда /вип"""
    user_id, user_obj = await find_user(message)
    
    if user_id:
        target = get_user(user_id)
        name = format_user(user_obj) if user_obj else f"ID: {user_id}"
        
        if target['vip'] and target.get('vip_until'):
            until = datetime.fromisoformat(target['vip_until'])
            days_left = (until - datetime.now()).days
            await message.reply(
                f"{name} - VIP\n"
                f"До {until.strftime('%d.%m.%Y')}\n"
                f"Осталось дней: {days_left}"
            )
        else:
            await message.reply(f"{name} не имеет VIP статуса")
        return
    
    user = get_user(message.from_user.id)
    if user['vip'] and user.get('vip_until'):
        until = datetime.fromisoformat(user['vip_until'])
        days_left = (until - datetime.now()).days
        color_name = get_color_name(user.get('nick_color', 'white'))
        
        await message.reply(
            f"Ваш VIP статус\n"
            f"Действует до: {until.strftime('%d.%m.%Y')}\n"
            f"Осталось дней: {days_left}\n"
            f"Цвет ника: {color_name}\n\n"
            f"Преимущества VIP:\n"
            f"✅ Увеличенный ежедневный бонус (x2)\n"
            f"✅ Цветной ник в чате\n"
            f"✅ Приоритетная поддержка\n"
            f"✅ Скидка 10% в магазине\n"
            f"✅ Ферма до 15 уровня"
        )
    else:
        await message.reply(
            "У вас нет VIP статуса\n\n"
            "Купить VIP:\n"
            "купитьвип 7 - 140 ирисок\n"
            "купитьвип 30 - 500 ирисок\n"
            "купитьвип 90 - 1200 ирисок\n"
            "купитьвип 365 - 4000 ирисок\n\n"
            "Также можно купить в магазине: магазин"
        )

@dp.message(Command("купитьвип"))
async def buy_vip_command(message: Message):
    """Команда /купитьвип"""
    args = message.text.split()
    if len(args) < 2:
        await message.reply("Использование: купитьвип дни")
        return
    
    try:
        days = int(args[1])
        if days not in [7, 30, 90, 365]:
            await message.reply("Доступные периоды: 7, 30, 90, 365 дней")
            return
    except ValueError:
        await message.reply("Укажите корректное число дней")
        return
    
    price = days * VIP_PRICE_PER_DAY
    user = get_user(message.from_user.id)
    
    if user['balance'] < price:
        await message.reply(
            f"Недостаточно средств\nНужно: {price}, у вас: {user['balance']}"
        )
        return
    
    user['balance'] -= price
    user['vip'] = True
    user['vip_until'] = (datetime.now() + timedelta(days=days)).isoformat()
    update_user(message.from_user.id, user)
    
    await message.reply(
        f"VIP приобретен на {days} дней\n"
        f"Использовано: {price} ирисок\n"
        f"Действует до: {datetime.fromisoformat(user['vip_until']).strftime('%d.%m.%Y')}"
    )

# ==================== МАГАЗИН ====================

@dp.message(Command("магазин"))
async def shop_command(message: Message):
    """Команда /магазин"""
    items = get_shop_items()
    keyboard = create_shop_keyboard()
    
    shop_text = "🏪 Магазин ирисок\n\n"
    for item_id, item in items.items():
        shop_text += f"{item['emoji']} {item['name']}\n"
        shop_text += f"   Цена: {item['price']} ирисок\n"
        shop_text += f"   ID: {item_id}\n\n"
    
    await message.reply(shop_text, reply_markup=keyboard)

@dp.callback_query(F.data.startswith("buy_"))
async def buy_callback(callback: CallbackQuery):
    """Обработчик покупки через кнопки"""
    item_id = callback.data.replace("buy_", "")
    items = get_shop_items()
    
    if item_id not in items:
        await callback.answer("Товар не найден")
        return
    
    item = items[item_id]
    user = get_user(callback.from_user.id)
    
    # Скидка для VIP
    price = item['price']
    if user['vip']:
        price = int(price * 0.9)  # 10% скидка
    
    if user['balance'] < price:
        await callback.answer(f"Недостаточно средств. Нужно: {price}")
        return
    
    user['balance'] -= price
    
    if item['type'] == 'vip':
        days = item['days']
        user['vip'] = True
        if user.get('vip_until'):
            current_until = datetime.fromisoformat(user['vip_until'])
            if current_until > datetime.now():
                new_until = current_until + timedelta(days=days)
            else:
                new_until = datetime.now() + timedelta(days=days)
        else:
            new_until = datetime.now() + timedelta(days=days)
        user['vip_until'] = new_until.isoformat()
        
    elif item['type'] == 'color':
        user['nick_color'] = item['color']
    
    update_user(callback.from_user.id, user)
    
    await callback.answer(f"Вы купили {item['name']}!")
    await callback.message.edit_text(
        f"✅ Вы купили {item['emoji']} {item['name']}!\n"
        f"Остаток: {user['balance']} ирисок"
    )

@dp.message(Command("купить"))
async def buy_command(message: Message):
    """Команда /купить"""
    args = message.text.split()
    if len(args) < 2:
        await message.reply("Использование: купить ID_товара")
        return
    
    item_id = args[1]
    items = get_shop_items()
    
    if item_id not in items:
        await message.reply("Товар не найден. Список товаров: магазин")
        return
    
    item = items[item_id]
    user = get_user(message.from_user.id)
    
    price = item['price']
    if user['vip']:
        price = int(price * 0.9)
    
    if user['balance'] < price:
        await message.reply(
            f"Недостаточно средств\nНужно: {price}, у вас: {user['balance']}"
        )
        return
    
    user['balance'] -= price
    
    if item['type'] == 'vip':
        days = item['days']
        user['vip'] = True
        if user.get('vip_until'):
            current_until = datetime.fromisoformat(user['vip_until'])
            if current_until > datetime.now():
                new_until = current_until + timedelta(days=days)
            else:
                new_until = datetime.now() + timedelta(days=days)
        else:
            new_until = datetime.now() + timedelta(days=days)
        user['vip_until'] = new_until.isoformat()
        
    elif item['type'] == 'color':
        user['nick_color'] = item['color']
    
    update_user(message.from_user.id, user)
    
    await message.reply(
        f"✅ Вы купили {item['emoji']} {item['name']}!\n"
        f"Остаток: {user['balance']} ирисок"
    )

# ==================== ПРОФИЛЬ ====================

@dp.message(Command("инфо"))
async def info_command(message: Message):
    """Команда /инфо"""
    user_id, user_obj = await find_user(message)
    
    if not user_id:
        user_id = message.from_user.id
        user_obj = message.from_user
    
    user = get_user(user_id)
    name = format_user(user_obj) if user_obj else f"ID: {user_id}"
    color_name = get_color_name(user.get('nick_color', 'white'))
    medals = format_medals(user.get('medals', []))
    
    info_text = (
        f"Информация о пользователе\n"
        f"Имя: {user_obj.first_name if user_obj else 'Неизвестно'}\n"
        f"ID: {user_id}\n\n"
        f"Ириски: {user['balance']}\n"
        f"Репутация: {user['reputation']}\n"
        f"Уровень: {user['level']}\n"
        f"VIP: {'Да' if user['vip'] else 'Нет'}\n"
        f"Цвет ника: {color_name}\n"
        f"Предупреждения: {user['warns']}/{MAX_WARNS}\n"
        f"Медали: {medals}\n"
        f"Приглашено: {len(user.get('referrals', []))}"
    )
    
    await message.reply(info_text)

@dp.message(Command("уровень"))
async def level_command(message: Message):
    """Команда /уровень"""
    user = get_user(message.from_user.id)
    progress = int((user['exp'] / user['exp_to_next']) * 20)
    bar = "█" * progress + "░" * (20 - progress)
    
    await message.reply(
        f"Ваш прогресс\n\n"
        f"Уровень: {user['level']}\n"
        f"Опыт: {user['exp']} / {user['exp_to_next']}\n"
        f"[{bar}] {int((user['exp'] / user['exp_to_next']) * 100)}%\n\n"
        f"Награда за следующий уровень: {user['level'] * 10} ирисок"
    )

@dp.message(Command("реферал"))
async def referral_command(message: Message):
    """Команда /реферал"""
    user_id = message.from_user.id
    user = get_user(user_id)
    
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={user_id}"
    
    referral_text = (
        f"Реферальная программа\n\n"
        f"Приглашайте друзей и получайте {REFERRAL_REWARD} ирисок за каждого\n\n"
        f"Ваша ссылка:\n{link}\n\n"
        f"Приглашено: {len(user.get('referrals', []))} человек"
    )
    
    await message.reply(referral_text)

# ==================== ФЕРМА ====================

@dp.message(Command("ферма"))
async def farm_command(message: Message):
    """Команда /ферма"""
    user = get_user(message.from_user.id)
    farm = user.get('farm', {"level": 1, "last_collect": None, "production": FARM_BASE_PRODUCTION})
    
    production = farm.get('production', FARM_BASE_PRODUCTION) * (1 + (farm.get('level', 1) - 1) * 0.5)
    production = int(production)
    
    last_collect = farm.get('last_collect')
    if last_collect:
        last_time = datetime.fromisoformat(last_collect)
        hours_passed = (datetime.now() - last_time).total_seconds() / 3600
        if hours_passed > 24:
            hours_passed = 24
        pending = int(production * hours_passed)
    else:
        pending = 0
    
    max_level = 15 if user['vip'] else 10
    
    await message.reply(
        f"Ваша ферма\n\n"
        f"Уровень: {farm.get('level', 1)} (макс: {max_level})\n"
        f"Производство: {production} ирисок/час\n"
        f"Готово к сбору: {pending} ирисок\n\n"
        f"Для сбора используйте: собрать\n"
        f"Для улучшения: улучшитьферму (стоит: {farm.get('level', 1) * 100} ирисок)"
    )

@dp.message(Command("собрать"))
async def collect_command(message: Message):
    """Команда /собрать"""
    user = get_user(message.from_user.id)
    farm = user.get('farm', {"level": 1, "last_collect": None, "production": FARM_BASE_PRODUCTION})
    
    production = farm.get('production', FARM_BASE_PRODUCTION) * (1 + (farm.get('level', 1) - 1) * 0.5)
    production = int(production)
    
    last_collect = farm.get('last_collect')
    if last_collect:
        last_time = datetime.fromisoformat(last_collect)
        hours_passed = (datetime.now() - last_time).total_seconds() / 3600
        if hours_passed > 24:
            hours_passed = 24
        pending = int(production * hours_passed)
    else:
        pending = 0
    
    if pending == 0:
        await message.reply("Нет ирисок для сбора. Подождите, пока ферма наработает")
        return
    
    user['balance'] += pending
    farm['last_collect'] = datetime.now().isoformat()
    user['farm'] = farm
    update_user(message.from_user.id, user)
    
    await message.reply(
        f"Собрано {pending} ирисок с фермы\n"
        f"Баланс: {user['balance']} ирисок"
    )

@dp.message(Command("улучшитьферму"))
async def upgrade_farm_command(message: Message):
    """Команда /улучшитьферму"""
    user = get_user(message.from_user.id)
    farm = user.get('farm', {"level": 1, "last_collect": None, "production": FARM_BASE_PRODUCTION})
    
    current_level = farm.get('level', 1)
    max_level = 15 if user['vip'] else 10
    
    if current_level >= max_level:
        await message.reply(f"Достигнут максимальный уровень фермы ({max_level})")
        return
    
    price = current_level * 100
    
    if user['balance'] < price:
        await message.reply(
            f"Недостаточно ирисок\nНужно: {price}, у вас: {user['balance']}"
        )
        return
    
    user['balance'] -= price
    farm['level'] = current_level + 1
    farm['production'] = FARM_BASE_PRODUCTION * (1 + (farm['level'] - 1) * 0.5)
    farm['production'] = int(farm['production'])
    user['farm'] = farm
    update_user(message.from_user.id, user)
    
    await message.reply(
        f"Ферма улучшена до уровня {farm['level']}\n"
        f"Производство: {farm['production']} ирисок/час"
    )

# ==================== БИРЖА ====================

@dp.message(Command("биржа"))
async def market_command(message: Message):
    """Команда /биржа"""
    orders = get_market_orders()
    
    market_text = "Биржа ирисок\n\n"
    market_text += "На продажу:\n"
    if orders.get('sell'):
        for order in orders['sell'][:5]:
            user = get_user(order['user_id'])
            user_name = user.get('nickname') or f"ID: {order['user_id']}"
            market_text += f" {order['amount']} ирисок за {order['price']} золота (от {user_name})\n"
    else:
        market_text += "Нет ордеров на продажу\n"
    
    market_text += "\nНа покупку:\n"
    if orders.get('buy'):
        for order in orders['buy'][:5]:
            user = get_user(order['user_id'])
            user_name = user.get('nickname') or f"ID: {order['user_id']}"
            market_text += f" {order['amount']} ирисок за {order['price']} золота (от {user_name})\n"
    else:
        market_text += "Нет ордеров на покупку\n"
    
    market_text += "\nИспользуйте:\n"
    market_text += "продать количество цена - выставить на продажу\n"
    market_text += "купитьбиржу количество цена - купить"
    
    await message.reply(market_text)

@dp.message(Command("продать"))
async def sell_command(message: Message):
    """Команда /продать"""
    args = message.text.split()
    if len(args) < 3:
        await message.reply("Использование: продать количество цена_за_1_ириску")
        return
    
    try:
        amount = int(args[1])
        price = int(args[2])
        if amount <= 0 or price <= 0:
            await message.reply("Количество и цена должны быть положительными")
            return
    except ValueError:
        await message.reply("Укажите корректные числа")
        return
    
    user = get_user(message.from_user.id)
    if user['balance'] < amount:
        await message.reply(f"Недостаточно ирисок. У вас: {user['balance']}")
        return
    
    user['balance'] -= amount
    update_user(message.from_user.id, user)
    
    orders = get_market_orders()
    orders['sell'].append({
        "user_id": message.from_user.id,
        "amount": amount,
        "price": price,
        "created_at": datetime.now().isoformat()
    })
    save_market_orders(orders)
    
    await message.reply(
        f"Ордер создан\n"
        f"{amount} ирисок по {price} золота за штуку"
    )

@dp.message(Command("купитьбиржу"))
async def buy_market_command(message: Message):
    """Команда /купитьбиржу"""
    args = message.text.split()
    if len(args) < 3:
        await message.reply("Использование: купитьбиржу количество цена_за_1_ириску")
        return
    
    try:
        amount = int(args[1])
        price = int(args[2])
        if amount <= 0 or price <= 0:
            await message.reply("Количество и цена должны быть положительными")
            return
    except ValueError:
        await message.reply("Укажите корректные числа")
        return
    
    user = get_user(message.from_user.id)
    total_price = amount * price
    
    if user['gold_balance'] < total_price:
        await message.reply(
            f"Недостаточно золота. Нужно: {total_price}, у вас: {user['gold_balance']}"
        )
        return
    
    user['gold_balance'] -= total_price
    user['balance'] += amount
    update_user(message.from_user.id, user)
    
    await message.reply(
        f"Куплено {amount} ирисок за {total_price} золота\n"
        f"Новый баланс: {user['balance']} ирисок"
    )

# ==================== МОДЕРАЦИЯ ====================

@dp.message(Command("предупредить"))
async def warn_command(message: Message):
    """Команда /предупредить"""
    target_id, target_obj = await find_user(message)
    if not target_id:
        await message.reply("Пользователь не найден. Укажите @username, ID или ответьте на сообщение")
        return
    
    if target_id == message.from_user.id:
        await message.reply("Нельзя предупредить самого себя")
        return
    
    target = get_user(target_id)
    target['warns'] += 1
    
    if target['warns'] >= MAX_WARNS:
        target['warns'] = 0
        until = datetime.now() + timedelta(minutes=MUTE_DEFAULT_MINUTES)
        target['mutes'].append(until.isoformat())
        update_user(target_id, target)
        await message.reply(
            f"Пользователь {format_user(target_obj if target_obj else target_id)} получил {MAX_WARNS} предупреждений и замучен на {MUTE_DEFAULT_MINUTES} минут"
        )
    else:
        update_user(target_id, target)
        await message.reply(
            f"Пользователь {format_user(target_obj if target_obj else target_id)} получил предупреждение ({target['warns']}/{MAX_WARNS})"
        )

@dp.message(Command("мут"))
async def mute_command(message: Message):
    """Команда /мут"""
    target_id, target_obj = await find_user(message)
    if not target_id:
        await message.reply("Пользователь не найден. Укажите @username, ID или ответьте на сообщение")
        return
    
    args = message.text.split()
    minutes = MUTE_DEFAULT_MINUTES
    if len(args) > 2:
        try:
            minutes = int(args[2])
        except ValueError:
            await message.reply("Укажите число минут")
            return
    
    target = get_user(target_id)
    until = datetime.now() + timedelta(minutes=minutes)
    target['mutes'].append(until.isoformat())
    update_user(target_id, target)
    
    await message.reply(
        f"Пользователь {format_user(target_obj if target_obj else target_id)} замучен на {minutes} минут"
    )

@dp.message(Command("размут"))
async def unmute_command(message: Message):
    """Команда /размут"""
    target_id, target_obj = await find_user(message)
    if not target_id:
        await message.reply("Пользователь не найден. Укажите @username, ID или ответьте на сообщение")
        return
    
    target = get_user(target_id)
    target['mutes'] = []
    update_user(target_id, target)
    
    await message.reply(
        f"Пользователь {format_user(target_obj if target_obj else target_id)} размучен"
    )

@dp.message(Command("кик"))
async def kick_command(message: Message):
    """Команда /кик"""
    target_id, target_obj = await find_user(message)
    if not target_id:
        await message.reply("Пользователь не найден. Укажите @username, ID или ответьте на сообщение")
        return
    
    try:
        await bot.kick_chat_member(message.chat.id, target_id)
        await bot.unban_chat_member(message.chat.id, target_id)
        await message.reply(
            f"Пользователь {format_user(target_obj if target_obj else target_id)} кикнут"
        )
    except Exception as e:
        await message.reply(f"Ошибка: {str(e)}")

@dp.message(Command("бан"))
async def ban_command(message: Message):
    """Команда /бан"""
    target_id, target_obj = await find_user(message)
    if not target_id:
        await message.reply("Пользователь не найден. Укажите @username, ID или ответьте на сообщение")
        return
    
    try:
        await bot.kick_chat_member(message.chat.id, target_id)
        await message.reply(
            f"Пользователь {format_user(target_obj if target_obj else target_id)} забанен"
        )
    except Exception as e:
        await message.reply(f"Ошибка: {str(e)}")

@dp.message(Command("разбан"))
async def unban_command(message: Message):
    """Команда /разбан"""
    target_id, target_obj = await find_user(message)
    if not target_id:
        await message.reply("Пользователь не найден. Укажите @username, ID или ответьте на сообщение")
        return
    
    try:
        await bot.unban_chat_member(message.chat.id, target_id)
        await message.reply(
            f"Пользователь {format_user(target_obj if target_obj else target_id)} разбанен"
        )
    except Exception as e:
        await message.reply(f"Ошибка: {str(e)}")

# ==================== НАСТРОЙКИ ГРУППЫ ====================

@dp.message(Command("приветствие"))
async def set_welcome_command(message: Message):
    """Команда /приветствие"""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Использование: приветствие Текст приветствия")
        return
    
    group = get_group(message.chat.id)
    group['settings']['welcome'] = args[1]
    update_group(message.chat.id, group)
    await message.reply("Приветствие сохранено")

@dp.message(Command("включитьприветствие"))
async def welcome_on_command(message: Message):
    """Команда /включитьприветствие"""
    group = get_group(message.chat.id)
    group['settings']['welcome_enabled'] = True
    update_group(message.chat.id, group)
    await message.reply("Приветствие включено")

@dp.message(Command("выключитьприветствие"))
async def welcome_off_command(message: Message):
    """Команда /выключитьприветствие"""
    group = get_group(message.chat.id)
    group['settings']['welcome_enabled'] = False
    update_group(message.chat.id, group)
    await message.reply("Приветствие выключено")

@dp.message(Command("правила"))
async def set_rules_command(message: Message):
    """Команда /правила"""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Использование: правила Текст правил")
        return
    
    group = get_group(message.chat.id)
    group['settings']['rules'] = args[1]
    update_group(message.chat.id, group)
    await message.reply("Правила сохранены")

@dp.message(Command("показатьправила"))
async def show_rules_command(message: Message):
    """Команда /показатьправила"""
    group = get_group(message.chat.id)
    rules = group['settings'].get('rules', 'Правила не установлены')
    await message.reply(f"Правила чата:\n\n{rules}")

@dp.message(Command("добавитьадмина"))
async def add_admin_command(message: Message):
    """Команда /добавитьадмина"""
    target_id, target_obj = await find_user(message)
    if not target_id:
        await message.reply("Пользователь не найден. Укажите @username, ID или ответьте на сообщение")
        return
    
    group = get_group(message.chat.id)
    
    if target_id in group['admins']:
        await message.reply("Пользователь уже является администратором")
        return
    
    group['admins'].append(target_id)
    update_group(message.chat.id, group)
    await message.reply(
        f"Пользователь {format_user(target_obj if target_obj else target_id)} добавлен в администраторы"
    )

@dp.message(Command("удалитьадмина"))
async def remove_admin_command(message: Message):
    """Команда /удалитьадмина"""
    target_id, target_obj = await find_user(message)
    if not target_id:
        await message.reply("Пользователь не найден. Укажите @username, ID или ответьте на сообщение")
        return
    
    group = get_group(message.chat.id)
    
    if target_id not in group['admins']:
        await message.reply("Пользователь не является администратором")
        return
    
    group['admins'].remove(target_id)
    update_group(message.chat.id, group)
    await message.reply(
        f"Пользователь {format_user(target_obj if target_obj else target_id)} удален из администраторов"
    )

# ==================== МЕДАЛИ ====================

@dp.message(Command("медаль"))
async def medal_command(message: Message):
    """Команда /медаль"""
    target_id, target_obj = await find_user(message)
    if not target_id:
        await message.reply("Пользователь не найден. Укажите @username, ID или ответьте на сообщение")
        return
    
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.reply("Использование: медаль пользователь Название медали")
        return
    
    medal_name = args[2]
    target = get_user(target_id)
    
    if 'medals' not in target:
        target['medals'] = []
    target['medals'].append(medal_name)
    update_user(target_id, target)
    
    await message.reply(
        f"Пользователю {format_user(target_obj if target_obj else target_id)} выдана медаль: {medal_name}"
    )

@dp.message(Command("медали"))
async def medals_command(message: Message):
    """Команда /медали"""
    user_id, user_obj = await find_user(message)
    if not user_id:
        user_id = message.from_user.id
        user_obj = message.from_user
    
    user = get_user(user_id)
    medals = user.get('medals', [])
    
    if medals:
        medals_text = f"Медали пользователя {format_user(user_obj) if user_obj else f'ID: {user_id}'}:\n\n"
        for medal in medals:
            medals_text += f" {medal}\n"
        await message.reply(medals_text)
    else:
        await message.reply("У пользователя нет медалей")

# ==================== РАЗВЛЕЧЕНИЯ ====================

@dp.message(Command("монетка"))
async def coins_command(message: Message):
    """Команда /монетка"""
    result = random.choice(["Орел", "Решка"])
    emoji = "🪙" if result == "Орел" else "🪙"
    await message.reply(f"{emoji} Выпал: {result}")

@dp.message(Command("кости"))
async def dice_command(message: Message):
    """Команда /кости"""
    value = random.randint(1, 6)
    emojis = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]
    await message.reply(f"🎲 Выпало: {emojis[value-1]} {value}")

# ==================== ОБРАБОТЧИК НОВЫХ УЧАСТНИКОВ ====================

@dp.message(F.new_chat_members)
async def welcome_new_member(message: Message):
    """Приветствие новых участников"""
    group = get_group(message.chat.id)
    
    if not group['settings'].get('welcome_enabled', False):
        return
    
    for new_member in message.new_chat_members:
        if new_member.id == bot.id:
            continue
        
        welcome_text = group['settings'].get('welcome', "Добро пожаловать в чат")
        welcome_text = welcome_text.replace("{name}", new_member.first_name or "Гость")
        
        await message.reply(welcome_text)

# ==================== ЗАПУСК БОТА ====================

async def main():
    print(f"🤖 {BOT_NAME} запущен!")
    print(f"✅ Используйте токен: {BOT_TOKEN[:10]}...")
    print(f"📁 Данные сохраняются в папке: {DATA_DIR}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
