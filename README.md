# Agenda Bot 📅

A personal automation that sends two daily WhatsApp messages pulled from your Google Calendar:

- **☀️ Morning message** — today's agenda, time-blocked and ready to go
- **🌙 Evening message** — tomorrow's preview so you can plan ahead

Built with Python and Flask. Scheduling handled by cron-job.org. Hosted for free on Render.

---

## Example messages

**Morning:**
```
☀️ Good morning! Tuesday, 17/06
_Busy one today — let's make it count._

Today's agenda:
• 07:00–08:00 — Gym
• 09:30–10:30 — Team standup
• 12:30–13:30 — Lunch with mom
• 15:00–15:30 — Doctor appointment
```

**Evening:**
```
🌙 Tomorrow preview — Wednesday, 18/06
_Heads up: busy day ahead tomorrow._

Tomorrow's agenda:
• 09:00–10:00 — Sprint planning
• 14:00–15:00 — 1:1 with manager
```

---

## What you'll need (all free)

| Service | What for |
|---|---|
| Google Cloud project | Read your Google Calendar |
| Twilio account | Send WhatsApp messages |
| Render account | Host the app 24/7 |
| cron-job.org account | Trigger messages at set times |
| UptimeRobot account | Keep Render awake |

---

## Step 1 — Google Cloud setup

1. Go to https://console.cloud.google.com and create a new project (e.g. "Agenda Bot")
2. Enable the **Google Calendar API**: APIs & Services → Library → search "Google Calendar API" → Enable
3. Create OAuth credentials: APIs & Services → Credentials → Create Credentials → OAuth client ID
   - Application type: **Web application**
   - Authorised redirect URI: `https://YOUR-APP.onrender.com/auth/callback` (fill in after Step 2)
4. Note your **Client ID** and **Client Secret**
5. Under OAuth consent screen → add your Gmail as a **Test user**

---

## Step 2 — Deploy to Render

1. Fork or clone this repo to your GitHub account
2. Go to https://render.com → New → Web Service → connect your repo
3. Settings:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `gunicorn app:app --workers 1`
   - **Instance type:** Free
4. Add these environment variables:

```
GOOGLE_CLIENT_ID        = your Google client ID
GOOGLE_CLIENT_SECRET    = your Google client secret
REDIRECT_URI            = https://YOUR-APP.onrender.com/auth/callback
GOOGLE_TOKEN            = (leave empty — filled automatically after login)
SELECTED_CALENDARS      = []
TWILIO_ACCOUNT_SID      = your Twilio SID
TWILIO_AUTH_TOKEN       = your Twilio auth token
TWILIO_WHATSAPP_FROM    = whatsapp:+14155238886
WHATSAPP_PHONE          = your number e.g. +5511999999999
TIMEZONE                = America/Sao_Paulo
RENDER_API_KEY          = your Render API key (Account Settings → API Keys)
RENDER_SERVICE_ID       = your Render service ID (starts with srv-)
FLASK_SECRET            = any random string
```

5. Deploy and copy your live URL
6. Go back to Google Cloud and add the full callback URL to Authorised redirect URIs

---

## Step 3 — Twilio sandbox setup

1. Create a free account at https://www.twilio.com
2. Go to Messaging → Try it out → Send a WhatsApp message
3. Activate the sandbox: on WhatsApp, send **join `<your-sandbox-word>`** to **+1 415 523 8886**
4. Note your **Account SID** and **Auth Token** from the main dashboard

---

## Step 4 — Connect and configure

1. Open your Render URL in a browser
2. Click **Connect Google Calendar** and authorise your account
3. Tick which calendars to include
4. Enter your WhatsApp number and click Save

---

## Step 5 — Schedule with cron-job.org

1. Create a free account at https://cron-job.org
2. Create two cron jobs:

**Morning message:**
- URL: `https://YOUR-APP.onrender.com/cron/morning`
- Schedule: your preferred morning time
- Timezone: America/Sao_Paulo

**Evening message:**
- URL: `https://YOUR-APP.onrender.com/cron/evening`
- Schedule: your preferred evening time
- Timezone: America/Sao_Paulo

---

## Step 6 — Keep Render awake with UptimeRobot

1. Create a free account at https://uptimerobot.com
2. Add a new HTTP(s) monitor pointing to your Render URL
3. Set interval to 5 minutes

This prevents Render's free tier from sleeping, ensuring cron-job.org calls always get a fast response.

---

## Notes

- The Google token and settings are stored as Render environment variables so they survive restarts
- This app is designed for a single user
- To upgrade from Twilio sandbox to a real WhatsApp number, follow Twilio's approval process (~$1/month)
- The Twilio sandbox disconnects after 72 hours of inactivity — reconnect by sending the join message again
