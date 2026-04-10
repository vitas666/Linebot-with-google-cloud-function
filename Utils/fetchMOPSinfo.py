from playwright.sync_api import sync_playwright
import re
import os
from bs4 import BeautifulSoup
from curl_cffi import requests


def fetchMOPSData(stock_id: str, language: str) -> dict:
    """
    從 MOPS 獲取財報資料，並解析成結構化格式。
    """
    with sync_playwright() as p:
        # headless=True 代表在背景默默跑，你可以先改成 False 看它跑一次，確認沒問題再改回 True
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            # 1. 進入法說會查詢頁面
            page.goto("https://mopsov.twse.com.tw/mops/web/t100sb07_1")
            
            # 2. 🌟 關鍵修正：使用你錄製到的精準 ID (#co_id)
            print(f"✍️ 正在搜尋: {stock_id} 的法說會相關資訊...")
            search_input = page.locator("#co_id")
            search_input.wait_for(state="visible") 
            search_input.fill(stock_id)
            
            # (選擇性) 為了避免自動完成的下拉選單擋住按鈕，我們模擬按下 Esc 鍵關閉下拉選單
            search_input.press("Escape")
            
            # 3. 🌟 關鍵修正：使用你錄製到的按鈕定位
            page.get_by_role("button", name="查詢").click()
            
            # 4. 等待網路冷靜下來 (代表資料已經從後端抓回來並渲染到畫面上了)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1500) # 給 Vue.js 渲染表格的時間
            
            # 5. 抓取渲染完成後的純 HTML
            html_content = page.content()
            # with open("mops_debug.html", "w", encoding="utf-8") as f:
            #     f.write(html_content)

            pdf_links = []
            
            match = re.findall(r'([A-Za-z0-9_-]+\.pdf)', html_content, re.IGNORECASE)
            if match:
                unique_pdfs = list(set(match))
                chinese_pdfs = [pdf for pdf in unique_pdfs if re.search(r'M\d+\.pdf$', pdf, re.IGNORECASE)]
                english_pdfs = [pdf for pdf in unique_pdfs if re.search(r'E\d+\.pdf$', pdf, re.IGNORECASE)]
                if language == 'TW':
                    pdf_filename = chinese_pdfs[0] if chinese_pdfs else None
                elif language == 'EN':
                    pdf_filename = english_pdfs[0] if english_pdfs else None

                pdf_links.append(pdf_filename)

            if pdf_links:
                print(f"成功獲取 PDF 網址: {pdf_links[0]} , 準備下載 PDF 檔案...")
                with page.expect_download() as download_info:
                    page.locator(f"input[value*='{pdf_filename}'], a:has-text('{pdf_filename}')").first.click()
                
                # 取得下載物件並存檔
                download = download_info.value
                download_dir = f"./downloads/{stock_id}/{language}"
                os.makedirs(download_dir, exist_ok=True)
                local_file_path = os.path.join(download_dir, pdf_filename)
                download.save_as(local_file_path)
                
                print(f"檔案已成功下載至本地端: {local_file_path}")
                return pdf_links[0]
            else:
                pending_msg = "內容檔案於當日會後公告於公開資訊觀測站"
                if pending_msg in html_content:
                    # 用正則表達式把日期抓出來 (例如 115/04/16), 尋找 <font color="blue">115/04/16</font> 裡面的日期格式
                    date_match = re.search(r'>(\d{2,3}/\d{2}/\d{2})<', html_content)
                    
                    if date_match:
                        roc_date = date_match.group(1)
                        # 簡單轉換成西元年給使用者看 (115/04/16 -> 2026/04/16)
                        year, month, day = roc_date.split('/')
                        ad_year = int(year) + 1911
                        
                        return f"法說會預計於 {ad_year}/{month}/{day} 舉辦，請靜候公司上傳資料。"
                else:
                    return f"法說會尚未舉辦。"
                
        except Exception as e:
            print(f"Playwright 執行時發生錯誤: {e}")
            return ""
        finally:
            browser.close()


if __name__ == '__main__':
    pdf_url = fetchMOPSData("2330", 'TW')
    if pdf_url:
        print(f"{pdf_url}")
    