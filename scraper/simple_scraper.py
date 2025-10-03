import json
import os
import sys
from pathlib import Path
from urllib.parse import urljoin

# Setup Django first
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'newsproject.settings')

import django
django.setup()

from newsapp.models import NewsArticle
from playwright.sync_api import sync_playwright

NewsArticle.objects.all().delete()
print("🗑️ Database cleared. Starting fresh...")

def scrape_website(config_file):
    """Simple synchronous scraper using Playwright"""
    
    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    site_name = config.get('site', config.get('source_name', 'Unknown'))
    print(f"Scraping {site_name}...")
    
    articles = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            # Go to website
            page.goto(config['base_url'], wait_until='networkidle')
            
            # Wait for articles to load
            page.wait_for_selector(config['article']['container'], timeout=10000)
            
            # Get all article containers
            article_elements = page.query_selector_all(config['article']['container'])
            print(f"Found {len(article_elements)} articles")
            
            for element in article_elements[:15]:
                try:
                    article_data = {}
                    
                    # Extract title
                    title_elem = element.query_selector(config['article']['title'])
                    if title_elem:
                        article_data['title'] = title_elem.text_content().strip()
                    
                    # Extract link
                    link_elem = element.query_selector(config['article']['link'])
                    if link_elem:
                        link = link_elem.get_attribute('href')
                        article_data['link'] = urljoin(config['base_url'], link) if link else None
                    
                    # Extract image
                    image_elem = element.query_selector(config['article']['image'])
                    if image_elem:
                        image_src = image_elem.get_attribute('src')
                        article_data['image'] = urljoin(config['base_url'], image_src) if image_src else None
                    
                    # Extract author
                    author_elem = element.query_selector(config['article']['author'])
                    if author_elem:
                        article_data['author'] = author_elem.text_content().strip()
                    
                    # Extract date
                    date_elem = element.query_selector(config['article']['date'])
                    if date_elem:
                        article_data['date'] = date_elem.text_content().strip()
                    
                    # Extract snippet
                    snippet_elem = element.query_selector(config['article']['snippet'])
                    if snippet_elem:
                        article_data['snippet'] = snippet_elem.text_content().strip()
                    
                    # Add source
                    article_data['source'] = site_name
                    
                    # Validate article
                    if (article_data.get('title') and 
                        article_data.get('link') and 
                        len(article_data['title']) > 10):
                        articles.append(article_data)
                        print(f"✓ {article_data['title'][:60]}...")
                    
                except Exception as e:
                    print(f"  Error processing article: {e}")
                    continue
                    
        except Exception as e:
            print(f"Error scraping {site_name}: {e}")
        finally:
            browser.close()
    
    return articles

def save_articles(articles):
    """Save articles to database"""
    saved_count = 0
    for article in articles:
        try:
            # Check if article already exists
            if NewsArticle.objects.filter(link=article['link']).exists():
                print(f"⏭️ Skipped (duplicate): {article['title'][:50]}...")
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
            )
            saved_count += 1
            print(f"✅ Saved: {article['title'][:50]}...")
            
        except Exception as e:
            print(f"❌ Error saving article: {e}")
    
    return saved_count

def main():
    """Main function"""
    config_dir = os.path.join(os.path.dirname(__file__), 'config')
    all_articles = []
    
    # Scrape Lagatar
    lagatar_config = os.path.join(config_dir, 'lagatar.json')
    if os.path.exists(lagatar_config):
        articles = scrape_website(lagatar_config)
        all_articles.extend(articles)
        print(f"Found {len(articles)} articles from Lagatar\n")
    
    # Scrape TheFollowUp
    thefollowup_config = os.path.join(config_dir, 'thefollowup.json')
    if os.path.exists(thefollowup_config):
        articles = scrape_website(thefollowup_config)
        all_articles.extend(articles)
        print(f"Found {len(articles)} articles from TheFollowUp\n")
    
    print(f"Total articles found: {len(all_articles)}")
    
    # Save to database
    if all_articles:
        saved_count = save_articles(all_articles)
        print(f"\n🎉 Successfully saved {saved_count} new articles to database!")
    else:
        print("No articles to save")

if __name__ == '__main__':
    main()