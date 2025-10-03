from django.shortcuts import render
from django.utils import timezone
from datetime import timedelta
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger # New imports
from .models import NewsArticle # Assuming NewsArticle is imported correctly

def news_list(request):
    """
    Fetches news articles published in the last 24 hours,
    orders them by date, and applies pagination (50 articles per page).
    """
    # Define the cutoff time (24 hours ago)
    twenty_four_hours_ago = timezone.now() - timedelta(hours=24)
    
    # 1. Get the filtered and ordered queryset
    # Filter by published_date in the last 24 hours (>= cutoff time)
    # Order by published_date in DESCENDING order (latest first)
    article_list = NewsArticle.objects.filter(
        published_date__gte=twenty_four_hours_ago
    ).order_by('-published_date')
    
    # 2. Set up Paginator, 50 articles per page
    paginator = Paginator(article_list, 50) 
    
    # 3. Get the current page number from the request URL
    page_number = request.GET.get('page')
    
    try:
        # Get the Page object for the requested page number
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        page_obj = paginator.get_page(1)
    except EmptyPage:
        # If page is out of range (e.g., 9999), deliver last page of results.
        page_obj = paginator.get_page(paginator.num_pages)
        
    context = {
        'page_obj': page_obj, # Pass the Page object to the template
    }
    return render(request, 'news_list.html', context)
