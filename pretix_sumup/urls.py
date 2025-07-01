from django.urls import re_path

from pretix_sumup.views import ReturnView, checkout_event

event_patterns = [
    re_path(
        r"^sumup/checkout_event/(?P<payment>[^/]+)$",
        checkout_event,
        name="checkout_event",
    ),
    re_path(
        r"^sumup/return/(?P<order>[^/]+)/(?P<hash>[^/]+)/(?P<payment>[0-9]+)/$",
        ReturnView.as_view(),
        name="return",
    ),
]
