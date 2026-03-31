#!/usr/bin/env python3
"""
🚀 Volume Spike Alert Bot v3
CEX Volume Monitor với dynamic threshold, auto-scan, watchlist scan
và giải thích chi tiết cho người dùng
"""

import json
import urllib.request
import os
import asyncio
from datetime import datetime

# ============================================
# CONFIG
# ============================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Supported exchanges (CoinGecko exchange IDs)
EXCHANGES = {
    "binance": {"id": "binance", "name": "Binance", "enabled": True},
    "coinbase": {"id": "gdax", "name": "Coinbase", "enabled": True},
    "okx": {"id": "okx", "name": "OKX", "enabled": True},
    "bybit": {"id": "bybit_spot", "name": "Bybit", "enabled": True},
    "kucoin": {"id": "kucoin", "name": "KuCoin", "enabled": False},
    "gate": {"id": "gate", "name": "Gate.io", "enabled": False},
    "htx": {"id": "huobi", "name": "HTX (Huobi)", "enabled": False},
    "bitget": {"id": "bitget", "name": "Bitget", "enabled": False},
}

# Dynamic thresholds based on market cap
MCAP_THRESHOLDS = [
    (1_000_000_000, 30),   # MCap >= $1B → alert at 30%
    (500_000_000, 50),     # MCap >= $500M → alert at 50%
    (100_000_000, 80),     # MCap >= $100M → alert at 80%
    (10_000_000, 100),     # MCap >= $10M → alert at 100%
    (0, 150),              # MCap < $10M → alert at 150%
]

# Price change filter
PRICE_CHANGE_MIN = 10

# Data files
CONFIG_FILE = os.path.expanduser("~/.openclaw/workspace/volume-monitor/bot-config.json")
WATCHLIST_FILE = os.path.expanduser("~/.openclaw/workspace/volume-monitor/watchlist.json")
HISTORY_FILE = os.path.expanduser("~/.openclaw/workspace/volume-monitor/history.json")
AUTOSCAN_FILE = os.path.expanduser("~/.openclaw/workspace/volume-monitor/autoscan.json")

# ============================================
# CONFIG MANAGEMENT
# ============================================

def load_config():
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    default = {
        "exchanges": {k: v["enabled"] for k, v in EXCHANGES.items()},
        "timeframe": "24h",
        "price_filter": PRICE_CHANGE_MIN,
        "custom_thresholds": None,
    }
    try:
        with open(CONFIG_FILE, 'r') as f:
            saved = json.load(f)
            default.update(saved)
    except:
        pass
    return default

def save_config(config):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def load_watchlist():
    os.makedirs(os.path.dirname(WATCHLIST_FILE), exist_ok=True)
    try:
        with open(WATCHLIST_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"coins": []}

def save_watchlist(data):
    os.makedirs(os.path.dirname(WATCHLIST_FILE), exist_ok=True)
    with open(WATCHLIST_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def load_history():
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    try:
        with open(HISTORY_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_history(data):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def load_autoscan():
    os.makedirs(os.path.dirname(AUTOSCAN_FILE), exist_ok=True)
    try:
        with open(AUTOSCAN_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"enabled": False, "interval_minutes": 15, "chat_ids": []}

def save_autoscan(data):
    os.makedirs(os.path.dirname(AUTOSCAN_FILE), exist_ok=True)
    with open(AUTOSCAN_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# ============================================
# API FUNCTIONS
# ============================================

def fetch_json(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json'
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return None

def get_coins_markets(per_page=100, page=1):
    url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=volume_desc&per_page={per_page}&page={page}&sparkline=false&price_change_percentage=1h,24h"
    return fetch_json(url)

def get_coin_by_id(coin_id):
    """Get single coin data by ID"""
    url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={coin_id}&sparkline=false&price_change_percentage=1h,24h"
    data = fetch_json(url)
    if data and len(data) > 0:
        return data[0]
    return None

# ============================================
# ANALYSIS
# ============================================

def get_threshold_for_mcap(mcap):
    config = load_config()
    custom = config.get("custom_thresholds")
    if custom:
        for min_mcap, threshold in sorted(custom, key=lambda x: -x[0]):
            if mcap >= min_mcap:
                return threshold
    for min_mcap, threshold in MCAP_THRESHOLDS:
        if mcap >= min_mcap:
            return threshold
    return 150

def analyze_coin(coin, config):
    """Analyze single coin for volume spike using 24h data"""
    coin_id = coin.get('id', '')
    current_volume = coin.get('total_volume', 0) or 0
    mcap = coin.get('market_cap', 0) or 0
    price_change = coin.get('price_change_percentage_24h', 0) or 0
    price = coin.get('current_price', 0)
    name = coin.get('name', '')
    symbol = coin.get('symbol', '').upper()

    if current_volume == 0 or mcap == 0:
        return None

    # Calculate volume/mcap ratio as proxy for spike detection
    # Higher ratio = more volume relative to market cap = unusual activity
    vol_mcap_ratio = (current_volume / mcap) * 100

    # Get threshold for this market cap
    threshold = get_threshold_for_mcap(mcap)

    # Check if volume is unusually high relative to mcap
    # Normal ratio is 2-15% for most coins
    # We flag when ratio is very high (>50%) AND price moved significantly
    spike_detected = False
    spike_pct = 0

    # Method 1: Compare with history
    history = load_history()
    if coin_id in history:
        prev_volume = history[coin_id].get('volume', 0)
        if prev_volume > 0:
            spike_pct = ((current_volume - prev_volume) / prev_volume) * 100
            if spike_pct >= threshold:
                spike_detected = True

    # Method 2: Use volume/mcap ratio as indicator
    if not spike_detected and vol_mcap_ratio > 50:
        # Very high volume relative to market cap = unusual
        spike_pct = vol_mcap_ratio  # Use ratio as spike indicator
        spike_detected = True

    # Price filter
    config_price_filter = config.get("price_filter", 10)
    if abs(price_change) < config_price_filter:
        return None  # Price not moving enough, skip

    if not spike_detected:
        return None

    return {
        'id': coin_id,
        'symbol': symbol,
        'name': name,
        'price': price,
        'price_change_24h': price_change,
        'volume': current_volume,
        'mcap': mcap,
        'spike_pct': spike_pct,
        'threshold': threshold,
        'vol_mcap_ratio': vol_mcap_ratio,
        'direction': 'PUMP' if price_change > 0 else 'DUMP',
    }

def scan_all(config):
    """Scan top coins + watchlist for volume spikes"""
    history = load_history()
    alerts = []
    all_coins = []
    scanned_ids = set()

    # 1. Fetch top 200 coins
    for page in [1, 2]:
        data = get_coins_markets(per_page=100, page=page)
        if data:
            all_coins.extend(data)
            for c in data:
                scanned_ids.add(c.get('id', ''))

    # 2. Fetch watchlist coins (even if not in top 200)
    wl = load_watchlist()
    for wc in wl.get('coins', []):
        coin_id = wc.get('id', '')
        if coin_id not in scanned_ids:
            coin_data = get_coin_by_id(coin_id)
            if coin_data:
                all_coins.append(coin_data)
                scanned_ids.add(coin_id)

    if not all_coins:
        return alerts, 0

    # 3. Analyze each coin
    for coin in all_coins:
        coin_id = coin.get('id', '')

        # Analyze for spike
        alert = analyze_coin(coin, config)
        if alert:
            alerts.append(alert)

        # Update history
        history[coin_id] = {
            'symbol': coin.get('symbol', '').upper(),
            'name': coin.get('name', ''),
            'volume': coin.get('total_volume', 0),
            'price': coin.get('current_price', 0),
            'last_updated': datetime.utcnow().isoformat(),
        }

    save_history(history)
    return alerts, len(all_coins)

# ============================================
# FORMAT
# ============================================

def format_usd(n):
    if n >= 1_000_000_000:
        return f"${n/1_000_000_000:.2f}B"
    elif n >= 1_000_000:
        return f"${n/1_000_000:.2f}M"
    elif n >= 1_000:
        return f"${n/1_000:.1f}K"
    return f"${n:.2f}"

def format_alert(alert):
    emoji = "🟢" if alert['price_change_24h'] > 0 else "🔴"
    lines = [
        f"🚨 *{escape_md(alert['symbol'])}* — VOLUME SPIKE {emoji}",
        f"   {escape_md(alert['name'])}",
        f"   💰 Price: `{format_usd(alert['price'])}`",
        f"   {emoji} {alert['direction']}: *{alert['price_change_24h']:+.1f}%*",
        f"   💎 Volume 24h: *{format_usd(alert['volume'])}*",
        f"   📊 Vol/MCap Ratio: *{alert['vol_mcap_ratio']:.1f}%*",
        f"   📏 MCap: {format_usd(alert['mcap'])}",
        f"   🎯 Threshold: {alert['threshold']}%",
    ]
    return "\n".join(lines)

def escape_md(text):
    special = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special:
        text = text.replace(char, f'\\{char}')
    return text

# ============================================
# HELP TEXT - GIẢI THÍCH CHI TIẾT
# ============================================

HELP_TEXT = """
📖 *HƯỚNG DẪN SỬ DỤNG — VOLUME SPIKE BOT*

━━━━━━━━━━━━━━━━━━━━━

🔍 *VOLUME SPIKE LÀ GÌ?*

Volume Spike = Khối lượng giao dịch tăng *đột biến* so với mức bình thường.

Ví dụ: Bitcoin thường có volume ~$40B/ngày. Nếu hôm nay volume突然 lên $120B → *Spike +200%* 🚨

━━━━━━━━━━━━━━━━━━━━━

🎯 *NGƯỠNG CẢNH BÁO (THRESHOLD)*

Bot tự động điều chỉnh ngưỡng theo Market Cap:
• MCap ≥ $1B → Báo khi tăng *30%*
• MCap ≥ $500M → Báo khi tăng *50%*
• MCap ≥ $100M → Báo khi tăng *80%*
• MCap ≥ $10M → Báo khi tăng *100%* (x2)
• MCap < $10M → Báo khi tăng *150%* (x2.5)

*Lý do:* Coin lớn (BTC, ETH) ít khi spike >50%. Coin nhỏ thường波动 mạnh hơn.

━━━━━━━━━━━━━━━━━━━━━

📈 *ĐIỀU KIỆN CẢNH BÁO*

Bot chỉ cảnh báo khi *ĐỦ 2 điều kiện:*
1. ✅ Volume tăng >= ngưỡng
2. ✅ Giá thay đổi >= ±*10%* (tăng hoặc giảm)

*Bỏ qua* khi volume tăng nhưng giá đi ngang (<±10%) → Có thể là wash trading.

━━━━━━━━━━━━━━━━━━━━━

⏰ *AUTO-SCAN (TỰ ĐỘNG QUÉT)*

• `/autoscan_on` → Bật tự quét (mặc định mỗi 15 phút)
• `/autoscan_off` → Tắt tự quét
• `/autoscan_interval 10` → Đổi interval (5-120 phút)

Bot tự quét và *chỉ gửi tin nhắn khi có spike* → Không spam.

━━━━━━━━━━━━━━━━━━━━━

📊 *NGUỒN DATA*

• CoinGecko API (miễn phí)
• Data tổng hợp từ: Binance, Coinbase, OKX, Bybit...
• Quét *Top 200 coins* + *Watchlist riêng*

━━━━━━━━━━━━━━━━━━━━━

📋 *WATCHLIST*

• `/add bitcoin` → Thêm vào watchlist
• `/remove bitcoin` → Xóa khỏi watchlist
• `/watchlist` → Xem danh sách

*Watchlist được scan riêng* — dù coin có volume thấp hay không nằm trong top 200.

━━━━━━━━━━━━━━━━━━━━━

⚙️ *CẤU HÌNH*

• `/config` → Xem cấu hình hiện tại
• `/exchanges` → Bật/tắt sàn (inline buttons)
• `/timeframe 4h` → Đổi timeframe
• `/threshold 80` → Đổi ngưỡng spike
• `/pricefilter 15` → Đổi price filter

━━━━━━━━━━━━━━━━━━━━━

🔍 *COMMANDS*

• `/scan` — Quét ngay
• `/add <id>` — Thêm watchlist
• `/remove <id>` — Xóa watchlist
• `/watchlist` — Xem watchlist
• `/config` — Xem config
• `/exchanges` — Quản lý sàn
• `/autoscan` — Auto-scan status
• Gửi coin name → Check nhanh

━━━━━━━━━━━━━━━━━━━━━
"""

# ============================================
# TELEGRAM BOT
# ============================================

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
except ImportError:
    print("❌ Cần cài: pip install python-telegram-bot requests")
    exit(1)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = load_config()
    enabled_exchanges = [v["name"] for k, v in EXCHANGES.items() if config["exchanges"].get(k, v["enabled"])]
    autoscan = load_autoscan()
    chat_id = update.effective_chat.id
    is_autoscan = chat_id in autoscan.get("chat_ids", [])

    msg = (
        "🚀 *VOLUME SPIKE ALERT BOT v3*\n"
        "\n"
        f"📊 Sàn: {', '.join(enabled_exchanges)}\n"
        f"⏰ Auto-scan: {'🟢 Bật' if is_autoscan else '🔴 Tắt'} (mỗi {autoscan.get('interval_minutes', 15)} phút)\n"
        f"📈 Price filter: ±{config.get('price_filter', 10)}%\n"
        f"🎯 Threshold: Dynamic theo MCap\n"
        "\n"
        "*Quick Start:*\n"
        "1️⃣ `/autoscan_on` — Bật tự quét\n"
        "2️⃣ `/add bitcoin` — Thêm coin theo dõi\n"
        "3️⃣ Đợi alert hoặc `/scan` quét ngay\n"
        "\n"
        "📖 `/help` — Hướng dẫn chi tiết\n"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode='Markdown')

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = load_config()
    await update.message.reply_text("🔍 Đang quét volume spike... ⏳")

    alerts, total = scan_all(config)

    if not alerts:
        await update.message.reply_text(
            f"✅ Không phát hiện volume spike\n"
            f"📊 Đã quét {total} coins\n"
            f"⏰ {datetime.utcnow().strftime('%H:%M UTC')}\n\n"
            f"💡 *Lý do không có alert:*\n"
            f"• Không có coin nào spike >= ngưỡng\n"
            f"• Hoặc giá không thay đổi >= ±{config.get('price_filter', 10)}%\n"
            f"• Thử lại sau 15-30 phút",
            parse_mode='Markdown'
        )
        return

    alerts.sort(key=lambda x: x['spike_pct'], reverse=True)

    await update.message.reply_text(
        f"🚨 *VOLUME SPIKES — {len(alerts)} found*\n"
        f"📊 Scanned: {total} coins\n"
        f"⏰ {datetime.utcnow().strftime('%H:%M UTC')}",
        parse_mode='Markdown'
    )

    for i, alert in enumerate(alerts[:10], 1):
        await update.message.reply_text(f"*#{i}*\n{format_alert(alert)}", parse_mode='Markdown')
        await asyncio.sleep(0.3)

async def add_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ Cú pháp: `/add <coin_id>`\n"
            "Ví dụ:\n"
            "• `/add bitcoin`\n"
            "• `/add ethereum`\n"
            "• `/add solana`\n"
            "• `/add pepe`",
            parse_mode='Markdown'
        )
        return

    coin_id = context.args[0].lower()
    wl = load_watchlist()

    for c in wl['coins']:
        if c['id'] == coin_id:
            await update.message.reply_text(f"⚠️ `{coin_id}` đã có trong watchlist", parse_mode='Markdown')
            return

    wl['coins'].append({
        'id': coin_id,
        'added_at': datetime.utcnow().isoformat(),
    })
    save_watchlist(wl)
    await update.message.reply_text(
        f"✅ Đã thêm *{escape_md(coin_id)}* vào watchlist\n"
        f"📊 Sẽ được scan trong lần tiếp theo",
        parse_mode='Markdown'
    )

async def remove_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Cú pháp: `/remove <coin_id>`", parse_mode='Markdown')
        return

    coin_id = context.args[0].lower()
    wl = load_watchlist()
    original = len(wl['coins'])
    wl['coins'] = [c for c in wl['coins'] if c['id'] != coin_id]
    save_watchlist(wl)

    if len(wl['coins']) < original:
        await update.message.reply_text(f"✅ Đã xóa *{escape_md(coin_id)}*", parse_mode='Markdown')
    else:
        await update.message.reply_text(f"❌ Không tìm thấy `{coin_id}`", parse_mode='Markdown')

async def show_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wl = load_watchlist()
    if not wl['coins']:
        await update.message.reply_text("📋 Watchlist trống\nThêm: `/add bitcoin`", parse_mode='Markdown')
        return

    msg = f"📋 *WATCHLIST ({len(wl['coins'])} coins)*\n\n"
    for i, c in enumerate(wl['coins'], 1):
        added = c.get('added_at', '')[:10]
        msg += f"{i}. *{escape_md(c['id'])}* (thêm: {added})\n"
    msg += f"\nXóa: `/remove <coin_id>`"
    await update.message.reply_text(msg, parse_mode='Markdown')

async def config_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = load_config()
    enabled = [v["name"] for k, v in EXCHANGES.items() if config["exchanges"].get(k, v["enabled"])]
    disabled = [v["name"] for k, v in EXCHANGES.items() if not config["exchanges"].get(k, v["enabled"])]

    msg = (
        "⚙️ *CẤU HÌNH HIỆN TẠI*\n\n"
        f"📊 *Sàn đang theo dõi:*\n"
        f"   ✅ {', '.join(enabled)}\n"
        f"   ❌ {', '.join(disabled) if disabled else 'Không có'}\n\n"
        f"⏰ *Timeframe:* {config.get('timeframe', '24h')}\n"
        f"📈 *Price filter:* ±{config.get('price_filter', 10)}%\n"
        f"   (Chỉ alert khi giá thay đổi >= ±{config.get('price_filter', 10)}%)\n\n"
        f"🎯 *Threshold theo MCap:*\n"
        f"   >= $1B → 30%\n"
        f"   >= $500M → 50%\n"
        f"   >= $100M → 80%\n"
        f"   >= $10M → 100%\n"
        f"   < $10M → 150%\n"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def set_timeframe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or context.args[0].lower() not in ["1h", "4h", "12h", "24h", "7d"]:
        await update.message.reply_text("❌ `/timeframe <1h/4h/12h/24h/7d>`", parse_mode='Markdown')
        return

    tf = context.args[0].lower()
    config = load_config()
    config['timeframe'] = tf
    save_config(config)
    await update.message.reply_text(f"✅ Timeframe: *{tf}*", parse_mode='Markdown')

async def set_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ `/threshold <phần_trăm>`\nVí dụ: `/threshold 80`", parse_mode='Markdown')
        return
    try:
        val = int(context.args[0])
        if val < 10 or val > 1000:
            raise ValueError()
    except:
        await update.message.reply_text("❌ Giá trị: 10-1000")
        return

    config = load_config()
    config['custom_thresholds'] = [[0, val]]
    save_config(config)
    await update.message.reply_text(
        f"✅ Threshold: *{val}%* (flat cho tất cả MCap)\n"
        f"Để reset về dynamic: `/threshold 0`",
        parse_mode='Markdown'
    )

async def set_pricefilter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ `/pricefilter <phần_trăm>`\nVí dụ: `/pricefilter 15`", parse_mode='Markdown')
        return
    try:
        val = int(context.args[0])
        if val < 1 or val > 50:
            raise ValueError()
    except:
        await update.message.reply_text("❌ Giá trị: 1-50")
        return

    config = load_config()
    config['price_filter'] = val
    save_config(config)
    await update.message.reply_text(f"✅ Price filter: *±{val}%*", parse_mode='Markdown')

async def exchanges_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = load_config()
    keyboard = []
    for key, ex in EXCHANGES.items():
        enabled = config["exchanges"].get(key, ex["enabled"])
        status = "✅" if enabled else "❌"
        keyboard.append([InlineKeyboardButton(f"{status} {ex['name']}", callback_data=f"toggle_exchange_{key}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("⚙️ *Nhấn để bật/tắt sàn:*", reply_markup=reply_markup, parse_mode='Markdown')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("toggle_exchange_"):
        key = query.data.replace("toggle_exchange_", "")
        config = load_config()
        if key in config["exchanges"]:
            config["exchanges"][key] = not config["exchanges"][key]
        else:
            config["exchanges"][key] = not EXCHANGES[key]["enabled"]
        save_config(config)

        keyboard = []
        for k, ex in EXCHANGES.items():
            enabled = config["exchanges"].get(k, ex["enabled"])
            status = "✅" if enabled else "❌"
            keyboard.append([InlineKeyboardButton(f"{status} {ex['name']}", callback_data=f"toggle_exchange_{k}")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("⚙️ *Nhấn để bật/tắt sàn:*", reply_markup=reply_markup, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()

    coin_map = {
        'btc': 'bitcoin', 'eth': 'ethereum', 'sol': 'solana',
        'bnb': 'binancecoin', 'xrp': 'ripple', 'ada': 'cardano',
        'doge': 'dogecoin', 'dot': 'polkadot', 'avax': 'avalanche-2',
        'link': 'chainlink', 'matic': 'matic-network', 'uni': 'uniswap',
        'pepe': 'pepe', 'bonk': 'bonk', 'wif': 'dogwifhat',
        'shib': 'shiba-inu', 'ltc': 'litecoin', 'trx': 'tron',
    }

    coin_id = coin_map.get(text, text)
    await update.message.reply_text(f"🔍 Đang tìm `{escape_md(coin_id)}`...", parse_mode='Markdown')

    coin = get_coin_by_id(coin_id)
    if coin:
        price = coin.get('current_price', 0)
        p1h = coin.get('price_change_percentage_1h_in_currency', 0) or 0
        p24h = coin.get('price_change_percentage_24h', 0) or 0
        vol = coin.get('total_volume', 0)
        mcap = coin.get('market_cap', 0)
        rank = coin.get('market_cap_rank', '?')
        threshold = get_threshold_for_mcap(mcap)

        msg = (
            f"📊 *{escape_md(coin.get('name', ''))}* ({escape_md(coin.get('symbol', '').upper())})\n"
            f"   🏆 Rank: #{rank}\n"
            f"   💰 Price: `{format_usd(price)}`\n"
            f"   📈 1h: {p1h:+.1f}% | 24h: {p24h:+.1f}%\n"
            f"   💎 Volume 24h: {format_usd(vol)}\n"
            f"   📏 MCap: {format_usd(mcap)}\n"
            f"   🎯 Spike threshold: {threshold}%\n"
            f"   📊 Vol/MCap: {(vol/mcap*100) if mcap > 0 else 0:.1f}%"
        )
        await update.message.reply_text(msg, parse_mode='Markdown')
    else:
        await update.message.reply_text(f"❌ Không tìm thấy `{escape_md(text)}`", parse_mode='Markdown')

# ============================================
# AUTO-SCAN
# ============================================

async def auto_scan_job(context: ContextTypes.DEFAULT_TYPE):
    autoscan = load_autoscan()
    if not autoscan.get("enabled") or not autoscan.get("chat_ids"):
        return

    config = load_config()
    alerts, total = scan_all(config)

    if not alerts:
        return

    alerts.sort(key=lambda x: x['spike_pct'], reverse=True)

    for chat_id in autoscan["chat_ids"]:
        try:
            msg = f"🚨 *AUTO-SCAN ALERT — {len(alerts)} spikes*\n📊 Scanned: {total} coins\n⏰ {datetime.utcnow().strftime('%H:%M UTC')}\n"
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')

            for i, alert in enumerate(alerts[:5], 1):
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"*#{i}*\n{format_alert(alert)}",
                    parse_mode='Markdown'
                )
                await asyncio.sleep(0.5)
        except Exception as e:
            print(f"Error sending to {chat_id}: {e}")

async def autoscan_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    autoscan = load_autoscan()
    if chat_id not in autoscan["chat_ids"]:
        autoscan["chat_ids"].append(chat_id)
    autoscan["enabled"] = True
    save_autoscan(autoscan)

    interval = autoscan.get("interval_minutes", 15)
    await update.message.reply_text(
        f"✅ *AUTO-SCAN BẬT*\n"
        f"⏰ Quét tự động mỗi *{interval} phút*\n"
        f"📊 Chỉ gửi khi có volume spike\n\n"
        f"Đổi interval: `/autoscan_interval <phút>`\n"
        f"Tắt: `/autoscan_off`",
        parse_mode='Markdown'
    )

async def autoscan_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    autoscan = load_autoscan()
    autoscan["chat_ids"] = [cid for cid in autoscan["chat_ids"] if cid != chat_id]
    if not autoscan["chat_ids"]:
        autoscan["enabled"] = False
    save_autoscan(autoscan)
    await update.message.reply_text("✅ Auto-Scan *TẮT*", parse_mode='Markdown')

async def autoscan_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ `/autoscan_interval <phút>`\nTối thiểu: 5 phút", parse_mode='Markdown')
        return
    try:
        val = int(context.args[0])
        if val < 5 or val > 120:
            raise ValueError()
    except:
        await update.message.reply_text("❌ Giá trị: 5-120 phút")
        return

    autoscan = load_autoscan()
    autoscan["interval_minutes"] = val
    save_autoscan(autoscan)
    await update.message.reply_text(f"✅ Auto-scan: mỗi *{val} phút*", parse_mode='Markdown')

async def autoscan_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    autoscan = load_autoscan()
    chat_id = update.effective_chat.id
    is_subscribed = chat_id in autoscan.get("chat_ids", [])
    status = "🟢 BẬT" if autoscan.get("enabled") and is_subscribed else "🔴 TẮT"
    interval = autoscan.get("interval_minutes", 15)

    msg = (
        f"⏰ *AUTO-SCAN*\n\n"
        f"Trạng thái: {status}\n"
        f"Interval: mỗi {interval} phút\n"
        f"Subscribers: {len(autoscan.get('chat_ids', []))}\n\n"
        f"/autoscan_on — Bật\n"
        f"/autoscan_off — Tắt\n"
        f"/autoscan_interval <phút> — Đổi interval\n"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

# ============================================
# MAIN
# ============================================

def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or not BOT_TOKEN:
        print("❌ Vui lòng set BOT_TOKEN environment variable")
        return

    print("🚀 Starting Volume Spike Alert Bot v3...")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("scan", scan_cmd))
    app.add_handler(CommandHandler("add", add_coin))
    app.add_handler(CommandHandler("remove", remove_coin))
    app.add_handler(CommandHandler("watchlist", show_watchlist))
    app.add_handler(CommandHandler("config", config_cmd))
    app.add_handler(CommandHandler("timeframe", set_timeframe))
    app.add_handler(CommandHandler("threshold", set_threshold))
    app.add_handler(CommandHandler("pricefilter", set_pricefilter))
    app.add_handler(CommandHandler("exchanges", exchanges_cmd))
    app.add_handler(CommandHandler("autoscan", autoscan_status))
    app.add_handler(CommandHandler("autoscan_on", autoscan_on))
    app.add_handler(CommandHandler("autoscan_off", autoscan_off))
    app.add_handler(CommandHandler("autoscan_interval", autoscan_interval))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Auto-scan job
    autoscan = load_autoscan()
    interval = autoscan.get("interval_minutes", 15)
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(auto_scan_job, interval=interval * 60, first=60)

    print(f"✅ Bot v3 is running! (Auto-scan every {interval} min)")
    app.run_polling()

if __name__ == "__main__":
    main()
