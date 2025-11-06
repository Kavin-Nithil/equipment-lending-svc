from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Equipment, EquipmentCategory, BorrowRequest

User = get_user_model()


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'first_name', 'last_name',
                  'role', 'phone', 'department']

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name',
                  'role', 'phone', 'department']


class EquipmentCategorySerializer(serializers.ModelSerializer):
    equipment_count = serializers.IntegerField(source='equipment.count', read_only=True)

    class Meta:
        model = EquipmentCategory
        fields = ['id', 'name', 'description', 'equipment_count', 'created_at']


class EquipmentSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    is_available = serializers.BooleanField(read_only=True)

    class Meta:
        model = Equipment
        fields = ['id', 'name', 'category', 'category_name', 'description',
                  'condition', 'total_quantity', 'available_quantity',
                  'serial_number', 'location', 'purchase_date', 'is_active',
                  'is_available', 'created_at', 'updated_at']
        read_only_fields = ['available_quantity']

    def create(self, validated_data):
        validated_data['available_quantity'] = validated_data['total_quantity']
        return super().create(validated_data)


class BorrowRequestSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    equipment_name = serializers.CharField(source='equipment.name', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.get_full_name', read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = BorrowRequest
        fields = ['id', 'user', 'user_name', 'equipment', 'equipment_name',
                  'quantity', 'purpose', 'status', 'requested_date',
                  'borrow_from', 'borrow_until', 'approved_by', 'approved_by_name',
                  'approved_date', 'issued_date', 'returned_date',
                  'rejection_reason', 'notes', 'is_overdue']
        read_only_fields = ['user', 'status', 'requested_date', 'approved_by',
                            'approved_date', 'issued_date', 'returned_date']

    def validate(self, data):
        if data['borrow_until'] <= data['borrow_from']:
            raise serializers.ValidationError("Return date must be after borrow date")

        if data['borrow_from'] < timezone.now():
            raise serializers.ValidationError("Borrow date cannot be in the past")

        equipment = data['equipment']
        if data['quantity'] > equipment.total_quantity:
            raise serializers.ValidationError(
                f"Requested quantity exceeds total quantity ({equipment.total_quantity})"
            )

        return data

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        request = BorrowRequest(**validated_data)

        if not request.check_availability():
            raise serializers.ValidationError(
                "Equipment not available for the requested period"
            )

        request.save()
        return request