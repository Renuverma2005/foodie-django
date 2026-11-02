
import logging
import re
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods

from .models import Category, ContactMessage, Food, Order, OrderItem

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum


User = get_user_model()
logger = logging.getLogger(__name__)

DELIVERY_FEE = Decimal("40.00")


# =========================================================
# HOME PAGE
# =========================================================

def home(request):
    categories = Category.objects.all().order_by("name")

    popular_foods = (
        Food.objects.filter(is_available=True)
        .select_related("category")
        .order_by("-id")
    )

    selected_category = None
    category_id = request.GET.get("category")

    if category_id:
        try:
            selected_category = get_object_or_404(
                Category,
                id=int(category_id),
            )
            popular_foods = popular_foods.filter(
                category=selected_category,
            )
        except (ValueError, TypeError):
            selected_category = None

    context = {
        "categories": categories,
        "popular_foods": popular_foods,
        "selected_category": selected_category,
    }

    return render(request, "home.html", context)


# =========================================================
# FOOD DETAIL PAGE
# =========================================================

def food_detail(request, food_id):
    food = get_object_or_404(
        Food.objects.select_related("category"),
        id=food_id,
        is_available=True,
        category__is_active=True,
    )

    related_foods = (
        Food.objects.filter(
            category=food.category,
            is_available=True,
            category__is_active=True,
        )
        .exclude(id=food.id)
        .select_related("category")[:4]
    )

    return render(
        request,
        "food_detail.html",
        {
            "food": food,
            "related_foods": related_foods,
        },
    )


# =========================================================
# CUSTOM ADMIN DASHBOARD
# =========================================================

def staff_required(user):
    return user.is_authenticated and user.is_active and user.is_staff


@user_passes_test(staff_required, login_url="/admin/login/")
def admin_dashboard(request):
    context = {
        "total_foods": Food.objects.count(),
        "available_foods": Food.objects.filter(
            is_available=True
        ).count(),
        "total_categories": Category.objects.count(),
        "total_users": User.objects.count(),
        "recent_foods": (
            Food.objects.select_related("category")
            .order_by("-created_at")[:5]
        ),
    }

    return render(request, "admin_dashboard.html", context)


# =========================================================
# ADD FOOD TO CART
# =========================================================

def add_to_cart(request, food_id):
    food = get_object_or_404(
        Food,
        id=food_id,
        is_available=True,
    )

    cart_data = request.session.get("cart", {})

    if not isinstance(cart_data, dict):
        cart_data = {}

    food_id = str(food.id)

    try:
        quantity = max(1, int(request.POST.get("quantity", 1)))
    except (TypeError, ValueError):
        quantity = 1

    existing = cart_data.get(food_id, {})

    if isinstance(existing, dict):
        try:
            old_quantity = max(0, int(existing.get("quantity", 1)))
        except (TypeError, ValueError):
            old_quantity = 1
    else:
        try:
            old_quantity = max(0, int(existing))
        except (TypeError, ValueError):
            old_quantity = 0

    cart_data[food_id] = {
        "quantity": old_quantity + quantity
    }

    request.session["cart"] = cart_data
    request.session.modified = True

    return redirect("cart")


# =========================================================
# CART PAGE
# =========================================================

def cart(request):
    cart_data = request.session.get("cart", {})

    cart_items = []
    total = Decimal("0.00")

    if not isinstance(cart_data, dict):
        cart_data = {}

    for food_id, details in cart_data.items():
        try:
            if isinstance(details, dict):
                quantity = int(details.get("quantity", 1))
            else:
                quantity = int(details)

            if quantity < 1:
                continue

            food = Food.objects.filter(
                id=int(str(food_id).split("_")[-1]),
                is_available=True,
            ).first()

        except (ValueError, TypeError):
            continue

        if food is None:
            continue

        item_total = food.price * quantity
        total += item_total

        cart_items.append({
            "food": food,
            "quantity": quantity,
            "item_total": item_total,
        })

    delivery_fee = (
        Decimal("30.00") if cart_items else Decimal("0.00")
    )

    tax = (total * Decimal("0.05")).quantize(
        Decimal("0.01")
    )

    grand_total = total + delivery_fee + tax

    return render(request, "cart.html", {
        "cart_items": cart_items,
        "total": total,
        "delivery_fee": delivery_fee,
        "tax": tax,
        "grand_total": grand_total,
    })


# =========================================================
# INCREASE / DECREASE CART QUANTITY
# =========================================================

def update_cart(request, food_id, action):
    if request.method == "POST":
        cart_data = request.session.get("cart", {})

        if not isinstance(cart_data, dict):
            cart_data = {}

        food_id = str(food_id)

        if food_id in cart_data:
            details = cart_data[food_id]

            try:
                if isinstance(details, dict):
                    quantity = max(
                        1,
                        int(details.get("quantity", 1)),
                    )
                else:
                    quantity = max(1, int(details))
            except (TypeError, ValueError):
                quantity = 1

            if action == "increase":
                cart_data[food_id] = {
                    "quantity": quantity + 1
                }

            elif action == "decrease":
                if quantity > 1:
                    cart_data[food_id] = {
                        "quantity": quantity - 1
                    }
                else:
                    cart_data.pop(food_id, None)

            request.session["cart"] = cart_data
            request.session.modified = True

    return redirect("cart")


# =========================================================
# REMOVE FOOD FROM CART
# =========================================================

def remove_from_cart(request, food_id):
    if request.method == "POST":
        cart_data = request.session.get("cart", {})

        if isinstance(cart_data, dict):
            cart_data.pop(str(food_id), None)
            request.session["cart"] = cart_data
            request.session.modified = True

    return redirect("cart")


# =========================================================
# CHECKOUT CART CALCULATION
# =========================================================

def get_checkout_cart(request):
    """
    Supports both cart formats:

    {"1": 2, "2": 1}

    {"1": {"quantity": 2}, "2": {"quantity": 1}}
    """

    cart_data = request.session.get("cart", {})
    items = []
    subtotal = Decimal("0.00")

    if not isinstance(cart_data, dict):
        return items, subtotal

    for key, value in cart_data.items():
        try:
            food_id = int(str(key).split("_")[-1])

            if isinstance(value, dict):
                quantity = int(value.get("quantity", 1))
            else:
                quantity = int(value)

            if quantity < 1:
                continue

        except (ValueError, TypeError):
            continue

        food = Food.objects.filter(
            pk=food_id,
            is_available=True,
        ).first()

        if food is None:
            continue

        line_total = food.price * quantity
        subtotal += line_total

        items.append({
            "food": food,
            "quantity": quantity,
            "line_total": line_total,
        })

    return items, subtotal


# =========================================================
# CHECKOUT PAGE AND ORDER CREATION
# =========================================================

def checkout(request):
    cart_items, subtotal = get_checkout_cart(request)

    if not cart_items:
        messages.warning(
            request,
            "Your cart is empty. Please add food before checkout.",
        )
        return redirect("cart")

    delivery_fee = DELIVERY_FEE
    total = subtotal + delivery_fee

    # POST request: form submit hone par
    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip()
        email = request.POST.get("email", "").strip()
        phone = request.POST.get("phone", "").strip()
        address = request.POST.get("address", "").strip()
        city = request.POST.get("city", "").strip()
        state = request.POST.get("state", "").strip()
        pincode = request.POST.get("pincode", "").strip()
        notes = request.POST.get("notes", "").strip()

        payment_method = request.POST.get(
            "payment_method", "cod"
        ).strip().lower()

        errors = []

        if not all([
            full_name, email, phone, address,
            city, state, pincode,
        ]):
            errors.append(
                "Please complete all required delivery fields."
            )

        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            errors.append("Enter a valid email address.")

        if not re.fullmatch(r"[6-9]\d{9}", phone):
            errors.append(
                "Enter a valid 10-digit Indian mobile number."
            )

        if not re.fullmatch(r"\d{6}", pincode):
            errors.append("Enter a valid 6-digit PIN code.")

        if payment_method not in ("cod", "online"):
            errors.append("Please select a valid payment method.")

        if errors:
            for error in errors:
                messages.error(request, error)

            return render(request, "checkout.html", {
                "cart_items": cart_items,
                "subtotal": subtotal,
                "delivery_fee": delivery_fee,
                "total": total,
            })

        try:
            with transaction.atomic():
                order = Order.objects.create(
                    customer=(
                        request.user
                        if request.user.is_authenticated
                        else None
                    ),
                    full_name=full_name,
                    email=email,
                    phone=phone,
                    address=address,
                    city=city,
                    state=state,
                    pincode=pincode,
                    notes=notes,
                    payment_method=payment_method,
                    payment_status="pending",
                    status="pending",
                    subtotal=subtotal,
                    delivery_fee=delivery_fee,
                    total=total,
                )

                for item in cart_items:
                    food = item["food"]

                    OrderItem.objects.create(
                        order=order,
                        food=food,
                        food_name=food.name,
                        unit_price=food.price,
                        quantity=item["quantity"],
                        line_total=item["line_total"],
                    )

        except Exception:
            logger.exception("Could not create Foodie order.")

            messages.error(
                request,
                "We could not place your order. Please try again.",
            )

            return render(request, "checkout.html", {
                "cart_items": cart_items,
                "subtotal": subtotal,
                "delivery_fee": delivery_fee,
                "total": total,
            })

        # Order successfully create ho gaya
        request.session["last_order_number"] = str(
            order.order_number
        )

        # Online payment page
        if payment_method == "online":
            request.session["pending_payment_order"] = str(
                order.order_number
            )
            request.session.modified = True

            return redirect(
                "payment",
                order_number=order.order_number,
            )

        # Cash on Delivery
        request.session["cart"] = {}
        request.session.modified = True

        return redirect(
            "order_confirmation",
            order_number=order.order_number,
        )

    # GET request: checkout page display karein
    return render(request, "checkout.html", {
        "cart_items": cart_items,
        "subtotal": subtotal,
        "delivery_fee": delivery_fee,
        "total": total,
    })


# =========================================================
# DEMO ONLINE PAYMENT PAGE
# =========================================================

@require_http_methods(["GET", "POST"])
def payment(request, order_number):
    if request.session.get("pending_payment_order") != str(
        order_number
    ):
        messages.error(request, "Invalid payment request.")
        return redirect("home")

    order = get_object_or_404(
        Order,
        order_number=order_number,
    )

    if order.payment_method != "online":
        messages.error(request, "Invalid payment method.")
        return redirect("home")

    if order.payment_status == "paid":
        return redirect(
            "order_confirmation",
            order_number=order.order_number,
        )

    if request.method == "POST":
        action = request.POST.get("payment_action", "")

        if action == "cancel":
            messages.info(
                request,
                "Payment was not completed. Your order remains pending.",
            )

            return redirect(
                "order_confirmation",
                order_number=order.order_number,
            )

        if action == "pay":
            messages.warning(
                request,
                "Online payment is not connected yet. "
                "No money has been charged.",
            )

    return render(request, "payment.html", {
        "order": order,
    })


# =========================================================
# ORDER CONFIRMATION PAGE
# =========================================================

def order_confirmation(request, order_number):
    if request.session.get("last_order_number") != str(
        order_number
    ):
        messages.error(
            request,
            "Order confirmation is unavailable.",
        )
        return redirect("home")

    order = get_object_or_404(
        Order.objects.prefetch_related("items"),
        order_number=order_number,
    )

    return render(request, "order_confirmation.html", {
        "order": order,
    })


# =========================================================
# FOOD MENU PAGE
# =========================================================

def food_menu(request):
    foods = (
        Food.objects.filter(is_available=True)
        .select_related("category")
        .order_by("-id")
    )

    categories = Category.objects.all()

    category_id = request.GET.get("category", "")

    if category_id:
        foods = foods.filter(category_id=category_id)

    search_query = request.GET.get("q", "").strip()

    if search_query:
        foods = foods.filter(
            Q(name__icontains=search_query)
            | Q(short_description__icontains=search_query)
        )

    sort_by = request.GET.get("sort", "")

    if sort_by == "price_low":
        foods = foods.order_by("price")
    elif sort_by == "price_high":
        foods = foods.order_by("-price")
    elif sort_by == "name":
        foods = foods.order_by("name")

    context = {
        "foods": foods,
        "categories": categories,
        "selected_category": category_id,
        "search_query": search_query,
        "sort_by": sort_by,
    }

    return render(request, "food_menu.html", context)


# =========================================================
# FOOD SEARCH SUGGESTIONS
# =========================================================

def food_suggestions(request):
    query = request.GET.get("q", "").strip()

    if not query:
        return JsonResponse({"foods": []})

    foods = (
        Food.objects.filter(
            is_available=True,
            category__is_active=True,
        )
        .filter(
            Q(name__icontains=query)
            | Q(category__name__icontains=query)
        )
        .order_by("name")[:8]
    )

    results = []

    for food in foods:
        results.append({
            "id": food.id,
            "name": food.name,
            "price": str(food.price),
            "image": food.image.url if food.image else "",
        })

    return JsonResponse({"foods": results})


# =========================================================
# ABOUT PAGE
# =========================================================

def about(request):
    context = {
        "category_count": Category.objects.filter(
            is_active=True
        ).count(),
        "food_count": Food.objects.filter(
            is_available=True
        ).count(),
    }

    return render(request, "about.html", context)


# =========================================================
# CONTACT PAGE
# =========================================================

def contact(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip()
        subject = request.POST.get("subject", "").strip()
        message = request.POST.get("message", "").strip()

        if name and email and subject and message:
            ContactMessage.objects.create(
                name=name,
                email=email,
                subject=subject,
                message=message,
            )

            messages.success(
                request,
                "Thank you! Your message has been sent successfully.",
            )

            return redirect("contact")

        messages.error(
            request,
            "Please fill in all the fields.",
        )

    return render(request, "contact.html")





# my order .html page start here


from django.contrib.auth.decorators import login_required
from .models import Order


@login_required
def my_orders(request):
    orders = (
        Order.objects
        .filter(customer=request.user)
        .prefetch_related("items")
        .order_by("-id")
    )

    return render(
        request,
        "my_orders.html",
        {"orders": orders},
    )
    
    
    



# login.html page start here

from django.contrib.auth import authenticate, login

def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:
            login(request, user)
            return redirect("home")
        else:
            messages.error(
                request,
                "Invalid username or password."
            )

    return render(request, "login.html")





# regiter.html page start here

def register_view(request):
    User = get_user_model()

    if request.method == "POST":
        name = request.POST.get("first_name", "").strip()
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password1 = request.POST.get("password1", "")
        password2 = request.POST.get("password2", "")

        errors = []

        if not name or not username or not email:
            errors.append("Please fill in all required fields.")

        if User.objects.filter(username=username).exists():
            errors.append("Username already exists.")

        if User.objects.filter(email=email).exists():
            errors.append("Email already registered.")

        if password1 != password2:
            errors.append("Passwords do not match.")

        if len(password1) < 8:
            errors.append("Password must be at least 8 characters.")

        if errors:
            return render(request, "register.html", {
                "form_errors": errors,
                "entered_name": name,
                "entered_username": username,
                "entered_email": email,
            })

        User.objects.create_user(
            username=username,
            email=email,
            password=password1,
            first_name=name,
        )

        messages.success(
            request,
            "Account created successfully! Please log in."
        )

        return redirect("login")

    return render(request, "register.html")




# viwes.html page start here


@staff_member_required(login_url='/login/')
def overview(request):

    User = get_user_model()

    total_orders = Order.objects.count()

    total_foods = Food.objects.count()

    total_customers = User.objects.filter(
        is_staff=False,
        is_superuser=False
    ).count()

    pending_orders = Order.objects.filter(
        status__iexact='pending'
    ).count()

    confirmed_orders = Order.objects.filter(
        status__iexact='confirmed'
    ).count()

    delivered_orders = Order.objects.filter(
        status__iexact='delivered'
    ).count()

    cancelled_orders = Order.objects.filter(
        status__iexact='cancelled'
    ).count()

    total_revenue = Order.objects.filter(
        status__iexact='delivered'
    ).aggregate(
        total=Sum('total')
    )['total'] or 0

    recent_orders = Order.objects.order_by(
        '-created_at'
    )[:5]

    context = {
        'total_orders': total_orders,
        'total_foods': total_foods,
        'total_customers': total_customers,
        'pending_orders': pending_orders,
        'confirmed_orders': confirmed_orders,
        'delivered_orders': delivered_orders,
        'cancelled_orders': cancelled_orders,
        'total_revenue': total_revenue,
        'recent_orders': recent_orders,
    }

    return render(request, 'overview.html', context)