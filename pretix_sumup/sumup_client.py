import requests
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

SUMUP_BASE_URL = "https://api.sumup.com/v0.1"


def _auth_header(access_token):
    return {"Authorization": "Bearer " + access_token}


def validate_access_token_and_get_merchant_code(access_token):
    if not access_token:
        raise ValidationError(_("No access token given."))

    response = requests.get(f"{SUMUP_BASE_URL}/me", headers=_auth_header(access_token))

    if response.status_code == 401:
        raise ValidationError(_("The access token is invalid."))

    # Forward other errors
    response.raise_for_status()

    response_body = response.json()
    return response_body["merchant_profile"]["merchant_code"]


def create_checkout(
    amount, currency, checkout_reference, merchant_code, return_url, access_token
):
    response = requests.post(
        f"{SUMUP_BASE_URL}/checkouts",
        json={
            "checkout_reference": checkout_reference,
            "amount": float(amount),
            "currency": currency,
            "merchant_code": merchant_code,
            "return_url": return_url,
        },
        headers=_auth_header(access_token),
    )

    if response.status_code == 401:
        raise ValidationError(_("The access token is invalid."))

    # Forward other errors
    response.raise_for_status()

    response_body = response.json()
    return response_body["id"]


def get_checkout(checkout_id, access_token):
    response = requests.get(
        f"{SUMUP_BASE_URL}/checkouts/{checkout_id}", headers=_auth_header(access_token)
    )

    if response.status_code == 401:
        raise ValidationError(_("The access token is invalid."))

    # Forward other errors
    response.raise_for_status()

    response_body = response.json()
    return response_body


def cancel_checkout(checkout_id, access_token):
    response = requests.delete(
        f"{SUMUP_BASE_URL}/checkouts/{checkout_id}", headers=_auth_header(access_token)
    )

    if response.status_code == 401:
        raise ValidationError(_("The access token is invalid."))

    # Forward other errors
    response.raise_for_status()


def get_transaction_by_code(transaction_code, access_token):
    response = requests.get(
        f"{SUMUP_BASE_URL}/me/transactions/",
        params={"transaction_code": transaction_code},
        headers=_auth_header(access_token),
    )

    if response.status_code == 401:
        raise ValidationError(_("The access token is invalid."))

    # Forward other errors
    response.raise_for_status()

    response_body = response.json()
    return response_body


def refund_transaction(transaction_id, access_token, amount=None):
    response = requests.post(
        f"{SUMUP_BASE_URL}/me/refund/{transaction_id}",
        json={"amount": float(amount)} if amount else None,
        headers=_auth_header(access_token),
    )

    if response.status_code == 401:
        raise ValidationError(_("The access token is invalid."))

    # Forward other errors
    response.raise_for_status()
