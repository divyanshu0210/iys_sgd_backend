from types import SimpleNamespace
from unittest import skipUnless

from django.apps import apps
from django.test import SimpleTestCase


@skipUnless(apps.is_installed('django.contrib.admin'), 'Requires admin settings')
class DonationAdminDisplayTests(SimpleTestCase):
    def test_columns_and_proof_preview_match_payment_admin(self):
        from django.contrib import admin
        from payment.admin import DonationAdmin, PaymentAdmin
        from payment.models import Donation, Payment

        donation_admin = DonationAdmin(Donation, admin.site)
        payment_admin = PaymentAdmin(Payment, admin.site)
        self.assertEqual(donation_admin.list_display[:4], ('transaction_id', 'amount', 'proof_preview', 'donor_name'))
        proof = SimpleNamespace(name='donation_proofs/example.png', url='https://example.com/example.png')
        donation_preview = donation_admin.proof_preview(SimpleNamespace(screenshot=proof))
        self.assertEqual(donation_preview, payment_admin.proof_preview(SimpleNamespace(proof=proof)))
        self.assertIn('payment-proof-preview__image', donation_preview)
        self.assertIn('payment/css/proof_preview.css', str(donation_admin.media))
        self.assertEqual(donation_admin.proof_preview(SimpleNamespace(screenshot=None)), '—')
