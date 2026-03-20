import asyncio
import config
import requests
import time
import gc
from googleDrive import getAllUsersUid, updateSendMsgFlag, getUserDonateData

async def sendMsgByRequest():
    headers = {'Authorization': 'Bearer ' + config.CHANNEL_ACCESS_TOKEN, 'Content-Type': 'application/json'}
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


def publishMsgBySchedule(userId):
    # check if we sent the message or not
    if isSentMessage(userId):
        return 'OK'
    return messageToSend(userId)


def messageToSend(userId):
    # design a function to send message, return string
    userDonateInformation = getUserDonateData(userId)
    # only send the message to the person who really donate to the church
    if userDonateInformation['總奉獻'] != '0':
        content = f'''Hello {userDonateInformation['名字']}, 收到你的奉獻如下: 
日期: {userDonateInformation['奉獻日期']}
一般奉獻: {userDonateInformation['一般奉獻']}元
十一奉獻: {userDonateInformation['十一奉獻']}元
ARK奉獻: {userDonateInformation['ARK奉獻']}元
總奉獻: {userDonateInformation['總奉獻']}元
謝謝你慷慨的給予！'''
        return content
    return ''

