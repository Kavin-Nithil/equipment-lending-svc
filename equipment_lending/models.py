from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.utils import timezone


class User(AbstractUser):
    """Extended user model with roles"""
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('staff', 'Staff'),
        ('admin', 'Admin'),
    ]
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='student')
    phone = models.CharField(max_length=15, blank=True)
    department = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = 'users'

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class EquipmentCategory(models.Model):
    """Categories for equipment classification"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'equipment_categories'
        verbose_name_plural = 'Equipment Categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class Equipment(models.Model):
    """Equipment items available for lending"""
    CONDITION_CHOICES = [
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
        ('maintenance', 'Under Maintenance'),
    ]

    name = models.CharField(max_length=200)
    category = models.ForeignKey(EquipmentCategory, on_delete=models.PROTECT, related_name='equipment')
    description = models.TextField(blank=True)
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='good')
    total_quantity = models.IntegerField(validators=[MinValueValidator(1)])
    available_quantity = models.IntegerField(validators=[MinValueValidator(0)])
    serial_number = models.CharField(max_length=100, unique=True, blank=True, null=True)
    location = models.CharField(max_length=200, blank=True)
    purchase_date = models.DateField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'equipment'
        ordering = ['name']
        indexes = [
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['available_quantity']),
        ]

    def __str__(self):
        return f"{self.name} ({self.available_quantity}/{self.total_quantity})"

    @property
    def is_available(self):
        return self.available_quantity > 0 and self.is_active

    def save(self, *args, **kwargs):
        if self.available_quantity > self.total_quantity:
            self.available_quantity = self.total_quantity
        super().save(*args, **kwargs)


class BorrowRequest(models.Model):
    """Borrowing requests made by users"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('issued', 'Issued'),
        ('returned', 'Returned'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='borrow_requests')
    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name='borrow_requests')
    quantity = models.IntegerField(validators=[MinValueValidator(1)], default=1)
    purpose = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    requested_date = models.DateTimeField(auto_now_add=True)
    borrow_from = models.DateTimeField()
    borrow_until = models.DateTimeField()

    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='approved_requests')
    approved_date = models.DateTimeField(null=True, blank=True)

    issued_date = models.DateTimeField(null=True, blank=True)
    returned_date = models.DateTimeField(null=True, blank=True)

    rejection_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'borrow_requests'
        ordering = ['-requested_date']
        indexes = [
            models.Index(fields=['status', 'user']),
            models.Index(fields=['equipment', 'status']),
            models.Index(fields=['borrow_from', 'borrow_until']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.equipment.name} ({self.status})"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.borrow_until <= self.borrow_from:
            raise ValidationError("Return date must be after borrow date")
        if self.quantity > self.equipment.total_quantity:
            raise ValidationError("Requested quantity exceeds available quantity")

    def check_availability(self):
        """Check if equipment is available for the requested period"""
        overlapping = BorrowRequest.objects.filter(
            equipment=self.equipment,
            status__in=['approved', 'issued'],
            borrow_from__lt=self.borrow_until,
            borrow_until__gt=self.borrow_from
        ).exclude(pk=self.pk)

        borrowed_quantity = sum(req.quantity for req in overlapping)
        available = self.equipment.total_quantity - borrowed_quantity
        return available >= self.quantity

    @property
    def is_overdue(self):
        return self.status == 'issued' and timezone.now() > self.borrow_until
