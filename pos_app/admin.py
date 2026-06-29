from django.contrib import admin
from django.contrib import messages
from django.utils import timezone
from django.db.models.deletion import ProtectedError
from .models import DeletionRequest, Product, Sale

def approve_selected(modeladmin, request, queryset):
    # Only process pending requests
    pending = queryset.filter(status='pending')
    if not pending:
        messages.warning(request, "No pending requests selected.")
        return

    for obj in pending:
        try:
            if obj.object_type == 'product':
                product = Product.objects.get(id=obj.object_id)
                product.delete()
            elif obj.object_type == 'sale':
                sale = Sale.objects.get(id=obj.object_id)
                if sale.payment_status == 'paid':
                    for item in sale.items.all():
                        product = item.product
                        product.quantity_in_stock += item.quantity
                        product.save()
                sale.delete()
            else:
                messages.error(request, f"Unknown object type: {obj.object_type}")
                continue

            obj.status = 'approved'
            obj.approved_by = request.user
            obj.approved_at = timezone.now()
            obj.save()
            messages.success(request, f"Approved deletion of {obj.object_repr}")

        except (Product.DoesNotExist, Sale.DoesNotExist):
            messages.error(request, f"Object {obj.object_repr} no longer exists. Marking as rejected.")
            obj.status = 'rejected'
            obj.save()

        except ProtectedError:
            messages.error(
                request,
                f"Cannot approve deletion of {obj.object_repr} because it is referenced in other records. Marked as rejected."
            )
            obj.status = 'rejected'
            obj.save()

approve_selected.short_description = "Approve selected deletion requests"


def reject_selected(modeladmin, request, queryset):
    queryset.update(status='rejected', approved_by=request.user, approved_at=timezone.now())
    messages.success(request, "Selected requests rejected.")
reject_selected.short_description = "Reject selected deletion requests"


class DeletionRequestAdmin(admin.ModelAdmin):
    list_display = ('object_type', 'object_repr', 'requested_by', 'requested_at', 'status')
    list_filter = ('status', 'object_type')
    search_fields = ('object_repr', 'requested_by__username')
    actions = [approve_selected, reject_selected]
    readonly_fields = ('object_type', 'object_id', 'object_repr', 'requested_by', 'requested_at', 'approved_by', 'approved_at')
    fieldsets = (
        (None, {'fields': ('object_type', 'object_repr', 'requested_by', 'requested_at', 'status')}),
        ('Approval', {'fields': ('approved_by', 'approved_at')}),
    )

admin.site.register(DeletionRequest, DeletionRequestAdmin)