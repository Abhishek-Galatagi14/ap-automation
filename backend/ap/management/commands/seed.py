from django.core.management.base import BaseCommand
from ap.models import *
class Command(BaseCommand):
    help = "Load demo vendor + PO"
    def handle(self, *a, **k):
        v, _ = Vendor.objects.get_or_create(gstin="29ABCDE1234F1Z5", defaults=dict(name="Acme Steels Pvt Ltd", status="approved", bank_name="HDFC", account_no="50100012345678", ifsc="HDFC0001234"))
        po, c = PurchaseOrder.objects.get_or_create(po_number="PO-1001", defaults=dict(vendor=v, date="2026-11-01", total=11800))
        if c: POLine.objects.create(po=po, description="Steel Rod", qty=10, rate=1000)
        self.stdout.write("Seeded vendor Acme (GSTIN 29ABCDE1234F1Z5) and PO-1001")
