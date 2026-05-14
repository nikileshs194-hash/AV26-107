import os
import requests as _requests

TWOFACTOR_KEY = os.getenv("TWOFACTOR_KEY", "")


def send_otp_sms(phone: str, otp: str) -> bool:
    """
    Send OTP via 2Factor.in (free, India). Falls back to console log.
    phone format: "+919876543210" or "9876543210"
    """
    # Strip to 10-digit India number
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    digits = digits[-10:]

    # Always print OTP to console
    print(f"\n{'='*40}")
    print(f"  OTP for {phone} ({digits}): {otp}")
    print(f"{'='*40}\n")

    if not TWOFACTOR_KEY:
        return True

    try:
        resp = _requests.get(
            f"https://2factor.in/API/V1/{TWOFACTOR_KEY}/SMS/{digits}/{otp}/OTP1",
            timeout=10,
        )
        result = resp.json()
        print(f"[SMS] 2Factor response: {result}")
        return result.get("Status") == "Success"
    except Exception as e:
        print(f"[SMS] Error: {e}")
        return False
