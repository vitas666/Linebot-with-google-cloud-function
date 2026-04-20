import datetime
import json
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, StickerSendMessage
from DB.DBConnection import get_recent_chat_history, save_chat_message, save_form_response, init_database
from Utils.fetchStockDaily import fetch_tw_index_technical_indicators, fetch_tx_foreign_open_interest, fetchLimitUpDownStocks
from Utils.googleSearch import findStockNews
from googleDrive import userRegister
from Utils.dateHelper import allSaturdays, allSundays, lastSaturday, lastSunday
import config
from Dictionary.updateStockName import get_stock_info
from googleForm import get_google_form_responses, AIResponseToForm, get_struct_answers
from Utils.utils import sendMsgByRequest, messageToSend
from Utils.fetchEarningContent import fetchMonthlyRevenue, fetchMaterialInformation
from Utils.fetchStockContent import fetch_historical_pe_bands, fetchLargeShareholdersData, fetchMarketLeverage, fetchStockFundamentals

def linebot(request):
    try:
        body = request.get_data(as_text = True)
        json_data = json.loads(body)

        try:
            line_bot_api = LineBotApi(config.CHANNEL_ACCESS_TOKEN)
            handler = WebhookHandler(config.CHANNEL_SECRET)
            signature = request.headers['X-Line-Signature']
            handler.handle(body, signature)
            tk = json_data['events'][0]['replyToken']
            userId = json_data['events'][0]['source']['userId']
            
            # if the event is follow event, register the user name then return, if not, continue
            if json_data['events'][0]['type'] == 'follow':
                line_bot_api.push_message(userId, TextSendMessage(
                    text='第一次加好友, 請在聊天室回覆您的真實姓名, 作為奉獻資訊的紀錄'))
                return 'OK'
            # only accept the message events
            if json_data['events'][0]['type'] == 'message':
                inputText = json_data['events'][0]['message']['text']
                registerStatus = userRegister(userId, inputText)
                print('this is register status: ', registerStatus)
                if registerStatus == 'update uid successful':
                    line_bot_api.push_message(userId, TextSendMessage(text='註冊成功'))
                    return 'OK'
                # if registerStatus == 'name is not on the sheet':
                #     line_bot_api.push_message(userId, TextSendMessage(text='您的名字不在註冊清單上, 請聯絡財務團隊或It團隊'))
                #     return 'OK'
                # send the donate information manually
                if inputText == '奉獻資訊':
                    msg = messageToSend(userId)
                    line_bot_api.push_message(userId, TextSendMessage(text=msg))
                    return 'OK'
                if inputText == '測試':
                    line_bot_api.push_message(userId, TextSendMessage(text='這是測試'))
                    return 'OK'
                if inputText == '表單測試':
                    init_database()
                    formResponse = get_google_form_responses()
                    structAnswers = get_struct_answers(formResponse)
                    response_id = structAnswers['response_id']
                    create_time = structAnswers['create_time']
                    text = AIResponseToForm(structAnswers)['analysis_result']
                    token_usage = AIResponseToForm(structAnswers)['token_usage']
                    save_form_response(structAnswers)
                    save_chat_message(
                        user_id=userId, 
                        session_id=response_id, # 可以用表單 ID 作為這次諮詢的 session_id
                        role='ai',
                        message=text,
                        prompt_tokens=token_usage["prompt_tokens"],
                        completion_tokens=token_usage["completion_tokens"],
                        total_tokens=token_usage["total_tokens"]
                    )
                    line_bot_api.push_message(userId, TextSendMessage(text=text))
                    print('this is form response: ', formResponse)
                    return 'OK'
                if inputText == 'RAG測試':
                    init_database()
                    chat_context = get_recent_chat_history(userId, response_id)
                    text = f"這是我們上一次的對話內容：\n\n{chat_context}\n\n請根據這些資訊，提供我一些投資建議。"
                    save_chat_message(
                        user_id=userId, 
                        session_id=''
                    )
                if '股票基本資訊' in inputText:
                    targetStock = inputText.replace('股票基本資訊', '').strip()
                    stock_id, stock_name = get_stock_info(targetStock)
                    stock_info = fetchStockFundamentals(stock_id)
                    line_bot_api.push_message(userId, TextSendMessage(text=stock_info))
                if '營收與重大資訊' in inputText:
                    targetStock = inputText.replace('營收與重大資訊', '').strip()
                    stock_id, stock_name = get_stock_info(targetStock)
                    revenue_info = fetchMonthlyRevenue(stock_id)
                    material_info = fetchMaterialInformation(stock_id)
                    line_bot_api.push_message(userId, TextSendMessage(text=revenue_info))
                    line_bot_api.push_message(userId, TextSendMessage(text=material_info))
                if '新聞' in inputText:
                    targetStock = inputText.replace('新聞', '').strip()
                    stock_id, stock_name = get_stock_info(targetStock)
                    if stock_id:
                        news_info = findStockNews(stock_name)
                        line_bot_api.push_message(userId, TextSendMessage(text=news_info))
                    else:
                        line_bot_api.push_message(userId, TextSendMessage(text=f"無法找到 {targetStock} 的股票資訊，請確認輸入的公司名稱是否正確。"))
                if '最新漲跌停資訊' in inputText:
                    today = datetime.datetime.now().strftime("%Y%m%d") # YYYYMMDD
                    upDownLimitReport = fetchLimitUpDownStocks(today)
                    line_bot_api.push_message(userId, TextSendMessage(text=upDownLimitReport))
                if '技術指標' in inputText:
                    targetStock = inputText.replace('技術指標', '').strip()
                    if targetStock == '大盤' or targetStock == '台股':
                        stock_id = 'TAIEX'
                    else:
                        stock_id, stock_name = get_stock_info(targetStock)
                    stockReport = fetch_tw_index_technical_indicators(stock_id)
                    line_bot_api.push_message(userId, TextSendMessage(text=stockReport))
                if '最新台指期三大法人未平倉資訊' in inputText:
                    foreignFuturesOIReport = fetch_tx_foreign_open_interest(1)
                    line_bot_api.push_message(userId, TextSendMessage(text=foreignFuturesOIReport))
                if '市場槓桿資訊' in inputText:
                    targetStock = inputText.replace('市場槓桿資訊', '').strip()
                    stock_id, stock_name = get_stock_info(targetStock)
                    fetchMarketLeverageReport = fetchMarketLeverage(stock_id)
                    line_bot_api.push_message(userId, TextSendMessage(text=fetchMarketLeverageReport))
                if '外資持股變化' in inputText:
                    targetStock = inputText.replace('外資持股變化', '').strip()
                    stock_id, stock_name = get_stock_info(targetStock)
                    largeShareholdersData = fetchLargeShareholdersData(stock_id)
                    line_bot_api.push_message(userId, TextSendMessage(text=largeShareholdersData))
                if '歷史本益比' in inputText:
                    targetStock = inputText.replace('歷史本益比', '').strip()
                    stock_id, stock_name = get_stock_info(targetStock)
                    historicalPE = fetch_historical_pe_bands(stock_id)
                    line_bot_api.push_message(userId, TextSendMessage(text=historicalPE))

                # msg = responseByAI(json_data['events'][0]['message']['text'])
                # line_bot_api.reply_message(tk, TextSendMessage(text=msg))
                return 'OK'
            
        except Exception as error:
            print('error occurs on reply events: ', error)
            
    except Exception as error:
        print('error occurs while getting json request data', error)
    #     try:
    #         if getSheetTitle() != lastSaturday(datetime.now()):
    #             return 'OK'
    #         asyncio.run(sendMsgByRequest())
    #     except Exception as error:
    #         print('error occurs on publishing events: ', error)

    return 'OK'


# 功能一：
# 設計完表單以後，讓API可以讀取表單內容，並存放表單內容到mysql中
# 將剛才抓的表單內容直接傳給AI閱讀, 做出第一次分析，並將第一次分析的對話紀錄同表單內容存到mysql中
# 將對話內容回傳給使用者，並且更新對話紀錄db table

# 功能二：識別使用者投資計劃：
# 閱讀聊天歷史紀錄，導入RAG，鼓勵，教使用者回傳自己的投資組合，並接受該標地的新聞通知，以及盤後，技術線，主力買賣情形
# 可產出excel分析報告提供使用者是否要下載的選項
# 使用者可隨時選擇是否要開啟此功能

# 功能三：讓使用者可以隨時調整投資計劃
# 要先給AI建立識別使用者傳的訊息的能力，機器人要可以回答其他閒聊問題，並導回投資相關
# 使用者可主動向AI提出投資計劃變更, 只要傳標的的改變或者收入結構的改變，AI就會主動提供投資建議或對應市場資訊

# 功能四：若市場產生波動，可即時提醒使用者調整投資計劃
# 上網抓每日的重點資訊，紀錄到table中，以日期為單位紀錄
# 使用者可決定是否開啟每日新聞摘要

# 功能五：提供投資組合績效報告
# 每月或者每季提供一次投資組合績效報告，讓使用者了解自己的投資表現以及需要調整的地方

# Note: 我需要拍一個教學影片可以讓使用者知道每一個功能分別是幹嘛用的


