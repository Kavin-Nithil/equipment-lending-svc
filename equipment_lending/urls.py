from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EquipmentViewSet, EquipmentCategoryViewSet, BorrowRequestViewSet, UserViewSet

router = DefaultRouter()
router.register('users', UserViewSet, basename='user')
router.register('categories', EquipmentCategoryViewSet, basename='category')
router.register('equipment', EquipmentViewSet, basename='equipment')
router.register('requests', BorrowRequestViewSet, basename='request')

urlpatterns = [
    path('', include(router.urls)),
]