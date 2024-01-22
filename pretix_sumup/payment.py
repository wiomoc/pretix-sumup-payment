import logging
from collections import OrderedDict
from django import forms
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import get_template
from django.template.response import TemplateResponse
from django.utils.safestring import SafeString
from django.utils.translation import gettext_lazy as _
from pretix.base.forms import SecretKeySettingsField
from pretix.base.models import OrderPayment, OrderRefund
from pretix.base.payment import BasePaymentProvider, PaymentException
from pretix.multidomain.urlreverse import build_absolute_uri, eventreverse
from pretix.plugins.stripe.forms import StripeKeyValidator

from pretix_sumup.sumup_client import (
    cancel_checkout,
    create_checkout,
    get_checkout,
    get_transaction_by_code,
    refund_transaction,
    validate_access_token_and_get_merchant_code,
)

logger = logging.getLogger("pretix.plugins.sumup")


class SumUp(BasePaymentProvider):
    identifier = "sumup"
    verbose_name = "SumUp"
    abort_pending_allowed = True

    @property
    def settings_form_fields(self):
        d = OrderedDict(
            [
                (
                    "access_token",
                    SecretKeySettingsField(
                        label=_("API Key"),
                        required=True,
                        help_text="API keys are authorization tokens that allow pretix to call SumUp on your behalf. "
                        '<a href="https://developer.sumup.com/api-keys" target="_blank">Click here to '
                        "manage API Keys in SumUp</a>",
                        validators=(StripeKeyValidator("sup_sk_"),),
                    ),
                ),
                (
                    "merchant_code",
                    forms.CharField(
                        widget=forms.TextInput(
                            attrs={
                                "maxlength": 10,
                                "readonly": "readonly",
                                "placeholder": "Automatically filled in",
                            }
                        ),
                        label=_("Merchant Code"),
                    ),
                ),
            ]
            + list(super().settings_form_fields.items())
        )

        d.move_to_end("_enabled", last=False)
        return d

    def settings_form_clean(self, cleaned_data):
        cleaned_data = super().settings_form_clean(cleaned_data)
        access_token = cleaned_data.get("payment_sumup_access_token")
        if access_token is None:
            # access token was already validated and turned out to be invalid
            return cleaned_data
        merchant_code = validate_access_token_and_get_merchant_code(access_token)
        cleaned_data["payment_sumup_merchant_code"] = merchant_code
        return cleaned_data

    def is_allowed(self, request, total=None):
        if total is None:
            return True
        # minimum amount is 1 EUR or similar in other currencies
        return total >= 1

    def execute_payment(self, request, payment):
        payment_id = payment.local_id
        order = payment.order
        event = order.event

        has_valid_checkout = self.synchronize_payment_status(payment)
        if has_valid_checkout:
            return
        try:
            checkout_id = create_checkout(
                checkout_reference=f"{event.slug}/{order.code}/{payment_id}",
                amount=payment.amount,
                currency=event.currency,
                merchant_code=self.settings.get("merchant_code"),
                return_url=build_absolute_uri(
                    event,
                    "plugins:pretix_sumup:checkout_event",
                    kwargs={"payment": payment.pk},
                ),
                access_token=self.settings.get("access_token"),
            )

            info_data = payment.info_data
            info_data["sumup_checkout_id"] = checkout_id
            payment.info_data = info_data
            payment.save()
        except Exception as err:
            payment.fail(info={"error": str(err)})
            logger.exception(f"Error while creating sumup checkout: {err}")
            raise PaymentException("Error while creating sumup checkout")

    def checkout_confirm_render(self, request, **kwargs):
        return "After confirmation you will be redirected to SumUp to complete the payment."

    def payment_form_render(self, request, **kwargs):
        return self.checkout_confirm_render(request, **kwargs)

    def payment_pending_render(self, request, payment):
        checkout_id = payment.info_data["sumup_checkout_id"]
        if checkout_id is None:
            return ""

        # Synchronize the payment status as backup if the return webhook fails
        self.synchronize_payment_status(payment)

        return SafeString(
            '<iframe src="{}" width="100%" height="630" frameBorder=0>'.format(
                eventreverse(
                    payment.order.event,
                    "plugins:pretix_sumup:payment_widget",
                    kwargs={"payment": payment.pk},
                )
            )
        )

    def payment_is_valid_session(self, request):
        return True

    def synchronize_payment_status(self, payment, force=False):
        """
        Synchronizes the payment status with the SumUp Checkout.
        :param force: True if the payment status should be synchronized even if it is already confirmed
        :param payment: The OrderPayment object to synchronize
        :return: True if a SumUp checkout exists which hasn't failed, False if no checkout exists or the checkout has failed
        """
        checkout_id = payment.info_data.get("sumup_checkout_id")
        if not checkout_id:
            return False
        if not force:
            if payment.state == OrderPayment.PAYMENT_STATE_CONFIRMED:
                return True
        try:
            checkout = get_checkout(checkout_id, self.settings.get("access_token"))
        except Exception as err:
            logger.exception(f"Error while synchronizing sumup checkout: {err}")
            raise PaymentException("Error while synchronizing sumup checkout")
        if checkout["status"] == "PAID":
            if not payment.state == OrderPayment.PAYMENT_STATE_CONFIRMED:
                transaction_codes = [
                    transaction["transaction_code"]
                    for transaction in checkout["transactions"]
                    if transaction["status"] == "SUCCESSFUL"
                ]

                # split into multiple line is required to invoke the setter of info_data
                info_data = payment.info_data
                info_data["sumup_transaction_codes"] = transaction_codes
                payment.info_data = info_data
                payment.save()

                payment.confirm()
            return True
        elif checkout["status"] == "PENDING":
            if not payment.state == OrderPayment.PAYMENT_STATE_PENDING:
                payment.state = OrderPayment.PAYMENT_STATE_PENDING
                payment.save(update_fields=["state"])
            return True
        elif checkout["status"] == "FAILED":
            if not payment.state == OrderPayment.PAYMENT_STATE_FAILED:
                payment.fail()
            return False

    def cancel_payment(self, payment):
        checkout_id = payment.info_data.get("sumup_checkout_id")
        if checkout_id:
            try:
                cancel_checkout(checkout_id, self.settings.get("access_token"))
            except Exception as err:
                logger.warn(f"Error while canceling sumup checkout: {err}")
                pass  # Ignore errors, the checkout might already be cancelled
        super().cancel_payment(payment)

    def payment_refund_supported(self, payment):
        return True

    def payment_partial_refund_supported(self, payment):
        return True

    def execute_refund(self, refund):
        payment = refund.payment
        has_valid_checkout = self.synchronize_payment_status(payment)
        sumup_transaction_codes = payment.info_data.get("sumup_transaction_codes")
        if not has_valid_checkout:
            return
        try:
            total_refunded_amount = float(refund.amount)
            for transaction_code in sumup_transaction_codes:
                transaction = get_transaction_by_code(
                    transaction_code, self.settings.get("access_token")
                )
                if transaction["status"] != "SUCCESSFUL":
                    continue
                # TODO double check if there is really the option of multiple successful transactions
                amount = None
                if total_refunded_amount is not None:
                    if total_refunded_amount <= 0:
                        break
                    amount = min(transaction["amount"], total_refunded_amount)
                    total_refunded_amount -= amount
                refund_transaction(
                    transaction_id=transaction["id"],
                    amount=amount,
                    access_token=self.settings.get("access_token"),
                )
            refund.done()
        except Exception as err:
            logger.exception(f"Error while refunding sumup transaction: {err}")
            refund.state = OrderRefund.REFUND_STATE_FAILED
            refund.save(update_fields=["state"])
            raise PaymentException("Error while refunding sumup transaction")

    def _get_transaction(self, payment):
        transaction_codes = payment.info_data.get("sumup_transaction_codes")
        if not transaction_codes or len(transaction_codes) == 0:
            return None
        try:
            return get_transaction_by_code(
                transaction_codes[0], self.settings.get("access_token")
            )
        except Exception as err:
            logger.warn(f"Error while getting sumup transaction: {err}")
            return None

    def render_invoice_text(self, order, payment):
        transaction = self._get_transaction(payment)
        if not transaction:
            return ""
        return "Payed via SumUp\n {} **** **** **** {}\n Auth code: {}".format(
            transaction["card"]["type"],
            transaction["card"]["last_4_digits"],
            transaction["auth_code"],
        )

    def payment_presale_render(self, payment):
        transaction = self._get_transaction(payment)
        if not transaction:
            return ""

        return get_template("pretix_sumup/payment_admin_info.html").render(
            {
                "auth_code": transaction["auth_code"],
                "card_type": transaction["card"]["type"],
                "card_last_4_digit": transaction["card"]["last_4_digits"],
                "transaction_code": transaction["transaction_code"],
                "merchant_code": transaction["merchant_code"],
            }
        )

    def payment_control_render(self, order, payment):
        return self.payment_presale_render(payment)

    def matching_id(self, payment):
        transaction_codes = payment.info_data.get("sumup_transaction_codes")
        if not transaction_codes or len(transaction_codes) == 0:
            return None
        return transaction_codes[0]

    def api_payment_details(self, payment):
        return {"sumup_transaction_code": self.matching_id(payment)}


def checkout_event(request, *args, **kwargs):
    provider = SumUp(request.event)
    order_payment = get_object_or_404(
        OrderPayment, pk=kwargs.get("payment"), order__event=request.event
    )
    provider.synchronize_payment_status(order_payment)
    return HttpResponse(status=204, content=b"")


def payment_widget(request, *args, **kwargs):
    provider = SumUp(request.event)
    order_payment = get_object_or_404(
        OrderPayment, pk=kwargs.get("payment"), order__event=request.event
    )
    # Synchronize the payment status as backup if the return webhook fails
    provider.synchronize_payment_status(order_payment)
    checkout_id = order_payment.info_data.get("sumup_checkout_id")
    if not checkout_id:
        raise ValidationError(_("No SumUp checkout ID found."))

    csp_header = {
        "Content-Security-Policy": "default-src *.sumup.com; "
        "script-src 'unsafe-inline' *.sumup.com; "
        "style-src 'unsafe-inline', *.sumup.com; "
        "frame-src *; "
        "img-src *.sumup.com; "
        "connect-src *.sumup.com; "
        "frame-ancestors 'self'"
    }
    if (
        order_payment.state == OrderPayment.PAYMENT_STATE_PENDING
        or order_payment.state == OrderPayment.PAYMENT_STATE_FAILED
    ):
        context = {
            "checkout_id": checkout_id,
            "retry": order_payment.state == OrderPayment.PAYMENT_STATE_FAILED,
        }
    elif order_payment.state == OrderPayment.PAYMENT_STATE_CONFIRMED:
        # The payment was paid in the meantime, reload the containing page to show the success message
        context = {"reload": True}
    else:
        return HttpResponse(status=204, content=b"")
    return TemplateResponse(
        template="pretix_sumup/payment_widget.html",
        context=context,
        request=request,
        headers=csp_header,
    )
