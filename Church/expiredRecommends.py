from church_of_jesus_christ_api import ChurchOfJesusChristAPI
import datetime, getpass

#get credentials for church account
'''username = input('Enter username:')
try:
    password = getpass.getpass()
except Exception as error:
    print('ERROR', error)'''

username = 'ckamachi'
password = 'ab#4ebDVM4yWG66fhN!on'

#create login value using the API
api = ChurchOfJesusChristAPI(username, password)

#gather the date range to work against
date_format = '%Y%m%d'
today = datetime.datetime.now()
oneweek = today + datetime.timedelta(days=7)

#get action and interview list
try:
    ai_list = api.get_action_and_interviews()
except Exception as error:
    print('ERROR', error)

#print(ai_list["data"])
#get counselor actions
for data in ai_list["data"]:
    print('\n\n' + data["sectionTypeKey"] + '\n')
    for action in data["items"]:
        #print(action)
        mname = action["name"]
        status = action["status"]
        task = action["suggestedAction"]
        phonenum = action["phoneNumber"]
        email = action["email"]
        if mname == None:
            mname = 'Not provided'
        if status == None:
            status = 'Not provided'
        if task == None:
            task = 'Not provided'
        if phonenum == None:
            phonenum = "Not provided"
        if email == None:
            email = "Not provided"
        print('Member name: ' + mname) 
        print('Member status: ' + status)
        print('Suggested action: ' + task)   
        print('Phone number: ' + phonenum)
        print('Email: ' + email + '\n')
    '''if data["sectionTypeKey"] == "BISHOPRIC_COUNSELOR_YOUTH_INTERVIEWS_CURRENT":
        for action in data["items"]:
            print(action["name"]) 
            print(action["status"])
            print(action["suggestedAction"])   
            print(action["phoneNumber"])
            print(action["email"])'''