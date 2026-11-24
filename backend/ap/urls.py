from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
router = DefaultRouter()
router.register("vendors", views.VendorV); router.register("pos", views.POV); router.register("grns", views.GRNV); router.register("invoices", views.InvoiceV)
urlpatterns = [path("", include(router.urls)), path("dashboard/", views.dashboard), path("reports/<str:name>/", views.report), path("escalate/", views.escalate)]
