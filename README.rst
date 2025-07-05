Pretix SumUp Payment
====================

.. image:: /images/SumUp_Pretix_plugin_header.png
   :align: center


This is a plugin for `Pretix`_.

Enables credit card payments, Apple Pay, Google Pay, and alternative payment methods via SumUp.

SumUp Payment Provider Setup Guide
----------------------------------

Overview
^^^^^^^^
This guide walks through setting up and configuring the SumUp payment provider for your Pretix installation. The SumUp payment provider allows you to accept credit card payments and various alternative payment methods.

Prerequisites
^^^^^^^^^^^^^
* A SumUp merchant account  
* API keys from the SumUp developer portal  
* Pretix installation

Configuration Options
^^^^^^^^^^^^^^^^^^^^^

Basic Setup
"""""""""""
1. **API Key**: Required authorization token that allows Pretix to call SumUp on your behalf.

   * Obtain it from: `SumUp API Keys <https://developer.sumup.com/api-keys>`_
   * Format must begin with ``sup_sk_``
   * Paste it into the ``API Key`` field under the plugin's settings.

2. **Merchant Code & Merchant Name**: Automatically filled in when a valid API key is provided after saving.

Alternative Payment Methods
"""""""""""""""""""""""""""
1. **Enable Alternative Payment Methods** under the plugin's settings: Allows customers to pay using:

   * Apple Pay
   * Google Pay
   * iDEAL
   * Other methods depending on your `SumUp account's country <https://developer.sumup.com/online-payments/apm/introduction#supported-alternative-payment-methods>`_

2. **Apple Pay Setup**:

   * Download the Domain verification file from `SumUp Wallets Settings <https://developer.sumup.com/settings/wallets/apple-pay?tab=web>`_ and open it with a text editor
   * Copy and paste the whole file as text to the ``ApplePay MerchantID Domain Association`` field under Pretix's ``Global settings`` (``yourdomain/control/global/settings/`` - only accessible as an Admin user via ``Admin mode``)
   * Verify your domain by pasting it to `SumUp Wallets Settings`_ and clicking ``Check domain`` (like ``example.com`` or ``world.example.com``)
   * You're done! Apple Pay should show as an option from now on for every new checkout, when visited by an supported device like an iPhone!

3. **Google Pay Setup**:

   * For the Google Pay checkout you'll need to register a Google Pay business account and validate your domain with Google by sending screenshots of your checkout to verify that it satisfies Google's guidelines. Additionally, you'll need to contact SumUp's Integration Team to activate Google Pay on your merchant account.
   * First, register a Google Pay business account `here <https://pay.google.com/business/console/>`_
   * Fill out your information under the ``Business profile`` tab and get it approved by Google
   * ``Enable Google Pay`` under the plugin's settings and fill in your Google ``Merchant ID`` (you can find it next to your business name on the Google Pay console)
   * Under the ``Google Pay API`` tab fill in your domain (like ``example.com`` or ``world.example.com``) and choose ``Gateway`` as ``Integration type``
   * Take screenshots of your **own** Pretix store (see the examples under `images </images/>`_) and submit them to Google. For the ``Payment method screen`` and ``GooglePay API Payment Screen`` add ``#sumup-widget:google-pay-demo-mode`` to your URL to generate a test Google Pay button. (e.g.: ``yourdomain.net/yourorganizer/yourevent/order/GDBBK/9ddqfjdkaujvhus45q/#sumup-widget:google-pay-demo-mode``)
   * Wait until Google Approves your implementation (usually within 48h)
   * Contact SumUp's Integration Team to activate Google Pay on your merchant account via the `contact form <https://developer.sumup.com/contact>`_.  
     You'll need to provide them with your SumUp Merchant Code, SumUp Merchant Email, and a URL to a test ticket shop in order to check if your store complies with their policies.
   * You're done! Google Pay should show as an option from now on for every new checkout!


4. **Other Alternative Payment Methods**

   * After enabling ``Alternative Payment Methods`` under the plugin's settings they should show up as an option depending on your `SumUp account's country`_


Development setup
-----------------

1. Make sure that you have a working `Pretix development setup`_.

2. Clone this repository.

3. Activate the virtual environment you use for Pretix development.

4. Execute ``python setup.py develop`` within this directory to register this application with Pretix's plugin registry.

5. Execute ``make`` within this directory to compile translations.

6. Restart your local Pretix server. You can now use the plugin from this repository for your events by enabling it in the 'plugins' tab in the settings.

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

.. _Pretix: https://github.com/Pretix/Pretix  
.. _Pretix development setup: https://docs.Pretix.eu/en/latest/development/setup.html
