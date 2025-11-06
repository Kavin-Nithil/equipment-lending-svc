from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.db.models import Q
from .models import Equipment, EquipmentCategory, BorrowRequest
from .serializers import (EquipmentSerializer, EquipmentCategorySerializer,
                          BorrowRequestSerializer, UserRegistrationSerializer, UserSerializer)
from .permissions import IsAdminOrStaff, IsAdmin, IsOwnerOrStaff


class UserViewSet(viewsets.GenericViewSet):
    serializer_class = UserSerializer

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def register(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                'message': 'User registered successfully',
                'user': UserSerializer(user).data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)


class EquipmentCategoryViewSet(viewsets.ModelViewSet):
    queryset = EquipmentCategory.objects.all()
    serializer_class = EquipmentCategorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdmin()]
        return [IsAuthenticated()]


class EquipmentViewSet(viewsets.ModelViewSet):
    queryset = Equipment.objects.select_related('category').all()
    serializer_class = EquipmentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'condition', 'is_active']
    search_fields = ['name', 'description', 'serial_number']
    ordering_fields = ['name', 'created_at', 'available_quantity']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = super().get_queryset()
        available = self.request.query_params.get('available', None)
        if available is not None:
            if available.lower() == 'true':
                queryset = queryset.filter(available_quantity__gt=0, is_active=True)
        return queryset

    @action(detail=True, methods=['get'])
    def availability(self, request, pk=None):
        equipment = self.get_object()
        start = request.query_params.get('start')
        end = request.query_params.get('end')

        if not start or not end:
            return Response(
                {'error': 'start and end parameters required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            start_date = timezone.datetime.fromisoformat(start)
            end_date = timezone.datetime.fromisoformat(end)
        except ValueError:
            return Response(
                {'error': 'Invalid date format'},
                status=status.HTTP_400_BAD_REQUEST
            )

        overlapping = BorrowRequest.objects.filter(
            equipment=equipment,
            status__in=['approved', 'issued'],
            borrow_from__lt=end_date,
            borrow_until__gt=start_date
        )

        borrowed_quantity = sum(req.quantity for req in overlapping)
        available = equipment.total_quantity - borrowed_quantity

        return Response({
            'equipment_id': equipment.id,
            'total_quantity': equipment.total_quantity,
            'available_quantity': available,
            'period': {'start': start, 'end': end}
        })


class BorrowRequestViewSet(viewsets.ModelViewSet):
    queryset = BorrowRequest.objects.select_related('user', 'equipment', 'approved_by').all()
    serializer_class = BorrowRequestSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'equipment', 'user']
    ordering_fields = ['requested_date', 'borrow_from', 'borrow_until']

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()

        if user.role == 'student':
            queryset = queryset.filter(user=user)

        overdue = self.request.query_params.get('overdue', None)
        if overdue and overdue.lower() == 'true':
            queryset = queryset.filter(
                status='issued',
                borrow_until__lt=timezone.now()
            )

        return queryset

    def get_permissions(self):
        if self.action in ['approve', 'reject', 'issue', 'return']:
            return [IsAdminOrStaff()]
        if self.action in ['update', 'partial_update', 'destroy']:
            return [IsOwnerOrStaff()]
        return [IsAuthenticated()]

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrStaff])
    def approve(self, request, pk=None):
        borrow_request = self.get_object()

        if borrow_request.status != 'pending':
            return Response(
                {'error': 'Only pending requests can be approved'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not borrow_request.check_availability():
            return Response(
                {'error': 'Equipment not available for requested period'},
                status=status.HTTP_400_BAD_REQUEST
            )

        borrow_request.status = 'approved'
        borrow_request.approved_by = request.user
        borrow_request.approved_date = timezone.now()
        borrow_request.save()

        serializer = self.get_serializer(borrow_request)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrStaff])
    def reject(self, request, pk=None):
        borrow_request = self.get_object()

        if borrow_request.status != 'pending':
            return Response(
                {'error': 'Only pending requests can be rejected'},
                status=status.HTTP_400_BAD_REQUEST
            )

        reason = request.data.get('reason', '')
        borrow_request.status = 'rejected'
        borrow_request.rejection_reason = reason
        borrow_request.approved_by = request.user
        borrow_request.approved_date = timezone.now()
        borrow_request.save()

        serializer = self.get_serializer(borrow_request)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrStaff])
    def issue(self, request, pk=None):
        borrow_request = self.get_object()

        if borrow_request.status != 'approved':
            return Response(
                {'error': 'Only approved requests can be issued'},
                status=status.HTTP_400_BAD_REQUEST
            )

        equipment = borrow_request.equipment
        if equipment.available_quantity < borrow_request.quantity:
            return Response(
                {'error': 'Insufficient equipment quantity'},
                status=status.HTTP_400_BAD_REQUEST
            )

        equipment.available_quantity -= borrow_request.quantity
        equipment.save()

        borrow_request.status = 'issued'
        borrow_request.issued_date = timezone.now()
        borrow_request.save()

        serializer = self.get_serializer(borrow_request)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrStaff])
    def return_equipment(self, request, pk=None):
        borrow_request = self.get_object()

        if borrow_request.status not in ['issued', 'overdue']:
            return Response(
                {'error': 'Only issued requests can be returned'},
                status=status.HTTP_400_BAD_REQUEST
            )

        equipment = borrow_request.equipment
        equipment.available_quantity += borrow_request.quantity
        equipment.save()

        borrow_request.status = 'returned'
        borrow_request.returned_date = timezone.now()
        notes = request.data.get('notes', '')
        if notes:
            borrow_request.notes = notes
        borrow_request.save()

        serializer = self.get_serializer(borrow_request)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_requests(self, request):
        requests = self.get_queryset().filter(user=request.user)
        serializer = self.get_serializer(requests, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsAdminOrStaff])
    def pending(self, request):
        requests = self.get_queryset().filter(status='pending')
        serializer = self.get_serializer(requests, many=True)
        return Response(serializer.data)

