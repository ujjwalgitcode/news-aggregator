import json
import os
import sys
import re
import time
from pathlib import Path
from urllib.parse import urljoin
from datetime import datetime, timedelta
import dateutil.parser
from dateutil.relativedelta import relativedelta
from django.utils import timezone # Import for timezone-aware operations

# --- SETUP DJANGO (Keep as is) ---
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'newsproject.settings')

import django
django.setup()

from newsapp.models import NewsArticle
from playwright.sync_api import sync_playwright

# --- DATE PARSER (Keep as is - Logic is correct) ---
class DateParser:
    @staticmethod
    def parse_date(date_text):
        """Parse various date formats and return datetime object, simplified."""
        if not date_text or not date_text.strip():
            return None
        
        original_text = date_text.strip()
        
        # 1. Clean the date text of boilerplate and noise
        patterns_to_remove = [
            r'BY\s+[\w\s]+\s*', 
            r'by\s+[\w\s]+\s*', 
            r'Posted\s+on\s*', r'Published\s+on\s*', r'Updated\s+on\s*', 
            r'•', r'\|\s*', r'\s-\s',
        ]
        cleaned_text = original_text
        for pattern in patterns_to_remove:
            cleaned_text = re.sub(pattern, ' ', cleaned_text, flags=re.IGNORECASE).strip()
        
        # Replace common time separators with spaces
        cleaned_text = re.sub(r'[,|•]', ' ', cleaned_text).strip()
        
        # 2. Handle Relative Times, Today, and Yesterday
        now = timezone.now() 
        
        # Handle relative times (e.g., 2 hours ago, 1 day ago)
        if 'ago' in cleaned_text.lower():
            return DateParser.parse_relative_time(cleaned_text)
        
        # Handle "today" and "yesterday"
        if 'today' in cleaned_text.lower():
            return now.replace(hour=12, minute=0, second=0, microsecond=0)
        elif 'yesterday' in cleaned_text.lower():
            return (now - timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
        
        # 3. Use dateutil for robust absolute date parsing
        try:
            parsed_date = dateutil.parser.parse(cleaned_text, fuzzy=True)
            
            if parsed_date.tzinfo is None or parsed_date.tzinfo.utcoffset(parsed_date) is None:
                parsed_date = timezone.make_aware(parsed_date, timezone.get_current_timezone())

            if parsed_date.date() == now.date():
                return parsed_date
            return parsed_date.replace(hour=12, minute=0, second=0, microsecond=0)
                
        except (ValueError, dateutil.parser.ParserError):
            try:
                return DateParser.manual_parse(cleaned_text)
            except Exception:
                return None

    @staticmethod
    def parse_relative_time(relative_text):
        """Parse relative time like '2 hours ago', '1 day ago'"""
        patterns = [
            (r'(\d+)\s+hour', 'hours'), (r'(\d+)\s+hr', 'hours'),
            (r'(\d+)\s+minute', 'minutes'), (r'(\d+)\s+min', 'minutes'),
            (r'(\d+)\s+day', 'days'), (r'(\d+)\s+week', 'weeks'),
            (r'(\d+)\s+month', 'months'), (r'(\d+)\s+year', 'years'),
        ]
        
        for pattern, unit in patterns:
            match = re.search(pattern, relative_text, re.IGNORECASE)
            if match:
                number = int(match.group(1))
                now = timezone.now()
                
                if unit == 'hours': return now - timedelta(hours=number)
                elif unit == 'minutes': return now - timedelta(minutes=number)
                elif unit == 'days': return now - timedelta(days=number)
                elif unit == 'weeks': return now - timedelta(weeks=number)
                elif unit == 'months': return now - relativedelta(months=number)
                elif unit == 'years': return now - relativedelta(years=number)
        
        return None
    
    @staticmethod
    def manual_parse(date_text):
        """Manual parsing fallback for specific formats (kept from original)"""
        date_text = date_text.strip()
        
        # Month DD, YYYY (Sep 30, 2024)
        month_match = re.match(r'([A-Za-z]{3,9})\s+(\d{1,2}),\s+(\d{4})', date_text)
        if month_match:
            month_str, day, year = month_match.groups()
            month_dict = {
                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
                'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
                'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
            }
            month = month_dict.get(month_str.lower(), 1)
            naive_dt = datetime(int(year), month, int(day), 12, 0, 0)
            return timezone.make_aware(naive_dt, timezone.get_current_timezone())
        
        # DD/MM/YYYY or MM/DD/YYYY
        slash_match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', date_text)
        if slash_match:
            part1, part2, year = slash_match.groups()
            try:
                naive_dt = datetime(int(year), int(part1), int(part2), 12, 0, 0)
            except ValueError:
                naive_dt = datetime(int(year), int(part2), int(part1), 12, 0, 0)
            
            return timezone.make_aware(naive_dt, timezone.get_current_timezone())
        
        return None
    
    @staticmethod
    def format_date_for_display(dt):
        """Format datetime for consistent display"""
        if not dt:
            return "N/A"
        return dt.strftime('%b %d, %Y') 

# --- GENERIC NEWS SCRAPER ---
class GenericNewsScraper:
    def __init__(self, config_dir="config"):
        self.config_dir = os.path.join(os.path.dirname(__file__), config_dir)
        self.date_parser = DateParser()
        self.existing_links = self.get_existing_links()
        
        # Using 25 hours to avoid edge-case filtering with time zones
        self.cutoff_time = timezone.now() - timedelta(hours=25) 
    
    def get_existing_links(self):
        """Get all existing article links from database to avoid duplicates"""
        print("🔍 Checking existing articles in database...")
        existing_links = set(NewsArticle.objects.values_list('link', flat=True))
        print(f"📚 Found {len(existing_links)} existing articles in database")
        return existing_links
    
    def get_all_configs(self):
        """Get all JSON config files from config directory (kept as is)"""
        config_files = []
        try:
            for file in os.listdir(self.config_dir):
                if file.endswith('.json'):
                    config_files.append(os.path.join(self.config_dir, file))
            print(f"📁 Found {len(config_files)} config files")
            return config_files
        except FileNotFoundError:
            print(f"❌ Config directory not found: {self.config_dir}")
            return []
    
    def load_config(self, config_file):
        """Load and validate config file (kept as is)"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            required_fields = ['base_url', 'article']
            for field in required_fields:
                if field not in config:
                    print(f"❌ Missing required field '{field}' in {os.path.basename(config_file)}")
                    return None
            
            site_name = config.get('site', config.get('source_name', 'Unknown'))
            print(f"✅ Loaded config: {site_name}")
            return config
            
        except Exception as e:
            print(f"❌ Error loading config {config_file}: {e}")
            return None
        
    def scrape_website(self, config):
        """Scrape a single website and filter by last 24 hours"""
        site_name = config.get('site', config.get('source_name', 'Unknown'))
        print(f"\n🎯 Scraping {site_name}... (Filtering by published date > 24 hours ago)")
        
        articles = []
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
            context = browser.new_context(viewport={'width': 1920, 'height': 1080}, java_script_enabled=True)
            page = context.new_page()
            
            try:
                print(f"   🌐 Navigating to {config['base_url']}...")
                page.goto(config['base_url'], wait_until='domcontentloaded', timeout=45000)
                
                print("   ⏳ Waiting for page content...")
                self.wait_for_content_load(page, config)
                
                selectors = config['article']
                article_elements = page.query_selector_all(selectors['container'])
                print(f"   🔗 Found {len(article_elements)} potential article containers")
                
                new_articles_count = 0
                for i, element in enumerate(article_elements[:config.get('limit', 20)]):
                    try:
                        article_data = self.extract_article_data(element, page, config)
                        
                        # --- CORE FILTERING LOGIC ---
                        link = article_data.get('link')
                        is_valid = self.validate_article(article_data)
                        is_new_link = link not in self.existing_links
                        is_recent = article_data.get('published_date') and \
                                    article_data['published_date'] >= self.cutoff_time

                        if is_valid and is_new_link and is_recent:
                            articles.append(article_data)
                            new_articles_count += 1
                            date_display = self.date_parser.format_date_for_display(article_data.get('published_date'))
                            time_diff = timezone.now() - article_data['published_date']
                            print(f"     ✅ Found new, recent article ({time_diff.total_seconds()//3600:.0f}hrs ago): {article_data['title'][:60]}... ({date_display})")
                        
                        # 💡 NEW DEBUGGING LOGIC
                        elif not is_valid:
                            # This is the most likely culprit: missing link or title
                            print(f"     ❌ Filtered (Invalid/Missing Data): Title: {article_data.get('title', 'N/A')[:30]}... | Link: {link}")
                        
                        elif not is_new_link:
                            # 💡 REQUIRED: Print if link already exists in DB
                            print(f"     ⏭️ Skipped (Already in DB): {article_data.get('title', 'N/A')[:50]}...")
                        
                        elif not is_recent:
                            # Too old (Shouldn't happen with 25hr window, but keeps logic clean)
                            time_diff = timezone.now() - article_data['published_date']
                            # print(f"     ⏭️ Skipped (Too Old, {time_diff.total_seconds()//3600:.1f}hrs ago): {article_data['title'][:50]}...")
                            pass
                            
                    except Exception as e:
                        # Log inner exception for deeper debugging if necessary
                        # print(f"     ⚠️ Extraction/Filtering Error: {e}")
                        continue 
                            
            except Exception as e:
                print(f"❌ Error scraping {site_name}: {e}")
            finally:
                browser.close()
        
        return articles
    
    def wait_for_content_load(self, page, config):
        """Wait for all dynamic content to load, prioritizing the article container."""
        selectors = config['article']
        try:
            page.wait_for_selector(selectors['container'], timeout=15000) 
            page.wait_for_load_state('networkidle', timeout=5000)
            time.sleep(1) 
        except Exception: 
            print("   ⚠️ Load timeout or container not found, continuing...")
    
    def extract_article_data(self, element, page, config):
        """Extract article data and includes debug output for date."""
        article_data = {}
        selectors = config['article']
        base_url = config['base_url']
        site_name = config.get('site', 'Unknown')

        try:
            # Extract Link and Title (essential fields)
            link_elem = element.query_selector(selectors.get('link', ''))
            title_elem = element.query_selector(selectors.get('title', ''))
            
            link = link_elem.get_attribute('href') if link_elem else None
            article_data['link'] = urljoin(base_url, link) if link else None
            article_data['title'] = title_elem.text_content().strip() if title_elem else None
            
            # --- DATE EXTRACTION & DEBUG (Kept from last successful iteration) ---
            raw_date_text = None
            date_elem = element.query_selector(selectors.get('date', ''))
            
            if date_elem:
                raw_date_text = date_elem.text_content().strip()
                parsed_date = self.date_parser.parse_date(raw_date_text)
                
                if parsed_date:
                    article_data['published_date'] = parsed_date
                    article_data['date'] = self.date_parser.format_date_for_display(parsed_date)
                    print(f"     🟢 DEBUG: Date found/parsed for {site_name}: '{raw_date_text}' -> {parsed_date}") 
                else:
                    print(f"     🟡 DEBUG: Date PARSE FAILED for {site_name}. Raw text: '{raw_date_text}'")
                    article_data['published_date'] = None
                    article_data['date'] = None
            else:
                print(f"     🔴 DEBUG: Date SELECTOR FAILED for {site_name}. Selector: {selectors.get('date', 'N/A')}")
                article_data['published_date'] = None
                article_data['date'] = None
            # --- END DATE DEBUG ---
            
            # Extract other fields (optional)
            image_elem = element.query_selector(selectors.get('image', ''))
            image_src = image_elem.get_attribute('src') if image_elem else None
            article_data['image'] = urljoin(base_url, image_src) if image_src else None
            
            author_elem = element.query_selector(selectors.get('author', ''))
            article_data['author'] = author_elem.text_content().strip() if author_elem else None
            
            snippet_elem = element.query_selector(selectors.get('snippet', ''))
            article_data['snippet'] = snippet_elem.text_content().strip() if snippet_elem else None
            
            article_data['source'] = site_name
            
        except Exception:
            pass
        
        return article_data
    
    def validate_article(self, article_data):
        """Validate if article has required fields (title, link, and link format)"""
        return (article_data.get('title') and 
                article_data.get('link') and 
                len(article_data['title']) > 10 and
                article_data['link'].startswith('http'))
    
    def save_articles(self, articles):
        """Save articles to database"""
        saved_count = 0
        for article in articles:
            try:
                # Double-check if article already exists (just in case)
                if NewsArticle.objects.filter(link=article['link']).exists():
                    print(f"⏭️ Skipped (duplicate, re-check): {article['title'][:50]}...")
                    continue
                
                # Create new article
                NewsArticle.objects.create(
                    source=article['source'],
                    title=article['title'],
                    link=article['link'],
                    image=article.get('image'),
                    author=article.get('author'),
                    date=article.get('date'), 
                    snippet=article.get('snippet'),
                    published_date=article.get('published_date'), 
                )
                saved_count += 1
                date_display = self.date_parser.format_date_for_display(article.get('published_date'))
                print(f"💾 Saved: {article['title'][:50]}... ({date_display})")
                
                # Add to existing links to avoid duplicates in current session
                self.existing_links.add(article['link'])
                
            except Exception as e:
                print(f"❌ Error saving article: {e}")
        
        return saved_count
    
    def run_all_scrapers(self):
        """Run all scrapers from config files (kept as is)"""
        config_files = self.get_all_configs()
        all_articles = []
        saved_count = 0
        
        for config_file in config_files:
            config = self.load_config(config_file)
            if config:
                articles = self.scrape_website(config)
                all_articles.extend(articles)
                print(f"📊 {config.get('site', 'Unknown')}: {len(articles)} new articles found in last 24 hours\n")
        
        if all_articles:
            saved_count = self.save_articles(all_articles)
            print(f"\n🎉 SUCCESS: Saved {saved_count} new articles out of {len(all_articles)} found!")
        else:
            print("✅ No new articles found to save")
        
        return len(all_articles), saved_count

def main():
    """Main function to run the generic scraper"""
    print("🚀 Starting **24-Hour Filtered** News Scraper...")
    scraper = GenericNewsScraper()
    total_found, total_saved = scraper.run_all_scrapers()
    print(f"\n📈 Final Results: {total_saved}/{total_found} new and recent articles saved successfully!")

if __name__ == '__main__':
    main()
