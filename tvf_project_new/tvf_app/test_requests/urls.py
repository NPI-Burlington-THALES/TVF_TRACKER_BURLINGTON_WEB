# tvf_app/test_requests/urls.py

from django.urls import path
from. import views # Import views from the current app

app_name = 'test_requests' # Namespace for your app's URLs

urlpatterns = [
    path('list/', views.test_request_list_view, name='list'),
    path('new/', views.test_request_create_view, name='create'),
    path('<int:pk>/', views.test_request_detail_view, name='detail'),
    path('<int:pk>/edit/', views.test_request_update_view, name='update'),
    path('<int:pk>/pdf/', views.test_request_pdf_view, name='pdf'),
    path('dashboard/', views.coach_dashboard, name='coach_dashboard'),
    path('tvf/create/', views.create_tvf_view, name='create_tvf'),
    path('tvf/<int:tvf_id>/npi_update/', views.npi_update_tvf_view, name='npi_update_tvf'),
    path('tvf/<int:tvf_id>/quality_update/', views.quality_update_tvf_view, name='quality_update_tvf'),
    path('tvf/<int:tvf_id>/logistics_update/', views.logistics_update_tvf_view, name='logistics_update_tvf'),
    path('tvf/<int:tvf_id>/reject/', views.reject_tvf_view, name='reject_tvf'),
    path('access_denied/', views.access_denied_view, name='access_denied'),
    path('ajax/get_filtered_projects/', views.get_filtered_projects, name='get_filtered_projects'),
    path('ajax/get_filtered_plastic_codes/', views.get_filtered_plastic_codes, name='get_filtered_plastic_codes'),
    path('ajax/get_filtered_trustport_folders/', views.get_filtered_trustport_folders, name='get_filtered_trustport_folders'),
    path('ajax/get_filtered_dispatch_methods/', views.get_filtered_dispatch_methods, name='get_filtered_dispatch_methods'),
    path('ajax/get_sla_and_calculate_ship_date/', views.get_sla_and_calculate_ship_date, name='get_sla_and_calculate_ship_date'),
]