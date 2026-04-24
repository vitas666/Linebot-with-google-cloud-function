import json
import os
import sys
import yfinance as yf
import requests
from datetime import datetime
import xml.etree.ElementTree as ET
import pandas as pd
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Dictionary.updateStockName import get_stock_info


def fetchStockFundamentals(symbol: str) -> dict:
    """
    抓取指定股票的客觀基本面數據 (包含法說會關注的毛利率、營收成長、EPS等)。
    範例代碼：台股台積電 '2330.TW' 或 美股 ADR 'TSM'
    """
    print(f"正在檢索 {symbol} 的客觀財務與營運數據...")
    s_id, s_name = get_stock_info(symbol)
    if s_id:
        symbol += '.TW'

    try:
        ticker = yf.Ticker(symbol)
        # 取得公司基本面與財務指標字典
        info = ticker.info
        current_price = ticker.fast_info.last_price

        # 萃取法說會與市場最關注的「客觀硬數據」
        fundamentals = {
            "目前股價": f"${round(current_price, 2)}",
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
    end_date = datetime.now()
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


def fetch_us_stock_chips(symbol: str) -> dict:
    """
    抓取美股特有的籌碼面數據 (季度機構持股、半月做空數據)。
    """
    print(f"正在獲取 {symbol} 的美股籌碼面數據...")
    
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        print(json.dumps(info, indent=4, ensure_ascii=False))
        # 如果找不到資料，代表代號錯誤或 API 阻擋
        if 'shortName' not in info:
            return {"status": "error", "message": f"查無 {symbol} 的籌碼資料"}

        # ==========================================
        # 🏢 1. 機構持股數據 (Institutional Ownership)
        # ==========================================
        # 取得機構持股比例 (轉換為百分比)
        inst_pct = info.get('heldPercentInstitutions')
        inst_pct_str = f"{inst_pct * 100:.2f}%" if inst_pct else "無資料"
        
        # 內部人持股比例 (CEO, 董事等)
        insider_pct = info.get('heldPercentInsiders')
        insider_pct_str = f"{insider_pct * 100:.2f}%" if insider_pct else "無資料"

        # ==========================================
        # 📉 2. 做空數據 (Short Interest) - 約每半個月更新
        # ==========================================
        # 做空股數佔在外流通股數的比例
        short_pct = info.get('shortPercentOfFloat')
        short_pct_str = f"{short_pct * 100:.2f}%" if short_pct else "無資料"
        
        # 空單回補天數 (Short Ratio / Days to Cover)
        short_ratio = info.get('shortRatio')
        short_ratio_str = f"{short_ratio:.2f} 天" if short_ratio else "無資料"
        
        # 總做空股數
        shares_short = info.get('sharesShort')
        shares_short_str = f"{shares_short:,} 股" if shares_short else "無資料"

        # ==========================================
        # 🎁 3. 組合回傳結果 (整理成給 LLM 或 Line Bot 閱讀的格式)
        # ==========================================
        chip_summary = {
            "機構持股比例": inst_pct_str,
            "內部人持股比例": insider_pct_str,
            "做空比例 (Short % of Float)": short_pct_str,
            "空單回補天數 (Days to Cover)": short_ratio_str,
            "目前總做空股數": shares_short_str
        }
        
        reply_msg = f"🏦 【{symbol} 美股籌碼面分佈】\n"
        reply_msg += "=" * 20 + "\n"
        reply_msg += f"• 🏢 機構持股比例: {inst_pct_str} (華爾街大戶佔比)\n"
        reply_msg += f"• 👔 內部人持股: {insider_pct_str} (高管/董事佔比)\n"
        reply_msg += "-" * 20 + "\n"
        reply_msg += f"• 📉 做空比例: {short_pct_str} (越高代表市場越看空)\n"
        reply_msg += f"• 🏃 空單回補天數: {short_ratio_str} (軋空潛在風險)\n"
        reply_msg += f"• 📊 總做空股數: {shares_short_str}\n"
        reply_msg += "=" * 20 + "\n"
        reply_msg += "💡 備註：美股機構持股為季度更新，做空數據為半月更新。"
        
        return reply_msg

    except Exception as e:
        return f"抓取美股籌碼數據時發生錯誤: {e}"
    

def fetchLargeShareholdersData(stock_id: str, days: int = 5) -> dict:
    """
    抓取台股「外資持股比例」的週變化，天數預設為五天
    比較不同天數區間，外資大戶的持股增減。
    """
    print(f"正在檢索 {stock_id} 的外資大戶持股動向...")
    
    end_date = datetime.now()
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


def fetch_historical_pe_bands(stock_id: str, years: int = 3) -> dict:
    """
    獲取個股歷史本益比，並計算出「歷史最高、最低、平均與目前位階」。
    將龐大的時間序列資料壓縮為 AI 容易理解的統計特徵。
    """
    print(f"正在計算 {stock_id} 過去 {years} 年的估值位階...")
    
    end_date = datetime.now()
    start_date = end_date - datetime.timedelta(days=years * 365)
    
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockPER",
        "data_id": stock_id,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d")
    }
    
    try:
        res = requests.get(url, params=params, timeout=10)
        data = res.json()
        
        if data.get("msg") != "success" or not data.get("data"):
            return {"status": "error", "message": "查無本益比資料"}
            
        records = data["data"]
        
        # 提取本益比資料，過濾掉為 0 或負數(通常代表公司該季虧損)的無效數值
        pe_list = [r["PER"] for r in records if r.get("PER", 0) > 0]
        
        if not pe_list:
            return {"status": "error", "message": "無有效本益比數據 (可能近期皆為虧損)"}
            
        latest_pe = pe_list[-1]
        max_pe = max(pe_list)
        min_pe = min(pe_list)
        avg_pe = sum(pe_list) / len(pe_list)
        
        # 找出中位數，避免極端值的干擾
        sorted_pe = sorted(pe_list)
        median_pe = sorted_pe[len(sorted_pe)//2]
        
        # 🌟 核心指標：計算目前位階百分比 (0% 代表跌到歷史最低，100% 代表創歷史新高)
        if max_pe == min_pe:
            position_percent = 50.0
        else:
            position_percent = ((latest_pe - min_pe) / (max_pe - min_pe)) * 100
            
        summary = {
            "資料區間": f"過去 {years} 年",
            "目前本益比": round(latest_pe, 2),
            "歷史最高本益比": round(max_pe, 2),
            "歷史最低本益比": round(min_pe, 2),
            "歷史平均本益比": round(avg_pe, 2),
            "歷史中位數本益比": round(median_pe, 2),
            # 給 AI 看的超直覺指標
            "目前歷史位階": f"{round(position_percent, 2)}% (100%代表最貴，0%代表最便宜)"
        }
        
        return {
            "status": "success",
            "symbol": stock_id,
            "pe_evaluation": summary
        }

    except Exception as e:
        return {"status": "error", "message": f"計算估值位階時發生錯誤: {e}"}


def fetch_us_historical_pe_bands(symbol: str, years: int = 3):
    print(f"正在分析 {symbol} 過去 {years} 年的美股估值數據...")
    
    ticker = yf.Ticker(symbol)
    
    # 1. 獲取歷史股價 (每日)
    end_date = datetime.now()
    start_date = end_date - datetime.timedelta(days=years * 365 + 120) # 多取4個月以計算第一個TTM
    hist = ticker.history(start=start_date, end=end_date)
    if hist.empty:
        return {"status": "error", "message": "找不到股價資料"}
    hist.index = hist.index.tz_localize(None)

    # 2. 獲取季度財報 (用於計算 EPS)
    # financials 包含每年的，quarterly_financials 包含每季的
    q_financials = ticker.quarterly_financials
    if q_financials.empty:
        return {"status": "error", "message": "無法取得財務報表"}

    # 提取 Diluted EPS (稀釋後每股盈餘)
    if 'Diluted EPS' in q_financials.index:
        eps_data = q_financials.loc['Diluted EPS']
    elif 'Basic EPS' in q_financials.index:
        eps_data = q_financials.loc['Basic EPS']
    else:
        return {"status": "error", "message": "報表中缺少 EPS 數據"}

    # 3. 計算 TTM EPS (滾動四季加總)
    eps_series = eps_data.sort_index() # 由舊到新排序
    ttm_eps = eps_series.rolling(window=4).sum().dropna()
    ttm_eps.index = ttm_eps.index.tz_localize(None)
    
    if ttm_eps.empty:
        return {"status": "error", "message": "EPS 數據不足以計算 TTM (需至少四季)"}

    # 4. 將 EPS 對齊到每日股價
    # 我們將 TTM EPS 擴展到每一天，直到下一次財報公佈
    pe_df = hist[['Close']].copy()
    # 將 EPS 的日期標記為「生效日」（通常財報公告會有延遲，這裡簡化處理）
    pe_df['ttm_eps'] = pd.Series(ttm_eps, index=ttm_eps.index).reindex(pe_df.index, method='ffill')
    
    # 5. 計算每日 PE
    pe_df['PE'] = pe_df['Close'] / pe_df['ttm_eps']
    
    # 過濾無效值 (PE < 0 通常不具參考價值)
    valid_pe = pe_df[pe_df['PE'] > 0]['PE']
    
    if valid_pe.empty:
        return {"status": "error", "message": "該股票可能較新，暫無有效歷史本益比"}

    # 6. 統計分析 (沿用你的邏輯)
    latest_pe = float(valid_pe.iloc[-1])
    max_pe = float(valid_pe.max())
    min_pe = float(valid_pe.min())
    avg_pe = float(valid_pe.mean())
    median_pe = float(valid_pe.median())

    position_percent = ((latest_pe - min_pe) / (max_pe - min_pe)) * 100 if max_pe != min_pe else 50.0

    return {
        "status": "success",
        "symbol": symbol,
        "summary": {
            "目前本益比": round(latest_pe, 2),
            "歷史最高": round(max_pe, 2),
            "歷史最低": round(min_pe, 2),
            "歷史平均": round(avg_pe, 2),
            "歷史中位數": round(median_pe, 2),
            "目前位階": f"{round(position_percent, 2)}%"
        }
    }

def getStockExcel(symbol: str):
    ticker = yf.Ticker(symbol)
    balance_sheet = ticker.balance_sheet
    balance_sheet.to_excel(f"{symbol}_balance_sheet.xlsx")
    print(f"Excel 檔案已儲存！")

def to_pct(val) -> str:
    # 輔助函數：將小數點轉為漂亮的百分比格式 (例如 0.531 -> 53.1%)
    return f"{round(val * 100, 2)}%"


if __name__ == "__main__":
    stock_data = fetchStockFundamentals("MU")
    for key, value in stock_data.items():
        print(f"指標 | {key}: {value}")

    # tsmc_chip = fetchMarketLeverage("2330")
    # print(f"\n--- {tsmc_chip['symbol']} 籌碼面數據 ({tsmc_chip['period']}) ---")
    # for key, value in tsmc_chip["chip_data"].items():
    #     # 加上明顯的買賣指標，幫助 LLM 理解情緒
    #     action = "買超" if value > 0 else "賣超"
    #     print(f"{key}: {value:,.0f} 張 ({action})")
    # for key, value in tsmc_chip["margin_data"].items():
    #     print(f"{key}: {value}")
    # us_stock = fetch_us_stock_chips("SNDK")
    # print(us_stock)
    # tsmc_large_shareholders = fetchLargeShareholdersData("2330", 4)
    # print(tsmc_large_shareholders)
    # print(f"\n--- {tsmc_large_shareholders['symbol']} 外資持股比例 ---")
    # for key, value in tsmc_large_shareholders["large_shareholders"].items():
    #     print(f"{key}: {value}")

    # tsmc_pe_bands = fetch_historical_pe_bands("2330", 3)
    # print(f"\n--- {tsmc_pe_bands['symbol']} 歷史本益比評估 ---")
    # for key, value in tsmc_pe_bands["pe_evaluation"].items():
    #     print(f"{key}: {value}")
    # us_pe_bands = fetch_us_historical_pe_bands("MU")
    # print(us_pe_bands)
