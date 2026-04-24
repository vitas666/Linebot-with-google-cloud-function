from datetime import datetime
import os
import sys
import requests
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

FMP_API_KEY = config.FMP_API_KEY

def fetch_earnings_call_global(symbol: str) -> str:
    """
    獲取美股最新一季的財報開獎結果 (EPS 預期 vs 實際)
    以及 Earnings Call (財報電話會議) 的逐字稿精華
    """
    print(f"正在調閱 {symbol} 的最新財報與法說會紀錄...")
    this_year = datetime.now().year
    this_quarter = (datetime.now().month - 1) // 3 + 1
    
    # 1. 抓取最新財報的 EPS 驚喜 (Beat or Miss)
    earning_call_url = f"https://financialmodelingprep.com/stable/earning-call-transcript?symbol={symbol}&year={this_year}&quarter={this_quarter}&apikey={FMP_API_KEY}"
    # 2. 抓取最新法說會的逐字稿 (Transcript)
    transcript_url = f"https://financialmodelingprep.com/stable/earning_call_transcript/{symbol}?limit=1&apikey={FMP_API_KEY}"
    
    try:
        # 取得 EPS 開獎結果
        res = requests.get(earning_call_url, timeout=10).json()
        print(f"EPS 驚喜資料: {res}")
        if not res:
            return f"查無 {symbol} 的財報開獎資料。"
            
        latest_earnings = res[0] # 取最新一季
        date = latest_earnings.get('date')
        actual_eps = latest_earnings.get('actualEarningResult')
        est_eps = latest_earnings.get('estimatedEarning')
        
        # 判斷是擊敗預期還是低於預期
        beat_miss = "擊敗預期 (Beat)" if actual_eps > est_eps else "低於預期 (Miss)"
        
        # 取得法說會逐字稿
        trans_res = requests.get(transcript_url, timeout=10).json()
        transcript_snippet = "暫無逐字稿資料"
        
        if trans_res:
            # 逐字稿通常很長，我們只取最前面的 300 個字當作摘要
            # 如果你要傳給 AI 分析，就可以把整包 trans_res[0]['content'] 傳過去
            full_content = trans_res[0].get('content', '')
            transcript_snippet = full_content[:300] + "...\n(後略，可交由 AI 進行深度 RAG 分析)"

        # 開始組裝回傳給 Line Bot 的訊息
        reply_msg = f"【{symbol} 美股財報與法說會 (Earnings Call)】\n"
        reply_msg += "=" * 20 + "\n"
        reply_msg += f"發布日期: {date}\n"
        reply_msg += f"• 實際 EPS: {actual_eps}\n"
        reply_msg += f"• 華爾街預期: {est_eps}\n"
        reply_msg += f"• 開獎結果: {beat_miss}\n"
        reply_msg += "-" * 20 + "\n"
        reply_msg += f"【CEO 法說會逐字稿節錄】\n"
        reply_msg += f"{transcript_snippet}\n"
        
        return reply_msg

    except Exception as e:
        return f"抓取美股法說會資料時發生錯誤: {e}"


if __name__ == '__main__':
    result = fetch_earnings_call_global("ASML")
    print(result)