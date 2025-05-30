from django.urls import re_path

from pretix_sumup.views import checkout_event

event_patterns = [
    re_path(
        r"^sumup/checkout_event/(?P<payment>[^/]+)$",
        checkout_event,
        name="checkout_event",
    ),
]
