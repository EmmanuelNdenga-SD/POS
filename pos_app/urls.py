from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Products (Staff & Admin)
    path('products/', views.product_list, name='product_list'),
    path('products/add/', views.product_create, name='product_create'),
    path('products/<int:pk>/edit/', views.product_update, name='product_update'),
    path('products/<int:pk>/delete/', views.product_delete, name='product_delete'),
    
    # Sales (Staff & Admin)
    path('sales/', views.sale_list, name='sale_list'),
    path('sales/add/', views.sale_create, name='sale_create'),
    path('sales/<int:pk>/', views.sale_detail, name='sale_detail'),
    path('sales/<int:pk>/delete/', views.sale_delete, name='sale_delete'),
    
    # Reports (Staff & Admin)
    path('reports/daily/', views.daily_report, name='daily_report'),
    path('reports/monthly/', views.monthly_report, name='monthly_report'),
    
    # Categories (Admin only)
    path('categories/', views.category_list, name='category_list'),
    path('categories/add/', views.category_create, name='category_create'),
    path('categories/<int:pk>/delete/', views.category_delete, name='category_delete'),
    
    # Staff-only URLs
    path('staff/login/', views.staff_login, name='staff_login'),
    path('staff/dashboard/', views.staff_dashboard, name='staff_dashboard'),
    path('staff/sale/', views.staff_make_sale, name='staff_make_sale'),
    path('staff/restock/<int:product_id>/', views.staff_restock, name='staff_restock'),
    
    # Pending Deletions (Admin only)
    path('pending-deletions/', views.pending_deletions, name='pending_deletions'),
    
    # ===== Authentication (Login/Logout) =====
    # Use staff_login view for login (renders staff_login.html)
    path('login/', views.staff_login, name='login'),
    # Logout - uses Django's built-in LogoutView
    path('logout/', auth_views.LogoutView.as_view(next_page='/login/'), name='logout'),
]