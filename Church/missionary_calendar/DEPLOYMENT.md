# Missionary Calendar – Linux Deployment

How to install the missionary calendar scripts on a Linux server and run them on a schedule with cron.

## What gets deployed

| Script | What it does | Schedule (example) |
|---|---|---|
| `weekly_missionary_update.py` | Emails the missionaries every appointment in the next 30 days | Sundays 8:00 PM |
| `family_reminders.py` | Emails each family that has a visit tomorrow | Daily 8:00 AM |
| `calendar_change_alert.py` | Emails the missionaries when an appointment between now and the next weekly update is added, canceled or changed | Hourly 7 AM – 9 PM, every day |

Supporting files:

- `calendly_common.py` – shared code (config, Calendly, email). Not run directly.
- `run.sh` – wrapper cron calls; runs a script with the project's Python and logs its output.
- `config.ini` – token, Gmail app password, missionaries and settings. **Not in git**; copied to the server by hand.
- `change_state.json` – created by the change alert to remember the last calendar it saw. Not in git.

## 1. Prerequisites

- A Linux server that stays on (any distro with Python 3.9 or newer).
- Outbound internet access to `api.calendly.com` (port 443) and `smtp.gmail.com` (port 465).
- `git`, `python3` and the `venv` module.

On Debian/Ubuntu:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv
python3 --version   # must be 3.9 or newer
```

On Fedora/RHEL/Rocky:

```bash
sudo dnf install -y git python3
```

> Some cloud hosts (DigitalOcean, Google Cloud, AWS Lightsail, etc.) block outbound email ports on new servers. Step 5 checks for this.

## 2. Get the code

Clone the repository as the user that will run the cron jobs (not root):

```bash
cd ~
git clone https://github.com/w0venr0gue/LDS_Automations.git
cd ~/LDS_Automations/Church/missionary_calendar
```

If the repository is private, sign in with a GitHub personal access token when prompted, or set up an SSH deploy key. **Do not** put a token in the clone URL (`https://<token>@github.com/...`): that saves it in plain text in `.git/config`.

The rest of this guide assumes the scripts live in:

```
~/LDS_Automations/Church/missionary_calendar
```

## 3. Create the Python environment

```bash
cd ~/LDS_Automations/Church/missionary_calendar
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`run.sh` expects the environment at `.venv` inside this folder. It's ignored by git.

## 4. Add `config.ini`

`config.ini` holds the secrets, so it isn't in git. Either copy the working one from the Windows PC or create it from the template.

**Copy from Windows** (run from PowerShell on the PC):

```powershell
scp C:\Users\cade\Desktop\git\Church\missionary_calendar\config.ini youruser@yourserver:~/LDS_Automations/Church/missionary_calendar/
```

**Or create it on the server:**

```bash
cp config.example.ini config.ini
nano config.ini
```

Fill in every section:

| Section | Setting | Value |
|---|---|---|
| `[calendly]` | `token` | Calendly personal access token with **only** `users:read` and `scheduled_events:read` |
| `[email]` | `sender` | Gmail address the emails come from |
| `[email]` | `app_password` | 16-character Gmail App Password for that account (not the normal password) |
| `[missionaries]` | `Name = email, phone` | One line per missionary; phone is optional and shown to families |
| `[reminders]` | `message` | Note added to the end of each family reminder |
| `[schedule]` | `weekly_day` | Day the weekly update runs (`Sunday`). **Must match the weekly cron job in step 8** |
| `[schedule]` | `weekly_time` | Time the weekly update runs, 24-hour (`20:00`). **Must match the weekly cron job in step 8** |
| `[testing]` | `test_mode` | `on` while testing: every email goes to `test_email` instead of the real recipients. `off` for production. See step 11 |
| `[testing]` | `test_email` | Address that receives every email while test mode is on |

Then lock it down so only your user can read it:

```bash
chmod 600 config.ini
```

## 5. Test before scheduling

Check that the server can reach Gmail's mail server:

```bash
.venv/bin/python -c "import socket; socket.create_connection(('smtp.gmail.com', 465), 10); print('smtp ok')"
```

If this times out, the host is blocking outbound email. Ask the provider to unblock port 465, or use a different server.

Preview each email. These read Calendly but **send nothing**:

```bash
.venv/bin/python weekly_missionary_update.py --preview
.venv/bin/python family_reminders.py --preview
.venv/bin/python calendar_change_alert.py --preview
```

Optionally send one real reminder to your test address instead of the families (pick a date that has a booking). `--test` forces test mode for that run, even if `test_mode` is off:

```bash
.venv/bin/python family_reminders.py --date 2026-11-12 --test
```

## 6. Save the change alert's starting point

The first real run of the change alert records the current calendar and sends nothing. Do this once now, so the first scheduled run has something to compare against:

```bash
.venv/bin/python calendar_change_alert.py
# First run: saved N appointment(s) as the starting point; no email sent
```

This creates `change_state.json`. If you ever delete that file, the next run quietly starts over the same way.

## 7. Set the server's time zone

Cron runs jobs on the **server's** clock, and many servers default to UTC. The scripts already use the Calendly account's time zone for appointment times, but the cron schedule needs the server on local time too. Otherwise "8:00 AM" means 8:00 AM UTC.

```bash
timedatectl                                   # shows the current time zone
sudo timedatectl set-timezone America/New_York
sudo systemctl restart cron 2>/dev/null || sudo systemctl restart crond
```

(If you'd rather not change the server's time zone, convert the cron times in step 8 to UTC, and remember the offset changes with daylight saving time.)

## 8. Schedule the cron jobs

Open your user's crontab (not root's):

```bash
crontab -e
```

Add these lines:

```cron
# Missionary calendar (times are server-local; see step 7)
# Weekly update to the missionaries: Sundays at 8:00 PM
0 20 * * 0    sh $HOME/LDS_Automations/Church/missionary_calendar/run.sh weekly_missionary_update.py

# Reminders to families with a visit tomorrow: every day at 8:00 AM
0 8 * * *     sh $HOME/LDS_Automations/Church/missionary_calendar/run.sh family_reminders.py

# Change alert to the missionaries: every hour 7:00 AM - 9:00 PM, every day
0 7-21 * * *  flock -n /tmp/missionary_change_alert.lock sh $HOME/LDS_Automations/Church/missionary_calendar/run.sh calendar_change_alert.py
```

Notes:

- **Weekly day must match.** The `0` at the end of the weekly line is Sunday (0 = Sunday … 6 = Saturday). `weekly_day` in `config.ini` must be `Sunday` to match. The change alert uses that setting to decide how far ahead to watch. If you move the weekly update to another day, change both.
- **The change alert only reports visits before the next weekly email.** It watches from now until the next weekly run (Sunday 8 PM). On Sunday before 8 PM, that means only Sunday's own visits. A change made Sunday afternoon to Tuesday's visit sends no alert, because it shows up in the 8 PM weekly list. From the 8 PM run on, the alert watches the coming week.
- **Bookings made before the weekly email aren't reported as new afterward.** A Tuesday visit booked at 7:30 PM Sunday is in the 8 PM weekly list, so the 8 PM and 9 PM alert runs don't repeat it. One booked at 8:30 PM is reported at 9 PM.
- **The weekly time must match too.** `weekly_time` in `config.ini` (`20:00`) must match the weekly cron line (`0 20 ...`). If you move the weekly update, change `weekly_day`, `weekly_time` and the cron line together.
- **No alerts at night.** The change alert doesn't run between 10 PM and 7 AM. Changes made overnight aren't lost: the 7 AM run compares against the last check and reports them.
- **Each family gets one reminder.** Run the family reminders exactly once a day. Running them twice the same day sends duplicate reminders.
- `flock -n` stops a second change alert from starting if the previous one is still running.

Confirm the jobs were saved:

```bash
crontab -l
```

## 9. Check that it's working

Each script writes to its own log in `logs/`:

```bash
cd ~/LDS_Automations/Church/missionary_calendar
tail -n 20 logs/calendar_change_alert.log
tail -n 20 logs/family_reminders.log
tail -n 20 logs/weekly_missionary_update.log
```

Every run starts with a `=== YYYY-MM-DD HH:MM:SS` line, followed by the script's output (for example `No changes since ...`, `Sent reminder to ...`, or an `ERROR` line).

To check right away instead of waiting for the schedule, run the wrapper by hand. It logs exactly as cron would:

```bash
sh run.sh calendar_change_alert.py && tail -n 3 logs/calendar_change_alert.log
```

If nothing shows up in the logs after a scheduled time, check that cron itself ran the job:

```bash
grep CRON /var/log/syslog | tail        # Debian/Ubuntu
sudo journalctl -u cron -u crond --since today
```

## 10. Ongoing maintenance

**Missionary transfers.** Edit the `[missionaries]` section of `config.ini` on the server. The next run uses the new list; nothing needs restarting.

```bash
nano ~/LDS_Automations/Church/missionary_calendar/config.ini
```

**Changing the weekly day or time.** Update `weekly_day` and `weekly_time` in `config.ini` and the weekly cron line together.

**Updating the code** after changes are pushed to GitHub:

```bash
cd ~/LDS_Automations
git pull
cd Church/missionary_calendar
.venv/bin/pip install -r requirements.txt
```

`config.ini`, `change_state.json`, `logs/` and `.venv/` aren't tracked by git, so a pull never overwrites them.

**Replacing credentials.**
- Calendly token: create a new one (only `users:read` and `scheduled_events:read`), put it in `config.ini`, and delete the old one in Calendly.
- Gmail app password: changing the Google account's normal password revokes app passwords. Create a new one and update `app_password`.

**Log cleanup.** The logs grow by a few lines per run. To clear them occasionally:

```bash
truncate -s 0 ~/LDS_Automations/Church/missionary_calendar/logs/*.log
```

## 11. Test mode and going live

Run the scripts in **test mode** for a couple of weeks before anyone else gets emails. In test mode everything runs exactly as in production: the same schedule, the same Calendly data, the same subjects and contents. The change alert even keeps its saved state up to date. The only difference is that every email goes to `test_email` instead of the missionaries and families.

```ini
[testing]
test_mode = on
test_email = you@example.com
```

How to read a test email:

- The **To** line names the real recipients, e.g. `"TEST - would go to: Smith Family <smith@example.com>" <you@example.com>`. The subject and body are exactly what that recipient would get.
- Family reminders arrive as one email per family, just as each family would get them.
- Test emails have **no Reply-To**, so replying to one can't reach a real missionary. (In production, family reminders reply to the missionaries.)
- Each run's log starts with `TEST MODE: all emails go to ...` or `PRODUCTION MODE: emails go to the real recipients`, so the logs show which mode was used.

**Going live:** once the test emails look right, put the real missionaries in `[missionaries]` and set:

```ini
test_mode = off
```

No restart is needed; the next scheduled run sends to the real recipients. To pause real emails again later (for example, while changing something), set `test_mode = on`.

Any script can also be forced into test mode for a single run with `--test`, whatever `test_mode` says:

```bash
.venv/bin/python weekly_missionary_update.py --test
```

## Troubleshooting

| Log shows | Cause | Fix |
|---|---|---|
| `ERROR: put your Calendly personal access token in ...` | `config.ini` missing or token still the placeholder | Step 4 |
| `ERROR 401 ...` | Calendly token invalid or deleted | Create a new token and update `config.ini` |
| `ERROR 403 ...` | Token is missing a required scope | New token with `users:read` and `scheduled_events:read` |
| `ERROR sending email: (535, ... Username and Password not accepted)` | Wrong or revoked Gmail app password, or `sender` doesn't match the account | Create a new app password |
| `ERROR sending email: timed out` | Host blocks outbound port 465 | Step 5 connectivity check; contact the host |
| `ERROR: add the missionaries to the [missionaries] section ...` | No missionaries listed | Add them to `config.ini` |
| `ERROR: [schedule] weekly_day ... must be a day name` | Typo in `weekly_day` | Use a full day name, e.g. `Sunday` |
| `ERROR: [schedule] weekly_time ... must be 24-hour HH:MM` | Typo in `weekly_time` | Use 24-hour time, e.g. `20:00` |
| `ERROR: [testing] test_mode ... must be on or off` | Typo in `test_mode` | Use `on` or `off` |
| `ERROR: test mode is on but [testing] test_email is empty` | Test mode with no test address | Fill in `test_email` |
| Families or missionaries aren't getting emails | Still in test mode (log says `TEST MODE`) | Set `test_mode = off` (step 11) |
| `.venv/bin/python: not found` | Virtual environment not created in this folder | Step 3 |
| Emails arrive at the wrong hour | Server time zone is UTC | Step 7 |
| Change alert reports nothing for a booking after the next weekly update | Expected. It only watches visits before the next weekly run; the weekly email covers later dates | – |
