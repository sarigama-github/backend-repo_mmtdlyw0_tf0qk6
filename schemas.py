"""
Database Schemas for Bill Printing App

Each Pydantic model corresponds to a MongoDB collection (lowercased class name).
"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field

class MenuItem(BaseModel):
    name: str = Field(..., description="Item name")
    category: str = Field(..., description="Category like Beverages, Mains, Desserts")
    price: float = Field(..., ge=0, description="Base price (pre-tax)")
    description: Optional[str] = Field(None, description="Short description")
    is_available: bool = Field(True, description="Available to order")
    gst_rate: float = Field(0.05, ge=0, le=0.28, description="GST rate fraction (e.g., 0.05 = 5%)")

class InventoryItem(BaseModel):
    sku: str = Field(..., description="Unique SKU or code")
    name: str = Field(..., description="Inventory item name")
    quantity: float = Field(..., ge=0, description="Current stock level")
    unit: str = Field("unit", description="Unit of measure")
    low_stock_threshold: float = Field(0, ge=0, description="Alert threshold")

class Customer(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    loyalty_points: int = Field(0, ge=0)

class OrderItem(BaseModel):
    menu_item_id: str = Field(..., description="Reference to MenuItem _id")
    name: Optional[str] = Field(None, description="Snapshot of name for receipt")
    price: Optional[float] = Field(None, description="Snapshot of unit price for receipt")
    quantity: int = Field(..., ge=1)
    notes: Optional[str] = None
    gst_rate: Optional[float] = Field(None, description="Snapshot GST rate")

class Payment(BaseModel):
    method: Literal["cash","card","upi","wallet","split","other"] = "cash"
    amount: float = Field(0, ge=0)
    reference: Optional[str] = None

class Order(BaseModel):
    table_no: Optional[str] = Field(None, description="Table number or token")
    customer_id: Optional[str] = None
    status: Literal["pending","preparing","ready","served","cancelled"] = "pending"
    items: List[OrderItem]
    subtotal: float = 0
    tax_total: float = 0
    grand_total: float = 0
    payments: List[Payment] = []
    discount: float = 0
    notes: Optional[str] = None

class ReportFilter(BaseModel):
    date_from: Optional[str] = None
    date_to: Optional[str] = None
