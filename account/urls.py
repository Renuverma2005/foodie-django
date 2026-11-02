
from django.urls import path
# from django.contrib.auth.views import LoginView, LogoutView

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    
    path("food/<int:food_id>/", views.food_detail, name="food_detail"),
    
    
    path("dashboard/", views.admin_dashboard, name="admin_dashboard"),


    # Cart page
    path("cart/", views.cart, name="cart"),

    # Add food to cart
    path("add-to-cart/<int:food_id>/",views.add_to_cart,name="cart_add"),

    # Increase and decrease quantity
    path("cart/update/<int:food_id>/<str:action>/",views.update_cart,name="update_cart"),

    # Remove food from cart
    path( "cart/remove/<int:food_id>/", views.remove_from_cart, name="remove_from_cart"),
    
    
    
    path('food-menu/', views.food_menu, name='food_menu'),
    
    path("about/", views.about, name="about"),
    
    
    path("contact/", views.contact, name="contact"),
    

    # Keep your existing home, cart and food URLs here.

    path("checkout/", views.checkout, name="checkout"),

     path("payment/", views.payment, name="payment"),


    path( "order-confirmation/<uuid:order_number>/", views.order_confirmation, name="order_confirmation", ),
    
    
    path("my-orders/", views.my_orders, name="my_orders"),
    
    
    
    path("login/", views.login_view, name="login"),
    
    
    path("register/", views.register_view, name="register"),
    
    path( 'overview/', views.overview, name='overview'),
]




    
   




