


from django.contrib import admin
from .models import Category, Food


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "is_active",
        "created_at",
    )

    list_display_links = ("name",)
    list_filter = ("is_active",)
    search_fields = ("name",)
    list_editable = ("is_active",)
    ordering = ("name",)


@admin.register(Food)
class FoodAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "category",
        "price",
        "old_price",
        "rating",
        "is_popular",
        "is_available",
    )

    list_display_links = ("name",)

    list_filter = (
        "category",
        "is_popular",
        "is_available",
    )

    search_fields = (
        "name",
        "category__name",
    )

    list_editable = (
        "is_popular",
        "is_available",
    )

    list_per_page = 20
    autocomplete_fields = ("category",)



# contact.html pagee start here


from .models import ContactMessage

@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "subject", "created_at")
    search_fields = ("name", "email", "subject")
    list_filter = ("created_at",)
    readonly_fields = ("created_at",)









from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        "food_name",
        "unit_price",
        "quantity",
        "line_total",
    )


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "full_name",
        "phone",
        "payment_method",
        "payment_status",
        "status",
        "total",
        "created_at",
    )

    list_filter = (
        "payment_method",
        "payment_status",
        "status",
        "created_at",
    )

    search_fields = (
        "order_number",
        "full_name",
        "email",
        "phone",
    )

    readonly_fields = (
        "order_number",
        "created_at",
    )

    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "food_name",
        "order",
        "unit_price",
        "quantity",
        "line_total",
    )

    search_fields = (
        "food_name",
        "order__full_name",
        "order__email",
    )
