# AP Automation (OCR + Workflow) — React + Django + PostgreSQL

## Run
```bash
# 1. PostgreSQL
createdb ap_db        # (user postgres / pass postgres, or set DB_NAME DB_USER DB_PASSWORD DB_HOST)
# 2. Backend
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate && python manage.py seed && python manage.py runserver     # :8000
# 3. Frontend
cd frontend && npm install && npm run dev                                           # :5173
```
Optional: install Tesseract OCR binary to read scanned JPG/PNG/TIFF. Text-based PDFs work without it.

Demo: seed gives vendor *Acme Steels* (GSTIN 29ABCDE1234F1Z5, approved) and PO-1001 (10 × Steel Rod, ₹11,800).
Upload an invoice PDF with: `Invoice No: INV-1`, `Date: 02/11/2026`, `PO No: PO-1001`, the GSTIN, line `Steel Rod 10 1000 10000`, `Subtotal: 10000`, `GST 18%: 1800`, `Total: 11800`.

## Database schema (generate DDL: `python manage.py sqlmigrate ap 0001 > schema.sql`)
| Table | Key columns | Relationships |
|---|---|---|
| ap_vendor | name, gstin (unique), pan, bank_name, account_no, ifsc, status | 1—N PO, 1—N Invoice |
| ap_purchaseorder | po_number (unique), date, total | FK vendor; 1—N po lines, 1—N GRN |
| ap_poline | description, qty, rate | FK po |
| ap_grn / ap_grnline | grn_number, date / description, qty_received | grn FK po; line FK grn |
| ap_invoice | invoice_number, vendor_gstin, dates, subtotal, tax, total, po_number, file, source, status, ocr_text, ocr_confidence, validation_errors (JSON), match_type, match_result (JSON) | FK vendor (nullable) |
| ap_invoiceline | description, qty, rate, amount | FK invoice |
| ap_approvalstep | role, status, comment, acted_at, escalated | FK invoice |
| ap_payment | reference, amount, status, paid_at, advice | 1—1 invoice |
| ap_auditlog | action, detail, at | FK invoice (nullable) |

## Module coverage
1 Capture: PDF/JPG/PNG/TIFF, drag-drop, bulk, email-ingest endpoint (`source=email`) · 2 OCR: pypdf + Tesseract, regex field/line-item/multi-page extraction, confidence % · 3 Validation: mandatory, duplicate, GSTIN, amount, vendor master · 4 PO matching: 2-way, auto 3-way when GRN exists (2% tolerance) · 5 Workflow: amount-based approval matrix (Manager / +Finance >50k / +CFO >5L), role steps in parallel, escalation job, responsive UI · 6 Vendors: master, bank details, GSTIN, onboarding approve/reject · 7 Payments: request, status, payment advice (bank API is a simulated "mark paid") · 8 Dashboard · 9 Reports: aging, status, exceptions, audit, GST.

## Challenges & solutions
- **Messy OCR output** → layered extraction (native PDF text first, Tesseract fallback), regex patterns, confidence score, and editable fields with re-validation so users can fix mistakes.
- **Matching with tolerance and partial deliveries** → totals/qty compared against PO with 2% tolerance; 3-way compares against cumulative GRN quantity.
- **Parallel approvals** → one step row per role created together; invoice becomes approved only when no step is non-approved; any rejection rejects it.
- **Auditability** → every state change writes an AuditLog row.
- **Deployment** → env-based DB settings, CORS enabled, Vite proxy for local dev.

## Known limitations
No login/RBAC yet (roles are simulated in UI), email ingestion is an upload endpoint (no IMAP poller), banking integration and push/mobile notifications are stubbed, escalation runs via button/endpoint (cron it for production).
