#!/usr/bin/env python3
"""
🚀 Volume Spike Alert Bot
Telegram bot để theo dõi volume đột biến của crypto tokens
Tạo bởi: @bizbrain_gaming

Hướng dẫn deploy:
1. Tạo bot mới trên @BotFather (Telegram)
2. Copy token vào biến BOT_TOKEN bên dưới
3. Chạy: pip install python-telegram-bot requests
4. Chạy: python3 bot.py
"""

import json
import urllib.request
import os
import asyncio
from datetime import datetime

# ============================================
# CONFIG — THAY ĐỔI Ở ĐÂY
# ============================================

BOT_TOKEN = "8708429125:AAFUHc3gmozOlT0Dh6bYS5Gl-UXBmCD2d7c"  # ← Thay bằng token từ @BotFather

# Volume spike threshold
SPIKE_THRESHOLD = 100  # Alert khi volume tăng >= 100%

# Networks supported
NETWORKS = {
    "solana": "solana",
    "eth": "eth",
    "ethereum": "eth",
    "bsc": "bsc",
    "base": "base",
    "arbitrum": "arbitrum",
    "arb": "arbitrum",
    "abstract": "abstract",
    "sui": "sui",
}

# ============================================
# DATA FUNCTIONS
# ============================================

def fetch_json(url):
    """Fetch JSON from URL"""
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json'
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return None

def get_token_pools(chain, address):
    """Get token pools from GeckoTerminal"""
    url = f"https://api.geckoterminal.com/api/v2/networks/{chain}/tokens/{address}/pools?page=1"
    return fetch_json(url)

def get_dexscreener_token(chain, address):
    """Get token data from DexScreener"""
    url = f"https://api.dexscreener.com/tokens/v1/{chain}/{address}"
    return fetch_json(url)

def get_trending(chain="solana"):
    """Get trending pools"""
    url = f"https://api.geckoterminal.com/api/v2/networks/{chain}/trending_pools"
    return fetch_json(url)

# ============================================
# FORMAT FUNCTIONS
# ============================================

def format_usd(n):
    if n >= 1_000_000_000:
        return f"${n/1_000_000_000:.2f}B"
    elif n >= 1_000_000:
        return f"${n/1_000_000:.2f}M"
    elif n >= 1_000:
        return f"${n/1_000:.1f}K"
    elif n >= 1:
        return f"${n:.2f}"
    return f"${n:.6f}"

def format_token_info(data):
    """Format token info from GeckoTerminal pool data"""
    if not data or 'data' not in data or len(data['data']) == 0:
        return None
    
    pool = data['data'][0]
    attrs = pool.get('attributes', {})
    
    name = attrs.get('name', 'Unknown')
    price = float(attrs.get('base_token_price_usd', '0') or '0')
    
    volume = attrs.get('volume_usd', {})
    vol_5m = float(volume.get('m5', '0') or '0')
    vol_1h = float(volume.get('h1', '0') or '0')
    vol_6h = float(volume.get('h6', '0') or '0')
    vol_24h = float(volume.get('h24', '0') or '0')
    
    price_chg = attrs.get('price_change_percentage', {})
    p5m = float(price_chg.get('m5', '0') or '0')
    p15m = float(price_chg.get('m15', '0') or '0')
    p1h = float(price_chg.get('h1', '0') or '0')
    p6h = float(price_chg.get('h6', '0') or '0')
    p24h = float(price_chg.get('h24', '0') or '0')
    
    txns = attrs.get('transactions', {})
    t1h = txns.get('h1', {})
    buys = t1h.get('buys', 0)
    sells = t1h.get('sells', 0)
    t5m = txns.get('m5', {})
    buys_5m = t5m.get('buys', 0)
    sells_5m = t5m.get('sells', 0)
    
    liquidity = float(attrs.get('reserve_in_usd', '0') or '0')
    fdv = float(attrs.get('fdv_usd', '0') or '0')
    
    # Calculate volume spike (vol_5m vs vol_24h/288 average)
    avg_5m = vol_24h / 288 if vol_24h > 0 else 0
    spike = ((vol_5m - avg_5m) / avg_5m * 100) if avg_5m > 0 else 0
    
    # Build message
    lines = []
    lines.append(f"📊 *{escape_md(name)}*")
    lines.append(f"💰 Price: `{format_usd(price)}`")
    lines.append("")
    
    # Price changes
    p5m_emoji = "🟢" if p5m > 0 else "🔴" if p5m < 0 else "⚪"
    p1h_emoji = "🟢" if p1h > 0 else "🔴" if p1h < 0 else "⚪"
    lines.append(f"📈 *Price:*")
    lines.append(f"   {p5m_emoji} 5m: {p5m:+.1f}% | 15m: {p15m:+.1f}% | {p1h_emoji} 1h: {p1h:+.1f}%")
    lines.append(f"   6h: {p6h:+.1f}% | 24h: {p24h:+.1f}%")
    lines.append("")
    
    # Volume
    lines.append(f"💎 *Volume:*")
    lines.append(f"   5m: {format_usd(vol_5m)} | 1h: {format_usd(vol_1h)}")
    lines.append(f"   6h: {format_usd(vol_6h)} | 24h: {format_usd(vol_24h)}")
    lines.append("")
    
    # Volume spike indicator
    if spike >= SPIKE_THRESHOLD:
        lines.append(f"🚨 *VOLUME SPIKE: +{spike:.0f}%* (vs 24h average)")
        lines.append("")
    
    # Transactions
    lines.append(f"🔄 *Transactions:*")
    lines.append(f"   5m: 🟢{buys_5m} | 🔴{sells_5m}")
    lines.append(f"   1h: 🟢{buys} | 🔴{sells}")
    lines.append("")
    
    # Liquidity & FDV
    lines.append(f"💧 Liquidity: {format_usd(liquidity)}")
    lines.append(f"📏 FDV: {format_usd(fdv)}")
    
    # Alerts
    alerts = []
    if spike >= SPIKE_THRESHOLD:
        alerts.append("🚨 Volume spike " + f"+{spike:.0f}%")
    if p1h >= 30:
        alerts.append(f"🟢 Pump +{p1h:.1f}% (1h)")
    if p1h <= -20:
        alerts.append(f"🔴 Dump {p1h:.1f}% (1h)")
    if buys_5m > sells_5m * 3 and buys_5m > 5:
        alerts.append(f"📈 Buy pressure ({buys_5m}b/{sells_5m}s)")
    if sells_5m > buys_5m * 3 and sells_5m > 5:
        alerts.append(f"📉 Sell pressure ({buys_5m}b/{sells_5m}s)")
    
    if alerts:
        lines.append("")
        lines.append("⚠️ *Alerts:*")
        for a in alerts:
            lines.append(f"   {a}")
    
    return "\n".join(lines)

def escape_md(text):
    """Escape markdown special characters"""
    special = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special:
        text = text.replace(char, f'\\{char}')
    return text

# ============================================
# TELEGRAM BOT
# ============================================

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
except ImportError:
    print("❌ Cần cài: pip install python-telegram-bot")
    print("   Chạy: pip install python-telegram-bot requests")
    exit(1)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    msg = (
        "🚀 *Volume Spike Alert Bot*\n"
        "\n"
        "Theo dõi volume đột biến của crypto tokens\n"
        "\n"
        "*Commands:*\n"
        "`/check <chain> <address>` — Check token\n"
        "   Ví dụ: `/check solana DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263`\n"
        "\n"
        "`/trending [chain]` — Xem trending pools\n"
        "   Ví dụ: `/trending solana`\n"
        "\n"
        "`/help` — Hướng dẫn\n"
        "\n"
        "*Supported chains:*\n"
        "solana, eth, bsc, base, arbitrum, abstract\n"
        "\n"
        "*Hoặc gửi trực tiếp:*\n"
        "• Contract address → auto-detect chain\n"
        "• `chain:address` → chỉ định chain\n"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    msg = (
        "📖 *Hướng dẫn sử dụng*\n"
        "\n"
        "*1. Check token:*\n"
        "`/check solana <address>`\n"
        "`/check eth <address>`\n"
        "\n"
        "*2. Xem trending:*\n"
        "`/trending solana`\n"
        "`/trending bsc`\n"
        "\n"
        "*3. Gửi nhanh:*\n"
        "• Gửi contract address (auto-detect)\n"
        "• Gửi `solana:DezXA...` (chỉ định chain)\n"
        "\n"
        "*Volume Spike = Volume hiện tại > 100% so với average*\n"
        "\n"
        "*Chains:* solana, eth, bsc, base, arbitrum, abstract\n"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def check_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /check command"""
    args = context.args
    
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Cú pháp: `/check <chain> <address>`\n"
            "Ví dụ: `/check solana DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263`",
            parse_mode='Markdown'
        )
        return
    
    chain = args[0].lower()
    address = args[1]
    
    if chain not in NETWORKS:
        await update.message.reply_text(
            f"❌ Chain không hỗ trợ: {chain}\n"
            f"Hỗ trợ: {', '.join(set(NETWORKS.values()))}"
        )
        return
    
    chain_id = NETWORKS[chain]
    
    await update.message.reply_text(f"🔍 Đang kiểm tra `{address[:20]}...` trên {chain_id.upper()}...", parse_mode='Markdown')
    
    data = get_token_pools(chain_id, address)
    result = format_token_info(data)
    
    if result:
        await update.message.reply_text(result, parse_mode='Markdown')
    else:
        # Try DexScreener
        ds_data = get_dexscreener_token(chain_id, address)
        if ds_data and len(ds_data) > 0:
            token = ds_data[0]
            msg = (
                f"📊 *{escape_md(token.get('baseToken', {}).get('name', 'Unknown'))}*\n"
                f"💰 Price: `{token.get('priceUsd', 'N/A')}`\n"
                f"📈 1h: {token.get('priceChange', {}).get('h1', 'N/A')}%\n"
                f"💎 Volume 24h: {format_usd(float(token.get('volume', {}).get('h24', 0) or 0))}\n"
                f"💧 Liquidity: {format_usd(float(token.get('liquidity', {}).get('usd', 0) or 0))}\n"
                f"📏 FDV: {format_usd(float(token.get('fdv', 0) or 0))}"
            )
            await update.message.reply_text(msg, parse_mode='Markdown')
        else:
            await update.message.reply_text(
                f"❌ Không tìm thấy token\n"
                f"Chain: {chain_id} | Address: `{address[:30]}...`",
                parse_mode='Markdown'
            )

async def trending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /trending command"""
    args = context.args
    chain = args[0].lower() if args else "solana"
    
    if chain not in NETWORKS:
        chain = "solana"
    chain_id = NETWORKS[chain]
    
    await update.message.reply_text(f"🔍 Đang lấy trending trên {chain_id.upper()}...")
    
    data = get_trending(chain_id)
    if not data or 'data' not in data:
        await update.message.reply_text("❌ Không lấy được data")
        return
    
    pools = data['data'][:10]
    msg = f"🔥 *Trending on {chain_id.upper()}*\n\n"
    
    for i, pool in enumerate(pools, 1):
        attrs = pool.get('attributes', {})
        name = attrs.get('name', 'Unknown')
        price_chg = attrs.get('price_change_percentage', {})
        p1h = float(price_chg.get('h1', '0') or '0')
        vol = attrs.get('volume_usd', {})
        vol_1h = float(vol.get('h1', '0') or '0')
        liquidity = float(attrs.get('reserve_in_usd', '0') or '0')
        
        emoji = "🟢" if p1h > 0 else "🔴" if p1h < 0 else "⚪"
        msg += f"*{i}\\. {escape_md(name)}*\n"
        msg += f"   {emoji} 1h: {p1h:+.1f}% | Vol: {format_usd(vol_1h)} | Liq: {format_usd(liquidity)}\n\n"
    
    await update.message.reply_text(msg, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages (auto-detect contract address)"""
    text = update.message.text.strip()
    
    # Check if it's chain:address format
    if ':' in text:
        parts = text.split(':', 1)
        chain = parts[0].lower().strip()
        address = parts[1].strip()
        if chain in NETWORKS:
            chain_id = NETWORKS[chain]
            await update.message.reply_text(f"🔍 Checking `{address[:20]}...` on {chain_id.upper()}...", parse_mode='Markdown')
            data = get_token_pools(chain_id, address)
            result = format_token_info(data)
            if result:
                await update.message.reply_text(result, parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ Không tìm thấy token")
            return
    
    # Check if it looks like a contract address
    # Solana: 32-44 chars base58
    # EVM: 0x + 40 hex chars
    if len(text) >= 32:
        # Try common chains
        chains_to_try = ['solana', 'eth', 'bsc', 'base']
        
        if text.startswith('0x') and len(text) == 42:
            chains_to_try = ['eth', 'bsc', 'base', 'arbitrum']
        
        for chain in chains_to_try:
            chain_id = NETWORKS[chain]
            data = get_token_pools(chain_id, text)
            if data and 'data' in data and len(data['data']) > 0:
                result = format_token_info(data)
                if result:
                    await update.message.reply_text(
                        f"✅ *Auto-detected: {chain_id.upper()}*\n\n{result}",
                        parse_mode='Markdown'
                    )
                    return
        
        await update.message.reply_text(
            "❌ Không tìm thấy token\n"
            "Thử chỉ định chain: `solana:address` hoặc `eth:address`",
            parse_mode='Markdown'
        )

def main():
    """Main function"""
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Vui lòng thay BOT_TOKEN bằng token từ @BotFather")
        print("   1. Mở @BotFather trên Telegram")
        print("   2. Gõ /newbot → đặt tên bot")
        print("   3. Copy token → paste vào BOT_TOKEN trong bot.py")
        return
    
    print("🚀 Starting Volume Spike Alert Bot...")
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("check", check_token))
    app.add_handler(CommandHandler("trending", trending))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start polling
    print("✅ Bot is running!")
    app.run_polling()

if __name__ == "__main__":
    main()
