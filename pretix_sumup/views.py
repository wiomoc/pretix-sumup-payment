from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
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
