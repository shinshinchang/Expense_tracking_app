import discord
from discord import app_commands
from discord.ext import tasks
import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import requests

# ==========================================
# 1. 初始設定與載入環境變數
# ==========================================
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
DB_PASS = os.getenv('DB_PASS')
REPORT_CHANNEL_ID = os.getenv('REPORT_CHANNEL_ID')

# 定義台灣時區 (UTC+8)
TW_TZ = timezone(timedelta(hours=8))

class MyBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        self.monthly_report_task.start()
        print(f"Synced commands for {self.user}")

    @tasks.loop(hours=24)
    async def monthly_report_task(self):
        now_tw = datetime.now(TW_TZ)
        if now_tw.day == 1:
            channel = self.get_channel(int(REPORT_CHANNEL_ID))
            if channel:
                # 自動發送上個月報表 (邏輯修正：計算上個月日期區間)
                today = now_tw.date()
                last_month_end = today.replace(day=1) - timedelta(days=1)
                last_month_start = last_month_end.replace(day=1)
                await generate_summary_report(channel, "上月結算", last_month_start, last_month_end)

bot = MyBot()

# ==========================================
# 2. 資料庫核心連線
# ==========================================
def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host='127.0.0.1',
            user='bot_user',
            password=DB_PASS,
            database='discord_bot_db',
            auth_plugin='mysql_native_password'
        )
        return connection
    except Error as e:
        print(f"❌ [DEBUG] 資料庫連線失敗: {e}")
        return None

# ==========================================
# 3. 報表產生核心邏輯
# ==========================================
async def generate_summary_report(target, title_suffix, start_date, end_date):
    """
    通用報表產生器
    start_date, end_date 必須是 datetime.date 物件
    """
    conn = get_db_connection()
    if not conn:
        if isinstance(target, discord.Interaction):
            await target.followup.send("❌ 資料庫連線失敗")
        else:
            await target.send("❌ 資料庫連線失敗")
        return
    
    try:
        cursor = conn.cursor()
        # SQL 查詢：篩選日期區間
        query = """
            SELECT category, SUM(amount) 
            FROM expenses 
            WHERE created_at >= %s AND created_at < %s
            GROUP BY category
        """
        # 結束日設為隔天凌晨，以包含當天資料
        next_day = end_date + timedelta(days=1)
        cursor.execute(query, (start_date, next_day))
        results = cursor.fetchall()
        
        embed = discord.Embed(
            title=f"📊 支出報表：{title_suffix}", 
            description=f"📅 區間：`{start_date}` 至 `{end_date}` (台北時間)",
            color=0x3498db
        )
        
        total = 0
        if not results:
            embed.add_field(name="提示", value="此時段內無紀錄。")
        else:
            for cat, amt in results:
                embed.add_field(name=cat, value=f"${amt:,}", inline=True)
                total += amt
            embed.add_field(name="💰 總計支出", value=f"**${total:,}**", inline=False)
        
        # 判斷目標是 Interaction 還是 Channel
        if isinstance(target, discord.Interaction):
            await target.followup.send(embed=embed)
        else:
            await target.send(embed=embed)

    finally:
        if conn.is_connected(): conn.close()

# ==========================================
# 4. 斜線指令
# ==========================================

# --- 指令：新增開支 (/add) ---
@bot.tree.command(name="add", description="新增一筆開支")
@app_commands.describe(category="分類 (食、衣、住、行、育、樂)", amount="金額", item_name="項目名稱")
async def add(interaction: discord.Interaction, category: str, amount: int, item_name: str = None):
    # 延遲回應，解決「Unknown interaction」問題
    await interaction.response.defer()
    
    # 核心修正：手動計算台灣現在時間
    now_tw = datetime.now(TW_TZ)
    
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            await interaction.followup.send("❌ 資料庫連線失敗")
            return
            
        cursor = conn.cursor()
        # 注意：SQL 語法現在明確包含 created_at 欄位，由 Python 傳入
        sql = "INSERT INTO expenses (user_id, category, amount, item_name, created_at) VALUES (%s, %s, %s, %s, %s)"
        val = (interaction.user.id, category, amount, item_name, now_tw)
        
        cursor.execute(sql, val)
        conn.commit()
        
        # --- [找回 UI] 這裡把精美的 Embed 加回來 ---
        embed = discord.Embed(title="✅ 記帳成功", color=0x2ecc71)
        embed.add_field(name="分類", value=category, inline=True)
        embed.add_field(name="金額", value=f"${amount:,}", inline=True)
        embed.add_field(name="項目", value=item_name or "未填寫", inline=False)
        # 顯示台灣時間
        embed.set_footer(text=f"記錄時間 (台北): {now_tw.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 改用 followup.send 發送 Embed
        await interaction.followup.send(embed=embed)

    except Exception as e:
        print(f"❌ 出錯了: {e}")
        await interaction.followup.send(f"❌ 發生錯誤: {e}")
    finally:
        if conn and conn.is_connected(): conn.close()

# --- 指令：綜合報表 (/summary) ---
@bot.tree.command(name="summary", description="查看支出報表 (YYMMDD-YYMMDD)")
@app_commands.describe(date_range="例如：260310-260324 (留空則顯示本月至今)")
async def summary(interaction: discord.Interaction, date_range: str = None):
    # 報表也需要延遲回應
    await interaction.response.defer()
    try:
        if date_range:
            parts = date_range.split('-')
            start_dt = datetime.strptime(f"20{parts[0]}", "%Y%m%d").date()
            end_dt = datetime.strptime(f"20{parts[1]}", "%Y%m%d").date()
            title = "自定義區間"
        else:
            now_tw = datetime.now(TW_TZ)
            start_dt = now_tw.date().replace(day=1)
            end_dt = now_tw.date()
            title = f"{now_tw.month} 月份總結 (至今)"
            
        await generate_summary_report(interaction, title, start_dt, end_dt)
        
    except ValueError:
        await interaction.followup.send("❌ 日期格式錯誤！請使用 `YYMMDD-YYMMDD` (例如 `260301-260315`)。")
    except Exception as e:
        await interaction.followup.send(f"❌ 發生未知錯誤: {e}")

# --- 指令：日幣匯率 (/jpy) ---
@bot.tree.command(name="jpy", description="日本旅遊小幫手：日幣轉台幣")
@app_commands.describe(jpy_amount="要換算的日幣金額")
async def jpy(interaction: discord.Interaction, jpy_amount: float):
    url = "https://api.frankfurter.app/latest?from=JPY&to=TWD"
    try:
        r = requests.get(url).json()
        rate = r['rates']['TWD']
        await interaction.response.send_message(f"🇯🇵 ¥{jpy_amount:,} → 🇹🇼 NT${jpy_amount * rate:,.2f} (參考匯率: {rate})")
    except:
        await interaction.response.send_message("目前無法取得即時匯率，請稍後再試。")

if __name__ == "__main__":
    bot.run(TOKEN)