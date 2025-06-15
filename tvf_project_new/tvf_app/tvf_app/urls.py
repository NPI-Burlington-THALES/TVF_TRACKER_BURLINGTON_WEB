# tvf_app/tvf_app/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView # Import TemplateView
from test_requests.views import RegisterView

urlpatterns = [
	path('admin/', admin.site.urls),
    path('tvf/', include('test_requests.urls', namespace='test_requests')), # Ensure it's included once with a namespace
	path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('accounts/login/', auth_views.LoginView.as_view(), name='login'),  # Optional
    path('', TemplateView.as_view(template_name='landing_page.html'), name='landing_page'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='landing_page'), name='logout'),
    path('register/', RegisterView.as_view(), name='register'), # <--- Use the new view
]

# Serve static and media files during development (ONLY FOR DEVELOPMENT!)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)