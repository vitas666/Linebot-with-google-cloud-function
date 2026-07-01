from datetime import datetime, timedelta
import requests
import yfinance as yf
import pandas as pd
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Utils.fetchStockContent import fetchLargeShareholdersData
from Utils.googleSearch import findStockNews
from DB.DBConnection import get_user_holdings
from GenerativeAI import responseByAI
from DB.DBConnection import get_user_holdings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def fetchLimitUpDownStocks(date_str: str) -> str:
    """
    獲取指定日期（格式：YYYYMMDD）的上市漲停與跌停股票清單。
    利用證交所「每日收盤行情」API，一次性過濾全市場數據。
    """
    print(f"正在掃描 {date_str} 的全市場收盤行情...")
    
    # 證交所 API：type=ALLBUT0999 代表「全部上市股票 (不含權證、牛熊證)」
    url = f"https://www.twse.com.tw/exchangeReport/MI_INDEX"
    params = {
        "response": "json",
        "date": date_str,
        "type": "ALLBUT0999"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        res = requests.get(url, params=params, headers=headers, timeout=10, verify=False)
        res_json = res.json()
        print(res_json)
        
        if res_json.get("stat") != "OK":
            return f"無法取得 {date_str} 的資料，可能是假日或尚未收盤。"
            
        # 🌟 動態尋找資料表：證交所回傳很多表格，我們找出包含「證券代號」與「收盤價」的那一張
        target_fields = []
        target_data = []

        for table in res_json.get("tables", []):
            raw_fields = table.get("fields", [])
            # 去除隱藏空白字元
            fields = [str(f).strip() for f in raw_fields]
            
            # 如果這個表格的欄位剛好包含這兩個，那它就是我們要的「收盤行情表」
            if "證券代號" in fields and "收盤價" in fields:
                target_fields = fields
                target_data = table.get("data", [])
                break
                    
        if not target_data:
            return {"status": "error", "message": "資料格式解析失敗，找不到對應的收盤行情表。"}
            
        # 建立欄位索引字典，方便後續抽取資料
        col_idx = {name: idx for idx, name in enumerate(target_fields)}
        
        limit_up_list = []
        limit_down_list = []
        
        # 開始掃描全市場股票
        for row in target_data:
            stock_id = row[col_idx["證券代號"]]
            stock_name = row[col_idx["證券名稱"]]
            
            # 清理字串中的逗號 (例如 1,000.50 -> 1000.50) 並過濾掉未成交('--')的股票
            close_str = row[col_idx["收盤價"]].replace(",", "")
            diff_str = row[col_idx["漲跌價差"]].replace(",", "")
            sign_str = row[col_idx["漲跌(+/-)"]] # 證交所的漲跌符號通常會包在 HTML tag 裡
            
            if close_str == "--" or diff_str == "--":
                continue
                
            try:
                close_price = float(close_str)
                diff = float(diff_str)
                
                if close_price == 0:
                    continue
                    
                # 判斷是漲還是跌
                is_up = "+" in sign_str
                is_down = "-" in sign_str
                
                # 推算昨收價，藉此精準計算漲跌幅
                if is_up:
                    prev_close = close_price - diff
                elif is_down:
                    prev_close = close_price + diff
                else:
                    prev_close = close_price # 平盤
                    
                if prev_close == 0:
                    continue
                    
                # 計算真實漲跌幅百分比
                change_percent = (diff / prev_close) * 100
                
                # 🌟 實務經驗法則：大於 9.5% 視為漲停，大於 9.5% 的跌幅視為跌停
                if is_up and change_percent >= 9.5:
                    limit_up_list.append(f"{stock_id} {stock_name} ({close_price})")
                elif is_down and change_percent >= 9.5:
                    limit_down_list.append(f"{stock_id} {stock_name} ({close_price})")
                    
            except ValueError:
                # 遇到無法轉成數字的奇怪資料就跳過
                continue

        # 整理最終要輸出的字串格式
        up_count = len(limit_up_list)
        down_count = len(limit_down_list)
        
        # 用「、」把清單串起來，如果沒有半家則顯示「無」
        up_stocks_str = "、".join(limit_up_list) if up_count > 0 else "無"
        down_stocks_str = "、".join(limit_down_list) if down_count > 0 else "無"
        
        reply_msg = (
            f"{date_str} 上市漲跌停統計\n"
            f"-------------------------------\n"
            f"🔴 漲停家數：{up_count} 家\n"
            f"{up_stocks_str}\n"
            f"-------------------------------\n"
            f"🟢 跌停家數：{down_count} 家\n"
            f"{down_stocks_str}"
        )
        
        return reply_msg 
        # return {
        #     "status": "success",
        #     "date": date_str,
        #     "limit_up_count": len(limit_up_list),
        #     "limit_down_count": len(limit_down_list),
        #     "limit_up_stocks": limit_up_list,
        #     "limit_down_stocks": limit_down_list
        # }

    except Exception as e:
        return {"status": "error", "message": f"抓取漲跌停資料時發生錯誤: {e}"}


def fetch_top_20_most_active_tw() -> str:
    """
    透過台灣證券交易所 (TWSE) 官方 OpenAPI，
    光速取得當日「上市成交量排名前 20 名」的熱力榜。
    """
    print("🇹🇼 正在呼叫台灣證交所 OpenAPI，獲取當日成交量 Top 20...")
    
    url = "https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX20"
    
    try:
        # 官方 API 非常穩定，設 5 秒 timeout 綽綽有餘
        res = requests.get(url, timeout=5) 
        
        if res.status_code != 200:
            return f"⚠️ 證交所 API 回傳異常，狀態碼: {res.status_code}"
            
        data = res.json()
        if not data:
            return "⚠️ 今日集中市場尚未產生或查無交易資料。"

        output_msg = f"🔥 【台股本日成交量 Top 20 熱力榜】\n"
        output_msg += "=" * 30 + "\n"
        
        for item in data[:20]:
            rank = int(item.get("Rank", 0))
            stock_id = item.get("StockNo", "")
            
            # 證交所給的公司全名有時會帶全形空白，把它清除乾淨並限縮字數
            name = item.get("Name", "").strip()[:10]
            
            # 💡 【核心物理轉換】證交所回傳的 TradeVolume 單位是「股」！
            # 台灣散戶習慣看「張」，所以我們除以 1,000：
            raw_shares = int(item.get("TradeVolume", 0))
            volume_in_zhang = raw_shares // 1000
            
            # 轉換為 萬張 或 張，版面極度清爽
            if volume_in_zhang >= 10_000:
                vol_str = f"{volume_in_zhang / 10000:.1f}萬張"
            else:
                vol_str = f"{volume_in_zhang:,}張"

            price_str = item.get("ClosingPrice", "0")
            change_amount = item.get("Change", "0")
            direction = item.get("Dir", "").strip() # '+', '-', 或代表平盤的奇怪標籤

            # 💡 【高階算術】證交所 API 只給「漲跌幾元」，沒給「漲跌幅(%)」
            # 我們自己逆推算回散戶愛看的百分比：
            try:
                price = float(price_str)
                chg_val = float(change_amount)
                
                # 證交所 API 遇到平盤時，Dir 欄位會吐出像 '<p> </p>' 這種 XML 廢碼
                if "p" in direction or direction == "" or chg_val == 0:
                    change_str = "平盤 0.00%"
                elif direction == "+":
                    prev_close = price - chg_val
                    pct = (chg_val / prev_close) * 100 if prev_close > 0 else 0
                    change_str = f"🔺 +{pct:.2f}%"
                elif direction == "-":
                    prev_close = price + chg_val
                    pct = (chg_val / prev_close) * 100 if prev_close > 0 else 0
                    change_str = f"🔻 -{pct:.2f}%"
                else:
                    change_str = f"{direction} {chg_val}"
            except:
                price = 0.0
                change_str = f"{direction} {change_amount}"

            # 嚴格等寬排版
            output_msg += f"[{rank:02d}] {stock_id:<5} {name:<6} | {vol_str:<7} | {change_str} (${price:.2f})\n"

        output_msg += "=" * 30 + "\n"
        output_msg += "💡 資料來源：台灣證券交易所官方 OpenAPI (集中市場)"
        
        return output_msg

    except Exception as e:
        return f"❌ 抓取台股熱門榜發生錯誤: {e}"


def fetch_top_20_most_active_us() -> str:
    """
    攔截 Yahoo Finance 官方的「本日最熱門交易 (Most Actives)」隱藏 API，
    光速抓取全美股成交量前 20 名的榜單（包含成交量、最新報價、漲跌幅）。
    """
    print("🇺🇸 正在攔截 Yahoo 伺服器，請求本日美股成交量 Top 20 榜單...")
    
    # 這是 Yahoo 網頁版背後真正在要資料的 Screener API
    url = "https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved"
    
    params = {
        "scrIds": "most_actives", # 參數指明要抓「成交量熱門榜」
        "count": 20               # 精準拿前 20 名
    }
    
    # ⚠️ 爬蟲鐵律：必須偽裝成正常的瀏覽器 User-Agent，否則 Yahoo 會送你 403 Forbidden
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    
    try:
        res = requests.get(url, params=params, headers=headers, timeout=10)
        
        if res.status_code != 200:
            return f"⚠️ 無法取得榜單，Yahoo 回傳狀態碼: {res.status_code}"
            
        data = res.json()
        result_list = data.get("finance", {}).get("result", [])
        
        if not result_list:
            return "⚠️ 查無成交量排行資料。"
            
        # 所有的股票報價陣列都藏在這個 quotes 裡面
        quotes = result_list[0].get("quotes", [])
        
        # 開始組裝給 Line Bot 的漂亮文字卡片
        output_msg = f"🔥 【美股本日成交量 Top 20 熱力榜】\n"
        output_msg += "=" * 30 + "\n"
        
        for rank, q in enumerate(quotes[:20], 1):
            symbol = q.get("symbol", "N/A")
            # 為了避免某些公司全名太長把 Line 版面撐爆，我們只取前10個字
            name = q.get("shortName", "")[:10] 
            price = q.get("regularMarketPrice", 0.0)
            change_pct = q.get("regularMarketChangePercent", 0.0)
            volume = q.get("regularMarketVolume", 0)
            
            # 💡 【UX 貼心設計】美股成交量單位是「股」，台灣人習慣看「張」或「萬」
            # 我們把它優化成 M (百萬股) 或 萬股，大腦秒懂：
            if volume >= 1_000_000:
                vol_str = f"{volume / 1_000_000:.2f}M"
            else:
                vol_str = f"{volume / 10_000:.0f}萬"
                
            # 漲跌幅加上正負號與視覺化 Emoji
            if change_pct > 0:
                change_str = f"🔺 +{change_pct:.2f}%"
            elif change_pct < 0:
                change_str = f"🔻 {change_pct:.2f}%"
            else:
                change_str = "0.00%"

            # 採用固定寬度排版，確保在 Line 裡面文字對齊
            output_msg += f"[{rank:02d}] {symbol:<5} | {vol_str:<6} | {change_str} (${price:.2f})\n"
        
        output_msg += "=" * 30 + "\n"
        output_msg += "💡 說明：M代表Million(百萬股)，數據為美股全市場即時/盤後統計。"
        
        return output_msg

    except Exception as e:
        return f"❌ 抓取熱門榜時發生錯誤: {e}"
    

def fetch_tw_index_technical_indicators(stock_symbol: str = "TAIEX") -> str:
    """
    獲取台股的經典技術指標 (MA, VOL, RSI, MACD, KD)，預設為台股大盤指數 (TAIEX)
    """
    print("正在透過 FinMind 獲取大盤現貨報價並計算技術指標...")
    
    # 抓取過去 1 年的資料，確保 MACD 和 KD 擁有完美的歷史收斂度
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": stock_symbol,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d")
    }
    
    try:
        # 1. 向 API 請求資料
        res = requests.get(url, params=params, timeout=10)
        data = res.json()
        if data.get("msg") != "success" or not data.get("data"):
            return "查無大盤報價資料或 API 連線異常。"
            
        # 2. 直接將 JSON 轉換為 Pandas DataFrame
        df = pd.DataFrame(data["data"])
        
        # 3. 欄位對齊：將 FinMind 欄位對應到我們習慣的欄位
        df.rename(columns={
            'max': 'High',
            'min': 'Low',
            'close': 'Close',
        }, inplace=True)
        
        # 確保日期格式正確，並照時間排序
        df['date'] = pd.to_datetime(df['date'])
        df.sort_values('date', inplace=True)
        df.reset_index(drop=True, inplace=True)
        
        # 提取運算欄位
        close_px = df['Close']
        high_px = df['High']
        low_px = df['Low']
        
        # ==========================================
        # 📊 手刻移動平均線 (SMA)
        # ==========================================
        df['SMA_5'] = close_px.rolling(window=5).mean()
        df['SMA_20'] = close_px.rolling(window=20).mean()
        
        # ==========================================
        # 📈 手刻相對強弱指標 (RSI - 14日)
        # ==========================================
        delta = close_px.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        
        avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
        
        rs = avg_gain / avg_loss
        df['RSI_14'] = 100 - (100 / (1 + rs))
        
        # ==========================================
        # 📉 手刻 MACD (12, 26, 9)
        # ==========================================
        ema_12 = close_px.ewm(span=12, adjust=False).mean()
        ema_26 = close_px.ewm(span=26, adjust=False).mean()
        df['MACD_line'] = ema_12 - ema_26
        df['Signal_line'] = df['MACD_line'].ewm(span=9, adjust=False).mean()
        df['MACD_histogram'] = df['MACD_line'] - df['Signal_line']
        
        # ==========================================
        # ⚡ 手刻「券商標準版」 KD 指標 (9, 3, 3)
        # ==========================================
        df['9D_High'] = high_px.rolling(window=9).max()
        df['9D_Low'] = low_px.rolling(window=9).min()
        
        denominator = df['9D_High'] - df['9D_Low']
        df['RSV'] = 100 * (close_px - df['9D_Low']) / denominator.replace(0, 1)
        
        # 強制初始值為 50 並手動迴圈收斂
        rsv_list = df['RSV'].fillna(50).tolist()
        k_list = [50.0]
        d_list = [50.0]
        
        for i in range(1, len(rsv_list)):
            today_k = (2/3) * k_list[-1] + (1/3) * rsv_list[i]
            today_d = (2/3) * d_list[-1] + (1/3) * today_k
            k_list.append(today_k)
            d_list.append(today_d)
            
        df['K'] = k_list
        df['D'] = d_list

        # ==========================================
        # 🎁 取出最新一筆資料並整理輸出
        # ==========================================
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        # KD 多空判斷
        curr_k, curr_d = latest['K'], latest['D']
        prev_k, prev_d = prev['K'], prev['D']
        
        kd_signal = "盤整"
        if prev_k < prev_d and curr_k > curr_d:
            kd_signal = "黃金交叉 (轉強)"
        elif prev_k > prev_d and curr_k < curr_d:
            kd_signal = "死亡交叉 (轉弱)"
        elif curr_k > curr_d:
            kd_signal = "偏多"
        elif curr_k < curr_d:
            kd_signal = "偏空"

        # 排版給 Line Bot
        reply_text = f"【{stock_symbol}技術面指標】\n"
        reply_text += "=" * 20 + "\n"
        reply_text += f"日期: {latest['date'].strftime('%Y-%m-%d')}\n"
        reply_text += f"• 收盤指數: {latest['Close']:.2f}\n"
        reply_text += f"• 成交總金額: {(latest['Trading_money']/100000000):.2f} 億元(含ETF與權證)\n"
        reply_text += f"• 5日均線: {latest['SMA_5']:.2f}\n"
        reply_text += f"• 20日均線: {latest['SMA_20']:.2f}\n"
        reply_text += f"• RSI (14日): {latest['RSI_14']:.2f}\n"
        reply_text += f"• MACD柱狀圖: {latest['MACD_histogram']:.2f}\n"
        reply_text += f"• KD 指標: K {curr_k:.2f} / D {curr_d:.2f} ({kd_signal})\n"
        reply_text += "=" * 20
        
        return reply_text

    except Exception as e:
        return f"計算技術指標時發生錯誤: {e}"

def get_us_market_indices() -> str:
    """
    獲取美股四大指數的最新報價與漲跌幅
    """
    # 定義指數名稱與對應的 Yahoo Finance 代號
    indices = {
        "道瓊工業指數": "^DJI",
        "那斯達克指數": "^IXIC",
        "費城半導體指數": "^SOX",
        "標普500指數": "^GSPC"
    }
    
    # 準備用來存放每一行文字的串列
    reply_lines = [
        "美股四大指數最新報價",
        "-------------------------------"
    ]
    
    for name, ticker_symbol in indices.items():
        try:
            ticker = yf.Ticker(ticker_symbol)
            # 獲取最近 5 天的歷史資料 (抓取多天以防遇到週末或國定假日)
            hist = ticker.history(period="5d")
            
            if len(hist) >= 2:
                # 最新交易日收盤價
                current_price = hist['Close'].iloc[-1]
                # 前一交易日收盤價
                previous_close = hist['Close'].iloc[-2]
                # 計算漲跌幅 (%)
                change_percent = ((current_price - previous_close) / previous_close) * 100
                
                # 格式化數字：加上千分位與小數點後兩位
                price_str = f"{current_price:,.2f}"
                
                # 處理漲跌幅的正負號顯示
                sign = "+" if change_percent > 0 else ""
                pct_str = f"{sign}{change_percent:.2f}%"
                
                reply_lines.append(f"{name}：{price_str} ({pct_str})")
            else:
                reply_lines.append(f"{name}：獲取失敗 (資料不足)")
                
        except Exception as e:
            reply_lines.append(f"{name}：獲取失敗")

    return "\n".join(reply_lines)


def fetch_tx_foreign_open_interest(days: int = 7) -> str:
    """
    獲取台灣期貨市場最重要的籌碼指標：「外資台指期未平倉淨口數」
    """
    print("正在調閱外資台指期未平倉籌碼...")
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days)
    
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanFuturesInstitutionalInvestors",
        "data_id": "TX", # TX 是台股大台指期的代碼
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d")
    }
    
    try:
        res = requests.get(url, params=params, timeout=10)
        data = res.json()
        if data.get("msg") != "success" or not data.get("data"):
            return f"查無期貨籌碼資料"
                    
        foreign_records = [r for r in data["data"] if r.get("institutional_investors") == "外資"]
        dealer_records = [r for r in data["data"] if r.get("institutional_investors") == "自營商"]
        investment_records = [r for r in data["data"] if r.get("institutional_investors") == "投信"]
        
        # # 只取使用者要求的近 N 個交易日
        # recent_records = foreign_records[-days:]
        
        # # 開始組裝要回傳給 Line Bot 的訊息
        # reply_msg = f"【外資台指期未平倉趨勢 - 近 {len(recent_records)} 日】\n"
        
        # for record in recent_records:
        #     long_oi = record.get("long_open_interest_balance_volume", 0)
        #     short_oi = record.get("short_open_interest_balance_volume", 0)
        #     net_oi = long_oi - short_oi
            
        #     # 判斷多空情緒
        #     sentiment = "偏多" if net_oi > 0 else "偏空"
        #     if abs(net_oi) > 20000:
        #         sentiment = "極度" + sentiment
                
        #     reply_msg += f"{record['date']}\n"
        #     reply_msg += f"淨未平倉: {net_oi:,} 口 ({sentiment})\n\n"

        # 取得最新一天的外資期貨部位
        latest_foreign_record = foreign_records[-1]
        latest_dealer_record = dealer_records[-1]
        latest_investment_record = investment_records[-1]
        
        # 核心計算：未平倉淨口數 = 多方未平倉 (buy_oi) - 空方未平倉 (sell_oi)
        long_foreign_oi = latest_foreign_record.get("long_open_interest_balance_volume", 0)
        short_foreign_oi = latest_foreign_record.get("short_open_interest_balance_volume", 0)
        net_foreign_oi = long_foreign_oi - short_foreign_oi

        long_dealer_oi = latest_dealer_record.get("long_open_interest_balance_volume", 0)
        short_dealer_oi = latest_dealer_record.get("short_open_interest_balance_volume", 0)
        net_dealer_oi = long_dealer_oi - short_dealer_oi

        long_investment_oi = latest_investment_record.get("long_open_interest_balance_volume", 0)
        short_investment_oi = latest_investment_record.get("short_open_interest_balance_volume", 0)
        net_investment_oi = long_investment_oi - short_investment_oi
            
        summary = {
            # "未平倉資訊": reply_msg,
            "訊息": f"以下為{latest_foreign_record['date']} 台指期三大法人多空單未平倉狀況(正為多，負為空)：",
            "外資淨未平倉": f"{net_foreign_oi} 口",
            "自營商淨未平倉": f"{net_dealer_oi} 口",
            "投信淨未平倉": f"{net_investment_oi} 口",
            "總未平倉": f"{net_foreign_oi + net_dealer_oi + net_investment_oi} 口"
        }
        
        reply_msg = (
            f"📅 以下為 {latest_foreign_record['date']} 台指期三大法人多空單未平倉狀況：\n"
            f"(正為多單，負為空單)\n"
            f"-------------------------------\n"
            f"🔹 外資淨未平倉：{net_foreign_oi:,} 口\n"
            f"🔹 自營商淨未平倉：{net_dealer_oi:,} 口\n"
            f"🔹 投信淨未平倉：{net_investment_oi:,} 口\n"
            f"📊 總未平倉：{net_foreign_oi + net_dealer_oi + net_investment_oi:,} 口"
        )
        return reply_msg

    except Exception as e:
        return f"抓取外資期貨籌碼時發生錯誤: {e}"


def generate_portfolio_advice(holdings: list) -> str:
    """
    根據使用者的持股清單 (含名稱與金額)，呼叫 AI 給予個人化的投資建議。
    """
    if not holdings:
        return "🤖 【AI 個人化投資建議】\n目前尚未設定任何持股，無法提供個人化建議。"

    total_amount = sum(h.get("amount") or 0 for h in holdings)
    holdings_lines = []
    for h in holdings:
        stock_name = h.get("stock_name")
        amount = h.get("amount") or 0
        weight = (amount / total_amount * 100) if total_amount else 0
        holdings_lines.append(f"- {stock_name}：新台幣 {amount:,} 元 (佔比 {weight:.1f}%)")
    holdings_text = "\n".join(holdings_lines)

    prompt = f"""
    你是一位專業且謹慎的理財顧問。以下是某位使用者目前的持股明細：

    {holdings_text}

    總投資金額：新台幣 {total_amount:,} 元

    請根據以上持股狀況，給予這位使用者投資建議，內容需包含：
    1. 資產配置與集中度分析 (是否過度集中在單一標的、產業或地區)
    2. 目前配置的風險與潛在機會
    3. 2-3 點具體且可執行的調整建議

    語氣專業但親切，控制在 300 字以內，並使用繁體中文條列呈現。
    """

    try:
        ai_result = responseByAI(prompt)
        advice_text = ai_result["text_content"]
    except Exception as e:
        return f"🤖 【AI 個人化投資建議】\n產生投資建議時發生錯誤: {e}"

    return f"🤖 【AI 個人化投資建議】\n{advice_text}"


def generate_daily_investment_report(user) -> str:
    """
    每日投資日報主控函數：
    100% 尊重模組化設計，直接呼叫你寫好的各個獨立函數，並依序組裝成最終日報字串。

    執行順序：
    1. 大盤焦點新聞 (findStockNews)
    2. 台指期未平倉 (fetch_tx_foreign_open_interest)
    3. 個人持股大戶籌碼 (迴圈呼叫 fetchLargeShareholdersData)
    4. AI 個人化投資建議 (generate_portfolio_advice)
    5. 成交量排名 (fetch_top_20_most_active_tw)
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    user_holdings = get_user_holdings(user)
    
    # 建立日報的開頭標頭
    report_segments = [
        f"⭐️ 【台股每日投資日報｜{date_str}】 ⭐️\n" + "=\n"
    ]
    
    # =========================================================================
    # 1. 大盤焦點新聞
    # =========================================================================
    try:
        # 直接呼叫你的新聞函數，依據你的減法思維，我們限額 maxResults=1
        news_part = findStockNews(keyword='台股大盤', maxResults=1, hours_limit=48)
        report_segments.append(news_part)
    except Exception as e:
        report_segments.append(f"❌ 讀取大盤焦點新聞時發生錯誤: {e}")

    # =========================================================================
    # 2. 台指期未平倉
    # =========================================================================
    try:
        # 直接呼叫你的期貨未平倉功能
        futures_part = fetch_tx_foreign_open_interest()
        report_segments.append(futures_part)
    except Exception as e:
        report_segments.append(f"❌ 讀取期貨未平倉數據時發生錯誤: {e}")

    # =========================================================================
    # 3. 個人持股大戶籌碼
    # =========================================================================
    portfolio_lines = ["🎯 【個人持股大戶籌碼動態】"]
    if not user_holdings:
        portfolio_lines.append("• 目前尚未設定追蹤任何自選持股。")
    else:
        for holding in user_holdings:
            stock_name = holding.get("stock_name")
            try:
                # 迴圈呼叫你的股權分散表函數，一檔一檔拉出來
                stock_chip_info = fetchLargeShareholdersData(stock_name, days=5)
                portfolio_lines.append(stock_chip_info)
            except Exception as e:
                portfolio_lines.append(f"• {stock_name} 籌碼查詢失敗: {e}")

    # 將個人持股部分用換行組合起來，塞進大報告中
    report_segments.append("\n".join(portfolio_lines))

    # =========================================================================
    # 4. AI 個人化投資建議
    # =========================================================================
    try:
        advice_part = generate_portfolio_advice(user_holdings)
        report_segments.append(advice_part)
    except Exception as e:
        report_segments.append(f"❌ 產生個人化投資建議時發生錯誤: {e}")

    # =========================================================================
    # 5. 成交量排名
    # =========================================================================
    try:
        # 直接呼叫你寫的 Top 20 集中市場熱力榜
        volume_rank_part = fetch_top_20_most_active_tw()
        report_segments.append(volume_rank_part)
    except Exception as e:
        report_segments.append(f"❌ 讀取成交量排行榜時發生錯誤: {e}")

    # =========================================================================
    # 最終組裝
    # =========================================================================
    # 用優雅的雙分隔線，把這五個獨立 Function 吐出來的文字黏接成一大封訊息
    final_report_str = "\n\n" + "\n\n".join(report_segments) + "\n\n" + "=" * 25
    
    return final_report_str


if __name__ == "__main__":
    # 測試一個確定的交易日 (請確保輸入的是台股有開盤的過去日期)
    # test_date = datetime.now().strftime("%Y%m%d") # YYYYMMDD
    
    # result = fetchLimitUpDownStocks(test_date)
    # print(result)

    # print("\n--- 台指大盤技術指標 ---")
    # tw_index_indicators = fetch_tw_index_technical_indicators()
    # print(tw_index_indicators)

    # us_market_indices = get_us_market_indices()
    # print(us_market_indices)

    # print("\n--- 台股熱門榜 ---")
    # top_stocks = fetch_top_20_most_active_tw()
    # print(top_stocks)

    # print("\n--- 美股熱門榜 ---")
    # top_us_stocks = fetch_top_20_most_active_us()
    # print(top_us_stocks)

    # print("\n--- 外資台指期未平倉籌碼 ---")
    # foreign_oi = fetch_tx_foreign_open_interest(1)
    # print(foreign_oi)

    print("\n--- 每日投資日報 ---")
    daily_report = generate_daily_investment_report("YongHan")
    print(daily_report)
