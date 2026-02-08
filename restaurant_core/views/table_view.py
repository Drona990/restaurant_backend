import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from core.permissions import IsAdminOrSuperuser
from ..models import Table
from ..serializers import TableSerializer
from ..utils import APIResponse, log_error

logger = logging.getLogger(__name__)

class TableViewSet(viewsets.ModelViewSet):
    queryset = Table.objects.filter(is_active=True)
    serializer_class = TableSerializer
    lookup_field = 'id'
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['is_active']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminOrSuperuser()]
        return [AllowAny()]
    
    def create(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            return APIResponse.success(data=serializer.data, message="Table created", status_code=201)
        except Exception as e:
            log_error("TableViewSet.create", "Error", e)
            return APIResponse.error(message="Failed to create table", status_code=500)

    def list(self, request, *args, **kwargs):
        try:
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return APIResponse.success(data=serializer.data)
        except Exception as e:
            return APIResponse.error(message="Failed to retrieve tables", status_code=500)

    @action(detail=False, methods=['get'], url_path='qr/(?P<qr_id>[^/.]+)')
    def get_by_qr(self, request, qr_id=None):
        table = get_object_or_404(Table, qr_id=qr_id, is_active=True)
        serializer = self.get_serializer(table)
        return APIResponse.success(data=serializer.data)