#daily email reminding each family that signed up in Calendly about their
#appointment with the missionaries tomorrow. Run once each morning.
import argparse, datetime, html, smtplib, sys
import requests
import calendly_common
from calendly_common import describe_mode, config, format_recipients, get_appointments, get_missionaries, get_missionary_contacts, get_user, send_email


def get_custom_message():
    #[reminders] message in config.ini; indent extra lines to continue it
    return config.get('reminders', 'message', fallback='').strip()


def describe_time(appt):
    #the "Time" form answer if the family gave one, otherwise the Calendly slot start
    return f"{appt['start']:%A, %B %d} at " + (appt['time'] or appt['start'].strftime('%I:%M %p').lstrip('0'))


def contact_line(email, phone):
    return email + (' - ' + phone if phone else '')


def build_text(invitee, appt, contacts, message):
    lines = [f"Hi {invitee['name']},", '',
             f"This is a reminder that the missionaries are scheduled to visit {describe_time(appt)}."]
    if contacts:
        lines += ['', 'The Odenton Ward missionaries:']
        lines += [f"  {name} - {contact_line(email, phone)}" for name, email, phone in contacts]
    if message:
        lines += ['', message]
    lines += ['', 'Sincerely,', 'The ward mission']
    return '\n'.join(lines)


def build_html(invitee, appt, contacts, message):
    e = html.escape
    parts = [
        '<div style="font-family:Arial,sans-serif;font-size:14px;color:#222;max-width:560px">',
        f'<p>Hi {e(invitee["name"])},</p>',
        f'<p>This is a reminder that the missionaries are scheduled to visit <b>{e(describe_time(appt))}</b>.</p>',
    ]
    if contacts:
        parts.append('<p style="margin-bottom:4px"><b>The Odenton Ward missionaries</b></p><ul style="margin-top:0">')
        for name, email, phone in contacts:
            phone_link = f' - <a href="tel:{e(phone)}">{e(phone)}</a>' if phone else ''
            parts.append(f'<li>{e(name)} - <a href="mailto:{e(email)}">{e(email)}</a>{phone_link}</li>')
        parts.append('</ul>')
    if message:
        parts.append('<p>' + e(message).replace('\n', '<br>') + '</p>')
    parts.append('<p>Sincerely,<br>The ward mission</p></div>')
    return '\n'.join(parts)


def main():
    parser = argparse.ArgumentParser(description='Email reminders to families with a missionary appointment tomorrow')
    parser.add_argument('--date', help='remind for this date (YYYY-MM-DD) instead of tomorrow')
    parser.add_argument('-p', '--preview', action='store_true', help='print the reminders instead of sending them')
    parser.add_argument('--test', action='store_true', help='send to [testing] test_email in config.ini instead of the real recipients')
    args = parser.parse_args()
    if args.test:
        calendly_common.force_test_mode = True
    if not args.preview:
        print(describe_mode())

    missionaries = get_missionaries()
    contacts = get_missionary_contacts()
    message = get_custom_message()

    try:
        user, tz = get_user()
        if args.date:
            day = datetime.date.fromisoformat(args.date)
        else:
            day = datetime.datetime.now(tz).date() + datetime.timedelta(days=1)
        start = datetime.datetime.combine(day, datetime.time.min, tz)
        appointments = get_appointments(user['uri'], start, start + datetime.timedelta(days=1), tz)
    except requests.RequestException as error:
        sys.exit('ERROR ' + str(error))

    sent = 0
    for appt in appointments:
        for invitee in appt['invitees']:
            recipient = [(invitee['name'], invitee['email'])]
            subject = f"Reminder: missionary visit {describe_time(appt)}"
            text_body = build_text(invitee, appt, contacts, message)

            if args.preview:
                print('To: ' + format_recipients(recipient))
                print('Reply-To: ' + (format_recipients(missionaries) or '(none)'))
                print('Subject: ' + subject + '\n')
                print(text_body + '\n' + '=' * 40)
                continue

            try:
                send_email(recipient, subject, text_body, build_html(invitee, appt, contacts, message), reply_to=missionaries)
                sent += 1
                print('Sent reminder to ' + format_recipients(recipient))
            except (smtplib.SMTPException, OSError) as error:
                #keep going so one bad address doesn't stop the other reminders
                print('ERROR sending to ' + format_recipients(recipient) + ': ' + str(error))

    if not appointments:
        print(f"No appointments on {day:%A, %B %d}; no reminders to send")
    elif not args.preview:
        print(f"Sent {sent} reminder(s) for {day:%A, %B %d}")


if __name__ == '__main__':
    main()
