from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from ..db.session import SessionLocal
from ..services.notification_service import send_pending_notifications


def start_scheduler():
    sched = BackgroundScheduler(timezone="Europe/Paris")

    def job():
        db = SessionLocal()
        try:
            send_pending_notifications(db)
        finally:
            db.close()

    sched.add_job(job, CronTrigger(hour=7, minute=0))
    sched.start()
    return sched

