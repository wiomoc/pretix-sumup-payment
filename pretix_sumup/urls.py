from django.urls import include, re_path

from pretix_sumup.views import checkout_event, ReturnView

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
