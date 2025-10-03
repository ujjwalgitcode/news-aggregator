import os
import asyncio
import sys
from pathlib import Path
from django.core.management.base import BaseCommand
from django.utils import timezone
from newsapp.models import NewsArticle

# Add the project root to Python path to import scraper module
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from scraper.scraper import scrape_all_news
except ImportError as e:
    print(f"Import error: {e}")
    print(f"Python path: {sys.path}")
    raise

class Command(BaseCommand):
    help = 'Scrape news articles from configured websites'

    def handle(self, *args, **options):
        self.stdout.write('Starting news scraping...')
        
        try:
            # Run the async scraper
            articles = asyncio.run(scrape_all_news())
            
            saved_count = 0
            for article_data in articles:
                try:
                    # Create or update article
                    obj, created = NewsArticle.objects.get_or_create(
                        link=article_data['link'],
                        defaults={
                            'source': article_data.get('source', 'Unknown'),
                            'title': article_data['title'],
                            'image': article_data.get('image'),
                            'author': article_data.get('author'),
                            'date': article_data.get('date'),
                            'snippet': article_data.get('snippet'),
                        }
                    )
                    if created:
                        saved_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(f'Added: {article_data["title"][:50]}...')
                        )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"Error saving article: {str(e)}")
                    )
                    continue
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully scraped and saved {saved_count} new articles from {len(articles)} found articles'
                )
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Scraping failed: {str(e)}')
            )
            import traceback
            traceback.print_exc()