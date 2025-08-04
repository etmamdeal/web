import smtplib
from email.mime.text import MIMEText
import json
import sys

def run_script(config):
    sender_email = config.get("sender_email")
    sender_password = config.get("sender_password")
    to_email = config.get("to_email")
    subject = config.get("subject")
    message = config.get("message")

    try:
        msg = MIMEText(message, 'plain')
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = to_email

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)

        print("Email sent successfully!")
    except Exception as e:
        print(f"Error sending email: {str(e)}")

if __name__ == "__main__":
    # يستقبل البيانات كـ JSON
    config_json = sys.argv[1]
    config = json.loads(config_json)
    run_script(config)
