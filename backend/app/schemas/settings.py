from pydantic import BaseModel, EmailStr
from typing import List


class NotificationSettings(BaseModel):
    recipients: List[EmailStr] = []
    reminders_active: bool = True
    remind_days: list[int] = [15, 10, 5]
    alert_no_auto_renewal: bool = False

