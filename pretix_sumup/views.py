from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import View
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from pretix.base.models import Order, OrderPayment
from pretix.multidomain.urlreverse import eventreverse
from pretix.helpers.http import redirect_to_url

from pretix_sumup.payment import SumUp


class ReturnView(View):
    """
    View to handle customer return after SumUp payment completion.
    Redirects the customer to their order page.
    """

    def get(self, request, *args, **kwargs):
        try:
            order = get_object_or_404(
                Order, code=kwargs.get("order"), event=request.event
            )
            payment = get_object_or_404(
                OrderPayment, pk=kwargs.get("payment"), order=order
            )

            # Verify the hash matches the order's secret
            if kwargs.get("hash") != order.tagged_secret("plugins:pretix_sumup"):
                messages.error(
                    request,
                    _(
                        "Sorry, there was an error in the payment process. Please check the link in your emails to continue."
                    ),
                )
                return redirect_to_url(
                    eventreverse(request.event, "presale:event.index")
                )

            # Synchronize payment status with SumUp
            provider = SumUp(request.event)
            provider._synchronize_payment_status(payment)

            # Redirect to order page
            return redirect_to_url(
                eventreverse(
                    request.event,
                    "presale:event.order",
                    kwargs={"order": order.code, "secret": order.secret},
                )
                + ("?paid=yes" if order.status == Order.STATUS_PAID else "")
            )

        except Exception as e:
            messages.error(
                request,
                _(
                    "Sorry, there was an error in the payment process. Please check the link in your emails to continue."
                ),
            )
            return redirect_to_url(
                eventreverse(request.event, "presale:event.index")
            )


@csrf_exempt
@require_POST
def checkout_event(request, *args, **kwargs):
    provider = SumUp(request.event)
    order_payment = get_object_or_404(
        OrderPayment, pk=kwargs.get("payment"), order__event=request.event
    )
    provider._synchronize_payment_status(order_payment)
    return HttpResponse(status=204)
