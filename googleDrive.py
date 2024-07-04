import pygsheets

gc = pygsheets.authorize(service_file='linebot-project-426706-2e61ac0e2adb.json')
sht = gc.open_by_url('https://docs.google.com/spreadsheets/d/1qsFXPl5owas_-yaBo5SVpRqixclmXY6Fnp-LR5hI2M0/edit?usp=sharing')
currentSheet = sht[0].get_all_records()
sheetTitle = sht[0].title
uidSheet = sht.worksheet('title','user_uid').get_all_records()

def getSheetTitle():
    return sheetTitle

def getUserDonateData(userId):
    nameDict = {item['名字']: item for item in currentSheet}
    uidDict = next((item for item in uidSheet if item['uid'] == userId), None)
    if not uidDict:
        return None
    currDict = nameDict.get(uidDict['名字'], {})
    # Combine two dictionaries
    fullData = {**uidDict, **currDict}
    return fullData

def userRegister(userId, realName):
    # this function is used for checking the user display name change or not, if no change do nothing
    uidList = [uid['uid'] for uid in uidSheet if uid['uid'] != '']
    if userId in uidList:
        return 'alreadyRegistered'

    else:
        nameList = [name['名字'] for name in uidSheet]
        if realName in nameList:
            uidDict = [item for item in uidSheet]
            userLabel = next((index for (index, d) in enumerate(uidDict) if d['名字'] == realName), None) + 2
            sht.worksheet('title','user_uid').update_value('B'+str(userLabel), userId)
            return 'successful'
        else:
            return 'failed'
    
def isSentMessage(userId):
    if getUserDonateData(userId)['已傳送訊息'] == 'Y':
        return True
    else:
        return False

async def updateSendMsgFlag(userId):
    nameDict = [item for item in currentSheet]
    name = getUserDonateData(userId)['名字']
    userLabel = next((index for (index, d) in enumerate(nameDict) if d['名字'] == name), None) + 2
    sht[0].update_value('F'+str(userLabel), 'Y')

def getAllUsersUid():
    # function to return all uid in currentSheet
    nameDict = {item['名字']: item for item in currentSheet}
    uidDict = {item['名字']: item for item in uidSheet}
    combined_data = []
    for name, currDict in nameDict.items():
        uidEntry = uidDict.get(name, {})
        # Combine two dictionaries
        fullData = {**uidEntry, **currDict}
        combined_data.append(fullData)
    uidList = [item['uid'] for item in combined_data]
    return uidList
