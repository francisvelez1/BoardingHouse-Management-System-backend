from models.otp import OtpCode
from datetime import datetime

from models.user import User

async def save_otp(email: str, code: str, expires_at: datetime) -> OtpCode:
    # delete any existing OTPs for this email first
    await OtpCode.find(OtpCode.email == email).delete()

    otp = OtpCode(email=email, code=code, expires_at=expires_at)
    await otp.save()
    return otp

async def find_otp(email: str, code: str):
    return await OtpCode.find_one(
        OtpCode.email == email,
        OtpCode.code  == code,
        OtpCode.used  == False,
    )
async def find_by_email(email: str):
    return await User.find_one(User.email == email)
async def mark_otp_used(otp: OtpCode):
    otp.used = True
    await otp.save()