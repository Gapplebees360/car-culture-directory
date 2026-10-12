import os
import re
import json
import datetime
import urllib.request
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Supabase Credentials
SUPABASE_URL = "https://lswnpxeiagureogrlopy.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imxzd25weGVpYWd1cmVvZ3Jsb3B5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTE3NjkwNDcsImV4cCI6MjEwNzM0NTA0N30.yg0B_yyMAgdM692J9s-HevvfaykqZoVV0a0AiS6mZ_s"

# Optional: Set up SMTP secrets in GitHub Secrets (e.g. SMTP_USER, SMTP_PASS)
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASS = os.environ.get('SMTP_PASS', '')

def fetch_supabase_data(endpoint):
    """Utility to query Supabase REST API"""
    try:
        url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
        req = urllib.request.Request(url)
        req.add_header('apikey', SUPABASE_ANON_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_ANON_KEY}')
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"Error fetching from Supabase ({endpoint}): {e}")
        return []

def send_email_alert(to_email, event):
    """Sends HTML email alert to subscriber"""
    if not SMTP_USER or not SMTP_PASS:
        print("SMTP credentials not configured. Skipping email send.")
        return

    subject = f"🚗 New Car Meet Alert: {event['title']} in {event['city']}, {event['state']}"
    
    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background-color: #0B0E14; color: #F3F4F6; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background: #131822; padding: 20px; border-radius: 10px; border: 1px solid #2D3748;">
          <h2 style="color: #FF2A3B; margin-top: 0;">New Automotive Event Announced!</h2>
          <h3 style="color: #FFFFFF;">{event['title']}</h3>
          <p><strong>Location:</strong> {event['venue']}, {event['city']}, {event['state']}</p>
          <p><strong>Date:</strong> {event['date']} | <strong>Category:</strong> {event['category']}</p>
          <p style="color: #9CA3AF;">{event.get('description', '')}</p>
          <hr style="border-color: #2D3748; margin: 20px 0;" />
          <a href="https://usautomeets.com" style="background: #FF2A3B; color: #FFFFFF; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">View on USA Auto Meets</a>
        </div>
      </body>
    </html>
    """

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"USA Auto Meets <{SMTP_USER}>"
    msg['To'] = to_email
    msg.attach(MIMEText(html_body, 'html'))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, to_email, msg.as_string())
            print(f"Email alert sent to {to_email} for event: {event['title']}")
    except Exception as e:
        print(f"Failed to send email to {to_email}: {e}")

def process_daily_notifications():
    """Matches new events in the last 24h with subscribers and dispatches alerts"""
    subscribers = fetch_supabase_data("subscribers")
    if not subscribers:
        print("No subscribers found.")
        return

    # Get events created in the last 24 hours
    yesterday_iso = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).isoformat()
    recent_events = fetch_supabase_data(f"events?created_at=gte.{yesterday_iso}")

    if not recent_events:
        print("No new events added in the last 24 hours.")
        return

    print(f"Processing {len(recent_events)} new events for {len(subscribers)} subscribers...")

    for event in recent_events:
        for sub in subscribers:
            # Match state and city ('ALL' or matching city)
            if sub['state'] == event['state'] and (sub['city'] == 'ALL' or sub['city'].lower() == event['city'].lower()):
                send_email_alert(sub['email'], event)

if __name__ == '__main__':
    process_daily_notifications()
