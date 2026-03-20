import pygsheets
import time
import gc
import config

targetSpreadSheet = pygsheets.authorize(service_file=config.LINEBOT_SERVICE_ACCOUNT_FILE_NAME)
sht = targetSpreadSheet.open_by_url(config.GOOGLE_SHEET_URL)
currentSheet = sht[0].get_all_records()
sheetTitle = sht[0].title
uidSheet = sht.worksheet('title','user_uid')
uidSheetData = uidSheet.get_all_records()
# cleanUidData = [row[:2] for row in uidSheetData if row[0] and row[1]]
# print('this is cleanData: ', cleanUidData)


def getSheetTitle():
    return sheetTitle

def getUserDonateData(userId):
    nameDict = {item['名字']: item for item in currentSheet}
    uidDict = next((item for item in uidSheetData if item['uid'] == userId), None)
    if not uidDict:
        return None
    currDict = nameDict.get(uidDict['名字'], {})
    # Combine two dictionaries
    fullData = {**uidDict, **currDict}
    return fullData

def userRegister(userId, realName):
    # this function is used for checking the user display name change or not, if no change do nothing
    uidList = [uid['uid'] for uid in uidSheetData if uid['uid'] != '']
    print('this is uidList: ', uidList)
    if userId in uidList:
        return 'alreadyRegistered'
    
    nameList = [name['名字'] for name in uidSheetData]
    if realName in nameList:
        uidDict = [item for item in uidSheetData]
        userLabel = next((index for (index, d) in enumerate(uidDict) if d['名字'] == realName), None) + 2
        uidSheet.update_value('B'+str(userLabel), userId)
        # sht.worksheet('title','user_uid').cell('B'+str(userLabel)).fetch()
        return 'update uid successful'
    else:
        return 'name is not on the sheet'


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

