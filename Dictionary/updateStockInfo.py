import requests
import json
import os

def update_market_mapping_file(output_filename="market_mapping.json"):
    """
    抓取全台股最新清單，並轉成 MOPS 的市場代碼 (sii, otc, rotc)
    這個腳本只需要每個月/每季在自己電腦跑一次，然後把 json 檔連同程式一起部署到雲端
    """
    print("正在從 FinMind 下載全台股最新資訊清單...")
    
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockInfo"
    }
    
    try:
        res = requests.get(url, params=params)
        data = res.json()
        
        if data.get("msg") != "success" or not data.get("data"):
            print("無法取得股票清單")
            return
            
        mapping = {}
        
        # 遍歷所有股票，進行市場代號轉換
        for item in data["data"]:
            stock_id = item["stock_id"]
            finmind_type = item.get("type", "").lower()
            
            # 轉換為 MOPS (公開資訊觀測站) 的專屬代碼
            if finmind_type == "twse":
                mapping[stock_id] = "sii"  # 上市
            elif finmind_type == "tpex":
                mapping[stock_id] = "otc"  # 上櫃
            elif finmind_type == "rotc":
                mapping[stock_id] = "rotc" # 興櫃
                
        # 儲存成靜態的 JSON 檔案
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(mapping, f, ensure_ascii=False, indent=2)
            
        print(f"更新完成！共收錄 {len(mapping)} 檔股票。已儲存為 {output_filename}")
        
    except Exception as e:
        print(f"更新過程中發生錯誤: {e}")

if __name__ == "__main__":
    update_market_mapping_file()
