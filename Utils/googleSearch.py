from ddgs import DDGS
import datetime
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


if __name__ == "__main__":
    news_data = findStockNews('2330', '台積電')
    for idx, n in enumerate(news_data["news"]):
            print(f"\n[{idx+1}] {n['title']}")
            print(f"摘要: {n['content']}")
