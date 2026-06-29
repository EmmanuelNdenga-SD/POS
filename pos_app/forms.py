from django import forms
from .models import Product, Category, Sale, SaleItem


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'name', 'category', 'description', 'price',
            'wholesale_price', 'quantity_in_stock', 'image'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'wholesale_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'quantity_in_stock': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
        }


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'parent']   # keep both fields
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter category name'}),
            'parent': forms.Select(attrs={'class': 'form-select'}),
        }


class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = ['customer_name', 'payment_method', 'payment_status']
        widgets = {
            'payment_status': forms.Select(choices=Sale.PAYMENT_STATUS),
            'payment_method': forms.Select(choices=Sale.PAYMENT_METHODS),
        }


class SaleItemForm(forms.ModelForm):
    class Meta:
        model = SaleItem
        fields = ['product', 'quantity']
        widgets = {
            'quantity': forms.NumberInput(attrs={'min': 1}),
        }


class RestockForm(forms.Form):
    quantity = forms.IntegerField(min_value=1, label='Units to add')


class StaffSaleForm(forms.Form):
    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(quantity_in_stock__gt=0)
    )
    quantity = forms.IntegerField(min_value=1)
    price_type = forms.ChoiceField(
        choices=SaleItem.PRICE_TYPE_CHOICES,
        initial='retail'
    )
    payment_method = forms.ChoiceField(choices=Sale.PAYMENT_METHODS)
    customer_name = forms.CharField(max_length=100, required=False)