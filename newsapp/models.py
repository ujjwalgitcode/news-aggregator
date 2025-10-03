# newsapp/models.py

from django.db import models

class NewsArticle(models.Model):
    source = models.CharField(max_length=100)
    title = models.CharField(max_length=255)
    link = models.URLField(unique=True)
    image = models.URLField(blank=True, null=True)
    author = models.CharField(max_length=100, blank=True, null=True)
    snippet = models.TextField(blank=True, null=True)
    
    # Stores the formatted date string (e.g., "Sep 30, 2024") for display
    date = models.CharField(max_length=50, blank=True, null=True)
    
    # 💡 NEW FIELD: Stores the actual datetime object for sorting and filtering
    published_date = models.DateTimeField(null=True, blank=True)
    
    # When the article was scraped (original field)
    scraped_at = models.DateTimeField(auto_now_add=True) 

    def __str__(self):
        return self.title