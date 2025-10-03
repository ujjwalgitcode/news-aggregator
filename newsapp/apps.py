from django.apps import AppConfig
from apscheduler.schedulers.background import BackgroundScheduler
from scraper.scraper import GenericNewsScraper

def start_scraper_job():
    scraper = GenericNewsScraper()
    scraper.run_all_scrapers()

class NewsappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'newsapp'

    def ready(self):
        if 'runserver' in __import__('sys').argv or 'gunicorn' in __import__('sys').argv:
            scheduler = BackgroundScheduler()
            scheduler.add_job(start_scraper_job, 'interval', hours=1)
            scheduler.start()
