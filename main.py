import json
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, StickerSendMessage
from DB.DBConnection import save_chat_message, save_form_response, init_database
from googleDrive import userRegister
from Utils.dateHelper import allSaturdays, allSundays, lastSaturday, lastSunday
import config
import google.generativeai as genai
from googleForm import get_google_form_responses, AIResponseToForm, get_struct_answers
from Utils.utils import sendMsgByRequest, messageToSend

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
                registerStatus = userRegister(userId, json_data['events'][0]['message']['text'])
                print('this is register status: ', registerStatus)
                if registerStatus == 'update uid successful':
                    line_bot_api.push_message(userId, TextSendMessage(text='註冊成功'))
                    return 'OK'
                # if registerStatus == 'name is not on the sheet':
                #     line_bot_api.push_message(userId, TextSendMessage(text='您的名字不在註冊清單上, 請聯絡財務團隊或It團隊'))
                #     return 'OK'
                # send the donate information manually
                if json_data['events'][0]['message']['text'] == '奉獻資訊':
                    msg = messageToSend(userId)
                    line_bot_api.push_message(userId, TextSendMessage(text=msg))
                    return 'OK'
                if json_data['events'][0]['message']['text'] == '測試':
                    line_bot_api.push_message(userId, TextSendMessage(text='這是測試'))
                    return 'OK'
                if json_data['events'][0]['message']['text'] == '表單測試':
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
# 讓AI在回覆對話之前先根據對話紀錄以及使用者適用的投資計劃進行RAG訓練
# 將進行完訓練的RAG模型用在對話生成上
# 將對話內容回傳給使用者，並且更新對話紀錄db table

# 功能二：識別使用者投資計劃：
# 鼓勵，教使用者回傳自己的投資組合，並接受該標地的新聞通知，以及盤後，技術線，主力買賣情形
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


