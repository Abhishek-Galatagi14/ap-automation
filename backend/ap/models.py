from django.db import models

class Vendor(models.Model):
    name = models.CharField(max_length=200)
    gstin = models.CharField(max_length=15, unique=True)
    pan = models.CharField(max_length=10, blank=True)
    email = models.EmailField(blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    account_no = models.CharField(max_length=30, blank=True)
    ifsc = models.CharField(max_length=15, blank=True)
    status = models.CharField(max_length=10, default="pending")  # onboarding: pending/approved/rejected
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name

class PurchaseOrder(models.Model):
    po_number = models.CharField(max_length=50, unique=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="pos")
    date = models.DateField()
    total = models.DecimalField(max_digits=14, decimal_places=2)

class POLine(models.Model):
    po = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    description = models.CharField(max_length=255)
    qty = models.DecimalField(max_digits=12, decimal_places=2)
    rate = models.DecimalField(max_digits=12, decimal_places=2)

class GRN(models.Model):
    grn_number = models.CharField(max_length=50, unique=True)
    po = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="grns")
    date = models.DateField()

class GRNLine(models.Model):
    grn = models.ForeignKey(GRN, on_delete=models.CASCADE, related_name="lines")
    description = models.CharField(max_length=255)
    qty_received = models.DecimalField(max_digits=12, decimal_places=2)

class Invoice(models.Model):
    invoice_number = models.CharField(max_length=60, blank=True)
    vendor = models.ForeignKey(Vendor, null=True, blank=True, on_delete=models.SET_NULL, related_name="invoices")
    vendor_name = models.CharField(max_length=200, blank=True)
    vendor_gstin = models.CharField(max_length=15, blank=True)
    invoice_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    po_number = models.CharField(max_length=50, blank=True)
    file = models.FileField(upload_to="invoices/", null=True, blank=True)
    source = models.CharField(max_length=20, default="upload")
    status = models.CharField(max_length=20, default="captured")
    ocr_text = models.TextField(blank=True)
    ocr_confidence = models.FloatField(default=0)
    validation_errors = models.JSONField(default=list)
    match_type = models.CharField(max_length=10, blank=True)
    match_result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    description = models.CharField(max_length=255)
    qty = models.DecimalField(max_digits=12, decimal_places=2)
    rate = models.DecimalField(max_digits=12, decimal_places=2)
    amount = models.DecimalField(max_digits=14, decimal_places=2)

class ApprovalStep(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="steps")
    role = models.CharField(max_length=30)
    status = models.CharField(max_length=10, default="pending")
    comment = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    acted_at = models.DateTimeField(null=True, blank=True)
    escalated = models.BooleanField(default=False)

class Payment(models.Model):
    invoice = models.OneToOneField(Invoice, on_delete=models.CASCADE, related_name="payment")
    reference = models.CharField(max_length=40)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=12, default="requested")
    requested_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    advice = models.TextField(blank=True)

class AuditLog(models.Model):
    invoice = models.ForeignKey(Invoice, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=60)
    detail = models.CharField(max_length=300, blank=True)
    at = models.DateTimeField(auto_now_add=True)
