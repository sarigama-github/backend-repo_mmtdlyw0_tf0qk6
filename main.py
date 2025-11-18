import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import MenuItem, InventoryItem, Customer, Order, OrderItem, Payment, ReportFilter

app = FastAPI(title="Bill Printing App API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Utility

def to_oid(id_str: str):
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")


@app.get("/")
def read_root():
    return {"message": "Bill Printing App API"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Connected & Working"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            response["collections"] = db.list_collection_names()
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response

# ----- Menu Management -----
@app.post("/menu", response_model=dict)
def create_menu_item(item: MenuItem):
    inserted_id = create_document("menuitem", item)
    return {"id": inserted_id}

@app.get("/menu", response_model=List[dict])
def list_menu_items():
    items = get_documents("menuitem")
    for it in items:
        it["_id"] = str(it.get("_id"))
    return items

# ----- Inventory Management -----
@app.post("/inventory", response_model=dict)
def create_inventory_item(item: InventoryItem):
    inserted_id = create_document("inventoryitem", item)
    return {"id": inserted_id}

@app.get("/inventory", response_model=List[dict])
def list_inventory_items():
    items = get_documents("inventoryitem")
    for it in items:
        it["_id"] = str(it.get("_id"))
    return items

# ----- Customer Management -----
@app.post("/customers", response_model=dict)
def create_customer(customer: Customer):
    inserted_id = create_document("customer", customer)
    return {"id": inserted_id}

@app.get("/customers", response_model=List[dict])
def list_customers():
    items = get_documents("customer")
    for it in items:
        it["_id"] = str(it.get("_id"))
    return items

# ----- Order Management -----

class OrderCreate(BaseModel):
    table_no: Optional[str] = None
    customer_id: Optional[str] = None
    items: List[OrderItem]
    discount: float = 0
    notes: Optional[str] = None

@app.post("/orders", response_model=dict)
def create_order(payload: OrderCreate):
    # expand items from menu snapshot
    subtotal = 0
    tax_total = 0
    expanded_items: List[OrderItem] = []

    for oi in payload.items:
        # fetch menu item details
        mi = db["menuitem"].find_one({"_id": to_oid(oi.menu_item_id)})
        if not mi:
            raise HTTPException(status_code=404, detail="Menu item not found")
        unit_price = float(mi.get("price", 0))
        line_subtotal = unit_price * oi.quantity
        gst_rate = float(mi.get("gst_rate", 0))
        line_tax = line_subtotal * gst_rate
        subtotal += line_subtotal
        tax_total += line_tax
        expanded_items.append(OrderItem(
            menu_item_id=oi.menu_item_id,
            name=mi.get("name"),
            price=unit_price,
            quantity=oi.quantity,
            notes=oi.notes,
            gst_rate=gst_rate,
        ))

    subtotal_after_discount = max(0.0, subtotal - float(payload.discount))
    # Recompute tax on discounted subtotal proportionally
    tax_ratio = 0.0 if subtotal == 0 else tax_total / subtotal
    tax_total_discounted = subtotal_after_discount * tax_ratio
    grand_total = subtotal_after_discount + tax_total_discounted

    order_doc = Order(
        table_no=payload.table_no,
        customer_id=payload.customer_id,
        items=expanded_items,
        subtotal=round(subtotal_after_discount, 2),
        tax_total=round(tax_total_discounted, 2),
        grand_total=round(grand_total, 2),
        payments=[],
        discount=float(payload.discount or 0),
        status="pending",
        notes=payload.notes,
    )

    inserted_id = create_document("order", order_doc)
    return {"id": inserted_id, "totals": {
        "subtotal": order_doc.subtotal,
        "tax_total": order_doc.tax_total,
        "grand_total": order_doc.grand_total
    }}

@app.get("/orders", response_model=List[dict])
def list_orders(status: Optional[str] = None):
    filt = {"status": status} if status else {}
    orders = get_documents("order", filt, limit=None)
    for o in orders:
        o["_id"] = str(o.get("_id"))
    return orders

class OrderStatusUpdate(BaseModel):
    status: str

@app.patch("/orders/{order_id}/status")
def update_order_status(order_id: str, payload: OrderStatusUpdate):
    res = db["order"].update_one({"_id": to_oid(order_id)}, {"$set": {"status": payload.status}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"ok": True}

class PaymentIn(BaseModel):
    method: str
    amount: float
    reference: Optional[str] = None

@app.post("/orders/{order_id}/pay")
def add_payment(order_id: str, payment: PaymentIn):
    res = db["order"].update_one(
        {"_id": to_oid(order_id)},
        {"$push": {"payments": payment.model_dump()}, "$set": {"updated_at": None}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"ok": True}

# ----- Reports -----
@app.post("/reports/sales")
def sales_report(filters: ReportFilter):
    pipeline = []
    # Future: add date filters when created_at exists by default in helper.
    pipeline.append({"$group": {"_id": None, "revenue": {"$sum": "$grand_total"}, "orders": {"$sum": 1}}})
    data = list(db["order"].aggregate(pipeline))
    if not data:
        return {"revenue": 0, "orders": 0}
    return {"revenue": round(float(data[0]["revenue"]), 2), "orders": int(data[0]["orders"]) }

# ----- Bill Print (data) -----
@app.get("/orders/{order_id}/bill")
def get_order_bill(order_id: str):
    o = db["order"].find_one({"_id": to_oid(order_id)})
    if not o:
        raise HTTPException(status_code=404, detail="Order not found")
    o["_id"] = str(o["_id"])
    return o

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
