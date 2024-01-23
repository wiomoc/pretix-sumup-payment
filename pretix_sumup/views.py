from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from pretix.base.middleware import _render_csp, get_language_from_request
from pretix.base.models import OrderPayment

from pretix_sumup.payment import SumUp


@csrf_exempt
@require_POST
def checkout_event(request, *args, **kwargs):
    provider = SumUp(request.event)
    order_payment = get_object_or_404(
        OrderPayment, pk=kwargs.get("payment"), order__event=request.event
    )
    provider._synchronize_payment_status(order_payment)
    return HttpResponse(status=204)


def payment_widget(request, *args, **kwargs):
    provider = SumUp(request.event)
    order_payment = get_object_or_404(
        OrderPayment,
        pk=kwargs.get("payment"),
        order__event=request.event,
        order__code=kwargs.get("order"),
        order__secret=kwargs.get("secret"),
    )
    # Synchronize the payment status as backup if the return webhook fails
    provider._synchronize_payment_status(order_payment)
    checkout_id = order_payment.info_data.get("sumup_checkout_id")
    if not checkout_id:
        raise ValidationError(_("No SumUp checkout ID found."))

    csp_nonce = get_random_string(10)
    csp = {
        "default-src": ["*.sumup.com"],
        "script-src": [f"'nonce-{csp_nonce}'", "*.sumup.com"],
        "style-src": [
            f"'nonce-{csp_nonce}'",
            "*.sumup.com",
            "'unsafe-inline'",  # workaround as sumup don't pass the nonce to the lazy loaded input fields
        ],
        "frame-src": [
            "*"  # sumup may due to 3DS verification load a site from the bank of the customer
        ],
        "img-src": ["*.sumup.com"],
        "connect-src": ["*.sumup.com"],
        "frame-ancestors": ["'self'"],
    }
    csp_header = {"Content-Security-Policy": _render_csp(csp)}
    if (
        order_payment.state == OrderPayment.PAYMENT_STATE_PENDING
        or order_payment.state == OrderPayment.PAYMENT_STATE_FAILED
    ):
        context = {
            "checkout_id": checkout_id,
            "email": order_payment.order.email,
            "retry": order_payment.state == OrderPayment.PAYMENT_STATE_FAILED,
            "locale": _get_sumup_locale(request),
            "csp_nonce": csp_nonce,
        }
    elif order_payment.state == OrderPayment.PAYMENT_STATE_CONFIRMED:
        # The payment was paid in the meantime, reload the containing page to show the success message
        context = {"reload": True, "csp_nonce": csp_nonce}
    else:
        # Invalid state, nothing to see here
        return HttpResponse(status=404)
    return TemplateResponse(
        template="pretix_sumup/payment_widget.html",
        context=context,
        request=request,
        headers=csp_header,
    )


def _get_sumup_locale(request):
    language = get_language_from_request(request)
    if language == "de" or language == "de-informal":
        return "de-DE"
    elif language == "fr":
        return "fr-FR"
    return "en-GB"
