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
# 1. 初始設定
# ==========================================
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
DB_PASS = os.getenv('DB_PASS')
REPORT_CHANNEL_ID = os.getenv('REPORT_CHANNEL_ID')
TW_TZ = timezone(timedelta(hours=8))

# --- 刪除按鈕組件 ---
class DeleteButton(discord.ui.View):
    def __init__(self, record_id):
        super().__init__(timeout=600)
        self.record_id = record_id

    @discord.ui.button(label="🗑️ 刪除此筆資料", style=discord.ButtonStyle.danger)
    async def delete_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        conn = get_db_connection()
        if not conn:
            await interaction.response.send_message("❌ 無法連線資料庫", ephemeral=True)
            return
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM expenses WHERE id = %s", (self.record_id,))
            conn.commit()
            
            # 刪除成功後，停用按鈕並更改外觀
            button.label = "已從資料庫刪除"
            button.disabled = True
            button.style = discord.ButtonStyle.secondary
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(f"✅ 成功移除紀錄 (ID: {self.record_id})", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 刪除失敗: {e}", ephemeral=True)
        finally:
            conn.close()

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
                today = now_tw.date()
                last_month_end = today.replace(day=1) - timedelta(days=1)
                last_month_start = last_month_end.replace(day=1)
                await generate_summary_report(channel, "上月自動結算", last_month_start, last_month_end)

bot = MyBot()

# ==========================================
# 2. 資料庫連線
# ==========================================
def get_db_connection():
    try:
        return mysql.connector.connect(
            host='127.0.0.1',
            user='bot_user',
            password=DB_PASS,
            database='discord_bot_db',
            auth_plugin='mysql_native_password'
        )
    except Error as e:
        print(f"❌ 資料庫錯誤: {e}")
        return None

# ==========================================
# 3. 報表產生
# ==========================================
async def generate_summary_report(target, title_suffix, start_date, end_date, target_category=None):
    conn = get_db_connection()
    if not conn: return
    
    try:
        cursor = conn.cursor()
        next_day = end_date + timedelta(days=1)
        embed = discord.Embed(color=0x3498db)
        
        if target_category:
            query = """
                SELECT item_name, amount, created_at 
                FROM expenses 
                WHERE created_at >= %s AND created_at < %s AND category = %s
                ORDER BY created_at ASC
            """
            cursor.execute(query, (start_date, next_day, target_category))
            results = cursor.fetchall()
            
            embed.title = f"🔍 類別明細：{target_category}"
            embed.description = f"📅 區間：`{start_date}` 至 `{end_date}`"
            
            total = 0
            if not results:
                embed.add_field(name="結果", value="此時段內該類別無紀錄。")
            else:
                items_text = ""
                for item, amt, dt in results:
                    items_text += f"• `{dt.strftime('%m/%d')}` {item or '未命名'}: **${amt:,}**\n"
                    total += amt
                # Discord Embed 欄位長度限制為 1024 字符
                embed.add_field(name="項目清單", value=items_text[:1000] or "無內容", inline=False)
                embed.add_field(name="💰 分類總計", value=f"**${total:,}**", inline=False)
        else:
            query = """
                SELECT category, SUM(amount) 
                FROM expenses 
                WHERE created_at >= %s AND created_at < %s
                GROUP BY category
            """
            cursor.execute(query, (start_date, next_day))
            results = cursor.fetchall()
            
            embed.title = f"📊 支出報表：{title_suffix}"
            embed.description = f"📅 區間：`{start_date}` 至 `{end_date}`"
            
            total = 0
            if not results:
                embed.add_field(name="結果", value="此時段內無任何記帳紀錄。")
            else:
                for cat, amt in results:
                    embed.add_field(name=cat, value=f"${amt:,}", inline=True)
                    total += amt
                embed.add_field(name="💰 總計支出", value=f"**${total:,}**", inline=False)

        if isinstance(target, discord.Interaction):
            await target.followup.send(embed=embed)
        else:
            await target.send(embed=embed)
    finally:
        conn.close()

# ==========================================
# 4. 斜線指令
# ==========================================

# --- [新增開支] ---
@bot.tree.command(name="add", description="新增一筆開支紀錄")
@app_commands.describe(category="請選擇或輸入分類", amount="支出金額", item_name="項目描述 (選填)")
async def add(interaction: discord.Interaction, category: str, amount: int, item_name: str = None):
    await interaction.response.defer()
    now_tw = datetime.now(TW_TZ)
    conn = get_db_connection()
    if not conn: return
    
    try:
        cursor = conn.cursor()
        sql = "INSERT INTO expenses (user_id, category, amount, item_name, created_at) VALUES (%s, %s, %s, %s, %s)"
        val = (interaction.user.id, category, amount, item_name, now_tw)
        cursor.execute(sql, val)
        conn.commit()
        last_id = cursor.lastrowid 

        embed = discord.Embed(title="✅ 記帳成功", color=0x2ecc71)
        embed.add_field(name="分類", value=f"`{category}`", inline=True)
        embed.add_field(name="金額", value=f"**${amount:,}**", inline=True)
        embed.add_field(name="項目", value=item_name or "未填寫", inline=False)
        embed.set_footer(text=f"紀錄 ID: {last_id} | 台北時間: {now_tw.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 發送 Embed 並附帶刪除按鈕
        await interaction.followup.send(embed=embed, view=DeleteButton(last_id))
    except Exception as e:
        await interaction.followup.send(f"❌ 儲存失敗: {e}")
    finally:
        conn.close()

# --- 分類選單自動補全邏輯 ---
@add.autocomplete('category')
async def category_autocomplete(interaction: discord.Interaction, current: str):
    # 這是你指定的 default choices
    default_choices = ['food', 'clothes', 'traffic', 'credit card', 'rental fee', 'entertainment', 'medical']
    return [
        app_commands.Choice(name=choice, value=choice)
        for choice in default_choices if current.lower() in choice.lower()
    ][:25]

# --- 支援日期與類別篩選 ---
@bot.tree.command(name="summary", description="產出支出報表")
@app_commands.describe(date_range="格式：260310-260324 (不填則顯示本月)", target_category="選填：指定查看某一類別細項")
async def summary(interaction: discord.Interaction, date_range: str = None, target_category: str = None):
    await interaction.response.defer()
    try:
        now_tw = datetime.now(TW_TZ)
        if date_range:
            parts = date_range.split('-')
            start_dt = datetime.strptime(f"20{parts[0]}", "%Y%m%d").date()
            end_dt = datetime.strptime(f"20{parts[1]}", "%Y%m%d").date()
            title = "自定義區間"
        else:
            start_dt = now_tw.date().replace(day=1)
            end_dt = now_tw.date()
            title = f"{now_tw.month} 月份總計"
            
        await generate_summary_report(interaction, title, start_dt, end_dt, target_category)
    except Exception as e:
        await interaction.followup.send(f"❌ 查詢失敗！請確認日期格式是否為 `YYMMDD-YYMMDD`。\n(錯誤訊息: {e})")

# --- 日幣匯率 ---
@bot.tree.command(name="jpy", description="日幣匯率即時換算")
@app_commands.describe(jpy_amount="要換算的日幣金額")
async def jpy(interaction: discord.Interaction, jpy_amount: float):
    url = "https://api.frankfurter.app/latest?from=JPY&to=TWD"
    try:
        r = requests.get(url).json()
        rate = r['rates']['TWD']
        await interaction.response.send_message(f"🇯🇵 ¥{jpy_amount:,} → 🇹🇼 NT${jpy_amount * rate:,.2f} (參考匯率: {rate})")
    except:
        await interaction.response.send_message("❌ 匯率服務暫時無法連線。")

if __name__ == "__main__":
    if not TOKEN:
        print("❌ 找不到 Token！請檢查 .env")
    else:
        bot.run(TOKEN)
