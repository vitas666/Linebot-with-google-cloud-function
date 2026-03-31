import yfinance as yf
import requests
import datetime
import xml.etree.ElementTree as ET
import pandas as pd


def fetchStockPrice(symbol: str) -> float:
    """symbol: 股票代碼，例如 'AAPL' 或 '2330.TW'"""
    try:
        ticker = yf.Ticker(symbol)
        # 取得即時股價 
        current_price = ticker.fast_info.last_price
        return round(current_price, 2)
        
    except Exception as e:
        print(f"抓取 {symbol} 資訊時發生錯誤: {e}")
        return 0


def fetchStockFundamentals(symbol: str) -> dict:
    """
    抓取指定股票的客觀基本面數據 (包含法說會關注的毛利率、營收成長、EPS等)。    
    範例代碼：台股台積電 '2330.TW' 或 美股 ADR 'TSM'
    """
    print(f"正在檢索 {symbol} 的客觀財務與營運數據...")
    
    try:
        ticker = yf.Ticker(symbol)
        # 取得公司基本面與財務指標字典
        info = ticker.info

        # 萃取法說會與市場最關注的「客觀硬數據」
        fundamentals = {
            # 1. 營收與成長性 (替代月營收，觀察季營收年增率)
            "營收成長率 (YoY)": to_pct(info.get("revenueGrowth")),
            "盈餘成長率 (Earnings Growth)": to_pct(info.get("earningsGrowth")),
            
            # 2. 獲利能力 (法說會必考題：三率)
            "毛利率 (Gross Margin)": to_pct(info.get("grossMargins")),
            "營業利益率 (Operating Margin)": to_pct(info.get("operatingMargins")),
            "股東權益報酬率 (ROE)": to_pct(info.get("returnOnEquity")),
            
            # 3. 估值與每股盈餘 (EPS)
            "過去12個月 EPS": info.get("trailingEps", "無資料"),
            "預估未來 EPS (財測)": info.get("forwardEps", "無資料"),
            "目前本益比 (P/E)": round(info.get("trailingPE", 0), 2) if info.get("trailingPE") else "無資料"
        }
        
        return fundamentals
        
    except Exception as e:
        return {"error": f"抓取 {symbol} 財務數據時發生錯誤: {e}"}


def fetchMarketLeverage(stock_id: str, days: int = 5) -> dict:
    """
    抓取台股特有的「籌碼面」數據 (目前實作：三大法人買賣超) 以及融資融券增減情況。
    利用 FinMind 開源 API 取得資料，轉換為 LLM 容易閱讀的文字格式。
    
    參數:
    - stock_id: 台股代碼 (例如 "2330")
    - days: 往前抓取幾天的資料 (預設 5 天，即一週交易日)
    """
    
    # 計算日期範圍
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=days + 4) # 多抓幾天避開假日
    
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    
    url = "https://api.finmindtrade.com/api/v4/data"
    
    try:
        params = {
            "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
            "data_id": stock_id,
            "start_date": start_str,
            "end_date": end_str
        }
        response = requests.get(url, params=params)
        data = response.json()
        if data["msg"] != "success" or not data["data"]:
            return {"status": "error", "message": "查無籌碼資料"}
            
        # 解析籌碼數據
        records = data["data"]
        
        # 我們來統計最近幾天的「外資」與「投信」累積買賣超 (單位: 張)
        # 注意：API 回傳的 buy/sell 是「股數」，除以 1000 換算成「張」
        chip_summary = {
            "外資累積買賣超 (張)": 0,
            "投信累積買賣超 (張)": 0,
            "自營商累積買賣超 (張)": 0
        }
        
        # 建立日期清單以確保我們只抓最近的交易日
        dates_found = sorted(list(set([r['date'] for r in records])), reverse=True)[:days]
        
        for record in records:
            if record['date'] in dates_found:
                net_buy_sell = record['buy'] - record['sell']
                net_volume = round(net_buy_sell / 1000, 2)
                
                # 分類統計
                if "Foreign_Investor" in record['name'] or "Foreign_Dealer_Self" in record['name']:
                    chip_summary["外資累積買賣超 (張)"] += net_volume
                elif "Investment_Trust" in record['name']:
                    chip_summary["投信累積買賣超 (張)"] += net_volume
                elif "Dealer_self" in record['name'] or "Dealer_Hedging" in record['name']:
                    chip_summary["自營商累積買賣超 (張)"] += net_volume

    except Exception as e:
        return {"error": f"抓取籌碼數據時發生錯誤: {e}"}
    
    try:
        params = {
            "dataset": "TaiwanStockMarginPurchaseShortSale", # 融資融券明細
            "data_id": stock_id,
            "start_date": start_str,
            "end_date": end_str
        }
        response = requests.get(url, params=params)
        data = response.json()
        if data.get("msg") != "success" or not data.get("data"):
            return {"status": "error", "message": "查無融資融券資料"}
            
        records = data["data"]
        
        # 取出最近的 N 個交易日
        dates_found = sorted(list(set([r['date'] for r in records])), reverse=True)[:days]
        
        if len(dates_found) < 2:
            return {"status": "error", "message": "資料天數不足以判斷趨勢"}
            
        # 篩選出第一天與最後一天的資料來算差額
        latest_record = next(r for r in records if r['date'] == dates_found[0])
        oldest_record = next(r for r in records if r['date'] == dates_found[-1])
        
        # MarginPurchaseTodayBalance = 融資餘額(張)
        # ShortSaleTodayBalance = 融券餘額(張)
        margin_change = latest_record['MarginPurchaseTodayBalance'] - oldest_record['MarginPurchaseTodayBalance']
        short_change = latest_record['ShortSaleTodayBalance'] - oldest_record['ShortSaleTodayBalance']
        
        margin_summary = {
            "最新資料日期": dates_found[0],
            "目前融資餘額 (張)": latest_record['MarginPurchaseTodayBalance'],
            f"近 {len(dates_found)} 日融資增減 (張)": margin_change,
            "目前融券餘額 (張)": latest_record['ShortSaleTodayBalance'],
            f"近 {len(dates_found)} 日融券增減 (張)": short_change
        }
        
    except Exception as e:
        return {"error": f"抓取融資融券數據時發生錯誤: {e}"}

    return {
        "symbol": stock_id,
        "period": f"最近 {len(dates_found)} 個交易日",
        "chip_data": chip_summary,
        "margin_data": margin_summary
    }

def fetchLargeShareholdersData(stock_id: str, days: int = 5) -> dict:
    """
    抓取台股「外資持股比例」的週變化，天數預設為五天
    比較不同天數區間，外資大戶的持股增減。
    """
    print(f"正在檢索 {stock_id} 的外資大戶持股動向...")
    
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days)
    
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockShareholding", # 股權分散表
        "data_id": stock_id,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d")
    }
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data.get("msg") != "success" or not data.get("data"):
            return {"status": "error", "message": "查無大戶持股資料"}
            
        records = data["data"]
        # 取得最新與前一次的資料 (資料已經照日期排好)
        latest_record = records[-1] # 最新日期
        prev_record = records[0]   # 對應最早日期區間的日期(預設為五天)
        
        # 🌟 毫不囉嗦，直接對應你貼的資料屬性！
        latest_ratio = latest_record['ForeignInvestmentSharesRatio']
        prev_ratio = prev_record['ForeignInvestmentSharesRatio']
        
        summary = {
            "資料比對日期": f"{prev_record['date']} vs {latest_record['date']}",
            "目前外資持股比例": f"{latest_ratio}%",
            "外資持股週變化": f"{round(latest_ratio - prev_ratio, 2)}%"
        }
        
        return {
            "symbol": stock_id,
            "large_shareholders": summary
        }
    
    except Exception as e:
        return {"error": f"抓取大戶持股時發生錯誤: {e}"}


def getStockExcel(symbol: str):
    ticker = yf.Ticker(symbol)
    balance_sheet = ticker.balance_sheet
    balance_sheet.to_excel(f"{symbol}_balance_sheet.xlsx")
    print(f"Excel 檔案已儲存！")


def to_pct(val) -> str:
    # 輔助函數：將小數點轉為漂亮的百分比格式 (例如 0.531 -> 53.1%)
    return f"{round(val * 100, 2)}%"


if __name__ == "__main__":
    # 測試抓取台積電 (TSMC)
    tsmc_data = fetchStockFundamentals("2330.TW")
    for key, value in tsmc_data.items():
        print(f"指標 | {key}: {value}")

    tsmc_chip = fetchMarketLeverage("2330")
    print(f"\n--- {tsmc_chip['symbol']} 籌碼面數據 ({tsmc_chip['period']}) ---")
    for key, value in tsmc_chip["chip_data"].items():
        # 加上明顯的買賣指標，幫助 LLM 理解情緒
        action = "買超" if value > 0 else "賣超"
        print(f"{key}: {value:,.0f} 張 ({action})")
    for key, value in tsmc_chip["margin_data"].items():
        print(f"{key}: {value}")

    tsmc_large_shareholders = fetchLargeShareholdersData("2330", 4)
    print(tsmc_large_shareholders)
    print(f"\n--- {tsmc_large_shareholders['symbol']} 外資持股比例 ---")
    for key, value in tsmc_large_shareholders["large_shareholders"].items():
        print(f"{key}: {value}")

