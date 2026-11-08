#shared pieces for the missionary_calendar scripts: config, Calendly API access and email
import configparser, datetime, os, re, smtplib, sys
from email.message import EmailMessage
from email.utils import formataddr
from zoneinfo import ZoneInfo
import requests

API_BASE = 'https://api.calendly.com'
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini')

#read settings from config.ini next to these scripts (not committed to git)
config = configparser.ConfigParser()
config.optionxform = str  #keep the capitalization of missionary names
config.read(CONFIG_FILE, encoding='utf-8-sig')  #utf-8-sig also accepts files saved with a BOM by Notepad

#get the personal access token (Calendly > Integrations > API & Webhooks)
#from config.ini, or the CALENDLY_TOKEN env var
token = config.get('calendly', 'token', fallback='').strip() or os.environ.get('CALENDLY_TOKEN')
if not token or token == 'paste-your-token-here':
    sys.exit('ERROR: put your Calendly personal access token in ' + CONFIG_FILE
             + ' (copy config.example.ini) or set the CALENDLY_TOKEN environment variable')

session = requests.Session()
session.headers.update({'Authorization': 'Bearer ' + token})


def api_get(url, params=None):
    #accept either a full url (from pagination / resource uris) or a path
    if not url.startswith('http'):
        url = API_BASE + url
    response = session.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def get_all(url, params=None):
    #follow Calendly's pagination and return every item in the collection
    items = []
    while url:
        data = api_get(url, params)
        items.extend(data['collection'])
        url = data['pagination'].get('next_page')
        params = None  #next_page already contains the query string
    return items


def get_user():
    #the Calendly account plus its time zone, so times are right on any computer
    user = api_get('/users/me')['resource']
    return user, ZoneInfo(user.get('timezone') or 'UTC')


def get_events(user_uri, start, end):
    return get_all('/scheduled_events', {
        'user': user_uri,
        'min_start_time': start.isoformat(),
        'max_start_time': end.isoformat(),
        'status': 'active',
        'sort': 'start_time:asc',
        'count': 100,
    })


def get_invitees(event_uri):
    return get_all(event_uri + '/invitees', {'status': 'active', 'count': 100})


def add_am_pm(time_answer):
    #families often type a bare "6:30"; visits are always in the evening, so add PM.
    #24-hour times like "18:00" become "6:00 PM". Anything else is left as typed.
    match = re.fullmatch(r'(\d{1,2})(:\d{2})?', time_answer)
    if not match:
        return time_answer
    hour, minutes = int(match.group(1)), match.group(2) or ''
    if 13 <= hour <= 23:
        return f"{hour - 12}{minutes} PM"
    if 1 <= hour <= 12:
        return f"{hour}{minutes} PM"
    return time_answer


def get_appointments(user_uri, start, end, tz):
    #scheduled events with their invitees, flattened into simple dicts
    appointments = []
    for event in get_events(user_uri, start, end):
        location = event.get('location') or {}
        invitees = []
        time_answer = ''
        for invitee in get_invitees(event['uri']):
            #booking form answers (phone, address, etc.) come through as questions and answers
            details = []
            for qa in invitee.get('questions_and_answers', []):
                #the "Time" form field is the real visit time; it replaces the Calendly slot time
                if qa['question'].strip().lower() == 'time' and qa['answer'].strip():
                    time_answer = time_answer or add_am_pm(qa['answer'].strip())
                else:
                    details.append((qa['question'], qa['answer']))
            if invitee.get('text_reminder_number'):
                details.insert(0, ('Text reminder number', invitee['text_reminder_number']))
            invitees.append({'name': invitee['name'], 'email': invitee['email'], 'details': details})
        appointments.append({
            'time': time_answer,
            'uri': event['uri'],
            'created': datetime.datetime.fromisoformat(event['created_at'].replace('Z', '+00:00')),
            'start': datetime.datetime.fromisoformat(event['start_time'].replace('Z', '+00:00')).astimezone(tz),
            'end': datetime.datetime.fromisoformat(event['end_time'].replace('Z', '+00:00')).astimezone(tz),
            'name': event['name'],
            'location': location.get('location') or location.get('join_url') or '',
            'invitees': invitees,
        })
    return appointments


def time_text(appt):
    #the "Time" form answer if the family gave one, otherwise the Calendly slot time
    if appt.get('time'):
        return appt['time']
    return appt['start'].strftime('%I:%M %p').lstrip('0') + ' - ' + appt['end'].strftime('%I:%M %p').lstrip('0')


def get_missionary_contacts():
    #[missionaries] section of config.ini: Name = email, phone (phone is optional)
    if not config.has_section('missionaries'):
        return []
    contacts = []
    for name, value in config.items('missionaries'):
        email, _, phone = (part.strip() for part in value.partition(','))
        if email:
            contacts.append((name, email, phone))
    return contacts


def get_missionaries():
    #(name, email) pairs, for sending email to the missionaries
    return [(name, email) for name, email, _ in get_missionary_contacts()]


def format_recipients(recipients):
    return ', '.join(f'{name} <{email}>' for name, email in recipients)


force_test_mode = False  #set by a script's --test flag


def get_test_email():
    #[testing] in config.ini: when test_mode is on (or --test is used), every email goes to
    #test_email instead of the real recipients. Returns None in production mode.
    try:
        test_mode = force_test_mode or config.getboolean('testing', 'test_mode', fallback=False)
    except ValueError:
        sys.exit('ERROR: [testing] test_mode in ' + CONFIG_FILE + ' must be on or off')
    if not test_mode:
        return None
    test_email = config.get('testing', 'test_email', fallback='').strip()
    if not test_email:
        sys.exit('ERROR: test mode is on but [testing] test_email is empty in ' + CONFIG_FILE)
    return test_email


def describe_mode():
    #one line for the logs saying where emails are going
    test_email = get_test_email()
    if test_email:
        return 'TEST MODE: all emails go to ' + test_email + ' instead of the real recipients'
    return 'PRODUCTION MODE: emails go to the real recipients'


def send_email(recipients, subject, text_body, html_body=None, reply_to=None):
    #[email] section of config.ini: Gmail address and app password used to send
    sender = config.get('email', 'sender', fallback='').strip()
    password = config.get('email', 'app_password', fallback='').strip()
    if not sender or not password:
        sys.exit('ERROR: fill in the [email] sender and app_password in ' + CONFIG_FILE)

    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = sender
    test_email = get_test_email()
    if test_email:
        #same subject and body as production; the To name shows who it would have gone to.
        #no Reply-To, so replying to a test email can't reach the real recipients
        message['To'] = formataddr(('TEST - would go to: ' + format_recipients(recipients), test_email))
        if reply_to:
            message['X-Test-Reply-To'] = format_recipients(reply_to)
    else:
        message['To'] = format_recipients(recipients)
        if reply_to:
            message['Reply-To'] = format_recipients(reply_to)
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype='html')

    server = config.get('email', 'smtp_server', fallback='smtp.gmail.com')
    port = config.getint('email', 'smtp_port', fallback=465)
    with smtplib.SMTP_SSL(server, port, timeout=30) as smtp:
        smtp.login(sender, password)
        smtp.send_message(message)
