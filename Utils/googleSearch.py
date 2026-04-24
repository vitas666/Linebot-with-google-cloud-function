from ddgs import DDGS
import datetime
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def findStockNews(company_name: str, maxResults: int = 5) -> str:
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
                "url": result.get("href", ""),
            })

        if not news:
            return "近期無相關新聞"
        
        reply_msg = f"【{company_name} 新聞】\n"
        reply_msg += "=" * 20 + "\n"
        for n in news:
            reply_msg += f"標題: {n['title']}\n"
            reply_msg += f"摘要: {n['content']}\n"
            reply_msg += f"連結: {n['url']}\n"
            reply_msg += "-" * 20 + "\n"

        return reply_msg
        
    except Exception as e:
        return f"搜尋過程中發生錯誤: {e}"


if __name__ == "__main__":
    news_data = findStockNews('台積電')
    print(news_data)
