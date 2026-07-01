from duckduckgo_search import DDGS
import datetime
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def findStockNews(keyword: str, maxResults: int = 5, hours_limit: int = 48) -> str:
    """
    利用爬蟲套件搜尋最新新聞，並嚴格過濾指定小時數內的資訊。
    """
    print(f"正在搜尋 {keyword} 的最新新聞 (限制 {hours_limit} 小時內)...")
    
    # 💡 技巧：搜尋引擎看不懂 Yahoo 的 '^TWII' 代號，我們幫它翻譯成人類語言
    search_term = keyword
    
    query = f"{search_term} 新聞"
    print(f"實際打給搜尋引擎的關鍵字: {query}")
    
    try:
        # 1. 改用 .news() 方法，並加上 timelimit='w' (只抓最近一週，減少後續處理量)
        # timelimit 參數支援: 'd' (天), 'w' (週), 'm' (月)
        results = DDGS().news(query, region='tw', safesearch='Off', timelimit='w', max_results=3)
        
        news = []
        # 取得現在的 UTC 時間 (因 DDGS 回傳的時間通常是 UTC 格式)
        now = datetime.datetime.now(datetime.timezone.utc) 
        
        for result in results:
            # DDGS.news() 的回傳格式通常有 'date', 'title', 'body', 'url'
            pub_date_str = result.get('date')
            
            if pub_date_str:
                try:
                    # 將字串 (如 2024-05-10T12:00:00Z) 轉為 Python 時間物件
                    # 替換 'Z' 為 '+00:00' 確保 timezone 解析正確
                    pub_date = datetime.datetime.fromisoformat(pub_date_str.replace('Z', '+00:00'))
                    
                    # 2. 計算時間差
                    time_diff = now - pub_date
                    
                    # 3. 判斷是否在 48 小時內 (48 * 3600 秒)
                    if time_diff.total_seconds() <= (hours_limit * 3600):
                        news.append({
                            # 轉換為台灣時間 (UTC+8) 方便閱讀
                            "time": (pub_date + datetime.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M"),
                            "title": result.get("title", ""),
                            "content": result.get("body", ""),
                            "url": result.get("url", "") # 注意: news() 裡網址的 key 是 'url' 不是 'href'
                        })
                except Exception as e:
                    print(f"時間解析失敗跳過: {e}")
                    pass
            
            # 如果收集滿了我們需要的篇數，就提早結束迴圈
            if len(news) >= maxResults:
                break

        # 4. 產出報告
        if not news:
            return f"近期 {hours_limit} 小時內無「{keyword}」的相關新聞"
        
        reply_msg = f"📊 【{keyword} 最新動態 ({hours_limit} 小時內)】\n"
        reply_msg += "=" * 25 + "\n"
        for n in news:
            reply_msg += f"🕒 時間: {n['time']}\n"
            reply_msg += f"📰 標題: {n['title']}\n"
            reply_msg += f"📝 摘要: {n['content']}\n"
            reply_msg += f"🔗 連結: {n['url']}\n"
            reply_msg += "-" * 25 + "\n"

        return reply_msg
        
    except Exception as e:
        return f"搜尋過程中發生錯誤: {e}"


if __name__ == "__main__":
    # 測試抓取台股大盤 48 小時內的新聞
    news_data = findStockNews('台指期', maxResults=3, hours_limit=48)
    print(news_data)
