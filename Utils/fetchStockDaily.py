from datetime import datetime, timedelta
import requests
import yfinance as yf
import pandas as pd
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def fetchLimitUpDownStocks(date_str: str) -> dict:
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
            return {"status": "error", "message": f"無法取得 {date_str} 的資料，可能是假日或尚未收盤。"}
            
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
                
        return {
            "status": "success",
            "date": date_str,
            "limit_up_count": len(limit_up_list),
            "limit_down_count": len(limit_down_list),
            "limit_up_stocks": limit_up_list,
            "limit_down_stocks": limit_down_list
        }

    except Exception as e:
        return {"status": "error", "message": f"抓取漲跌停資料時發生錯誤: {e}"}


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


def get_us_market_indices():
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
    
    results = []
    for name, ticker_symbol in indices.items():
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
            results.append({
                "指數名稱": name,
                "代號": ticker_symbol,
                "最新報價": round(current_price, 2),
                "漲跌幅 (%)": round(change_percent, 2)
            })
        else:
            results.append({
                "指數名稱": name,
                "代號": ticker_symbol,
                "最新報價": "獲取失敗",
                "漲跌幅 (%)": "獲取失敗"
            })

    return results


def fetch_tx_foreign_open_interest(days: int = 7) -> dict:
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
            return {"status": "error", "message": "查無期貨籌碼資料"}
                    
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
        
        return {
            "status": "success",
            "foreign_futures_oi": summary
        }

    except Exception as e:
        return {"status": "error", "message": f"抓取外資期貨籌碼時發生錯誤: {e}"}
    

if __name__ == "__main__":
    # 測試一個確定的交易日 (請確保輸入的是台股有開盤的過去日期)
    # test_date = datetime.now().strftime("%Y%m%d") # YYYYMMDD
    
    # result = fetchLimitUpDownStocks(test_date)
    
    # if result["status"] == "success":
    #     print(f"\n日期: {result['date']}")
    #     print(f"漲停家數: {result['limit_up_count']}")
    #     # 為了避免洗版，我們只印出前 10 檔
    #     for stock in result['limit_up_stocks']:
    #         print(f"{stock}")
            
    #     print(f"\n跌停家數: {result['limit_down_count']}")
    #     for stock in result['limit_down_stocks']:
    #         print(f"{stock}")

    # print("\n--- 台指大盤技術指標 ---")
    # tw_index_indicators = fetch_tw_index_technical_indicators()
    # print(tw_index_indicators)

    # us_market_indices = get_us_market_indices()
    # print("\n--- 美股四大指數最新報價與漲跌幅 ---")
    # for idx in us_market_indices:
    #     print(f"{idx['指數名稱']} ({idx['代號']}): {idx['最新報價']} 點, 漲跌幅: {idx['漲跌幅 (%)']}%")

    print("\n--- 外資台指期未平倉籌碼 ---")
    foreign_oi = fetch_tx_foreign_open_interest(1)
    if foreign_oi["status"] == "success":
        for key, value in foreign_oi["foreign_futures_oi"].items():
            print(f"{key}: {value}")
    else:
        print(foreign_oi["message"])
