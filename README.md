# Agenda Bot 📅

Sends you a daily WhatsApp message with a motivational line and your time-blocked Google Calendar agenda.

---

## What you'll need (all free)

| Service | What for |
|---|---|
| Google Cloud project | Read your calendar |
| Twilio account | Send WhatsApp messages |
| Render account | Host the bot 24/7 |

---

## Step 1 — Google Cloud setup

1. Go to https://console.cloud.google.com and create a new project (e.g. "Agenda Bot")
2. Enable the **Google Calendar API**: APIs & Services → Library → search "Google Calendar API" → Enable
3. Create OAuth credentials: APIs & Services → Credentials → Create Credentials → OAuth client ID
   - Application type: **Web application**
   - Authorised redirect URI: `https://YOUR-APP-NAME.onrender.com/auth/callback`
4. Download the credentials — note your **Client ID** and **Client Secret**
5. Under OAuth consent screen, add your Google account as a test user

---

## Step 2 — Twilio sandbox setup

1. Create a free account at https://www.twilio.com
2. Go to Messaging → Try it out → Send a WhatsApp message
3. Follow the instructions to activate the sandbox (you'll send a WhatsApp message to a Twilio number)
4. Note your **Account SID** and **Auth Token** from the dashboard

---

## Step 3 — Deploy to Render

1. Push this folder to a GitHub repository
2. Go to https://render.com → New → Web Service → connect your repo
3. Set these environment variables in Render:

```
TWILIO_ACCOUNT_SID      = your Twilio SID
TWILIO_AUTH_TOKEN       = your Twilio auth token
TWILIO_WHATSAPP_FROM    = whatsapp:+14155238886
GOOGLE_CLIENT_ID        = your Google client ID
GOOGLE_CLIENT_SECRET    = your Google client secret
REDIRECT_URI            = https://YOUR-APP-NAME.onrender.com/auth/callback
TIMEZONE                = America/Sao_Paulo
```

4. Deploy. Render will give you a URL like `https://agenda-bot-xxxx.onrender.com`

---

## Step 4 — Connect and configure

1. Open your Render URL in a browser
2. Click **Connect Google Calendar** and authorise
3. Tick which calendars to include
4. Enter your WhatsApp number (e.g. `+5511999999999`)
5. Set your preferred send time
6. Click **Send now** to test

---

## Example message

```
Hey! Let's start your Monday (26/05) with high energy — looks like a busy day.
Busy day ahead. Prioritise, focus, deliver.

08:00–09:00 — Gym
09:30–10:30 — Team standup
11:00–12:00 — Work on platform tickets
12:30–13:30 — Lunch with mom
15:00–15:30 — Doctor appointment

You've got this 💪
```

---

## Notes

- The `data/` folder stores your settings and Google token. On Render free tier, this resets on each deploy — use a persistent disk or environment variables for production use.
- To upgrade from sandbox to a real WhatsApp number, follow Twilio's approval process (costs ~$1/month).
