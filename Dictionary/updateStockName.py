import requests
import json


def update_stock_name_mapping_file(output_filename="stock_name_mapping.json"):
    """
    抓取全台股最新清單，並建立股票代碼與公司名稱的對應表 (例如: {"2330": "台積電"})
    """
    print("正在從 FinMind 下載全台股最新資訊清單以更新名稱對照表...")
    
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
            
        name_mapping = {}
        
        # 遍歷所有股票，建立 代碼 -> 名稱 的映射
        for item in data["data"]:
            stock_id = item["stock_id"]
            stock_name = item.get("stock_name", "")
            
            # 只收錄有代碼且有名稱的資料
            if stock_id and stock_name:
                name_mapping[stock_id] = stock_name
                
        # 儲存成靜態的 JSON 檔案
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(name_mapping, f, ensure_ascii=False, indent=2)
            
        print(f"名稱更新完成！共收錄 {len(name_mapping)} 檔股票。已儲存為 {output_filename}")
        
    except Exception as e:
        print(f"更新過程中發生錯誤: {e}")


def get_stock_info(target_str):
    """
    不管使用者輸入「代號」還是「名稱」，都能精準回傳 (代號, 名稱)
    """
    with open('stock_name_mapping.json', 'r') as file:
        stock_name_mapping = json.load(file)
        # 情況 1：如果輸入的是代號 (例如 target_str 是 "2330")
        if target_str in stock_name_mapping:
            return target_str, stock_name_mapping[target_str]
        
        # 情況 2：如果輸入的是中文名稱 (例如 target_str 是 "台積電")
        for s_id, s_name in stock_name_mapping.items():
            if target_str == s_name:
                return s_id, s_name
                
        # 找不到的情況
        return None, None


if __name__ == "__main__":
    # 執行新函數
    # update_stock_name_mapping_file()
    
    stock_name = get_stock_info("2330")
    print(f"輸入: 2330 -> 代碼: {stock_name[0]}, 名稱: {stock_name[1]}")
    stock_id = get_stock_info("台積電")
    print(f"輸入: 台積電 -> 代碼: {stock_id[0]}, 名稱: {stock_id[1]}")