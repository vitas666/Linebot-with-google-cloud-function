import requests
import datetime
import json
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def fetchMonthlyRevenue(stock_id: str) -> dict:
    """
    抓取台股最新的月營收、年增率(YoY)、月增率(MoM)與官方備註說明。
    """
    print(f"正在檢索 {stock_id} 的最新月營收資料...")
    
    # 月營收每月公布一次，往前抓 120 天確保能拿到最近 3~4 個月的資料來算 MoM
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=120)
    
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockMonthRevenue",
        "data_id": stock_id,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d")
    }
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        if data.get("msg") != "success" or not data.get("data"):
            return {"status": "error", "message": "查無月營收資料"}
            
        records = data["data"]
        
        if len(records) < 2:
             return {"status": "error", "message": "資料月份不足以計算月增率"}
             
        # 取得最新兩個月的營收 (依照日期排序，最後一筆通常是最新)
        latest_record = records[-1]
        prev_record = records[-2]
        
        # 提取數據
        rev_year = latest_record['revenue_year']
        rev_month = latest_record['revenue_month']
        latest_rev = latest_record['revenue']
        prev_rev = prev_record['revenue']
        
        # 計算 MoM (月增率)
        mom_growth = ((latest_rev - prev_rev) / prev_rev) * 100 if prev_rev else 0
        
        summary = {
            "資料月份": f"{rev_year}年 {rev_month}月",
            "單月營收 (億)": f"{round(latest_rev / 100000000, 2)} 億",
            "月增率 (MoM)": f"{round(mom_growth, 2)}%",
            "年增率 (YoY)": f"{latest_record.get('year_on_year_growth_rate', '無資料')}%",
            "累計營收年增率": f"{latest_record.get('accumulated_year_on_year_growth_rate', '無資料')}%",
            "官方備註說明": latest_record.get('note', '無特別說明').strip() or "無特別說明"
        }
        
        return {
            "symbol": stock_id,
            "monthly_revenue": summary
        }

    except Exception as e:
        return {"error": f"抓取月營收時發生錯誤: {e}"}
    

def fetchMaterialInformation(stock_id: str) -> dict:
    """
    抓取台股最新的「公開重大訊息」(Material Information)。
    包含法說會公告、擴廠、營收異常說明等。
    直接對接台灣證交所 Open API。
    """
    print(f"正在檢索 {stock_id} 的最新重大訊息...")
    
    # 這是台灣政府開源資料庫的端點 (回傳目前全市場最新的重大訊息)
    url = "https://openapi.twse.com.tw/v1/opendata/t187ap04_L"
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=15, verify=False)
        response.raise_for_status()
        response.encoding = 'utf-8'
        
        # 2. 讀取下載到記憶體中的純文字內容 (response.text)，然後手動轉成 JSON
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError:
             return {"status": "error", "message": "政府資料格式異常，無法解析 JSON 檔案"}
        # 從全市場的 JSON 中，過濾出我們要的股票代碼
        company_news = [item for item in data if item.get('公司代號') == stock_id]
        
        if not company_news:
            return {"status": "success", "message": "近期無重大訊息公告"}
            
        # 擷取最新的 3 則重大訊息
        recent_news = company_news[:3]
        news_list = []
        
        for news in recent_news:
            # 台灣政府 API 的日期是民國年 (例如 1130510)
            roc_date = news.get('發言日期', '')
            title = news.get('主旨', '').replace('\r', '').replace('\n', '')
            content = news.get('說明', '').replace('\r', '').replace('\n', ' ')
            
            # 因為說明通常很長，我們只取前 150 字餵給 AI 避免 Prompt 爆掉
            short_content = content[:150] + "..." if len(content) > 150 else content
            
            news_list.append({
                "日期": roc_date,
                "主旨": title,
                "說明": short_content
            })
            
        return {
            "symbol": stock_id,
            "material_info": news_list
        }

    except Exception as e:
        return {"error": f"抓取重大訊息時發生錯誤: {e}"}
    

if __name__ == "__main__":
    stock_id = "2330"  # 台積電
    print(fetchMonthlyRevenue(stock_id))
    print(fetchMaterialInformation(stock_id))
