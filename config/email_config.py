from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic_settings import BaseSettings

class MailSettings(BaseSettings):
    mail_username: str
    mail_password: str
    mail_from:     str

    model_config = {
        "env_file": ".env",
        "extra": "ignore",
    }

def get_mail_config() -> ConnectionConfig:
    settings = MailSettings()
    return ConnectionConfig(
        MAIL_USERNAME   = settings.mail_username,
        MAIL_PASSWORD   = settings.mail_password,
        MAIL_FROM       = settings.mail_from,
        MAIL_PORT       = 587,
        MAIL_SERVER     = "smtp.gmail.com",
        MAIL_STARTTLS   = True,
        MAIL_SSL_TLS    = False,
        USE_CREDENTIALS = True,
    )

async def send_otp_email(email: str, otp: str):
    config = get_mail_config()
    fm = FastMail(config)

    message = MessageSchema(
        subject    = "ResidEase — Your Password Reset Code",
        recipients = [email],
        body       = f"""
            <h2>Password Reset Request</h2>
            <p>Your OTP code is:</p>
            <h1 style="letter-spacing: 8px; color: #2563eb;">{otp}</h1>
            <p>This code expires in <strong>10 minutes</strong>.</p>
            <p>If you did not request this, ignore this email.</p>
        """,
        subtype = MessageType.html,
    )

    await fm.send_message(message)