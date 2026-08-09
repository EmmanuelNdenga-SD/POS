from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Sum, Count, Q, Avg
from django.utils import timezone
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm
from django.db.models.deletion import ProtectedError
from django.db import models

from .models import Product, Category, Sale, SaleItem, DeletionRequest
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
    low_stock = Product.objects.filter(quantity_in_stock__lt=10, quantity_in_stock__gt=0).count()
    out_of_stock = Product.objects.filter(quantity_in_stock=0).count()
    
    # Recent sales (last 5)
    recent_sales = Sale.objects.filter(payment_status='paid').order_by('-created_at')[:5]
    
    # Today's stats
    today = timezone.now().date()
    today_sales = Sale.objects.filter(created_at__date=today, payment_status='paid')
    today_sales_count = today_sales.count()
    today_revenue = today_sales.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    
    # Average order value
    avg_order_value = Sale.objects.filter(payment_status='paid').aggregate(
        Avg('total_amount')
    )['total_amount__avg'] or 0
    
    # Total customers
    total_customers = Sale.objects.filter(payment_status='paid').values('customer_name').distinct().count()
    
    context = {
        'total_products': total_products,
        'total_sales': total_sales,
        'total_revenue': total_revenue,
        'pending_sales': pending_sales,
        'low_stock_count': low_stock,
        'out_of_stock_count': out_of_stock,
        'recent_sales': recent_sales,
        'today_sales_count': today_sales_count,
        'today_revenue': today_revenue,
        'avg_order_value': avg_order_value,
        'total_customers': total_customers,
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
    low_stock = Product.objects.filter(quantity_in_stock__lt=10, quantity_in_stock__gt=0).count()
    out_of_stock = Product.objects.filter(quantity_in_stock=0).count()
    total_products = products.count()
    
    context = {
        'products': products,
        'low_stock_count': low_stock,
        'out_of_stock_count': out_of_stock,
        'total_products': total_products,
    }
    return render(request, 'pos_app/staff_dashboard.html', context)

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
                # Deduct stock
                product.quantity_in_stock -= quantity
                product.save()
                
                messages.success(request, f'Sold {quantity} x {product.name} (KSh {price} each).')
                return redirect('staff_dashboard')
            except ValueError as e:
                messages.error(request, str(e))
                sale.delete()
                return redirect('staff_make_sale')
    else:
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
    categories = Category.objects.all()
    
    in_stock_count = products.filter(quantity_in_stock__gt=0).count()
    low_stock_count = products.filter(quantity_in_stock__gt=0, quantity_in_stock__lt=10).count()
    out_of_stock_count = products.filter(quantity_in_stock=0).count()
    
    return render(request, 'pos_app/product_list.html', {
        'products': products,
        'categories': categories,
        'in_stock_count': in_stock_count,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
    })

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
    
    categories = Category.objects.all()
    return render(request, 'pos_app/product_form.html', {
        'form': form, 
        'title': 'Add Product',
        'categories': categories
    })

@login_required
@user_passes_test(is_staff_or_admin)
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
    
    categories = Category.objects.all()
    return render(request, 'pos_app/product_form.html', {
        'form': form, 
        'title': 'Edit Product',
        'product': product,
        'categories': categories
    })

@login_required
@user_passes_test(is_staff_or_admin)
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        if request.user.is_superuser or request.user.groups.filter(name='Admin').exists():
            try:
                product.delete()
                messages.success(request, f"Product '{product.name}' deleted successfully.")
            except ProtectedError:
                messages.error(request, f"Cannot delete '{product.name}' because it has been used in sales.")
        else:
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
    # Handle completing sale (direct submission)
    if request.method == 'POST' and 'complete_sale' in request.POST:
        # Get payment method and status
        payment_method = request.POST.get('payment_method')
        payment_status = request.POST.get('payment_status')
        
        if not payment_method:
            messages.error(request, 'Please select a payment method.')
            return redirect('sale_create')
        
        # Collect products with quantity > 0
        cart_items = []
        total = 0
        
        for key, value in request.POST.items():
            if key.startswith('quantity_') and int(value) > 0:
                product_id = key.replace('quantity_', '')
                qty = int(value)
                
                # Get price type
                price_type_key = f'price_type_{product_id}'
                price_type = request.POST.get(price_type_key, 'retail')
                
                try:
                    product = Product.objects.get(pk=product_id)
                except Product.DoesNotExist:
                    messages.error(request, f'Product not found: ID {product_id}')
                    return redirect('sale_create')
                
                # Get price based on type
                price = product.wholesale_price if price_type == 'wholesale' else product.price
                
                cart_items.append({
                    'product': product,
                    'quantity': qty,
                    'price': price,
                    'price_type': price_type
                })
                total += price * qty
        
        if not cart_items:
            messages.error(request, 'Please add at least one product (quantity > 0).')
            return redirect('sale_create')
        
        try:
            # Create sale
            sale = Sale.objects.create(
                payment_method=payment_method,
                payment_status=payment_status or 'paid',
                created_by=request.user,
                customer_name='Walk-in',
                total_amount=0
            )
            
            # Create sale items and deduct stock
            for item in cart_items:
                # Check stock for paid sales
                if payment_status == 'paid' and item['product'].quantity_in_stock < item['quantity']:
                    messages.error(request, f"Insufficient stock for {item['product'].name}. Available: {item['product'].quantity_in_stock}")
                    sale.delete()
                    return redirect('sale_create')
                
                SaleItem.objects.create(
                    sale=sale,
                    product=item['product'],
                    quantity=item['quantity'],
                    price_at_sale=item['price'],
                    price_type=item['price_type']
                )
                
                # Deduct stock for paid sales
                if payment_status == 'paid':
                    item['product'].quantity_in_stock -= item['quantity']
                    item['product'].save()
            
            sale.total_amount = total
            sale.save()
            
            messages.success(request, f'Sale #{sale.id} created successfully. Total: KSh {total}')
            return redirect('sale_list')
            
        except Exception as e:
            messages.error(request, f'Error creating sale: {str(e)}')
            return redirect('sale_create')
    
    # GET request - display form
    products = Product.objects.all()
    
    context = {
        'products': products,
    }
    return render(request, 'pos_app/sale_form.html', context)

@login_required
@user_passes_test(is_staff_or_admin)
def sale_detail(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    
    # Calculate subtotal for each item
    items = []
    for item in sale.items.all():
        items.append({
            'product': item.product,
            'quantity': item.quantity,
            'price_at_sale': item.price_at_sale,
            'price_type': item.price_type,
            'subtotal': item.quantity * item.price_at_sale
        })
    
    return render(request, 'pos_app/sale_detail.html', {
        'sale': sale,
        'items': items
    })

@login_required
def sale_delete(request, pk):
    """
    Delete a sale directly - Staff and Admin can delete without approval
    No admin approval required - direct deletion with stock restoration
    """
    sale = get_object_or_404(Sale, pk=pk)
    
    # Check if user is staff or admin
    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, 'You do not have permission to delete sales.')
        return redirect('sale_list')
    
    if request.method == 'POST':
        sale_id = sale.id
        customer = sale.customer_name or 'Walk-in'
        items_restored = 0
        
        # Restore stock if sale was paid
        if sale.payment_status == 'paid':
            for item in sale.items.all():
                product = item.product
                product.quantity_in_stock += item.quantity
                product.save()
                items_restored += 1
        
        # Delete the sale (cascades to sale items)
        sale.delete()
        
        if items_restored > 0:
            messages.success(request, f'Sale #{sale_id} for {customer} deleted. {items_restored} product(s) stock restored.')
        else:
            messages.success(request, f'Sale #{sale_id} for {customer} deleted successfully.')
        
        return redirect('sale_list')
    
    return redirect('sale_list')

# ---------- Category CRUD (Staff & Admin) ----------
@login_required
@user_passes_test(is_staff_or_admin)
def category_list(request):
    categories = Category.objects.annotate(product_count=models.Count('products'))
    return render(request, 'pos_app/category_list.html', {'categories': categories})

@login_required
@user_passes_test(is_staff_or_admin)
def category_create(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            # Check if it's an AJAX request (for the modal)
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'id': category.id,
                    'name': category.name,
                })
            # Regular form submission (fallback)
            messages.success(request, f'Category "{category.name}" created successfully.')
            return redirect('product_create')
        else:
            # If AJAX, return errors as JSON
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors,
                }, status=400)
            # Regular form submission with errors
            messages.error(request, 'Please correct the errors below.')
            return redirect('product_create')
    
    # GET request - not expected, but handle gracefully
    return redirect('product_create')

@login_required
@user_passes_test(is_staff_or_admin)
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
    # Get date from query parameter or use today
    date_str = request.GET.get('date')
    if date_str:
        try:
            report_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            report_date = timezone.now().date()
    else:
        report_date = timezone.now().date()
    
    # Date range for the day - use timezone-aware datetimes
    start = timezone.make_aware(datetime.combine(report_date, datetime.min.time()))
    end = timezone.make_aware(datetime.combine(report_date, datetime.max.time()))
    
    # Get sales for the day
    sales = Sale.objects.filter(created_at__range=(start, end), payment_status='paid')
    
    # Total sales and count
    total_sales = sales.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    sales_count = sales.count()
    
    # Average order value
    avg_order = sales.aggregate(Avg('total_amount'))['total_amount__avg'] or 0
    
    # Total items sold
    total_items_sold = SaleItem.objects.filter(sale__in=sales).aggregate(Sum('quantity'))['quantity__sum'] or 0
    
    # Payment method breakdown
    payment_breakdown = []
    payment_methods = ['cash', 'mpesa', 'bank']
    method_labels = {'cash': 'Cash', 'mpesa': 'M-Pesa', 'bank': 'Bank Transfer'}
    
    for method in payment_methods:
        method_sales = sales.filter(payment_method=method)
        method_count = method_sales.count()
        method_total = method_sales.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        
        if method_count > 0 or method_total > 0:
            payment_breakdown.append({
                'method': method,
                'label': method_labels.get(method, method.title()),
                'count': method_count,
                'total': method_total,
                'percentage': round((method_total / total_sales * 100) if total_sales > 0 else 0, 1)
            })
    
    # Top selling products
    top_products = SaleItem.objects.filter(sale__in=sales).values(
        'product__name', 'product__category__name', 'price_type'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_revenue=Sum('price_at_sale') * Sum('quantity')
    ).order_by('-total_quantity')[:10]
    
    # Previous and next dates for navigation
    previous_date = report_date - timedelta(days=1)
    next_date = report_date + timedelta(days=1)
    
    context = {
        'date': report_date,
        'total_sales': total_sales,
        'sales_count': sales_count,
        'avg_order': avg_order,
        'total_items_sold': total_items_sold,
        'sales': sales,
        'payment_breakdown': payment_breakdown,
        'top_products': top_products,
        'previous_date': previous_date.strftime('%Y-%m-%d'),
        'next_date': next_date.strftime('%Y-%m-%d'),
    }
    return render(request, 'pos_app/daily_report.html', context)

@login_required
@user_passes_test(is_staff_or_admin)
def monthly_report(request):
    # Get month from query parameter or use current month
    month_str = request.GET.get('month')
    if month_str:
        try:
            report_date = datetime.strptime(month_str, '%Y-%m').date()
        except ValueError:
            report_date = timezone.now().date()
    else:
        report_date = timezone.now().date()
    
    # Get first day of the month - use timezone-aware datetimes
    start = timezone.make_aware(datetime.combine(report_date.replace(day=1), datetime.min.time()))
    
    # Get last day of the month
    if start.month == 12:
        end = timezone.make_aware(datetime.combine(start.replace(year=start.year+1, month=1, day=1), datetime.min.time())) - timedelta(seconds=1)
    else:
        end = timezone.make_aware(datetime.combine(start.replace(month=start.month+1, day=1), datetime.min.time())) - timedelta(seconds=1)
    
    # Get sales for the month
    sales = Sale.objects.filter(created_at__range=(start, end), payment_status='paid')
    
    # Total sales and count
    total_sales = sales.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    sales_count = sales.count()
    
    # Average order value
    avg_order = sales.aggregate(Avg('total_amount'))['total_amount__avg'] or 0
    
    # Total items sold
    total_items_sold = SaleItem.objects.filter(sale__in=sales).aggregate(Sum('quantity'))['quantity__sum'] or 0
    
    # Customer stats
    total_customers = sales.values('customer_name').distinct().count()
    new_customers = sales.filter(customer_name__isnull=False).values('customer_name').distinct().count()
    repeat_customers = total_customers - new_customers
    
    # Days with sales
    days_with_sales = sales.values('created_at__date').distinct().count()
    days_in_month = (end - start).days + 1
    
    # Best day
    best_day_data = sales.values('created_at__date').annotate(
        daily_total=Sum('total_amount')
    ).order_by('-daily_total').first()
    best_day = best_day_data['created_at__date'] if best_day_data else None
    best_day_total = best_day_data['daily_total'] if best_day_data else 0
    
    # Payment breakdown
    payment_breakdown = []
    payment_methods = ['cash', 'mpesa', 'bank']
    method_labels = {'cash': 'Cash', 'mpesa': 'M-Pesa', 'bank': 'Bank Transfer'}
    
    for method in payment_methods:
        method_sales = sales.filter(payment_method=method)
        method_count = method_sales.count()
        method_total = method_sales.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        
        if method_count > 0 or method_total > 0:
            payment_breakdown.append({
                'method': method,
                'label': method_labels.get(method, method.title()),
                'count': method_count,
                'total': method_total,
                'percentage': round((method_total / total_sales * 100) if total_sales > 0 else 0, 1)
            })
    
    # Retail vs Wholesale
    retail_sales = SaleItem.objects.filter(sale__in=sales, price_type='retail').aggregate(
        total=Sum('price_at_sale') * Sum('quantity')
    )['total'] or 0
    
    wholesale_sales = SaleItem.objects.filter(sale__in=sales, price_type='wholesale').aggregate(
        total=Sum('price_at_sale') * Sum('quantity')
    )['total'] or 0
    
    # Top products
    top_products = SaleItem.objects.filter(sale__in=sales).values(
        'product__name', 'product__category__name', 'price_type'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_revenue=Sum('price_at_sale') * Sum('quantity')
    ).order_by('-total_quantity')[:10]
    
    # Navigation
    prev_month = start - timedelta(days=1)
    next_month = end + timedelta(days=1)
    
    context = {
        'month': start.strftime('%B'),
        'year': start.year,
        'total_sales': total_sales,
        'sales_count': sales_count,
        'avg_order': avg_order,
        'total_items_sold': total_items_sold,
        'total_customers': total_customers,
        'new_customers': new_customers,
        'repeat_customers': repeat_customers,
        'days_with_sales': days_with_sales,
        'days_in_month': days_in_month,
        'best_day': best_day,
        'best_day_total': best_day_total,
        'payment_breakdown': payment_breakdown,
        'retail_sales': retail_sales,
        'wholesale_sales': wholesale_sales,
        'top_products': top_products,
        'sales': sales,
        'previous_month': prev_month.strftime('%Y-%m'),
        'next_month': next_month.strftime('%Y-%m'),
    }
    return render(request, 'pos_app/monthly_report.html', context)

# ---------- Pending Deletions (Admin only) ----------
@login_required
@user_passes_test(is_admin)
def pending_deletions(request):
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

    requests = DeletionRequest.objects.filter(status='pending').order_by('-requested_at')
    return render(request, 'pos_app/pending_deletions.html', {'requests': requests})