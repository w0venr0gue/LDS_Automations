#emails the missionaries when appointments between now and the next weekly update
#are added, canceled or changed. Run on a recurring schedule; each run compares Calendly
#against what it saw last time (saved in change_state.json next to this script).
import argparse, datetime, html, json, os, smtplib, sys
import requests
import calendly_common
from calendly_common import describe_mode, CONFIG_FILE, config, format_recipients, get_appointments, get_missionaries, get_user, send_email, time_text

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'change_state.json')
WEEKDAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']


def get_next_weekly_run(now):
    #when the weekly update next runs ([schedule] weekly_day and weekly_time in config.ini).
    #the alert only watches appointments before then, since the weekly email covers the rest
    weekly_day = config.get('schedule', 'weekly_day', fallback='Sunday').strip().lower()
    if weekly_day not in WEEKDAYS:
        sys.exit(f"ERROR: [schedule] weekly_day in {CONFIG_FILE} must be a day name like Sunday, not '{weekly_day}'")
    weekly_time = config.get('schedule', 'weekly_time', fallback='20:00').strip()
    try:
        run_time = datetime.datetime.strptime(weekly_time, '%H:%M').time()
    except ValueError:
        sys.exit(f"ERROR: [schedule] weekly_time in {CONFIG_FILE} must be 24-hour HH:MM like 20:00, not '{weekly_time}'")
    days_until = (WEEKDAYS.index(weekly_day) - now.weekday()) % 7
    next_run = datetime.datetime.combine(now.date() + datetime.timedelta(days=days_until), run_time, now.tzinfo)
    if next_run <= now:
        next_run += datetime.timedelta(days=7)
    return next_run


def snapshot(appt):
    #the parts of an appointment we watch for changes, in a JSON-friendly form
    return {
        'time': appt['time'],
        'start': appt['start'].isoformat(),
        'end': appt['end'].isoformat(),
        'name': appt['name'],
        'location': appt['location'],
        'invitees': [[i['name'], i['email'], [list(d) for d in i['details']]] for i in appt['invitees']],
    }


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def save_state(checked_at, appointments):
    with open(STATE_FILE, 'w') as f:
        json.dump({'checked_at': checked_at.isoformat(),
                   'appointments': {a['uri']: snapshot(a) for a in appointments}}, f, indent=2)


def find_changes(previous, appointments, now, end):
    last_check = datetime.datetime.fromisoformat(previous['checked_at'])
    #bookings made before the last weekly run were listed in that email, so don't report them as added
    added_after = max(last_check, end - datetime.timedelta(days=7))
    #state saved before the "Time" field was tracked has no 'time'; treat it as blank
    old = {uri: {'time': '', **snap} for uri, snap in previous['appointments'].items()}
    current = {a['uri']: snapshot(a) for a in appointments}
    changes = []

    for uri, snap in current.items():
        if uri not in old:
            #booked since the last check (not just an older booking rolling into the window)
            appt = next(a for a in appointments if a['uri'] == uri)
            if appt['created'] > added_after:
                changes.append(('Added', snap, None))
        elif snap != old[uri]:
            changes.append(('Changed', snap, old[uri]))

    for uri, snap in old.items():
        start = datetime.datetime.fromisoformat(snap['start'])
        #gone from Calendly but still in the future and inside the window: canceled or moved away
        if uri not in current and now <= start < end:
            changes.append(('Canceled', snap, None))

    changes.sort(key=lambda c: c[1]['start'])
    return changes


def describe(snap, tz):
    #date from the Calendly slot; time from the "Time" form answer, or the slot if there isn't one
    start = datetime.datetime.fromisoformat(snap['start']).astimezone(tz)
    end = datetime.datetime.fromisoformat(snap['end']).astimezone(tz)
    return f"{start:%A, %B %d} " + time_text({'time': snap.get('time'), 'start': start, 'end': end})


def detail_rows(snap):
    rows = [('Location', snap['location'])] if snap['location'] else []
    for name, email, details in snap['invitees']:
        rows.append(('Signed up', f"{name} <{email}>"))
        rows += [tuple(d) for d in details]
    return rows


def what_changed(new, old, tz):
    notes = []
    if describe(new, tz) != describe(old, tz):
        notes.append('Time changed from ' + describe(old, tz))
    if new['location'] != old['location']:
        notes.append('Location changed from ' + (old['location'] or '(none)'))
    if new['invitees'] != old['invitees'] or new['name'] != old['name']:
        notes.append('Sign-up details changed')
    return notes


def build_text(changes, tz):
    lines = ['The missionary calendar has changed since the last update:', '']
    for kind, snap, old in changes:
        lines.append(f"{kind.upper()}: {describe(snap, tz)}  {snap['name']}")
        if old:
            lines += ['    ' + note for note in what_changed(snap, old, tz)]
        lines += [f"    {label}: {value}" for label, value in detail_rows(snap)]
        lines.append('')
    return '\n'.join(lines)


def build_html(changes, tz):
    e = html.escape
    colors = {'Added': '#2e7d32', 'Changed': '#b26a00', 'Canceled': '#c62828'}
    parts = ['<div style="font-family:Arial,sans-serif;font-size:14px;color:#222;max-width:640px">',
             '<p>The missionary calendar has changed since the last update:</p>']
    for kind, snap, old in changes:
        parts.append(f'<div style="margin:0 0 12px;padding:8px 12px;background:#f4f6f9;border-left:4px solid {colors[kind]};border-radius:4px">')
        parts.append(f'<div><b style="color:{colors[kind]}">{kind.upper()}</b> &nbsp; <b>{e(describe(snap, tz))}</b> &nbsp; {e(snap["name"])}</div>')
        if old:
            parts += [f'<div style="color:{colors[kind]}">{e(note)}</div>' for note in what_changed(snap, old, tz)]
        rows = detail_rows(snap)
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
    parser = argparse.ArgumentParser(description='Email the missionaries when Calendly appointments before the next weekly update change')
    parser.add_argument('-p', '--preview', action='store_true', help='print the email instead of sending it (does not save state)')
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
        end = get_next_weekly_run(now)
        appointments = get_appointments(user['uri'], now, end, tz)
    except requests.RequestException as error:
        sys.exit('ERROR ' + str(error))

    previous = load_state()
    if previous is None:
        #first run: just remember the calendar so the next run has something to compare to
        if args.preview:
            print(f"First run: {len(appointments)} appointment(s) would be saved as the starting point (preview, nothing saved)")
            return
        save_state(now, appointments)
        print(f"First run: saved {len(appointments)} appointment(s) as the starting point; no email sent")
        return

    changes = find_changes(previous, appointments, now, end)
    if not changes:
        if not args.preview:
            save_state(now, appointments)
        print('No changes since ' + datetime.datetime.fromisoformat(previous['checked_at']).astimezone(tz).strftime('%b %d %I:%M %p'))
        return

    counts = ', '.join(f"{sum(1 for c in changes if c[0] == k)} {k.lower()}" for k in ('Added', 'Changed', 'Canceled')
                       if any(c[0] == k for c in changes))
    subject = f"Calendar update: {counts}"
    text_body = build_text(changes, tz)

    if args.preview:
        print('To: ' + (format_recipients(missionaries) or '(no missionaries configured)'))
        print('Subject: ' + subject + '\n')
        print(text_body)
        return

    try:
        send_email(missionaries, subject, text_body, build_html(changes, tz))
    except (smtplib.SMTPException, OSError) as error:
        #don't save state, so the same changes are reported on the next run
        sys.exit('ERROR sending email: ' + str(error))
    save_state(now, appointments)
    print(f"Sent {len(changes)} change(s) to " + ', '.join(name for name, _ in missionaries))


if __name__ == '__main__':
    main()
