import logging
from collections import OrderedDict
from decimal import Decimal
from django import forms
from django.http import HttpRequest
from django.template.loader import get_template
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _
from pretix.base.forms import SECRET_REDACTED, SecretKeySettingsField
from pretix.base.middleware import get_language_from_request
from pretix.base.models import Order, OrderPayment, OrderRefund
from pretix.base.payment import BasePaymentProvider, PaymentException
from pretix.multidomain.urlreverse import build_absolute_uri
from pretix.plugins.stripe.forms import StripeKeyValidator

from pretix_sumup import sumup_client

logger = logging.getLogger("pretix.plugins.sumup")


class SumUp(BasePaymentProvider):
    identifier = "sumup"
    verbose_name = _("Credit card via SumUp")
    public_name = _("Credit card via SumUp")
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
                        help_text=_(
                            "API keys are authorization tokens that allow pretix to call SumUp on your behalf. "
                            '<a href="https://developer.sumup.com/api-keys" target="_blank">Click here to '
                            "manage API Keys in SumUp</a>"
                        ),
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
                                "placeholder": _("Automatically filled in"),
                            }
                        ),
                        # As the field is required but is autofilled later, we need
                        # some default value that is used internally before we resolve the correct value
                        empty_value="-",
                        label=_("Merchant Code"),
                    ),
                ),
                (
                    "merchant_name",
                    forms.CharField(
                        widget=forms.TextInput(
                            attrs={
                                "readonly": "readonly",
                                "placeholder": _("Automatically filled in"),
                            }
                        ),
                        # As the field is required but is autofilled later, we need
                        # some default value that is used internally before we resolve the correct value
                        empty_value="-",
                        label=_("Merchant Name"),
                    ),
                ),
                (
                    "enable_apms",
                    forms.BooleanField(
                        label=_("Enable Alternative Payment Methods"),
                        required=False,
                        help_text=_(
                            "Allow customers to pay using alternative payment methods like Apple Pay, Google Pay, iDEAL. <br>"
                            "<i>The supported payment methods depend on the country of your SumUp account. </i>"
                            '<i><a href="https://developer.sumup.com/online-payments/apm/introduction" target="_blank">Learn more</a></i> <br>'
                            "<br>"
                            "<i>In order to enable Apple Pay please follow the steps "
                            '<a href="https://developer.sumup.com/settings/wallets" target="_blank">here</a>.</i><br>'
                            "<i>You should add the Apple Developer MerchantID Domain Association file to your Pretix Global settings.</i>"
                        ),
                    ),
                ),
                (
                    "enable_google_pay",
                    forms.BooleanField(
                        label=_("Enable Google Pay"),
                        required=False,
                        help_text=_(
                            "Allow customers to pay using Google Pay.<br>"
                            "<br>"
                            "<i>In order to enable Google Pay, first you need to validate your domain with Google."
                            ' <a href="https://developer.sumup.com/online-payments/apm/google-pay" target="_blank">Learn more</a></i> <br>'
                            "<br>"
                            "<i>To display a test Google Pay button please add the following to the end of your payment URL:</i> <br>"
                            "<code> #sumup-widget:google-pay-demo-mode </code> <br>"
                            "<br>"
                            "<i>Once your domain is verified please reach out to SumUp's Integration Team to activate Google Pay on your merchant"
                            ' account through the <a href="https://developer.sumup.com/contact" target="_blank">SumUp contact form</a>.</i>'
                        ),
                        widget=forms.CheckboxInput(
                            attrs={
                                "data-checkbox-dependency": "#id_payment_sumup_enable_apms",
                            }
                        ),
                    ),
                ),
                (
                    "google_pay_merchant_id",
                    forms.CharField(
                        label=_("Google Pay Merchant ID"),
                        required=False,
                        help_text=_(
                            "The Merchant ID for Google Pay. Must be between 12-18 characters long."
                        ),
                        min_length=12,
                        max_length=18,
                        disabled=False,
                        widget=forms.TextInput(
                            attrs={
                                "data-checkbox-dependency": "#id_payment_sumup_enable_apms"
                            }
                        ),
                    ),
                ),
            ]
            + list(super().settings_form_fields.items())
        )

        d.move_to_end("_enabled", last=False)
        return d

    def settings_form_clean(self, cleaned_data: dict):
        cleaned_data = super().settings_form_clean(cleaned_data)
        errors = {}

        access_token = cleaned_data.get("payment_sumup_access_token")
        if access_token is not None and access_token != SECRET_REDACTED:
            try:
                merchant_name, merchant_code = (
                    sumup_client.validate_access_token_and_get_merchant_code(
                        access_token
                    )
                )
                cleaned_data["payment_sumup_merchant_code"] = merchant_code
                cleaned_data["payment_sumup_merchant_name"] = merchant_name
            except Exception as e:
                errors["payment_sumup_access_token"] = _("Invalid API key: {}").format(
                    str(e)
                )

        # Validate Google Pay settings
        apms_enabled = cleaned_data.get("payment_sumup_enable_apms", False)
        enable_google_pay = (
            cleaned_data.get("payment_sumup_enable_google_pay", False) and apms_enabled
        )

        # Technically this shouldn't be necessary as the form should not allow enabling Google Pay without APMs, but just in case
        if (
            cleaned_data.get("payment_sumup_enable_google_pay", False)
            and not apms_enabled
        ):
            errors["payment_sumup_enable_google_pay"] = _(
                "Google Pay requires Alternative Payment Methods to be enabled first."
            )

        if enable_google_pay:
            merchant_id = cleaned_data.get("payment_sumup_google_pay_merchant_id")
            merchant_name = cleaned_data.get("payment_sumup_merchant_name")

            if not merchant_id:
                errors["payment_sumup_google_pay_merchant_id"] = _(
                    "Google Pay Merchant ID is required when Google Pay is enabled."
                )

            if not merchant_name:
                errors["payment_sumup_merchant_name"] = _(
                    "Merchant Name is required when Google Pay is enabled. Please input your API key again in order to retrieve your Merchant Name."
                )

        if errors:
            raise forms.ValidationError(errors)

        return cleaned_data

    def is_allowed(self, request: HttpRequest, total: Decimal = None):
        if total is None:
            return True
        # minimum amount is 1 EUR or similar in other currencies
        return total >= 1

    def execute_payment(self, request: HttpRequest, payment: OrderPayment):
        payment_id = payment.local_id
        order = payment.order
        event = order.event

        has_valid_checkout = self._synchronize_payment_status(payment)
        if has_valid_checkout:
            return
        try:
            checkout_params = {
                "checkout_reference": f"{event.slug}/{order.code}/{payment_id}",
                "amount": payment.amount,
                "currency": event.currency,
                "description": f"{event.name} #{order.code}",
                "merchant_code": self.settings.get("merchant_code"),
                "return_url": build_absolute_uri(
                    event,
                    "plugins:pretix_sumup:checkout_event",
                    kwargs={"payment": payment.pk},
                ),
                "access_token": self.settings.get("access_token"),
            }

            # Only include redirect_url if enable_apms is True
            if self.settings.get("enable_apms", as_type=bool, default=False):
                checkout_params["redirect_url"] = build_absolute_uri(
                    event,
                    "plugins:pretix_sumup:return",
                    kwargs={
                        "order": order.code,
                        "payment": payment.pk,
                        "hash": order.tagged_secret("plugins:pretix_sumup"),
                    },
                )

            checkout_id = sumup_client.create_checkout(**checkout_params)

            info_data = payment.info_data
            info_data["sumup_checkout_id"] = checkout_id
            payment.info_data = info_data
            payment.save()
        except Exception as err:
            internal_exception_message = f"Error while creating SumUp checkout: {err}"
            payment.fail(info={"error": internal_exception_message})
            logger.exception(internal_exception_message)
            raise PaymentException(_("Error while creating SumUp checkout"))

    def checkout_confirm_render(self, request: HttpRequest, **kwargs):
        return _(
            "After confirmation you will be redirected to SumUp to complete the payment."
        )

    def payment_form_render(self, request: HttpRequest, **kwargs):
        return self.checkout_confirm_render(request, **kwargs)

    def payment_pending_render(self, request: HttpRequest, payment: OrderPayment):
        checkout_id = payment.info_data.get("sumup_checkout_id")
        if checkout_id is None:
            return ""

        # Synchronize the payment status as backup if the return webhook fails
        self._synchronize_payment_status(payment)

        csp_nonce = get_random_string(10)
        # XXX: smuggle csp nonce in http request to our csp middleware signal handler
        request.__dict__["sumup_csp_nonce"] = csp_nonce

        # Check if Google Pay is explicitly enabled for this request
        enable_google_pay = self.settings.get(
            "enable_google_pay", as_type=bool, default=False
        )
        request.__dict__["sumup_enable_google_pay"] = enable_google_pay

        if (
            payment.state == OrderPayment.PAYMENT_STATE_PENDING
            or payment.state == OrderPayment.PAYMENT_STATE_FAILED
        ):
            context = {
                "checkout_id": checkout_id,
                "email": payment.order.email,
                "retry": payment.state == OrderPayment.PAYMENT_STATE_FAILED,
                "locale": self._get_sumup_locale(request),
                "csp_nonce": csp_nonce,
                "google_pay_merchant_id": self.settings.get(
                    "google_pay_merchant_id", ""
                ),
                "merchant_name": self.settings.get("merchant_name", ""),
                "enable_google_pay": enable_google_pay,
            }
        elif payment.state == OrderPayment.PAYMENT_STATE_CONFIRMED:
            # The payment was paid in the meantime, reload the containing page to show the success message
            context = {"reload": True, "csp_nonce": csp_nonce}
        else:
            # Invalid state, nothing to see here
            return ""

        return get_template("pretix_sumup/payment_widget.html").render(context)

    def payment_is_valid_session(self, request: HttpRequest):
        return True

    def cancel_payment(self, payment: OrderPayment):
        checkout_id = payment.info_data.get("sumup_checkout_id")
        if checkout_id:
            try:
                sumup_client.cancel_checkout(
                    checkout_id, self.settings.get("access_token")
                )
            except Exception as err:
                logger.warn(f"Error while canceling SumUp checkout: {err}")
                pass  # Ignore errors, this hasn't any impact on us
        super().cancel_payment(payment)

    def payment_refund_supported(self, payment: OrderPayment):
        self._synchronize_payment_status(payment)
        return payment.info_data.get("sumup_transaction") is not None

    def payment_partial_refund_supported(self, payment: OrderPayment):
        self._synchronize_payment_status(payment)
        return payment.info_data.get("sumup_transaction") is not None

    def execute_refund(self, refund: OrderRefund):
        payment = refund.payment
        transaction = payment.info_data.get("sumup_transaction")
        if not transaction:
            logger.exception(
                "Error while refunding sumup transaction. No transaction found"
            )
            raise PaymentException(_("Error while refunding SumUp transaction"))
        try:
            sumup_client.refund_transaction(
                transaction_id=transaction["id"],
                amount=float(refund.amount),
                access_token=self.settings.get("access_token"),
            )
            refund.done()
        except Exception as err:
            logger.exception(f"Error while refunding SumUp transaction: {err}")
            refund.state = OrderRefund.REFUND_STATE_FAILED
            refund.save(update_fields=["state"])
            raise PaymentException(_("Error while refunding SumUp transaction"))

        # Synchronize the transaction to get the refund status
        self._try_synchronize_transaction(payment, transaction["id"])

    def render_invoice_text(self, order: Order, payment: OrderPayment):
        transaction = payment.info_data.get("sumup_transaction")
        if not transaction:
            return ""
        return _("Payed via SumUp\n{} **** **** **** {}\nAuth code: {}").format(
            transaction.get("card", {}).get("type", "UNKNOWN"),
            transaction.get("payment_type", ""),
            transaction.get("card", {}).get("last_4_digits", ""),
            transaction.get("auth_code", ""),
        )

    def payment_presale_render(self, payment: OrderPayment):
        transaction = payment.info_data.get("sumup_transaction")
        if not transaction:
            return ""

        return get_template("pretix_sumup/control.html").render(
            {
                "card_type": transaction.get("card", {}).get("type", "UNKNOWN"),
                "payment_type": transaction.get("entry_mode", "").upper(),
                "card_last_4_digit": transaction.get("card", {}).get(
                    "last_4_digits", ""
                ),
            }
        )

    def payment_control_render(self, order: Order, payment: OrderPayment):
        transaction = payment.info_data.get("sumup_transaction")
        print(transaction)
        if not transaction:
            return ""

        return get_template("pretix_sumup/control.html").render(
            {
                "card_type": transaction.get("card", {}).get("type", "UNKNOWN"),
                "payment_type": transaction.get("entry_mode", "").upper(),
                "card_last_4_digit": transaction.get("card", {}).get(
                    "last_4_digits", ""
                ),
                "receipt_url": self._build_receipt_url(transaction),
            }
        )

    def refund_control_render(self, request: HttpRequest, refund: OrderRefund):
        if refund.amount != refund.payment.amount:
            # we are not able to match partial refunds which result potentially in multiple refunds
            return ""
        transaction = refund.payment.info_data.get("sumup_transaction")
        if not transaction:
            return ""
        refund_event_id = next(
            (
                event.get("id")
                for event in transaction.get("events")
                if event.get("type") == "REFUND"
            ),
            None,
        )
        if not refund_event_id:
            return ""

        return get_template("pretix_sumup/control.html").render(
            {
                "card_type": transaction.get("card", {}).get("type", "UNKNOWN"),
                "payment_type": transaction.get("entry_mode", "").upper(),
                "card_last_4_digit": transaction.get("card", {}).get(
                    "last_4_digits", ""
                ),
                "receipt_url": self._build_receipt_url(
                    transaction, event_id=refund_event_id
                ),
            }
        )

    def matching_id(self, payment):
        transaction = payment.info_data.get("sumup_transaction")
        if not transaction:
            return None
        return transaction.get("transaction_code")

    def api_payment_details(self, payment):
        return {"sumup_transaction": payment.info_data.get("sumup_transaction")}

    @staticmethod
    def _build_receipt_url(transaction, event_id: str = None):
        merchant_code = transaction.get("merchant_code")
        transaction_code = transaction.get("transaction_code")
        if not merchant_code or not transaction_code:
            return None
        url = f"https://receipts-ng.sumup.com/v0.1/receipts/{transaction_code}?mid={merchant_code}&format=pdf"
        if event_id:
            url += f"&tx_event_id={event_id}"
        return url

    def _synchronize_payment_status(self, payment: OrderPayment, force: bool = False):
        """
        Synchronizes the payment status with the SumUp Checkout.
        :param force: True if the payment status should be synchronized even if it is already confirmed and the transactions was synchronized
        :param payment: The OrderPayment object to synchronize
        :return: True if a SumUp checkout exists which hasn't failed, False if no checkout exists or the checkout has failed
        """
        checkout_id = payment.info_data.get("sumup_checkout_id")
        if not checkout_id:
            return False
        if not force:
            if (
                payment.state == OrderPayment.PAYMENT_STATE_CONFIRMED
                and payment.info_data.get("sumup_transaction") is not None
            ):
                return True
        try:
            checkout = sumup_client.get_checkout(
                checkout_id, self.settings.get("access_token")
            )
        except Exception as err:
            logger.exception(f"Error while synchronizing SumUp checkout: {err}")
            raise PaymentException(_("Error while synchronizing SumUp checkout"))
        if checkout["status"] == "PAID":
            if not payment.state == OrderPayment.PAYMENT_STATE_CONFIRMED:
                payment.confirm()

            # Every try of processing the payment results in a transaction, we only care about the successful one
            transaction_id = next(
                (
                    transaction.get("id")
                    for transaction in checkout["transactions"]
                    if transaction["status"] == "SUCCESSFUL"
                ),
                None,
            )
            if transaction_id is not None:
                self._try_synchronize_transaction(payment, transaction_id)
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

    def _try_synchronize_transaction(self, payment: OrderPayment, transaction_id: str):
        try:
            transaction = sumup_client.get_transaction(
                transaction_id=transaction_id,
                merchant_code=self.settings.get("merchant_code"),
                access_token=self.settings.get("access_token"),
            )
            # split into multiple line is required to invoke the setter of info_data
            info_data = payment.info_data
            info_data["sumup_transaction"] = transaction
            payment.info_data = info_data
            payment.save()
        except Exception as err:
            logger.warn(f"Error while synchronizing SumUp transaction: {err}")

    @staticmethod
    def _get_sumup_locale(request):
        language = get_language_from_request(request)
        if language == "de" or language == "de-informal":
            return "de-DE"
        elif language == "fr":
            return "fr-FR"
        return "en-GB"
