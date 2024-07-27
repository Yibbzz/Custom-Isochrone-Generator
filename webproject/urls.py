from django.urls import include, path
from myapp import views
from django.contrib.auth import views as auth_views
from django.contrib import admin

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.login_view, name='login'),  # Keep the root login view
    path('accounts/login/', views.login_view, name='login'),
    path('captcha/', include('captcha.urls')),
    path('register/', views.register, name='register'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/'), name='logout'),
    path('geojson/', views.geojson_view, name='geojson_view'),
    path('get-geodata/', views.integrate_data_and_run_docker, name='get_geodata'),
    path('make-isochrone/', views.create_isochrone, name='make_isochrone'),
    path('export-isochrones/', views.export_isochrones, name='export_isochrones'),
    path('container-button-activate/', views.container_button_activate, name='container_button_activate'),
    path('container-status-update/', views.container_status_update, name='container_status_update'),
    path('how-to/', views.how_to_view, name='how_to'),
]
