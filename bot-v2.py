#!/usr/bin/env python3
"""
🚀 Volume Spike Alert Bot v2
CEX Volume Monitor với dynamic threshold & customizable alerts
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
# Format: (min_mcap, threshold_percent)
MCAP_THRESHOLDS = [
    (1_000_000_000, 30),   # MCap >= $1B → alert at 30%
    (500_000_000, 50),     # MCap >= $500M → alert at 50%
    (100_000_000, 80),     # MCap >= $100M → alert at 80%
    (10_000_000, 100),     # MCap >= $10M → alert at 100%
    (0, 150),              # MCap < $10M → alert at 150%
]

# Price change filter (only alert when price moves significantly)
PRICE_CHANGE_MIN = 10  # Alert only if price change >= ±10%

# Timeframes available
TIMEFRAMES = {
    "1h": {"hours": 1, "label": "1 Hour"},
    "4h": {"hours": 4, "label": "4 Hours"},
    "12h": {"hours": 12, "label": "12 Hours"},
    "24h": {"hours": 24, "label": "24 Hours"},
    "7d": {"hours": 168, "label": "7 Days"},
}

# Data files
CONFIG_FILE = os.path.expanduser("~/.openclaw/workspace/volume-monitor/bot-config.json")
WATCHLIST_FILE = os.path.expanduser("~/.openclaw/workspace/volume-monitor/watchlist.json")
HISTORY_FILE = os.path.expanduser("~/.openclaw/workspace/volume-monitor/history.json")

# Auto-scan config
AUTOSCAN_FILE = os.path.expanduser("~/.openclaw/workspace/volume-monitor/autoscan.json")

# ============================================
# CONFIG MANAGEMENT
# ============================================

def load_config():
    """Load bot configuration"""
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    default = {
        "exchanges": {k: v["enabled"] for k, v in EXCHANGES.items()},
        "timeframe": "24h",
        "price_filter": PRICE_CHANGE_MIN,
        "custom_thresholds": None,  # None = use MCAP_THRESHOLDS
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

def load_autoscan():
    """Load auto-scan settings"""
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
    """Get coins sorted by volume"""
    url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=volume_desc&per_page={per_page}&page={page}&sparkline=false&price_change_percentage=1h,24h&locale=en"
    return fetch_json(url)

def get_exchange_coins(exchange_id, per_page=100, page=1):
    """Get coins listed on specific exchange"""
    url = f"https://api.coingecko.com/api/v3/exchanges/{exchange_id}/tickers?depth=false&order=volume_desc&per_page={per_page}&page={page}"
    return fetch_json(url)

def get_coin_detail(coin_id):
    """Get detailed coin data"""
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}?localization=false&tickers=false&community_data=false&developer_data=false"
    return fetch_json(url)

# ============================================
# ANALYSIS
# ============================================

def get_threshold_for_mcap(mcap):
    """Get spike threshold based on market cap"""
    config = load_config()
    custom = config.get("custom_thresholds")
    
    if custom:
        for min_mcap, threshold in sorted(custom, key=lambda x: -x[0]):
            if mcap >= min_mcap:
                return threshold
    
    for min_mcap, threshold in MCAP_THRESHOLDS:
        if mcap >= min_mcap:
            return threshold
    return 150  # Default for very small caps

def detect_volume_spike(coin, prev_volume, config):
    """Detect if coin has volume spike"""
    current_volume = coin.get('total_volume', 0) or 0
    mcap = coin.get('market_cap', 0) or 0
    price_change = coin.get('price_change_percentage_24h', 0) or 0
    
    if current_volume == 0 or prev_volume == 0:
        return None
    
    # Calculate spike
    spike_pct = ((current_volume - prev_volume) / prev_volume) * 100
    
    # Get threshold for this market cap
    threshold = get_threshold_for_mcap(mcap)
    
    # Check if spike exceeds threshold
    if spike_pct < threshold:
        return None
    
    # Price filter: only alert if price changed significantly
    if abs(price_change) < config.get("price_filter", 10):
        return None
    
    return {
        'id': coin.get('id'),
        'symbol': coin.get('symbol', '').upper(),
        'name': coin.get('name', ''),
        'price': coin.get('current_price', 0),
        'price_change_24h': price_change,
        'volume_current': current_volume,
        'volume_prev': prev_volume,
        'spike_pct': spike_pct,
        'threshold': threshold,
        'mcap': mcap,
        'image': coin.get('image', ''),
    }

def scan_all(config):
    """Scan all enabled exchanges for volume spikes"""
    history = load_history()
    alerts = []
    all_coins = []
    
    # Fetch top coins by volume (2 pages = 200 coins)
    for page in [1, 2]:
        data = get_coins_markets(per_page=100, page=page)
        if data:
            all_coins.extend(data)
        asyncio.sleep(0.5) if hasattr(asyncio, 'sleep') else None
    
    if not all_coins:
        return alerts, 0
    
    # Check watchlist coins too
    wl = load_watchlist()
    wl_ids = [c['id'] for c in wl.get('coins', [])]
    
    # Process each coin
    for coin in all_coins:
        coin_id = coin.get('id', '')
        
        # Check if on enabled exchanges (approximate - CoinGecko gives aggregated data)
        # For detailed per-exchange data, we'd need more API calls
        
        # Get previous volume from history
        prev_volume = history.get(coin_id, {}).get('volume', 0)
        
        # Detect spike
        alert = detect_volume_spike(coin, prev_volume, config)
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
    """Format volume spike alert"""
    emoji = "🟢" if alert['price_change_24h'] > 0 else "🔴"
    direction = "PUMP" if alert['price_change_24h'] > 0 else "DUMP"
    
    lines = [
        f"🚨 *{escape_md(alert['symbol'])}* — VOLUME SPIKE {emoji}",
        f"   {escape_md(alert['name'])}",
        f"   💰 Price: `{format_usd(alert['price'])}`",
        f"   {emoji} {direction}: *{alert['price_change_24h']:+.1f}%*",
        f"   📈 Volume: {format_usd(alert['volume_prev'])} → *{format_usd(alert['volume_current'])}*",
        f"   🚀 Spike: *+{alert['spike_pct']:.0f}%* (threshold: {alert['threshold']}%)",
        f"   📏 MCap: {format_usd(alert['mcap'])}",
    ]
    return "\n".join(lines)

def escape_md(text):
    special = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special:
        text = text.replace(char, f'\\{char}')
    return text

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
    """Handle /start"""
    config = load_config()
    enabled_exchanges = [v["name"] for k, v in EXCHANGES.items() if config["exchanges"].get(k, v["enabled"])]
    timeframe = config.get("timeframe", "24h")
    price_filter = config.get("price_filter", 10)
    
    msg = (
        "🚀 *Volume Spike Alert Bot v2*\n"
        "\n"
        f"📊 Sàn đang theo dõi: {', '.join(enabled_exchanges)}\n"
        f"⏰ Timeframe: {timeframe}\n"
        f"📈 Price filter: ±{price_filter}%\n"
        f"🎯 Threshold: Dynamic theo MCap\n"
        "\n"
        "*Commands:*\n"
        "/scan — Quét volume spike ngay\n"
        "/add <id> — Thêm coin vào watchlist\n"
        "/remove <id> — Xóa coin khỏi watchlist\n"
        "/watchlist — Xem watchlist\n"
        "/config — Cấu hình bot\n"
        "/exchanges — Quản lý sàn\n"
        "/autoscan — Bật/tắt auto-scan\n"
        "/timeframe <1h/4h/12h/24h/7d> — Đổi timeframe\n"
        "/threshold <phần_trăm> — Đổi ngưỡng spike\n"
        "/help — Hướng dẫn\n"
        "\n"
        "Gửi coin name/ticker để check nhanh!"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📖 *Hướng dẫn sử dụng*\n"
        "\n"
        "*🔔 Cảnh báo Volume Spike:*\n"
        "• Tăng >= 30% so với trước đó (MCap > $1B)\n"
        "• Tăng >= 50% so với trước đó (MCap > $500M)\n"
        "• Tăng >= 100% so với trước đó (MCap < $10M)\n"
        "• Chỉ alert khi giá thay đổi >= ±10%\n"
        "\n"
        "*📊 Scan:*\n"
        "/scan — Quét ngay tất cả coin\n"
        "\n"
        "*📋 Watchlist:*\n"
        "/add bitcoin — Thêm BTC\n"
        "/add ethereum — Thêm ETH\n"
        "/remove bitcoin — Xóa BTC\n"
        "/watchlist — Xem danh sách\n"
        "\n"
        "*⚙️ Config:*\n"
        "/timeframe 4h — Đổi timeframe sang 4h\n"
        "/threshold 80 — Đổi ngưỡng spike 80%\n"
        "/exchanges — Bật/tắt sàn\n"
        "/pricefilter 15 — Đổi price filter ±15%\n"
        "\n"
        "*🔍 Check nhanh:*\n"
        "Gửi: bitcoin, eth, sol...\n"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /scan"""
    config = load_config()
    await update.message.reply_text("🔍 Đang quét volume spike... Chờ tí ⏳")
    
    alerts, total = scan_all(config)
    
    if not alerts:
        await update.message.reply_text(
            f"✅ Không phát hiện volume spike\n"
            f"📊 Đã quét {total} coins\n"
            f"⏰ Timeframe: {config.get('timeframe', '24h')}\n"
            f"🎯 Threshold: Dynamic theo MCap"
        )
        return
    
    # Sort by spike percentage
    alerts.sort(key=lambda x: x['spike_pct'], reverse=True)
    
    msg = f"🚨 *VOLUME SPIKES — {len(alerts)} found*\n📊 Scanned: {total} coins\n⏰ {datetime.utcnow().strftime('%H:%M UTC')}\n\n"
    await update.message.reply_text(msg, parse_mode='Markdown')
    
    for i, alert in enumerate(alerts[:10], 1):
        await update.message.reply_text(f"*#{i}*\n{format_alert(alert)}", parse_mode='Markdown')
        await asyncio.sleep(0.3)  # Avoid flood

async def add_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /add"""
    if not context.args:
        await update.message.reply_text("❌ Cú pháp: `/add <coin_id>`\nVí dụ: `/add bitcoin`", parse_mode='Markdown')
        return
    
    coin_id = context.args[0].lower()
    wl = load_watchlist()
    
    # Check if already exists
    for c in wl['coins']:
        if c['id'] == coin_id:
            await update.message.reply_text(f"⚠️ `{coin_id}` đã có trong watchlist", parse_mode='Markdown')
            return
    
    # Add
    wl['coins'].append({
        'id': coin_id,
        'added_at': datetime.utcnow().isoformat(),
    })
    save_watchlist(wl)
    await update.message.reply_text(f"✅ Đã thêm *{escape_md(coin_id)}* vào watchlist", parse_mode='Markdown')

async def remove_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /remove"""
    if not context.args:
        await update.message.reply_text("❌ Cú pháp: `/remove <coin_id>`", parse_mode='Markdown')
        return
    
    coin_id = context.args[0].lower()
    wl = load_watchlist()
    original = len(wl['coins'])
    wl['coins'] = [c for c in wl['coins'] if c['id'] != coin_id]
    save_watchlist(wl)
    
    if len(wl['coins']) < original:
        await update.message.reply_text(f"✅ Đã xóa *{escape_md(coin_id)}* khỏi watchlist", parse_mode='Markdown')
    else:
        await update.message.reply_text(f"❌ Không tìm thấy `{coin_id}` trong watchlist", parse_mode='Markdown')

async def show_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /watchlist"""
    wl = load_watchlist()
    if not wl['coins']:
        await update.message.reply_text("📋 Watchlist trống\nThêm coin: `/add bitcoin`", parse_mode='Markdown')
        return
    
    msg = f"📋 *WATCHLIST ({len(wl['coins'])} coins)*\n\n"
    for i, c in enumerate(wl['coins'], 1):
        msg += f"{i}. *{escape_md(c['id'])}*\n"
    msg += f"\nXóa: `/remove <coin_id>`"
    await update.message.reply_text(msg, parse_mode='Markdown')

async def config_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /config"""
    config = load_config()
    enabled = [v["name"] for k, v in EXCHANGES.items() if config["exchanges"].get(k, v["enabled"])]
    disabled = [v["name"] for k, v in EXCHANGES.items() if not config["exchanges"].get(k, v["enabled"])]
    
    msg = (
        "⚙️ *CONFIG*\n\n"
        f"📊 *Sàn đang theo dõi:*\n"
        f"   ✅ {', '.join(enabled)}\n"
        f"   ❌ {', '.join(disabled) if disabled else 'Không có'}\n\n"
        f"⏰ *Timeframe:* {config.get('timeframe', '24h')}\n"
        f"📈 *Price filter:* ±{config.get('price_filter', 10)}%\n"
        f"🎯 *Threshold:* Dynamic theo MCap\n"
        f"   >= $1B → 30%\n"
        f"   >= $500M → 50%\n"
        f"   >= $100M → 80%\n"
        f"   >= $10M → 100%\n"
        f"   < $10M → 150%\n\n"
        f"*Commands:*\n"
        f"/timeframe <1h/4h/12h/24h/7d>\n"
        f"/threshold <phần_trăm>\n"
        f"/pricefilter <phần_trăm>\n"
        f"/exchanges"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def set_timeframe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /timeframe"""
    if not context.args or context.args[0].lower() not in TIMEFRAMES:
        tf_list = ', '.join(TIMEFRAMES.keys())
        await update.message.reply_text(f"❌ Cú pháp: `/timeframe <{tf_list}>`", parse_mode='Markdown')
        return
    
    tf = context.args[0].lower()
    config = load_config()
    config['timeframe'] = tf
    save_config(config)
    await update.message.reply_text(f"✅ Timeframe: *{TIMEFRAMES[tf]['label']}*", parse_mode='Markdown')

async def set_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /threshold"""
    if not context.args:
        await update.message.reply_text("❌ Cú pháp: `/threshold <phần_trăm>`\nVí dụ: `/threshold 80`", parse_mode='Markdown')
        return
    
    try:
        val = int(context.args[0])
        if val < 10 or val > 1000:
            raise ValueError()
    except:
        await update.message.reply_text("❌ Giá trị phải từ 10-1000")
        return
    
    config = load_config()
    # Set flat threshold for all mcap ranges
    config['custom_thresholds'] = [[0, val]]
    save_config(config)
    await update.message.reply_text(f"✅ Threshold: *{val}%* (flat for all MCap)", parse_mode='Markdown')

async def set_pricefilter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /pricefilter"""
    if not context.args:
        await update.message.reply_text("❌ Cú pháp: `/pricefilter <phần_trăm>`\nVí dụ: `/pricefilter 15`", parse_mode='Markdown')
        return
    
    try:
        val = int(context.args[0])
        if val < 1 or val > 50:
            raise ValueError()
    except:
        await update.message.reply_text("❌ Giá trị phải từ 1-50")
        return
    
    config = load_config()
    config['price_filter'] = val
    save_config(config)
    await update.message.reply_text(f"✅ Price filter: *±{val}%*", parse_mode='Markdown')

async def exchanges_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /exchanges"""
    config = load_config()
    keyboard = []
    
    for key, ex in EXCHANGES.items():
        enabled = config["exchanges"].get(key, ex["enabled"])
        status = "✅" if enabled else "❌"
        keyboard.append([InlineKeyboardButton(
            f"{status} {ex['name']}",
            callback_data=f"toggle_exchange_{key}"
        )])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "⚙️ *Nhấn để bật/tắt sàn:*",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button presses"""
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
        
        # Rebuild keyboard
        keyboard = []
        for k, ex in EXCHANGES.items():
            enabled = config["exchanges"].get(k, ex["enabled"])
            status = "✅" if enabled else "❌"
            keyboard.append([InlineKeyboardButton(
                f"{status} {ex['name']}",
                callback_data=f"toggle_exchange_{k}"
            )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "⚙️ *Nhấn để bật/tắt sàn:*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages - search for coin"""
    text = update.message.text.strip().lower()
    
    # Common coin mappings
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
    
    # Try to get coin data
    markets = get_coins_markets(per_page=250)
    if markets:
        for coin in markets:
            if coin.get('id') == coin_id or coin.get('symbol', '').lower() == text:
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
                )
                await update.message.reply_text(msg, parse_mode='Markdown')
                return
    
    await update.message.reply_text(f"❌ Không tìm thấy `{escape_md(text)}`\nThử: /add {text}", parse_mode='Markdown')

# ============================================
# AUTO-SCAN
# ============================================

async def auto_scan_job(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job: auto-scan and send alerts"""
    autoscan = load_autoscan()
    if not autoscan.get("enabled"):
        return
    if not autoscan.get("chat_ids"):
        return
    
    config = load_config()
    alerts, total = scan_all(config)
    
    if not alerts:
        return  # No alerts, don't spam
    
    alerts.sort(key=lambda x: x['spike_pct'], reverse=True)
    
    for chat_id in autoscan["chat_ids"]:
        try:
            msg = f"🚨 *AUTO-SCAN ALERT — {len(alerts)} spikes*\n📊 Scanned: {total} coins\n⏰ {datetime.utcnow().strftime('%H:%M UTC')}\n\n"
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
    """Handle /autoscan_on"""
    chat_id = update.effective_chat.id
    autoscan = load_autoscan()
    
    if chat_id not in autoscan["chat_ids"]:
        autoscan["chat_ids"].append(chat_id)
    
    autoscan["enabled"] = True
    save_autoscan(autoscan)
    
    interval = autoscan.get("interval_minutes", 15)
    await update.message.reply_text(
        f"✅ *Auto-Scan BẬT*\n"
        f"⏰ Quét tự động mỗi *{interval} phút*\n"
        f"📊 Chỉ gửi khi có volume spike\n\n"
        f"Đổi interval: `/autoscan_interval <phút>`\n"
        f"Tắt: `/autoscan_off`",
        parse_mode='Markdown'
    )

async def autoscan_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /autoscan_off"""
    chat_id = update.effective_chat.id
    autoscan = load_autoscan()
    
    autoscan["chat_ids"] = [cid for cid in autoscan["chat_ids"] if cid != chat_id]
    if not autoscan["chat_ids"]:
        autoscan["enabled"] = False
    save_autoscan(autoscan)
    
    await update.message.reply_text("✅ Auto-Scan *TẮT*", parse_mode='Markdown')

async def autoscan_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /autoscan_interval"""
    if not context.args:
        await update.message.reply_text(
            "❌ Cú pháp: `/autoscan_interval <phút>`\n"
            "Ví dụ: `/autoscan_interval 10`\n"
            "Tối thiểu: 5 phút",
            parse_mode='Markdown'
        )
        return
    
    try:
        val = int(context.args[0])
        if val < 5 or val > 120:
            raise ValueError()
    except:
        await update.message.reply_text("❌ Giá trị phải từ 5-120 phút")
        return
    
    autoscan = load_autoscan()
    autoscan["interval_minutes"] = val
    save_autoscan(autoscan)
    
    await update.message.reply_text(f"✅ Auto-Scan interval: *mỗi {val} phút*", parse_mode='Markdown')

async def autoscan_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /autoscan"""
    autoscan = load_autoscan()
    chat_id = update.effective_chat.id
    is_subscribed = chat_id in autoscan.get("chat_ids", [])
    
    status = "🟢 ĐANG BẬT" if autoscan.get("enabled") and is_subscribed else "🔴 ĐANG TẮT"
    interval = autoscan.get("interval_minutes", 15)
    
    msg = (
        f"⏰ *AUTO-SCAN STATUS*\n\n"
        f"Trạng thái: {status}\n"
        f"Interval: mỗi {interval} phút\n"
        f"Subscribers: {len(autoscan.get('chat_ids', []))}\n\n"
        f"*Commands:*\n"
        f"/autoscan_on — Bật auto-scan\n"
        f"/autoscan_off — Tắt auto-scan\n"
        f"/autoscan_interval <phút> — Đổi interval\n"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or not BOT_TOKEN:
        print("❌ Vui lòng set BOT_TOKEN environment variable")
        print("   Railway: Settings → Variables → Add BOT_TOKEN")
        return
    
    print("🚀 Starting Volume Spike Alert Bot v2...")
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Command handlers
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
    
    # Auto-scan commands
    app.add_handler(CommandHandler("autoscan", autoscan_status))
    app.add_handler(CommandHandler("autoscan_on", autoscan_on))
    app.add_handler(CommandHandler("autoscan_off", autoscan_off))
    app.add_handler(CommandHandler("autoscan_interval", autoscan_interval))
    
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Schedule auto-scan job
    autoscan = load_autoscan()
    interval = autoscan.get("interval_minutes", 15)
    job_queue = app.job_queue
    job_queue.run_repeating(auto_scan_job, interval=interval * 60, first=60)  # First run after 1 min
    
    print(f"✅ Bot is running! (Auto-scan every {interval} min)")
    app.run_polling()

if __name__ == "__main__":
    main()
