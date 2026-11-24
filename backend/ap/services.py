import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from django.db.models import Sum
from django.utils import timezone
from .models import *

GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]Z[A-Z0-9]\b")

def audit(inv, action, detail=""): AuditLog.objects.create(invoice=inv, action=action, detail=detail[:300])

def dec(s):
    try: return Decimal(str(s).replace(",", ""))
    except (InvalidOperation, ValueError): return Decimal(0)

def read_text(f):
    """OCR layer: native PDF text via pypdf; scanned images/TIFF via Tesseract if installed."""
    name = f.name.lower(); f.open("rb")
    try:
        if name.endswith(".pdf"):
            from pypdf import PdfReader
            return "\n".join((p.extract_text() or "") for p in PdfReader(f).pages)
        from PIL import Image, ImageSequence
        import pytesseract
        img = Image.open(f)
        return "\n".join(pytesseract.image_to_string(fr) for fr in ImageSequence.Iterator(img))
    except Exception: return ""
    finally: f.close()

def parse_date(s):
    for fmt in ("%d/%m/%Y","%d-%m-%Y","%Y-%m-%d","%d %b %Y","%d.%m.%Y"):
        try: return datetime.strptime(s.strip(), fmt).date()
        except ValueError: pass

def extract(text):
    g = lambda p: (re.search(p, text, re.I) or [None, ""])[1].strip()
    d = {"invoice_number": g(r"invoice\s*(?:no|number|#)\.?\s*[:\-]?\s*([A-Z0-9/\-]+)"),
         "invoice_date": parse_date(g(r"(?:invoice\s*)?date\s*[:\-]?\s*([\d/.\- A-Za-z]{8,11})") or ""),
         "due_date": parse_date(g(r"due\s*date\s*[:\-]?\s*([\d/.\- A-Za-z]{8,11})") or ""),
         "po_number": g(r"\bPO\s*(?:no|number|#)?\.?\s*[:\-]?\s*([A-Z0-9/\-]*\d[A-Z0-9/\-]*)"),
         "vendor_name": g(r"(?:vendor|supplier|from)\s*[:\-]\s*(.+)") or (text.strip().splitlines() or [""])[0][:200],
         "vendor_gstin": (GSTIN_RE.search(text.upper()) or [""])[0],
         "subtotal": dec(g(r"sub\s*total\s*[:\-]?\s*(?:Rs\.?|INR|₹)?\s*([\d,]+\.?\d*)")),
         "tax": dec(g(r"(?:total\s*)?(?:gst|tax|igst)\s*(?:\(?[\d.]+%\)?)?\s*[:\-]?\s*(?:Rs\.?|INR|₹)?\s*([\d,]+\.?\d*)")),
         "total": dec(g(r"(?:grand\s*total|total\s*amount|net\s*payable|(?<!sub)(?<!sub )total)\s*[:\-]?\s*(?:Rs\.?|INR|₹)?\s*([\d,]+\.?\d*)"))}
    lines = []
    for ln in text.splitlines():
        m = re.match(r"^\s*(?:\d+[.)]?\s+)?([A-Za-z][\w \-/&]+?)\s+(\d+(?:\.\d+)?)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s*$", ln)
        if m: lines.append((m[1].strip(), dec(m[2]), dec(m[3]), dec(m[4])))
    return d, lines

def process(inv):
    text = read_text(inv.file) if inv.file else ""
    inv.ocr_text = text
    d, lines = extract(text)
    for k, v in d.items():
        if v: setattr(inv, k, v)
    keys = ["invoice_number","invoice_date","vendor_gstin","total","po_number"]
    inv.ocr_confidence = round(100 * sum(1 for k in keys if d[k]) / len(keys), 1)
    inv.lines.all().delete()
    for ds, q, r, a in lines: InvoiceLine.objects.create(invoice=inv, description=ds, qty=q, rate=r, amount=a)
    inv.status = "extracted"; inv.save()
    audit(inv, "captured+ocr", f"source={inv.source} confidence={inv.ocr_confidence}%")
    validate(inv); return inv

def validate(inv):
    e = []
    for f in ("invoice_number","vendor_name","invoice_date"):
        if not getattr(inv, f): e.append(f"Missing mandatory field: {f}")
    if not inv.total: e.append("Missing mandatory field: total")
    if inv.invoice_number and Invoice.objects.filter(invoice_number=inv.invoice_number, vendor_gstin=inv.vendor_gstin).exclude(pk=inv.pk).exists():
        e.append("Duplicate invoice (same number + vendor GSTIN)")
    if not GSTIN_RE.fullmatch(inv.vendor_gstin or ""): e.append("Invalid or missing GSTIN")
    lines = list(inv.lines.all())
    if inv.subtotal and abs(inv.subtotal + inv.tax - inv.total) > 1: e.append("Amount mismatch: subtotal + tax != total")
    if lines and inv.subtotal and abs(sum(l.amount for l in lines) - inv.subtotal) > 1: e.append("Line items do not add up to subtotal")
    inv.vendor = Vendor.objects.filter(gstin=inv.vendor_gstin).first()
    if not inv.vendor: e.append("Vendor not found in vendor master")
    elif inv.vendor.status != "approved": e.append("Vendor not approved in master")
    inv.validation_errors = e
    if e: inv.status = "exception"
    elif inv.status == "exception": inv.status = "extracted"
    inv.save(); return e

def match(inv):
    """2-way (PO vs Invoice); 3-way (PO vs GRN vs Invoice) when GRNs exist for the PO."""
    po = PurchaseOrder.objects.filter(po_number=inv.po_number).first()
    if not po: return ["No matching PO found"], {}
    inv_qty = sum(l.qty for l in inv.lines.all())
    po_qty = po.lines.aggregate(s=Sum("qty"))["s"] or 0
    errs = []
    if inv.total > po.total * Decimal("1.02"): errs.append(f"Invoice total {inv.total} exceeds PO total {po.total} (2% tolerance)")
    if inv_qty and po_qty and inv_qty > po_qty: errs.append("Invoice quantity exceeds PO quantity")
    res = {"po_total": str(po.total), "po_qty": str(po_qty), "invoice_qty": str(inv_qty)}
    mt = "2-way"
    if GRNLine.objects.filter(grn__po=po).exists():
        mt = "3-way"; grn_qty = GRNLine.objects.filter(grn__po=po).aggregate(s=Sum("qty_received"))["s"] or 0
        res["grn_qty"] = str(grn_qty)
        if inv_qty and inv_qty > grn_qty: errs.append("Invoice quantity exceeds goods received (GRN)")
    inv.match_type = mt; inv.match_result = {**res, "errors": errs}; inv.save()
    return errs, res

def approval_roles(total):  # approval matrix by amount
    roles = ["Manager"]
    if total > 50000: roles.append("Finance")
    if total > 500000: roles.append("CFO")
    return roles

def submit(inv):
    errs = validate(inv)
    if not errs:
        errs, _ = match(inv)
        if errs: inv.status = "exception"; inv.validation_errors = errs; inv.save()
    if errs: audit(inv, "submit_failed", "; ".join(errs)); return errs
    inv.steps.all().delete()
    for r in approval_roles(inv.total): ApprovalStep.objects.create(invoice=inv, role=r)  # parallel
    inv.status = "pending_approval"; inv.save(); audit(inv, "submitted", f"{inv.match_type} match ok"); return []

def decide(step, decision, comment=""):
    step.status = decision; step.comment = comment; step.acted_at = timezone.now(); step.save()
    inv = step.invoice; audit(inv, f"{decision} by {step.role}", comment)
    if decision == "rejected": inv.status = "rejected"
    elif not inv.steps.exclude(status="approved").exists(): inv.status = "approved"
    inv.save()

def escalate_overdue(hours=24):
    n = 0
    for s in ApprovalStep.objects.filter(status="pending", escalated=False, created_at__lt=timezone.now() - timedelta(hours=hours)):
        s.escalated = True; s.save(); audit(s.invoice, "escalated", f"{s.role} step pending > {hours}h"); n += 1
    return n

def request_payment(inv):
    p, _ = Payment.objects.get_or_create(invoice=inv, defaults={"reference": f"PAY-{inv.pk:06d}", "amount": inv.total})
    inv.status = "payment_requested"; inv.save(); audit(inv, "payment_requested", p.reference); return p

def mark_paid(inv):
    p = inv.payment; p.status = "paid"; p.paid_at = timezone.now(); v = inv.vendor
    p.advice = (f"PAYMENT ADVICE\nRef: {p.reference}\nVendor: {inv.vendor_name}\nInvoice: {inv.invoice_number}\n"
                f"Amount: INR {p.amount}\nBank: {v.bank_name if v else ''} A/c {v.account_no if v else ''}\nPaid on: {p.paid_at:%d-%b-%Y}")
    p.save(); inv.status = "paid"; inv.save(); audit(inv, "paid", p.reference); return p
