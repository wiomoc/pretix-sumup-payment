from django.dispatch import receiver
from django.http import HttpRequest, HttpResponse
from pretix.base.middleware import _merge_csp, _parse_csp, _render_csp
from pretix.base.signals import register_payment_providers
from pretix.presale.signals import process_response


@receiver(register_payment_providers, dispatch_uid="sumup_payment")
def register_payment_provider(sender, **kwargs):
    from .payment import SumUp

    return SumUp


@receiver(process_response, dispatch_uid="sumup_csp_middleware_resp")
def signal_process_response(
    sender, request: HttpRequest, response: HttpResponse, **kwargs
):
    sumup_csp_nonce = request.__dict__.get("sumup_csp_nonce")
    # Only append csp policies if this was requested by the provider
    if not sumup_csp_nonce:
        return response

    if "Content-Security-Policy" in response:
        h = _parse_csp(response["Content-Security-Policy"])
    else:
        h = {}

    csps = {
        "default-src": ["*.sumup.com"],
        "script-src": [
            f"'nonce-{sumup_csp_nonce}'",
            "'unsafe-inline'",  # Required by Google Pay
            "*.sumup.com",
            "pay.google.com",
            "apis.google.com",
            "*.gstatic.com",
            "*.google.com",
        ],
        "style-src": [
            f"'nonce-{sumup_csp_nonce}'",
            "'unsafe-inline'",  # Required by Google Pay
            "*.sumup.com",
            "pay.google.com",
            "*.gstatic.com",
        ],
        "frame-src": [
            "*",  # sumup may due to 3DS verification load a site from the bank of the customer
        ],
        "img-src": [
            "*.sumup.com",
            "pay.google.com",
            "*.gstatic.com",
            "*.googleusercontent.com",
            "data:",
        ],
        "connect-src": [
            "*.sumup.com",
            "pay.google.com",
            "cdn.optimizely.com",
            "apis.google.com",
        ],
    }

    _merge_csp(h, csps)

    if h:
        response["Content-Security-Policy"] = _render_csp(h)

    return response
