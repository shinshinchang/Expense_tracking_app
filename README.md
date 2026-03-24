# 💰 SSC 雲端記帳小幫手 (Discord Bookkeeping Bot)

這是一個基於 Python 與 MySQL 開發的 Discord 記帳機器人，部署於 Oracle Cloud (日本大阪機房)。除了基礎的開支記錄外，還整合了自動化報表分析與日本旅遊匯率換算功能(測試中)。

## 🌟 核心功能
1. 智能記帳系統 (/add)
快速記錄：支援分類（食、衣、住、行等）、金額與自定義項目名稱。
時區自動校正：針對雲端伺服器位在海外的問題，系統自動將所有紀錄校正為 台北時間 (UTC+8)。
防錯機制：內建資料庫連線自動釋放邏輯，確保在高頻率使用下系統依然穩定。

2. 支出報表 (/summary)
本月概覽：一鍵產生本月 1 號至今的各分類支出比例與加總。
區間查詢：支援自定義日期格式（如 260310-260324），精確分析特定時段的消費習慣。
自動化月報：系統內建排程任務（Cron Job），每月 1 號自動推播上月結算至指定頻道。

3. 日本旅遊小幫手 (/jpy) — 測試開發中
即時匯率換算：整合第三方金融 API (Frankfurter)，提供日幣與台幣的即時轉換參考。
彈性擴展：目前為測試階段，未來計畫加入更多幣別與旅遊開支專屬分類。

## 🛠️ 技術架構 (Tech Stack)
開發語言: Python 3.10+\
機器人框架: discord.py (Slash Commands / App Commands)\
資料庫: MySQL 8.0 (由 mysql-connector-python 驅動)\
雲端環境: Oracle Cloud Infrastructure (OCI) - Ubuntu Server 22.04 LTS\
連線工具: SSH (RSA 4096-bit key), Screen (後台持久化執行)

## 📊 資料庫關聯設計 (ERD)
系統使用關聯式資料庫存儲，確保數據的一致性與可追蹤性。

## SQL
CREATE TABLE expenses (\
    id INT AUTO_INCREMENT PRIMARY KEY,\
    user_id VARCHAR(255),        -- Discord 使用者唯一 ID\
    category VARCHAR(50),        -- 消費分類\
    amount INT,                  -- 消費金額\
    item_name VARCHAR(255),      -- 項目備註\
    created_at DATETIME          -- 台北時間紀錄戳記\
);

## 🚀 部署與維運 (Deployment)
環境隔離：使用 Python venv 虛擬環境，避免套件衝突。\
機密管理：使用 .env 檔案管理 Discord Token 與資料庫密碼，防止敏感資訊外洩至 GitHub。\
異地維運：透過 ssh 遠端連線，並利用 screen 實現 24/7 不間斷服務。\
動態擴展：透過雲端控制台 VCN 設定防火牆（Security List），嚴格控管 3306 與 SSH 埠位。

## 📈 未來展望 (Roadmap)
[ ] 加入 matplotlib 繪製圓餅圖，讓報表視覺化。\
[ ] 支援 CSV 匯出功能，方便導入 Excel 進行個人理財分析。\
[ ] 增加「預算提醒」功能，當本月支出超過設定值時自動警告。\
[ ] 完善 /jpy 功能，加入更多匯率 API 備援。


## 好用ubuntu代碼
執行ubuntu: ssh -i "檔案位址" ubuntu@64.110.106.255

回到專案目錄: cd my_bot

建立虛擬環境: source venv/bin/activate

修改程式碼:
1. nano main.py 進入程式碼
2. ctrl+k 全部刪除
3. ctrl+O 存檔(+enter)
4. ctrl+x 離開

查看資料庫:
1. sudo mysql -u bot_user -p 進入(要輸入密碼)
2. USE discord_bot_db; 切換資料庫
3. SELECT * FROM expenses ORDER BY created_at DESC LIMIT 10; 查詢最新10筆資料
4. Exit 離開

啟動: python3 main.py

丟回雲端空間:
1. 回到後台： screen -S my_bot
2. 停止： 按 Ctrl + C
3. 啟動： python3 main.py
4. 離開： 按 Ctrl + A 再按 D
5. 確認後台列表: screen -ls
