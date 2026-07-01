import os
import sys
import requests

# 讓本檔可以匯入專案根目錄下的 DB 模組
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from DB.DBConnection import save_stock_name_mapping, get_stock_info_from_db


def update_stock_name_mapping_file():
    """
    抓取全台股最新清單，並將股票代碼與公司名稱的對應表寫入 MySQL。
    (例如: {"2330": "台積電"} -> stock_name_mapping 資料表)
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

        # 將資料寫入 MySQL，而非靜態 JSON 檔案
        saved_count = save_stock_name_mapping(name_mapping)

        print(f"名稱更新完成！共收錄 {saved_count} 檔股票，已寫入 MySQL。")

    except Exception as e:
        print(f"更新過程中發生錯誤: {e}")


def get_stock_info(target_str):
    return get_stock_info_from_db(target_str)


if __name__ == "__main__":
    # 第一次使用或需要更新資料時，先執行下行抓取並寫入 MySQL
    update_stock_name_mapping_file()

    stock_name = get_stock_info("2330")
    print(f"輸入: 2330 -> 代碼: {stock_name[0]}, 名稱: {stock_name[1]}")
    stock_id = get_stock_info("台積電")
    print(f"輸入: 台積電 -> 代碼: {stock_id[0]}, 名稱: {stock_id[1]}")
