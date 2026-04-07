import requests
import datetime
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


def fetch_tw_index_technical_indicators(ticker_symbol: str = "^TWII") -> dict:
    """
    獲取台股大盤的經典技術指標 (MA, RSI, MACD)。
    純 Pandas 實作，無須依賴 pandas_ta 或 TA-Lib，完美支援最新版 Python。
    """
    print("正在使用Pandas計算台指大盤的最新技術指標...")
    
    try:
        # 抓取最近 3 個月的資料
        df = yf.download(ticker_symbol, period="3mo", progress=False)
        
        if df.empty:
            return {"status": "error", "message": "無法取得大盤報價資料"}
            
        # 處理 yfinance 回傳的 MultiIndex 欄位問題
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        close_px = df['Close']
        
        # ==========================================
        # 📊 1. 手刻移動平均線 (SMA)
        # ==========================================
        df['SMA_5'] = close_px.rolling(window=5).mean()
        df['SMA_20'] = close_px.rolling(window=20).mean()
        
        # ==========================================
        # 📈 2. 手刻相對強弱指標 (RSI - 14日)
        # ==========================================
        # 計算每日漲跌幅
        delta = close_px.diff()
        # 分離上漲與下跌
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        
        # 使用 Wilder's 經典平滑法 (對應 alpha=1/14 的指數移動平均)
        avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
        
        # 計算相對強度 (RS) 與 RSI
        rs = avg_gain / avg_loss
        df['RSI_14'] = 100 - (100 / (1 + rs))
        
        # ==========================================
        # 📉 3. 手刻 MACD (12, 26, 9)
        # ==========================================
        # 計算 12日與 26日 EMA (指數移動平均)
        ema_12 = close_px.ewm(span=12, adjust=False).mean()
        ema_26 = close_px.ewm(span=26, adjust=False).mean()
        
        # 計算 MACD 差離值 (DIF)
        df['MACD_line'] = ema_12 - ema_26
        # 計算訊號線 (DEM)
        df['Signal_line'] = df['MACD_line'].ewm(span=9, adjust=False).mean()
        # 計算柱狀圖 (OSC)
        df['MACD_histogram'] = df['MACD_line'] - df['Signal_line']
        
        # 取得最新一天的所有數據
        latest = df.iloc[-1]
        
        summary = {
            "最新收盤價": f"{latest['Close']:.2f}",
            "5日均線(周線)": f"{latest['SMA_5']:.2f}",
            "20日均線(月線)": f"{latest['SMA_20']:.2f}",
            "RSI (14日)": f"{latest['RSI_14']:.2f}",
            "MACD 柱狀圖": f"{latest['MACD_histogram']:.2f}"
        }
        
        return {
            "status": "success",
            "symbol": "台股加權指數",
            "indicators": summary
        }

    except Exception as e:
        return {"status": "error", "message": f"計算技術指標時發生錯誤: {e}"}
    

def fetch_tx_foreign_open_interest() -> dict:
    """
    獲取台灣期貨市場最重要的籌碼指標：「外資台指期未平倉淨口數」。
    """
    print("正在調閱外資台指期未平倉籌碼...")
    
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=7)
    
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
            
        # 過濾出「外資及陸資」的紀錄
        records = [r for r in data["data"] if r.get("institutional_investors") == "外資"]        
        if not records:
             return {"status": "error", "message": "查無外資期貨紀錄"}
             
        # 取得最新一天的外資期貨部位
        latest_record = records[-1]
        
        # 🌟 核心計算：未平倉淨口數 = 多方未平倉 (buy_oi) - 空方未平倉 (sell_oi)
        # 很多開源資料庫欄位名稱會有落差，我們加上 dict.get 容錯處理
        long_oi = latest_record.get("long_open_interest_balance_volume", 0)
        short_oi = latest_record.get("short_open_interest_balance_volume", 0)
        net_oi = long_oi - short_oi
        
        # 判斷多空情緒
        sentiment = "偏多" if net_oi > 0 else "偏空"
        if abs(net_oi) > 20000:
            sentiment = "極度強烈" + sentiment
            
        summary = {
            "日期": latest_record["date"],
            "外資多單留倉": f"{long_oi} 口",
            "外資空單留倉": f"{short_oi} 口",
            "外資淨未平倉": f"{net_oi} 口 ({sentiment})"
        }
        
        return {
            "status": "success",
            "foreign_futures_oi": summary
        }

    except Exception as e:
        return {"status": "error", "message": f"抓取外資期貨籌碼時發生錯誤: {e}"}
    

if __name__ == "__main__":
    # 測試一個確定的交易日 (請確保輸入的是台股有開盤的過去日期)
    # test_date = "20260407" # YYYYMMDD
    
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
    # if tw_index_indicators["status"] == "success":
    #     for key, value in tw_index_indicators["indicators"].items():
    #         print(f"{key}: {value}")
    # else:
    #     print(tw_index_indicators["message"])

    print("\n--- 外資台指期未平倉籌碼 ---")
    foreign_oi = fetch_tx_foreign_open_interest()
    if foreign_oi["status"] == "success":
        for key, value in foreign_oi["foreign_futures_oi"].items():
            print(f"{key}: {value}")
    else:
        print(foreign_oi["message"])
