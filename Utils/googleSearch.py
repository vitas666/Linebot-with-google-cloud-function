from ddgs import DDGS
import requests
import datetime
import re
from bs4 import BeautifulSoup
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def findStockNews(stock_id: str, company_name: str, maxResults: int = 5) -> dict:
    """
    利用爬蟲套件，搜尋指定公司相關的新聞
    """
    print(f"正在搜尋 {company_name} 的最新新聞...")
    query = f"{company_name} 新聞"
    print(f"使用的搜尋關鍵字: {query}")
    
    try:
        results = DDGS().text(query, region='tw', safesearch='Off', max_results=maxResults)
        news = []
        for result in results:
            news.append({
                "title": result.get("title", ""),
                "content": result.get("body", ""),
                "url": result.get("url", ""),
            })

        if not news:
            return {"message": "近期無相關新聞"}
        
        return {
            "company_name": company_name,
            "news": news
        }
        
    except Exception as e:
        return {"error": f"搜尋過程中發生錯誤: {e}"}


def fetch_mops_earnings_call_pdf(stock_id: str, year: int) -> str:
    """
    直接對接「公開資訊觀測站 (MOPS)」底層 API，免除 Selenium 瀏覽器模擬。
    擷取指定公司與年度的最新的法說會 PDF 簡報連結。
    """
    # 1. 台灣官方網站一律使用「民國年」，需進行轉換 (例如 2025 -> 114)
    roc_year = year - 1911
    print(f"正在 MOPS 尋找 {stock_id} 民國 {roc_year} 年的法說會資料...")
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive"
    })
    
    try:
        # 🌟 破防關鍵 2：先去首頁逛一圈，讓伺服器發 Cookie 給我們
        main_url = "https://mops.twse.com.tw/mops/web/t100sb02"
        session.get(main_url, timeout=10, verify=False)
        
        # 準備好真正的目標與參數
        ajax_url = "https://mops.twse.com.tw/mops/web/ajax_t100sb02_1"
        payload = {
            "encodeURIComponent": "1",
            "step": "1",
            "firstin": "1",
            "TYPEK": "sii", # 這裡先用上市 (sii) 測試
            "co_id": stock_id,
            "year": str(roc_year)
        }
        
        # 針對 AJAX 請求再補上特定的 Headers
        ajax_headers = {
            "Referer": main_url,
            "Origin": "https://mops.twse.com.tw",
            "X-Requested-With": "XMLHttpRequest"
        }
        
        print(f"🕵️ 拿到通行證了！正在向內部 API 提取 {stock_id} 簡報...")
        # 🌟 破防關鍵 3：使用同一個 session 發送 POST，這時 Cookie 會自動帶上！
        res = session.post(ajax_url, headers=ajax_headers, data=payload, timeout=10, verify=False)
        res.encoding = 'utf-8'
        with open("mops_debug.html", "w", encoding="utf-8") as f:
            f.write(res.text)
            
        soup = BeautifulSoup(res.text, 'html.parser')
        
        pdf_links = []
        for tag in soup.find_all(['input', 'a']):
            text_to_search = str(tag.get('onclick', '')) + str(tag.get('href', ''))
            match = re.search(r"['\"]([^'\"]*\.pdf)['\"]", text_to_search, re.IGNORECASE)
            if match:
                link = match.group(1)
                if link.startswith("/"):
                    link = "https://mops.twse.com.tw" + link
                pdf_links.append(link)
                
        if pdf_links:
            print(f"✅ 成功獲取 PDF: {pdf_links[0]}")
            return pdf_links[0]
        else:
            print(f"⚠️ 找不到 {stock_id} 的 PDF 簡報檔。")
            return ""
            
    except Exception as e:
        print(f"擷取過程發生錯誤: {e}")
        return ""



if __name__ == "__main__":
    # news_data = findStockNews('2330', '台積電')
    # for idx, n in enumerate(news_data["news"]):
    #         print(f"\n[{idx+1}] {n['title']}")
    #         print(f"摘要: {n['content']}")

    pdf_url = fetch_mops_earnings_call_pdf(stock_id="2330", year=2025)
    if pdf_url:
        print(f"\n最終取得的網址: {pdf_url}")
        print("接下來，你可以直接把這個網址傳給 analyze_earnings_call_pdf() 讓 Gemini 閱讀了！")
    