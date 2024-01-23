from django.urls import re_path

from pretix_sumup.views import checkout_event, payment_widget

event_patterns = [
    re_path(
        r"^sumup/checkout_event/(?P<payment>[^/]+)$",
        checkout_event,
        name="checkout_event",
    ),
    re_path(
        r"^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/sumup/payment_widget/(?P<payment>[^/]+)$",
        payment_widget,
        name="payment_widget",
    ),
]
