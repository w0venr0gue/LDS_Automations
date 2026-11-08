#weekly email to the missionaries listing every Calendly appointment
#for the next 30 days
import argparse, datetime, html, smtplib, sys
import requests
import calendly_common
from calendly_common import describe_mode, CONFIG_FILE, format_recipients, get_appointments, get_missionaries, get_user, send_email, time_text


def group_by_day(appointments):
    days = {}
    for appt in appointments:
        days.setdefault(appt['start'].date(), []).append(appt)
    return days


def build_text(appointments, start, end, owner):
    lines = [f"Appointments for {owner}", f"{start:%A, %B %d} through {end:%A, %B %d}", '']
    if not appointments:
        lines.append('No appointments are scheduled for this period.')
    for day, appts in group_by_day(appointments).items():
        lines.append(f"{day:%A, %B %d}")
        lines.append('-' * 30)
        for appt in appts:
            lines.append(f"  {time_text(appt)}  {appt['name']}")
            if appt['location']:
                lines.append(f"    Location: {appt['location']}")
            for invitee in appt['invitees']:
                lines.append(f"    Signed up: {invitee['name']} <{invitee['email']}>")
                for question, answer in invitee['details']:
                    lines.append(f"    {question}: {answer}")
            lines.append('')
    return '\n'.join(lines)


def build_html(appointments, start, end, owner):
    e = html.escape
    parts = [
        '<div style="font-family:Arial,sans-serif;font-size:14px;color:#222;max-width:640px">',
        f'<h2 style="margin:0 0 4px">Appointments for {e(owner)}</h2>',
        f'<p style="margin:0 0 16px;color:#555">{start:%A, %B %d} through {end:%A, %B %d}</p>',
    ]
    if not appointments:
        parts.append('<p>No appointments are scheduled for this period.</p>')
    for day, appts in group_by_day(appointments).items():
        parts.append(f'<h3 style="margin:20px 0 6px;padding-bottom:4px;border-bottom:2px solid #2b5797;color:#2b5797">{day:%A, %B %d}</h3>')
        for appt in appts:
            parts.append('<div style="margin:0 0 12px;padding:8px 12px;background:#f4f6f9;border-radius:6px">')
            parts.append(f'<div><b>{e(time_text(appt))}</b> &nbsp; {e(appt["name"])}</div>')
            rows = []
            if appt['location']:
                rows.append(('Location', appt['location']))
            for invitee in appt['invitees']:
                rows.append(('Signed up', f"{invitee['name']} <{invitee['email']}>"))
                rows.extend(invitee['details'])
            if rows:
                parts.append('<table style="margin-top:4px;border-collapse:collapse">')
                for label, value in rows:
                    parts.append(f'<tr><td style="padding:2px 12px 2px 0;color:#555;vertical-align:top">{e(label)}</td>'
                                 f'<td style="padding:2px 0">{e(str(value))}</td></tr>')
                parts.append('</table>')
            parts.append('</div>')
    parts.append('</div>')
    return '\n'.join(parts)


def main():
    parser = argparse.ArgumentParser(description='Email upcoming Calendly appointments to the missionaries')
    parser.add_argument('-d', '--days', type=int, default=30, help='number of days ahead to look (default 30)')
    parser.add_argument('-p', '--preview', action='store_true', help='print the email instead of sending it')
    parser.add_argument('--test', action='store_true', help='send to [testing] test_email in config.ini instead of the real recipients')
    args = parser.parse_args()
    if args.test:
        calendly_common.force_test_mode = True
    if not args.preview:
        print(describe_mode())

    missionaries = get_missionaries()
    if not missionaries and not args.preview:
        sys.exit('ERROR: add the missionaries to the [missionaries] section of ' + CONFIG_FILE)

    try:
        user, tz = get_user()
        now = datetime.datetime.now(tz)
        end = now + datetime.timedelta(days=args.days)
        appointments = get_appointments(user['uri'], now, end, tz)
    except requests.RequestException as error:
        sys.exit('ERROR ' + str(error))

    subject = f"Appointments: {now:%b %d} - {end:%b %d} ({len(appointments)} scheduled)"
    text_body = build_text(appointments, now, end, user['name'])
    html_body = build_html(appointments, now, end, user['name'])

    if args.preview:
        print('To: ' + (format_recipients(missionaries) or '(no missionaries configured)'))
        print('Subject: ' + subject + '\n')
        print(text_body)
        return

    try:
        send_email(missionaries, subject, text_body, html_body)
    except (smtplib.SMTPException, OSError) as error:
        sys.exit('ERROR sending email: ' + str(error))
    print(f"Sent {len(appointments)} appointment(s) to " + ', '.join(name for name, _ in missionaries))


if __name__ == '__main__':
    main()
