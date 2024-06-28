import pygsheets

gc = pygsheets.authorize(service_file='your service account information file.json')
sht = gc.open_by_url('your public google excel sheet')
currentSheet = sht.worksheet('title','2024-6-22')
uidSheet = sht.worksheet('title','user_uid')
currentSheet.hidden = False

def getUserDonateData(userId):
    findLabel = uidSheet.find(userId)[0].label
    personalDonateInformation = currentSheet.get_row(int(findLabel.replace('B', '')), include_tailing_empty=False)
    return {
        'DonateInformation': personalDonateInformation,
        'Label': findLabel
    }

def userRegister(userId, realName):
    # this function is used for checking the user display name change or not, if no change do nothing
    nameList = uidSheet.get_col(1, include_tailing_empty=False)
    try:
        if uidSheet.find(userId)[0].value == userId:
            return 'alreadyRegistered'
    except:
        if realName in nameList:
            userLabel = uidSheet.find(realName)[0].label
            uidSheet.update_value('B'+userLabel.replace('A', ''), userId)
            return 'successful'
        else:
            return 'failed'
    
def isSentMessage(userId):
    if getUserDonateData(userId)['DonateInformation'][-1] == 'Y':
        return True
    else:
        return False

async def updateSendMsgFlag(userId):
    userLabel = getUserDonateData(userId)['Label']
    currentSheet.update_value('F'+userLabel.replace('B', ''), 'Y')

def getAllUsersUid():
    nameList = currentSheet.get_col(1, include_tailing_empty=False)
    labelArray = [uidSheet.find(name)[0].label for name in nameList if name != '名字']
    return [uidSheet.get_row(int(label.replace('A', '')), include_tailing_empty=False)[1] for label in labelArray]

