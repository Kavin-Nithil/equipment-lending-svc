from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Equipment, EquipmentCategory, BorrowRequest

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'role', 'first_name', 'last_name']
    list_filter = ['role', 'is_staff', 'is_active']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Additional Info', {'fields': ('role', 'phone', 'department')}),
    )

@admin.register(EquipmentCategory)
class EquipmentCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'created_at']
    search_fields = ['name']

@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'condition', 'total_quantity',
                    'available_quantity', 'is_active']
    list_filter = ['category', 'condition', 'is_active']
    search_fields = ['name', 'serial_number']

@admin.register(BorrowRequest)
class BorrowRequestAdmin(admin.ModelAdmin):
    list_display = ['user', 'equipment', 'quantity', 'status',
                    'borrow_from', 'borrow_until']
    list_filter = ['status', 'requested_date']
    search_fields = ['user__username', 'equipment__name']