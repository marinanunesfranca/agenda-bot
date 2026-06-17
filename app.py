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

DATA_FILE = "data/schedule.json"
TIMEZONE = os.getenv("TIMEZONE", "America/Sao_Paulo")
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

MOTIVATIONAL_BUSY = [
    "Looks like a full one — let's make every block count.",
    "Busy day ahead. Prioritise, focus, deliver.",
    "A packed schedule means you're in demand. Own it.",
    "Full calendar today — energy up, distractions down.",
    "Lots on the plate. You've handled days like this before.",
]

MOTIVATIONAL_LIGHT = [
    "A lighter day — use the space to think ahead.",
    "Some breathing room today. Use it well.",
    "Fewer meetings means more deep work. Make it count.",
    "Open blocks are opportunities in disguise.",
    "A calm day is a good day to get ahead.",
]

DAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def load_data():
    if not os.path.exists(DATA_FILE):
        return {"send_time": "07:00", "phone": "", "selected_calendars": []}
    with open(DATA_FILE) as f:
        return json.load(f)


def save_data(data):
    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


# --- Token stored as Render environment variable ---

def get_token_from_env():
    raw = os.getenv("GOOGLE_TOKEN", "")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def save_token_to_render(creds):
    """Persist token by updating the Render environment variable via Render API."""
    render_api_key = os.getenv("RENDER_API_KEY")
    service_id = os.getenv("RENDER_SERVICE_ID")

    token_data = json.dumps({
        "token": creds.token,
        "refresh_token": creds.refresh_token,
    })

    # Also update in-process so current session works immediately
    os.environ["GOOGLE_TOKEN"] = token_data

    if not render_api_key or not service_id:
        # Fallback: save to file if Render API not configured
        os.makedirs("data", exist_ok=True)
        with open("data/google_token.json", "w") as f:
            f.write(token_data)
        return

    try:
        # Get current env vars
        res = requests.get(
            f"https://api.render.com/v1/services/{service_id}/env-vars",
            headers={"Authorization": f"Bearer {render_api_key}"},
        )
        env_vars = res.json()

        # Build updated list
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
        print("Token saved to Render env vars.")
    except Exception as e:
        print(f"Could not save token to Render: {e}")


def get_google_creds():
    token_data = get_token_from_env()

    # Fallback to file
    if not token_data and os.path.exists("data/google_token.json"):
        with open("data/google_token.json") as f:
            token_data = json.load(f)

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


def get_today_events():
    creds = get_google_creds()
    if not creds:
        return [], {}

    data = load_data()
    selected = data.get("selected_calendars", [])
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)

    service = build("calendar", "v3", credentials=creds)
    all_events = []

    cal_list = service.calendarList().list().execute()
    calendars = {c["id"]: c["summary"] for c in cal_list.get("items", [])}

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
            start_raw = ev["start"].get("dateTime", ev["start"].get("date"))
            end_raw = ev["end"].get("dateTime", ev["end"].get("date"))
            all_day = "dateTime" not in ev["start"]
            if not all_day:
                dt_start = datetime.fromisoformat(start_raw).astimezone(tz)
                dt_end = datetime.fromisoformat(end_raw).astimezone(tz)
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


def build_message():
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    day_label = DAYS_EN[now.weekday()]
    date_label = now.strftime("%d/%m")

    events, _ = get_today_events()
    timed = [e for e in events if not e["all_day"]]
    allday = [e for e in events if e["all_day"]]

    busy = len(timed) >= 4
    quote = random.choice(MOTIVATIONAL_BUSY if busy else MOTIVATIONAL_LIGHT)
    busy_word = "a busy" if busy else "a lighter"

    lines = [
        f"Hey! Let's start your *{day_label}* ({date_label}) with high energy — looks like {busy_word} day. {quote}",
        "",
    ]

    if allday:
        for e in allday:
            lines.append(f"📌 _{e['summary']}_")
        lines.append("")

    if timed:
        for e in timed:
            lines.append(f"*{e['time']}* — {e['summary']}")
    else:
        lines.append("_No timed events today. Enjoy the open space!_")

    lines.append("")
    lines.append("You've got this 💪")

    return "\n".join(lines)


def send_whatsapp():
    data = load_data()
    phone = data.get("phone", "").strip()
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
            body=build_message(),
            from_=from_num,
            to=f"whatsapp:{phone}",
        )
        print(f"Sent: {msg.sid}")
    except Exception as e:
        print(f"Twilio error: {e}")


scheduler = BackgroundScheduler()
scheduler.start()


def reschedule(send_time):
    tz = pytz.timezone(TIMEZONE)
    hour, minute = map(int, send_time.split(":"))
    scheduler.remove_all_jobs()
    scheduler.add_job(send_whatsapp, "cron", hour=hour, minute=minute,
                      timezone=tz, id="daily")
    print(f"Scheduled at {send_time} {TIMEZONE}")


data0 = load_data()
reschedule(data0.get("send_time", "07:00"))


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
    data = load_data()
    data["phone"] = request.form.get("phone", "").strip()
    data["send_time"] = request.form.get("send_time", "07:00").strip()
    data["selected_calendars"] = request.form.getlist("calendars")
    save_data(data)
    reschedule(data["send_time"])
    return redirect(url_for("index"))


@app.route("/auth/google")
def auth_google():
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                "redirect_uris": [os.getenv("REDIRECT_URI")],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
    )
    flow.redirect_uri = os.getenv("REDIRECT_URI")
    auth_url, state = flow.authorization_url(access_type="offline", prompt="consent")
    session["oauth_state"] = state
    return redirect(auth_url)


@app.route("/auth/callback")
def auth_callback():
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                "redirect_uris": [os.getenv("REDIRECT_URI")],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        state=session.get("oauth_state"),
    )
    flow.redirect_uri = os.getenv("REDIRECT_URI")
    flow.fetch_token(authorization_response=request.url)
    save_token_to_render(flow.credentials)
    return redirect(url_for("index"))


@app.route("/preview")
def preview():
    return jsonify({"message": build_message()})


@app.route("/send-now", methods=["POST"])
def send_now():
    send_whatsapp()
    return jsonify({"status": "sent"})

@app.route("/debug-token")
def debug_token():
    token_data = get_token_from_env()
    if not token_data and os.path.exists("data/google_token.json"):
        with open("data/google_token.json") as f:
            token_data = json.load(f)
    return jsonify(token_data or {"error": "no token found"})

@app.route("/debug-render")
def debug_render():
    import requests
    api_key = os.getenv("RENDER_API_KEY")
    service_id = os.getenv("RENDER_SERVICE_ID")
    res = requests.get(
        f"https://api.render.com/v1/services/{service_id}/env-vars",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    return jsonify({"status": res.status_code, "body": res.json()})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
