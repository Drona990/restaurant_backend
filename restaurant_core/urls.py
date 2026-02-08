from django.urls import path
from restaurant_core.views.claim_table_view import ClaimTableView, MyTablesView
from restaurant_core.views.discount_view import DiscountViewSet
from restaurant_core.views.live_updates_view import AdminLiveDashboardView, CompleteTicketView, InitializeSessionView, OrderTrackingView, StationKDSView, SubmitOrderView, UpdateItemStatusView, WaiterActionView
from restaurant_core.views.menu_view import CategoryViewSet, MenuItemViewSet
from restaurant_core.views.order_view import GenerateBillView, OrderHistoryView, OrderListView, PlaceOrderView
from restaurant_core.views.report_analytic_view import AdvancedAnalyticsView, AnalyticsView
from restaurant_core.views.table_view import TableViewSet

urlpatterns = [
    # --- Tables Endpoints ---
    path('tables/', TableViewSet.as_view({
        'get': 'list', 
        'post': 'create'
    }), name='table-list'),
    
    path('tables/<int:id>/', TableViewSet.as_view({
        'get': 'retrieve', 
        'put': 'update', 
        'patch': 'partial_update', 
        'delete': 'destroy'
    }), name='table-detail'),

    # Custom action for QR lookup
    path('tables/qr/<str:qr_id>/', TableViewSet.as_view({
        'get': 'get_by_qr'
    }), name='table-qr-lookup'),
    
    # --- Categories Endpoints ---
    path('categories/', CategoryViewSet.as_view({
        'get': 'list', 
        'post': 'create'
    }), name='category-list'),
    
    path('categories/<int:pk>/', CategoryViewSet.as_view({
        'get': 'retrieve', 
        'put': 'update', 
        'patch': 'partial_update', 
        'delete': 'destroy'
    }), name='category-detail'),
    
    # --- Menu Items Endpoints ---
    path('menu-items/', MenuItemViewSet.as_view({
        'get': 'list', 
        'post': 'create'
    }), name='menuitem-list'),
    
    path('menu-items/<int:pk>/', MenuItemViewSet.as_view({
        'get': 'retrieve', 
        'put': 'update', 
        'patch': 'partial_update', 
        'delete': 'destroy'
    }), name='menuitem-detail'),

    # Custom action for Menu by Category
    path('menu-items/category/<int:category_id>/', MenuItemViewSet.as_view({
        'get': 'by_category'
    }), name='menuitem-by-category'),


   path('discounts/', DiscountViewSet.as_view({
        'get': 'list', 
        'post': 'create'
    }), name='discount-list'),

    path('discounts/<int:pk>/', DiscountViewSet.as_view({
        'get': 'retrieve', 
        'put': 'update', 
        'patch': 'partial_update', 
        'delete': 'destroy'
    }), name='discount-detail'),

   
    path('discounts/apply_discount/', DiscountViewSet.as_view({
        'post': 'apply_discount'
    }), name='apply-discount'),

   
    path('discounts/generate_code/', DiscountViewSet.as_view({
        'get': 'generate_code'
    }), name='generate-coupon-code'),

    # --- Order Endpoints ---
    path('orders/my_tables/', MyTablesView.as_view(), name='my-tables'),
    path('order/init-session/', InitializeSessionView.as_view()),
    path('orders/submit/', SubmitOrderView.as_view()),
    path('orders/status/', OrderTrackingView.as_view()), #For customer only

    path('table/claim/<str:identifier>/', ClaimTableView.as_view(), name='claim-table'),
    path('reports/analytics/', AnalyticsView.as_view(), name='analytics'),
    path('reports/advance/analytics/', AdvancedAnalyticsView.as_view(), name='advance-analytics'),

    path('orders/place/', PlaceOrderView.as_view(), name='place-order'),
    path('orders/history/', OrderHistoryView.as_view(), name='place-order'),
    path('orders/', OrderListView.as_view(), name='order-detals'),

    # ✋ Waiter Actions (Approve/Serve)
    path('orders/waiter-action/', WaiterActionView.as_view(), name='waiter_action'),

    # 🍳 KDS (Chef/Barman) Display Data
    path('orders/kds/', StationKDSView.as_view(), name='station_kds'),

    # 🔄 Status Updates (Cooking/Ready)
    path('orders/update-item-status/', UpdateItemStatusView.as_view(), name='update_item_status'),

    # 🏁 Bump Full Ticket
    path('orders/complete-ticket/', CompleteTicketView.as_view(), name='complete_ticket'),

    # 🗺️ Manager/Admin Live Map
    path('admin/floor-map/', AdminLiveDashboardView.as_view(), name='admin_floor_map'),
    path('orders/generate-bill/', GenerateBillView.as_view(), name='generate_bill'),

]