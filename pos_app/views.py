from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm
from django.db.models.deletion import ProtectedError
from django.db import models

from .models import Product, Category, Sale, SaleItem, DeletionRequest  # <-- added DeletionRequest
from .forms import (
    ProductForm, CategoryForm, SaleForm, SaleItemForm,
    RestockForm, StaffSaleForm
)

# ---------- Helper functions ----------
def is_admin(user):
    return user.is_superuser or user.groups.filter(name='Admin').exists()

def is_staff_or_admin(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)

# ---------- Dashboard (main) ----------
@login_required
@user_passes_test(is_staff_or_admin, login_url='login')
def dashboard(request):
    total_products = Product.objects.count()
    total_sales = Sale.objects.filter(payment_status='paid').count()
    total_revenue = Sale.objects.filter(payment_status='paid').aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    pending_sales = Sale.objects.filter(payment_status='pending').count()
    low_stock = Product.objects.filter(quantity_in_stock__lt=10).count()
    context = {
        'total_products': total_products,
        'total_sales': total_sales,
        'total_revenue': total_revenue,
        'pending_sales': pending_sales,
        'low_stock': low_stock,
    }
    return render(request, 'pos_app/dashboard.html', context)

# ---------- Staff Login ----------
def staff_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            if user.is_staff:
                login(request, user)
                return redirect('staff_dashboard')
            else:
                messages.error(request, 'You are not authorised as staff.')
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = AuthenticationForm()
    return render(request, 'pos_app/staff_login.html', {'form': form})

# ---------- Staff Dashboard ----------
@login_required
@user_passes_test(is_staff_or_admin, login_url='staff_login')
def staff_dashboard(request):
    products = Product.objects.select_related('category').all().order_by('name')
    return render(request, 'pos_app/staff_dashboard.html', {'products': products})

# ---------- Staff Make Sale (single product) ----------
@login_required
@user_passes_test(is_staff_or_admin, login_url='staff_login')
def staff_make_sale(request):
    if request.method == 'POST':
        form = StaffSaleForm(request.POST)
        if form.is_valid():
            product = form.cleaned_data['product']
            quantity = form.cleaned_data['quantity']
            price_type = form.cleaned_data['price_type']
            payment_method = form.cleaned_data['payment_method']
            customer_name = form.cleaned_data.get('customer_name', '')

            price = product.wholesale_price if price_type == 'wholesale' else product.price

            sale = Sale.objects.create(
                customer_name=customer_name,
                payment_method=payment_method,
                payment_status='paid',
                created_by=request.user,
                total_amount=price * quantity
            )

            try:
                SaleItem.objects.create(
                    sale=sale,
                    product=product,
                    quantity=quantity,
                    price_at_sale=price,
                    price_type=price_type
                )
                messages.success(request, f'Sold {quantity} x {product.name} (KSh {price} each).')
                return redirect('staff_dashboard')
            except ValueError as e:
                messages.error(request, str(e))
                sale.delete()
                return redirect('staff_make_sale')
    else:
        # Pre-select product if passed via URL parameter
        initial = {}
        product_id = request.GET.get('product')
        if product_id:
            try:
                product = Product.objects.get(id=product_id, quantity_in_stock__gt=0)
                initial['product'] = product
            except Product.DoesNotExist:
                pass
        form = StaffSaleForm(initial=initial)
    return render(request, 'pos_app/staff_make_sale.html', {'form': form})

# ---------- Staff Restock ----------
@login_required
@user_passes_test(is_staff_or_admin, login_url='staff_login')
def staff_restock(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    if request.method == 'POST':
        form = RestockForm(request.POST)
        if form.is_valid():
            qty = form.cleaned_data['quantity']
            product.quantity_in_stock += qty
            product.last_restocked = timezone.now()
            product.save()
            messages.success(request, f'Added {qty} units to {product.name}.')
            return redirect('staff_dashboard')
    else:
        form = RestockForm()
    return render(request, 'pos_app/staff_restock.html', {'product': product, 'form': form})

# ---------- Product CRUD (Staff & Admin) ----------
@login_required
@user_passes_test(is_staff_or_admin)
def product_list(request):
    products = Product.objects.select_related('category').all()
    return render(request, 'pos_app/product_list.html', {'products': products})

@login_required
@user_passes_test(is_staff_or_admin)
def product_create(request):
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Product added successfully.')
            return redirect('product_list')
    else:
        form = ProductForm()
    return render(request, 'pos_app/product_form.html', {'form': form, 'title': 'Add Product'})

@login_required
@user_passes_test(is_staff_or_admin)  # changed from is_admin to allow staff to edit
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, 'Product updated successfully.')
            return redirect('product_list')
    else:
        form = ProductForm(instance=product)
    return render(request, 'pos_app/product_form.html', {'form': form, 'title': 'Edit Product'})

@login_required
@user_passes_test(is_staff_or_admin)
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        # Check if user is admin (superuser or Admin group)
        if request.user.is_superuser or request.user.groups.filter(name='Admin').exists():
            try:
                product.delete()
                messages.success(request, f"Product '{product.name}' deleted successfully.")
            except ProtectedError:
                messages.error(request, f"Cannot delete '{product.name}' because it has been used in sales.")
        else:
            # Staff: create pending request
            pending = DeletionRequest.objects.filter(
                object_type='product', object_id=pk, status='pending'
            ).first()
            if pending:
                messages.warning(request, f"Deletion request for '{product.name}' is already pending approval.")
            else:
                DeletionRequest.objects.create(
                    object_type='product',
                    object_id=pk,
                    object_repr=product.name,
                    requested_by=request.user
                )
                messages.info(request, f"Deletion request for '{product.name}' sent to admin for approval.")
        return redirect('product_list')
    return render(request, 'pos_app/product_confirm_delete.html', {'product': product})

# ---------- Sales (Staff & Admin) ----------
@login_required
@user_passes_test(is_staff_or_admin)
def sale_list(request):
    sales = Sale.objects.select_related('created_by').order_by('-created_at')
    return render(request, 'pos_app/sale_list.html', {'sales': sales})

@login_required
@user_passes_test(is_staff_or_admin)
def sale_create(request):
    if request.method == 'POST':
        sale_form = SaleForm(request.POST)
        if sale_form.is_valid():
            sale = sale_form.save(commit=False)
            sale.created_by = request.user
            sale.total_amount = 0
            sale.save()

            product_ids = request.POST.getlist('product_id')
            quantities = request.POST.getlist('quantity')
            total = 0
            for pid, qty in zip(product_ids, quantities):
                if pid and qty and int(qty) > 0:
                    product = get_object_or_404(Product, pk=pid)
                    qty = int(qty)
                    if sale.payment_status == 'paid' and product.quantity_in_stock < qty:
                        messages.error(request, f"Insufficient stock for {product.name}. Available: {product.quantity_in_stock}")
                        sale.delete()
                        return redirect('sale_create')
                    price = product.price
                    SaleItem.objects.create(
                        sale=sale,
                        product=product,
                        quantity=qty,
                        price_at_sale=price
                    )
                    total += price * qty
            sale.total_amount = total
            sale.save()
            messages.success(request, f'Sale #{sale.id} created successfully.')
            return redirect('sale_list')
    else:
        sale_form = SaleForm()
    products = Product.objects.all()
    return render(request, 'pos_app/sale_form.html', {'sale_form': sale_form, 'products': products})

@login_required
@user_passes_test(is_staff_or_admin)
def sale_detail(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    return render(request, 'pos_app/sale_detail.html', {'sale': sale})

@login_required
@user_passes_test(is_staff_or_admin)  # changed from is_admin to allow staff to request deletion
def sale_delete(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    if request.method == 'POST':
        # Check if user is admin (superuser or Admin group)
        if request.user.is_superuser or request.user.groups.filter(name='Admin').exists():
            # Admin: delete directly
            if sale.payment_status == 'paid':
                for item in sale.items.all():
                    product = item.product
                    product.quantity_in_stock += item.quantity
                    product.save()
            sale.delete()
            messages.success(request, f'Sale #{sale.id} deleted and stock restored.')
        else:
            # Staff: create pending request
            pending = DeletionRequest.objects.filter(
                object_type='sale', object_id=pk, status='pending'
            ).first()
            if pending:
                messages.warning(request, f"Deletion request for Sale #{sale.id} is already pending approval.")
            else:
                DeletionRequest.objects.create(
                    object_type='sale',
                    object_id=pk,
                    object_repr=f"Sale #{sale.id}",
                    requested_by=request.user
                )
                messages.info(request, f"Deletion request for Sale #{sale.id} sent to admin for approval.")
        return redirect('sale_list')
    return redirect('sale_list')

# ---------- Category CRUD (Admin only) ----------
@login_required
@user_passes_test(is_admin)
def category_list(request):
    categories = Category.objects.annotate(product_count=models.Count('products'))
    return render(request, 'pos_app/category_list.html', {'categories': categories})

@login_required
@user_passes_test(is_admin)
def category_create(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'id': category.id,
                    'name': category.name,
                })
            messages.success(request, 'Category created.')
            return redirect('product_create')
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors,
                }, status=400)
    return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

@login_required
@user_passes_test(is_admin)
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        if category.products.exists():
            messages.error(
                request,
                f"Cannot delete '{category.name}' — it has {category.products.count()} product(s). Reassign or delete them first."
            )
            return redirect('category_list')
        category.delete()
        messages.success(request, f"Category '{category.name}' deleted successfully.")
        return redirect('category_list')
    return redirect('category_list')

# ---------- Reports ----------
@login_required
@user_passes_test(is_staff_or_admin)
def daily_report(request):
    today = timezone.now().date()
    start = datetime.combine(today, datetime.min.time())
    end = datetime.combine(today, datetime.max.time())
    sales = Sale.objects.filter(created_at__range=(start, end), payment_status='paid')
    total = sales.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    count = sales.count()
    products = Product.objects.all()
    context = {
        'date': today,
        'total_sales': total,
        'sales_count': count,
        'sales': sales,
        'products': products,
    }
    return render(request, 'pos_app/daily_report.html', context)

@login_required
@user_passes_test(is_staff_or_admin)
def monthly_report(request):
    now = timezone.now()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year+1, month=1, day=1) - timedelta(days=1)
    else:
        end = start.replace(month=start.month+1) - timedelta(days=1)
    sales = Sale.objects.filter(created_at__range=(start, end), payment_status='paid')
    total = sales.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    count = sales.count()
    products = Product.objects.all()
    context = {
        'month': start.strftime('%B %Y'),
        'total_sales': total,
        'sales_count': count,
        'sales': sales,
        'products': products,
    }
    return render(request, 'pos_app/monthly_report.html', context)

@login_required
@user_passes_test(is_admin)  # only superuser or Admin group
def pending_deletions(request):
    """
    Admin page to review and approve/reject deletion requests.
    """
    # Handle POST actions
    if request.method == 'POST':
        action = request.POST.get('action')
        request_id = request.POST.get('request_id')
        deletion_request = get_object_or_404(DeletionRequest, id=request_id, status='pending')

        if action == 'approve':
            try:
                if deletion_request.object_type == 'product':
                    product = Product.objects.get(id=deletion_request.object_id)
                    product.delete()
                elif deletion_request.object_type == 'sale':
                    sale = Sale.objects.get(id=deletion_request.object_id)
                    if sale.payment_status == 'paid':
                        for item in sale.items.all():
                            product = item.product
                            product.quantity_in_stock += item.quantity
                            product.save()
                    sale.delete()
                deletion_request.status = 'approved'
                deletion_request.approved_by = request.user
                deletion_request.approved_at = timezone.now()
                deletion_request.save()
                messages.success(request, f"Approved deletion of {deletion_request.object_repr}")
            except (Product.DoesNotExist, Sale.DoesNotExist):
                messages.error(request, f"Object {deletion_request.object_repr} no longer exists.")
                deletion_request.status = 'rejected'
                deletion_request.save()
            except ProtectedError:
                messages.error(request, f"Cannot delete {deletion_request.object_repr} – it is referenced elsewhere.")
                deletion_request.status = 'rejected'
                deletion_request.save()

        elif action == 'reject':
            deletion_request.status = 'rejected'
            deletion_request.approved_by = request.user
            deletion_request.approved_at = timezone.now()
            deletion_request.save()
            messages.success(request, f"Rejected deletion of {deletion_request.object_repr}")

        return redirect('pending_deletions')

    # GET: list pending requests
    requests = DeletionRequest.objects.filter(status='pending').order_by('-requested_at')
    return render(request, 'pos_app/pending_deletions.html', {'requests': requests})