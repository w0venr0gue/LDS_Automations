from church_of_jesus_christ_api import ChurchOfJesusChristAPI
import datetime, getpass

#get credentials for church account
username = input('Enter username:')
try:
    password = getpass.getpass()
except Exception as error:
    print('ERROR', error)

#create login value using the API
api = ChurchOfJesusChristAPI(username, password)

#gather the date range to work against
date_format = '%Y%m%d'
today = datetime.datetime.now()
oneweek = today + datetime.timedelta(days=7)

#get ward birthdays
try:
    birthday_list = api.get_birthdays()
except Exception as error:
    print('ERROR', error)

#Find birthdays in the next 7 days
for month in birthday_list:
    for member in month["birthdays"]:
        bdate = member['birthDate']
        date_obj = datetime.datetime.strptime(bdate, date_format)
        newdate = date_obj.replace(year=today.year)
        if newdate >= today and newdate <= oneweek:
            print('Member: ' + member['spokenName'])
            print('Birthdate: ' + member['birthDayFormatted'] + '\n')