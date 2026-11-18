from django.test import SimpleTestCase, override_settings

from routing.clients.http import build_session


class BuildSessionTests(SimpleTestCase):
    def test_session_retries_transient_failures(self):
        session = build_session()

        retry = session.get_adapter("https://router.project-osrm.org").max_retries
        self.assertEqual(retry.total, 1)
        self.assertEqual(retry.read, 1)
        self.assertIn(503, retry.status_forcelist)
        self.assertFalse(retry.raise_on_status)
        self.assertIn("fuel-route-planner", session.headers["User-Agent"])

    def test_retry_count_comes_from_settings(self):
        from django.conf import settings

        config = dict(settings.FUEL_ROUTER, HTTP_RETRIES=3)
        with override_settings(FUEL_ROUTER=config):
            session = build_session()

        self.assertEqual(session.get_adapter("https://example.org").max_retries.total, 3)
