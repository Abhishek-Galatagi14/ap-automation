from django.contrib import admin
from . import models
for m in [models.Vendor, models.PurchaseOrder, models.GRN, models.Invoice, models.Payment, models.AuditLog]:
    admin.site.register(m)
