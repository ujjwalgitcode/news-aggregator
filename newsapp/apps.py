from django.apps import AppConfig
from apscheduler.schedulers.background import BackgroundScheduler

scheduler_started = False

def start_scraper_job():
    # Import scraper only when the job runs, after Django is ready
    from scraper.scraper import GenericNewsScraper
    scraper = GenericNewsScraper()
    scraper.run_all_scrapers()

class NewsappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'newsapp'

    def ready(self):
        global scheduler_started
        if not scheduler_started:
            import sys
            if 'runserver' in sys.argv or 'gunicorn' in sys.argv:
                scheduler = BackgroundScheduler()
                scheduler.add_job(start_scraper_job, 'interval', hours=1)
                scheduler.start()
                print("✅ APScheduler started for news scraper (every 1 hour)")
                scheduler_started = True
