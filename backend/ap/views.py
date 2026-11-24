from datetime import date
from django.db.models import Sum, Count, Avg, F
from rest_framework import viewsets, serializers
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from .models import *
from . import services

class Base(serializers.ModelSerializer):
    class Meta: fields = "__all__"
def mk(m, **kw): return type(m.__name__+"S", (Base,), {"Meta": type("Meta", (Base.Meta,), {"model": m}), **kw})
LineS, StepS, PayS, VendorS = mk(InvoiceLine), mk(ApprovalStep), mk(Payment), mk(Vendor)
POLineS = mk(POLine); GRNLineS = mk(GRNLine)
class POS(mk(PurchaseOrder, lines=POLineS(many=True, required=False), vendor_name=serializers.CharField(source="vendor.name", read_only=True))):
    def create(self, v):
        lines = v.pop("lines", []); po = PurchaseOrder.objects.create(**v)
        for l in lines: POLine.objects.create(po=po, **l)
        return po
class GRNS(mk(GRN, lines=GRNLineS(many=True, required=False))):
    def create(self, v):
        lines = v.pop("lines", []); g = GRN.objects.create(**v)
        for l in lines: GRNLine.objects.create(grn=g, **l)
        return g
class InvoiceS(mk(Invoice, lines=LineS(many=True, read_only=True), steps=StepS(many=True, read_only=True),
                  payment=PayS(read_only=True), vendor_display=serializers.CharField(source="vendor.name", read_only=True, default=""))): pass

class VendorV(viewsets.ModelViewSet):
    queryset = Vendor.objects.all().order_by("-id"); serializer_class = VendorS
    @action(detail=True, methods=["post"])
    def decide(self, r, pk=None):  # vendor onboarding workflow
        v = self.get_object(); v.status = r.data.get("status", "approved"); v.save(); return Response(VendorS(v).data)
class POV(viewsets.ModelViewSet): queryset = PurchaseOrder.objects.all().order_by("-id"); serializer_class = POS
class GRNV(viewsets.ModelViewSet): queryset = GRN.objects.all().order_by("-id"); serializer_class = GRNS

class InvoiceV(viewsets.ModelViewSet):
    queryset = Invoice.objects.all().order_by("-id"); serializer_class = InvoiceS
    def create(self, r, *a, **k):
        files = r.FILES.getlist("files")  # bulk / multi-format / drag&drop / email ingest (source=email)
        if not files: return super().create(r, *a, **k)
        out = [InvoiceS(services.process(Invoice.objects.create(file=f, source=r.data.get("source", "upload")))).data for f in files]
        return Response(out, status=201)
    def partial_update(self, r, *a, **k):  # manual correction after OCR
        super().partial_update(r, *a, **k); inv = self.get_object(); services.validate(inv); services.audit(inv, "edited")
        return Response(InvoiceS(inv).data)
    @action(detail=True, methods=["post"])
    def submit(self, r, pk=None):
        inv = self.get_object(); errs = services.submit(inv); return Response({"errors": errs, "invoice": InvoiceS(inv).data})
    @action(detail=True, methods=["post"])
    def approve(self, r, pk=None):
        inv = self.get_object(); step = inv.steps.get(pk=r.data["step_id"])
        services.decide(step, r.data.get("decision", "approved"), r.data.get("comment", "")); return Response(InvoiceS(inv).data)
    @action(detail=True, methods=["post"])
    def pay_request(self, r, pk=None):
        inv = self.get_object()
        if inv.status != "approved": return Response({"error": "Invoice not approved"}, 400)
        services.request_payment(inv); return Response(InvoiceS(inv).data)
    @action(detail=True, methods=["post"])
    def mark_paid(self, r, pk=None):
        inv = self.get_object()
        if inv.status != "payment_requested": return Response({"error": "No payment request"}, 400)
        services.mark_paid(inv); return Response(InvoiceS(inv).data)

@api_view(["POST"])
def escalate(r): return Response({"escalated": services.escalate_overdue(int(r.data.get("hours", 24)))})

@api_view(["GET"])
def dashboard(r):
    inv = Invoice.objects.all(); today = date.today(); b = {"not due": 0, "0-30": 0, "31-60": 0, "61-90": 0, "90+": 0}
    for i in inv.exclude(status__in=["paid", "rejected"]):
        d = i.due_date or i.invoice_date
        if not d: continue
        age = (today - d).days
        b["not due" if age <= 0 else "0-30" if age <= 30 else "31-60" if age <= 60 else "61-90" if age <= 90 else "90+"] += 1
    tat = [(p.paid_at - p.invoice.created_at).total_seconds() / 3600 for p in Payment.objects.filter(status="paid")]
    return Response({"by_status": list(inv.values("status").annotate(n=Count("id"))), "aging": b,
        "pending_approvals": ApprovalStep.objects.filter(status="pending").count(),
        "avg_turnaround_hours": round(sum(tat) / len(tat), 2) if tat else 0,
        "ocr_accuracy": round(inv.aggregate(a=Avg("ocr_confidence"))["a"] or 0, 1),
        "vendors": list(inv.values(name=F("vendor_name")).annotate(count=Count("id"), total=Sum("total")).order_by("-total")[:10]),
        "payments": list(Payment.objects.values("status").annotate(n=Count("id"), amt=Sum("amount")))})

@api_view(["GET"])
def report(r, name):
    if name == "aging": q = Invoice.objects.exclude(status__in=["paid", "rejected"]).values("invoice_number", "vendor_name", "total", "invoice_date", "due_date", "status")
    elif name == "status": q = Invoice.objects.values("status").annotate(count=Count("id"), total=Sum("total"))
    elif name == "exceptions": q = Invoice.objects.filter(status="exception").values("invoice_number", "vendor_name", "total", "validation_errors")
    elif name == "audit": q = AuditLog.objects.order_by("-at").values("invoice__invoice_number", "action", "detail", "at")[:300]
    elif name == "gst": q = Invoice.objects.values("vendor_name", "vendor_gstin").annotate(taxable=Sum("subtotal"), gst=Sum("tax"), total=Sum("total"))
    else: return Response({"error": "unknown report"}, 404)
    return Response(list(q))
