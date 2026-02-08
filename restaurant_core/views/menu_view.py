import logging
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from core.permissions import IsAdminOrSuperuser
from ..models import Category, MenuItem
from ..serializers import CategorySerializer, MenuItemSerializer
from ..utils import APIResponse, log_error

logger = logging.getLogger(__name__)

class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    # 🌟 Added 'station' in search and filter
    search_fields = ['name']
    filterset_fields = ['station', 'is_active']

    def get_queryset(self):
        return Category.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminOrSuperuser()]
        return [AllowAny()]


class MenuItemViewSet(viewsets.ModelViewSet):
    serializer_class = MenuItemSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    # 🌟 Operational Filters: Category, Availability, and Ready-to-Serve logic
    filterset_fields = ['category', 'is_available', 'is_ready_to_serve', 'category__station']
    search_fields = ['name', 'category__name']
    ordering_fields = ['price', 'created_at', 'prep_time']

    def get_queryset(self):
        # 🌟 Optimization: select_related use karein taaki category data ke liye extra queries na hon
        return MenuItem.objects.select_related('category').all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminOrSuperuser()]
        return [AllowAny()]

    @action(detail=False, methods=['get'])
    def ready_to_serve(self, request):
        """Custom endpoint to quickly get all instant items (like Cold Drinks)"""
        ready_items = self.get_queryset().filter(is_ready_to_serve=True, is_available=True)
        serializer = self.get_serializer(ready_items, many=True)
        return APIResponse.success(data=serializer.data)