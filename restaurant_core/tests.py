from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from decimal import Decimal
from .models import Table, Category, MenuItem, Order, OrderItem


class TableModelTest(TestCase):
    """Test cases for Table model."""
    
    def setUp(self):
        """Set up test data."""
        self.table = Table.objects.create(table_number=1)
    
    def test_table_creation(self):
        """Test table is created successfully."""
        self.assertEqual(self.table.table_number, 1)
        self.assertTrue(self.table.is_active)
        self.assertIsNotNone(self.table.qr_id)
    
    def test_table_qr_code_generation(self):
        """Test QR code is generated on save."""
        self.assertIsNotNone(self.table.qr_code_image)


class CategoryModelTest(TestCase):
    """Test cases for Category model."""
    
    def setUp(self):
        """Set up test data."""
        self.category = Category.objects.create(
            name="Appetizers",
            description="Starters and appetizers"
        )
    
    def test_category_creation(self):
        """Test category is created successfully."""
        self.assertEqual(self.category.name, "Appetizers")
        self.assertTrue(self.category.is_active)


class MenuItemModelTest(TestCase):
    """Test cases for MenuItem model."""
    
    def setUp(self):
        """Set up test data."""
        self.category = Category.objects.create(name="Main Course")
        self.item = MenuItem.objects.create(
            category=self.category,
            name="Grilled Chicken",
            price=Decimal("10.99"),
            description="Delicious grilled chicken"
        )
    
    def test_menu_item_creation(self):
        """Test menu item is created successfully."""
        self.assertEqual(self.item.name, "Grilled Chicken")
        self.assertEqual(self.item.price, Decimal("10.99"))
        self.assertTrue(self.item.is_available)


class OrderModelTest(TestCase):
    """Test cases for Order model."""
    
    def setUp(self):
        """Set up test data."""
        self.table = Table.objects.create(table_number=1)
        self.category = Category.objects.create(name="Beverages")
        self.menu_item = MenuItem.objects.create(
            category=self.category,
            name="Coffee",
            price=Decimal("2.99")
        )
    
    def test_order_creation(self):
        """Test order is created successfully."""
        order = Order.objects.create(
            table=self.table,
            customer_name="John Doe",
            customer_mobile="+1234567890",
            total_amount=Decimal("2.99")
        )
        self.assertIsNotNone(order.invoice_number)
        self.assertEqual(order.status, 'awaiting_payment')
        self.assertFalse(order.is_paid)
    
    def test_order_invoice_number_generation(self):
        """Test invoice number is unique."""
        order1 = Order.objects.create(
            table=self.table,
            customer_name="John",
            total_amount=Decimal("10.00")
        )
        order2 = Order.objects.create(
            table=self.table,
            customer_name="Jane",
            total_amount=Decimal("15.00")
        )
        self.assertNotEqual(order1.invoice_number, order2.invoice_number)


class TableAPITest(TestCase):
    """Test cases for Table API views."""
    
    def setUp(self):
        """Set up test client and data."""
        self.client = APIClient()
        self.table = Table.objects.create(table_number=1)
    
    def test_get_tables_list(self):
        """Test retrieving list of tables."""
        response = self.client.get('/api/tables/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
    
    def test_get_table_by_id(self):
        """Test retrieving single table."""
        response = self.client.get(f'/api/tables/{self.table.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])


class MenuItemAPITest(TestCase):
    """Test cases for MenuItem API views."""
    
    def setUp(self):
        """Set up test client and data."""
        self.client = APIClient()
        self.category = Category.objects.create(name="Desserts")
        self.menu_item = MenuItem.objects.create(
            category=self.category,
            name="Chocolate Cake",
            price=Decimal("5.99")
        )
    
    def test_get_menu_items_list(self):
        """Test retrieving list of menu items."""
        response = self.client.get('/api/menu-items/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])


class OrderAPITest(TestCase):
    """Test cases for Order API views."""
    
    def setUp(self):
        """Set up test client and data."""
        self.client = APIClient()
        self.table = Table.objects.create(table_number=1)
        self.category = Category.objects.create(name="Drinks")
        self.menu_item = MenuItem.objects.create(
            category=self.category,
            name="Orange Juice",
            price=Decimal("3.99")
        )
    
    def test_place_order_success(self):
        """Test placing an order successfully."""
        order_data = {
            "table": self.table.id,
            "customer_name": "John Doe",
            "customer_mobile": "+1234567890",
            "items": [
                {
                    "menu_item": self.menu_item.id,
                    "quantity": 2,
                    "special_instructions": "No ice"
                }
            ]
        }
        response = self.client.post('/api/orders/place/', order_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])
    
    def test_place_order_without_items(self):
        """Test placing order without items fails."""
        order_data = {
            "table": self.table.id,
            "customer_name": "Jane Doe",
            "items": []
        }
        response = self.client.post('/api/orders/place/', order_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
    
    def test_confirm_payment(self):
        """Test confirming payment for an order."""
        order = Order.objects.create(
            table=self.table,
            customer_name="John",
            total_amount=Decimal("10.00")
        )
        response = self.client.patch(
            f'/api/orders/{order.id}/confirm-payment/',
            {"payment_method": "card"},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        
        # Verify order is marked as paid
        order.refresh_from_db()
        self.assertTrue(order.is_paid)

