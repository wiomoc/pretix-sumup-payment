from django.urls import re_path

from pretix_sumup.payment import checkout_event, payment_widget

event_patterns = [
    re_path(
        r"^sumup/checkout_event/(?P<payment>[^/]+)$",
        checkout_event,
        name="checkout_event",
    ),
    re_path(
        r"^sumup/payment_widget/(?P<payment>[^/]+)$",
        payment_widget,
        name="payment_widget",
    ),
]
