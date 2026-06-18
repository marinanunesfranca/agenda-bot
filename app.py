import os
import json
import random
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from apscheduler.schedulers.background import BackgroundScheduler
from twilio.rest import Client

import pytz
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request as GoogleRequest

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "change-me-in-production")

TIMEZONE = os.getenv("TIMEZONE", "America/Sao_Paulo")
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

MORNING_OPENERS_BUSY = [
    "Busy one today — let's make it count.",
    "Full schedule ahead. Stay focused.",
    "Lots on today. You've got this.",
    "A packed day — prioritise and move.",
]
MORNING_OPENERS_LIGHT = [
    "Lighter day today. Good time for deep work.",
    "Some breathing room today — use it well.",
    "Not much on the calendar. Good day to get ahead.",
]
EVENING_OPENERS_BUSY = [
    "Tomorrow's looking full — good to be prepared.",
    "Heads up: busy day ahead tomorrow.",
    "Tomorrow has a lot going on. Plan accordingly.",
]
EVENING_OPENERS_LIGHT = [
    "Tomorrow looks calm. Enjoy the evening.",
    "Light schedule tomorrow — rest up tonight.",
    "Not much on tomorrow. Good night ahead.",
]

DAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# --- Settings stored in Render env vars ---

def load_data():
    return {
        "morning_time": os.getenv("MORNING_TIME", ""),
        "evening_time": os.getenv("EVENING_TIME", ""),
        "phone": os.getenv("WHATSAPP_PHONE", ""),
        "selected_calendars": json.loads(os.getenv("SELECTED_CALENDARS", "[]")),
    }


def save_data_to_render(morning_time, evening_time, phone, selected_calendars):
    """Save all settings to Render environment variables."""
    os.environ["MORNING_TIME"] = morning_time
    os.environ["EVENING_TIME"] = evening_time
    os.environ["WHATSAPP_PHONE"] = phone
    os.environ["SELECTED_CALENDARS"] = json.dumps(selected_calendars)

    render_api_key = os.getenv("RENDER_API_KEY")
    service_id = os.getenv("RENDER_SERVICE_ID")
    if not render_api_key or not service_id:
        return

    try:
        res = requests.get(
            f"https://api.render.com/v1/services/{service_id}/env-vars",
            headers={"Authorization": f"Bearer {render_api_key}"},
        )
        raw = res.json()
        # Handle both formats: list of {key,value} or list of {cursor, envVar:{key,value}}
        env_vars = []
        for item in raw:
            if "envVar" in item:
                env_vars.append(item["envVar"])
            elif "key" in item:
                env_vars.append(item)

        updates = {
            "MORNING_TIME": morning_time,
            "EVENING_TIME": evening_time,
            "WHATSAPP_PHONE": phone,
            "SELECTED_CALENDARS": json.dumps(selected_calendars),
        }
        updated = []
        for ev in env_vars:
            k = ev["key"]
            if k in updates:
                updated.append({"key": k, "value": updates.pop(k)})
            else:
                updated.append({"key": k, "value": ev["value"]})
        for key, value in updates.items():
            updated.append({"key": key, "value": value})
        requests.put(
            f"https://api.render.com/v1/services/{service_id}/env-vars",
            headers={"Authorization": f"Bearer {render_api_key}"},
            json=updated,
        )
        print(f"Settings saved to Render: morning={morning_time}, evening={evening_time}")
    except Exception as e:
        print(f"Could not save settings to Render: {e}")


# --- Google token ---

def get_token_from_env():
    raw = os.getenv("GOOGLE_TOKEN", "")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def save_token_to_render(creds):
    token_data = json.dumps({
        "token": creds.token,
        "refresh_token": creds.refresh_token,
    })
    os.environ["GOOGLE_TOKEN"] = token_data

    render_api_key = os.getenv("RENDER_API_KEY")
    service_id = os.getenv("RENDER_SERVICE_ID")
    if not render_api_key or not service_id:
        return

    try:
        res = requests.get(
            f"https://api.render.com/v1/services/{service_id}/env-vars",
            headers={"Authorization": f"Bearer {render_api_key}"},
        )
        raw = res.json()
        env_vars = []
        for item in raw:
            if "envVar" in item:
                env_vars.append(item["envVar"])
            elif "key" in item:
                env_vars.append(item)
        updated = []
        found = False
        for ev in env_vars:
            if ev["key"] == "GOOGLE_TOKEN":
                updated.append({"key": "GOOGLE_TOKEN", "value": token_data})
                found = True
            else:
                updated.append({"key": ev["key"], "value": ev["value"]})
        if not found:
            updated.append({"key": "GOOGLE_TOKEN", "value": token_data})
        requests.put(
            f"https://api.render.com/v1/services/{service_id}/env-vars",
            headers={"Authorization": f"Bearer {render_api_key}"},
            json=updated,
        )
        print("Token saved to Render.")
    except Exception as e:
        print(f"Could not save token to Render: {e}")


def get_google_creds():
    token_data = get_token_from_env()
    if not token_data:
        return None
    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        scopes=SCOPES,
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleRequest())
        save_token_to_render(creds)
    return creds


# --- Calendar ---

def get_events_for_day(target_date):
    creds = get_google_creds()
    if not creds:
        return [], {}

    data = load_data()
    selected = data.get("selected_calendars", [])
    tz = pytz.timezone(TIMEZONE)
    start = tz.localize(datetime.combine(target_date, datetime.min.time()))
    end = start + timedelta(days=1)

    service = build("calendar", "v3", credentials=creds)
    cal_list = service.calendarList().list().execute()
    calendars = {c["id"]: c["summary"] for c in cal_list.get("items", [])}

    all_events = []
    for cal_id in selected:
        if cal_id not in calendars:
            continue
        result = service.events().list(
            calendarId=cal_id,
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        for ev in result.get("items", []):
            all_day = "dateTime" not in ev["start"]
            if not all_day:
                dt_start = datetime.fromisoformat(ev["start"]["dateTime"]).astimezone(tz)
                dt_end = datetime.fromisoformat(ev["end"]["dateTime"]).astimezone(tz)
                time_label = f"{dt_start.strftime('%H:%M')}–{dt_end.strftime('%H:%M')}"
                sort_key = dt_start
            else:
                time_label = "All day"
                sort_key = start
            all_events.append({
                "summary": ev.get("summary", "Busy"),
                "time": time_label,
                "all_day": all_day,
                "sort": sort_key,
            })

    all_events.sort(key=lambda x: x["sort"])
    return all_events, calendars


def format_event_list(events):
    lines = []
    timed = [e for e in events if not e["all_day"]]
    allday = [e for e in events if e["all_day"]]
    if allday:
        for e in allday:
            lines.append(f"📌 {e['summary']} _(all day)_")
    for e in timed:
        lines.append(f"• *{e['time']}* — {e['summary']}")
    return lines


def build_morning_message():
    tz = pytz.timezone(TIMEZONE)
    today = datetime.now(tz).date()
    day_label = DAYS_EN[today.weekday()]
    date_label = today.strftime("%d/%m")
    events, _ = get_events_for_day(today)
    timed = [e for e in events if not e["all_day"]]
    busy = len(timed) >= 4
    opener = random.choice(MORNING_OPENERS_BUSY if busy else MORNING_OPENERS_LIGHT)
    lines = [
        f"☀️ *Good morning! {day_label}, {date_label}*",
        f"_{opener}_", "",
        "*Today's agenda:*",
    ]
    event_lines = format_event_list(events)
    lines += event_lines if event_lines else ["_Nothing scheduled — free day!_"]
    return "\n".join(lines)


def build_evening_message():
    tz = pytz.timezone(TIMEZONE)
    tomorrow = datetime.now(tz).date() + timedelta(days=1)
    day_label = DAYS_EN[tomorrow.weekday()]
    date_label = tomorrow.strftime("%d/%m")
    events, _ = get_events_for_day(tomorrow)
    timed = [e for e in events if not e["all_day"]]
    busy = len(timed) >= 4
    opener = random.choice(EVENING_OPENERS_BUSY if busy else EVENING_OPENERS_LIGHT)
    lines = [
        f"🌙 *Tomorrow preview — {day_label}, {date_label}*",
        f"_{opener}_", "",
        "*Tomorrow's agenda:*",
    ]
    event_lines = format_event_list(events)
    lines += event_lines if event_lines else ["_Nothing scheduled yet._"]
    return "\n".join(lines)


def send_whatsapp(message):
    phone = os.getenv("WHATSAPP_PHONE", "").strip()
    if not phone:
        print("No phone set.")
        return
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_num = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    if not sid or not token:
        print("Twilio credentials missing.")
        return
    client = Client(sid, token)
    try:
        msg = client.messages.create(
            body=message, from_=from_num, to=f"whatsapp:{phone}",
        )
        print(f"Sent: {msg.sid}")
    except Exception as e:
        print(f"Twilio error: {e}")


def send_morning():
    print(">>> send_morning triggered by scheduler")
    send_whatsapp(build_morning_message())


def send_evening():
    print(">>> send_evening triggered by scheduler")
    send_whatsapp(build_evening_message())


@app.route("/cron/morning")
def cron_morning():
    send_morning()
    return "ok"


@app.route("/cron/evening")
def cron_evening():
    send_evening()
    return "ok"


scheduler = BackgroundScheduler()
scheduler.start()


def reschedule(morning_time=None, evening_time=None):
    tz = pytz.timezone(TIMEZONE)
    morning_time = morning_time or os.getenv("MORNING_TIME", "")
    evening_time = evening_time or os.getenv("EVENING_TIME", "")
    scheduler.remove_all_jobs()
    if morning_time:
        mh, mm = map(int, morning_time.split(":"))
        scheduler.add_job(send_morning, "cron", hour=mh, minute=mm, timezone=tz, id="morning")
        print(f"Scheduled morning {morning_time} {TIMEZONE}")
    if evening_time:
        eh, em = map(int, evening_time.split(":"))
        scheduler.add_job(send_evening, "cron", hour=eh, minute=em, timezone=tz, id="evening")
        print(f"Scheduled evening {evening_time} {TIMEZONE}")


reschedule()


@app.route("/")
def index():
    data = load_data()
    creds = get_google_creds()
    calendars = {}
    if creds:
        try:
            service = build("calendar", "v3", credentials=creds)
            cal_list = service.calendarList().list().execute()
            calendars = {c["id"]: c["summary"] for c in cal_list.get("items", [])}
        except Exception:
            pass
    return render_template("index.html", data=data, calendars=calendars,
                           connected=bool(creds) and bool(calendars))


@app.route("/save-settings", methods=["POST"])
def save_settings():
    morning_time = request.form.get("morning_time", "07:00").strip()
    evening_time = request.form.get("evening_time", "18:00").strip()
    phone = request.form.get("phone", "").strip()
    selected_calendars = request.form.getlist("calendars")
    save_data_to_render(morning_time, evening_time, phone, selected_calendars)
    reschedule(morning_time, evening_time)
    return redirect(url_for("index"))


@app.route("/auth/google")
def auth_google():
    flow = Flow.from_client_config(
        {"web": {
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "redirect_uris": [os.getenv("REDIRECT_URI")],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }},
        scopes=SCOPES,
    )
    flow.redirect_uri = os.getenv("REDIRECT_URI")
    auth_url, state = flow.authorization_url(access_type="offline", prompt="consent")
    session["oauth_state"] = state
    return redirect(auth_url)


@app.route("/auth/callback")
def auth_callback():
    flow = Flow.from_client_config(
        {"web": {
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "redirect_uris": [os.getenv("REDIRECT_URI")],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }},
        scopes=SCOPES,
        state=session.get("oauth_state"),
    )
    flow.redirect_uri = os.getenv("REDIRECT_URI")
    flow.fetch_token(authorization_response=request.url)
    save_token_to_render(flow.credentials)
    return redirect(url_for("index"))


@app.route("/preview/morning")
def preview_morning():
    return jsonify({"message": build_morning_message()})


@app.route("/preview/evening")
def preview_evening():
    return jsonify({"message": build_evening_message()})


@app.route("/send-now/morning", methods=["POST"])
def send_now_morning():
    send_morning()
    return jsonify({"status": "sent"})


@app.route("/send-now/evening", methods=["POST"])
def send_now_evening():
    send_evening()
    return jsonify({"status": "sent"})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
