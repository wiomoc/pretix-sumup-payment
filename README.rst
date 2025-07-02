Pretix SumUp Payment
====================

This is a plugin for `pretix`_.

Enables credit card payments, Apple Pay, Google Pay and alternative payment methods via SumUp.

SumUp Payment Provider Setup Guide
----------------------------------

Overview
^^^^^^^^
This guide walks through setting up and configuring the SumUp payment provider for your pretix installation. The SumUp payment provider allows you to accept credit card payments and various alternative payment methods.

Prerequisites
^^^^^^^^^^^^^
* A SumUp merchant account  
* API keys from the SumUp developer portal  
* pretix installation  

Configuration Options
^^^^^^^^^^^^^^^^^^^^^

Basic Setup
"""""""""""
1. **API Key**: Required authorization token that allows pretix to call SumUp on your behalf.

   * Obtain from: `SumUp API Keys <https://developer.sumup.com/api-keys>`_
   * Format must begin with ``sup_sk_``

2. **Merchant Code & Merchant Name**: Automatically filled in when a valid API key is provided.

Alternative Payment Methods
"""""""""""""""""""""""""""
1. **Enable Alternative Payment Methods**: Allows customers to pay using:

   * Apple Pay
   * Google Pay
   * iDEAL
   * Other methods depending on your SumUp account's country

2. **Apple Pay Setup**:

   * Follow setup steps at `SumUp Wallets Settings <https://developer.sumup.com/settings/wallets>`_ to activate your domain for Apple Pay
   * Add Apple Developer MerchantID Domain Association file to Pretix Global settings

3. **Google Pay Setup**:

   * You must enable Alternative Payment Methods first
   * Validate your domain with Google (`Learn more <https://developer.sumup.com/online-payments/apm/google-pay>`_)
   * For the validation screenshots, add ``#sumup-widget:google-pay-demo-mode`` to your payment URL to generate a test Google Pay button
   * Provide a Google Pay MerchantID (12–18 characters)
   * Contact SumUp's Integration Team to activate Google Pay via the `contact form <https://developer.sumup.com/contact>`_.  
     You'll need to provide them with your MerchantID, Merchant Email, and a URL to a test ticket shop in order to check if your store complies with their policies.

Development setup
-----------------

1. Make sure that you have a working `pretix development setup`_.

2. Clone this repository.

3. Activate the virtual environment you use for pretix development.

4. Execute ``python setup.py develop`` within this directory to register this application with pretix's plugin registry.

5. Execute ``make`` within this directory to compile translations.

6. Restart your local pretix server. You can now use the plugin from this repository for your events by enabling it in the 'plugins' tab in the settings.

This plugin has CI set up to enforce a few code style rules. To check locally, you need these packages installed::

    pip install flake8 isort black

To check your plugin for rule violations, run::

    black --check .
    isort -c .
    flake8 .

You can auto-fix some of these issues by running::

    isort .
    black .

To automatically check for these issues before you commit, you can run ``.install-hooks``.

License
-------

Copyright 2025 Christoph Walcher & Botond Moksony

Released under the terms of the Apache License 2.0

.. _pretix: https://github.com/pretix/pretix  
.. _pretix development setup: https://docs.pretix.eu/en/latest/development/setup.html
