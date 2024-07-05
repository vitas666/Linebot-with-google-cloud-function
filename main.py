import json
import gc
import asyncio
import requests
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, StickerSendMessage
from datetime import datetime, timedelta
import time
from googleDrive import getUserDonateData, userRegister, isSentMessage, getAllUsersUid, updateSendMsgFlag, getSheetTitle
from dateHelper import allSaturdays, allSundays, lastSaturday, lastSunday
import config


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
                # send the donate information manually
                if json_data['events'][0]['message']['text'] == '奉獻資訊':
                    msg = messageToSend(userId)
                    line_bot_api.push_message(userId, TextSendMessage(text=msg))
                    return 'OK'
                if json_data['events'][0]['message']['text'] == '測試':
                    line_bot_api.push_message(userId, TextSendMessage(text='這是測試'))
                    return 'OK'
                # check if old friends are in the excel or not
                registerStatus = userRegister(
                    userId, json_data['events'][0]['message']['text'])
                if registerStatus == 'failed':
                    line_bot_api.reply_message(
                        tk, TextSendMessage(text='註冊失敗, 請聯絡財務團隊或It團隊'))
                elif registerStatus == 'successful':
                    line_bot_api.reply_message(tk, TextSendMessage(text='註冊成功'))
                msg = responseByAI(json_data['events'][0]['message']['text'])
                line_bot_api.reply_message(tk, TextSendMessage(text=msg))
                return 'OK'
            
        except Exception as error:
            print('error occurs on reply events: ', error)
            
    except:
        try:
            if getSheetTitle() != lastSaturday(datetime.now()) and getSheetTitle() != lastSunday(datetime.now()):
                return 'OK'
            asyncio.run(sendMsgByRequest())
        except Exception as error:
            print('error occurs on publishing events: ', error)

    return 'OK'


def messageToSend(userId):
    # design a function to send message, return string
    userDonateInformation = getUserDonateData(userId)
    # only send the message to the person who really donate to the church
    if userDonateInformation['總奉獻'] != '0':
        content = f'''Hello {userDonateInformation['名字']}, 收到你的奉獻如下: 
日期: {getSheetTitle()}
一般奉獻: {userDonateInformation['一般奉獻']}元
十一奉獻: {userDonateInformation['十一奉獻']}元
ARK奉獻: {userDonateInformation['ARK奉獻']}元
總奉獻: {userDonateInformation['總奉獻']}元
謝謝你慷慨的給予！'''
        return content
    return ''


def publishMsgBySchedule(userId):
    # check if we sent the message or not
    if isSentMessage(userId):
        return 'OK'
    return messageToSend(userId)


async def sendMsgByRequest():
    headers = {'Authorization': 'Bearer jkE5qxpWwrfFgkvgEVitn00Da/RAGN2rNIR0FAZwMrnJacYy5PVZOMveCI9t4ZdRRIEzhPOgTQXWA1PKH/NzPq1F3eL9Oa+i6E26TF5AUrjBL0PK9iT+UBulR4yqH+cZAUUL9r3f+mEdtzCY6a2GGQdB04t89/1O/w1cDnyilFU=', 'Content-Type': 'application/json'}
    nameList = getAllUsersUid()
    for uid in nameList:
        msg = publishMsgBySchedule(uid)
        if msg == 'OK':
            continue
        body = {
            'to': uid,
            'messages': [{
                'type': 'text',
                'text': msg
            }]
        }
        res = requests.request('POST', 'https://api.line.me/v2/bot/message/push', headers=headers, data=json.dumps(body).encode('utf-8'))
        del msg
        del body
        del res
        gc.collect()
        # after sending the message, we should update the sent msg flag, preventing from sending the same message again.
        await updateSendMsgFlag(uid)
        time.sleep(5)
        
    return 'OK'

