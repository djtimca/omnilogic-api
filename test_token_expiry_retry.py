#!/usr/bin/env python3
"""
Test script to verify automatic token re-authentication and retry in omnilogic-api.
Includes both mock unit tests and live API verification.
"""

import asyncio
import logging
import sys
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, "/tmp/omnilogic-api")
from omnilogic import OmniLogic, OmniLogicException, LoginException

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
_LOGGER = logging.getLogger("test_token_expiry")


def create_mock_response(status=200, text_data="", json_data=None):
    """Helper to create a properly configured mock aiohttp response context manager."""
    resp = MagicMock()
    resp.status = status
    resp.text = AsyncMock(return_value=text_data)
    if json_data is not None:
        resp.json = AsyncMock(return_value=json_data)
    
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


class TestTokenExpiryRetry(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.api = OmniLogic("test@example.com", "password123")
        # Close the default ClientSession created in __init__ to prevent warning
        await self.api._session.close()
        self.api.token = "initial_expired_token"
        self.api.userid = "12345"
        # Mock session to avoid real network and provide close method
        self.api._session = MagicMock()
        self.api._session.close = AsyncMock()

    async def test_empty_response_triggers_reauth_and_retry_success(self):
        """Verify that an empty response (invalid/expired token) triggers re-auth and retries."""
        telemetry_xml = (
            '<Response status="0">'
            '<Parameters>'
            '<Parameter name="Status" dataType="int">0</Parameter>'
            '<Parameter name="StatusMessage" dataType="string">Success</Parameter>'
            '</Parameters>'
            '<Backyard systemId="339524">ok</Backyard>'
            '</Response>'
        )

        ctx_expired = create_mock_response(status=200, text_data="")
        ctx_reauth = create_mock_response(status=200, json_data={
            "token": "brand_new_valid_token",
            "refreshToken": "new_refresh",
            "userID": "12345"
        })
        ctx_success = create_mock_response(status=200, text_data=telemetry_xml)

        self.api._session.post = MagicMock(side_effect=[ctx_expired, ctx_reauth, ctx_success])

        params = {"Token": self.api.token, "MspSystemID": "339524"}
        result = await self.api.call_api("GetTelemetryData", params)

        self.assertIn("Backyard systemId", result)
        self.assertEqual(self.api.token, "brand_new_valid_token")
        self.assertEqual(params["Token"], "brand_new_valid_token")
        self.assertEqual(self.api._session.post.call_count, 3)
        _LOGGER.info("✓ test_empty_response_triggers_reauth_and_retry_success passed")

    async def test_non_xml_response_triggers_reauth_and_retry_success(self):
        """Verify that a non-XML response (e.g. HTML error page or cloudflare text) triggers re-auth."""
        valid_xml = (
            '<Response status="0">'
            '<Parameters>'
            '<Parameter name="Status" dataType="int">0</Parameter>'
            '<Parameter name="StatusMessage" dataType="string">Success</Parameter>'
            '</Parameters>'
            '<Backyard systemId="339524">ok</Backyard>'
            '</Response>'
        )

        ctx_bad_text = create_mock_response(status=200, text_data="Unauthorized: Invalid session token")
        ctx_reauth = create_mock_response(status=200, json_data={
            "token": "refreshed_token_xyz",
            "refreshToken": "refresh_xyz",
            "userID": "12345"
        })
        ctx_success = create_mock_response(status=200, text_data=valid_xml)

        self.api._session.post = MagicMock(side_effect=[ctx_bad_text, ctx_reauth, ctx_success])

        params = {"Token": self.api.token, "MspSystemID": "339524"}
        result = await self.api.call_api("GetTelemetryData", params)

        self.assertIn("Backyard systemId", result)
        self.assertEqual(self.api.token, "refreshed_token_xyz")
        _LOGGER.info("✓ test_non_xml_response_triggers_reauth_and_retry_success passed")

    async def test_retry_failure_does_not_infinite_loop(self):
        """Verify that if retry also returns invalid XML, OmniLogicException is raised once without recursion."""
        ctx_expired1 = create_mock_response(status=200, text_data="")
        ctx_reauth = create_mock_response(status=200, json_data={
            "token": "second_attempt_token",
            "refreshToken": "refresh_2",
            "userID": "12345"
        })
        ctx_expired2 = create_mock_response(status=200, text_data="")

        self.api._session.post = MagicMock(side_effect=[ctx_expired1, ctx_reauth, ctx_expired2])

        params = {"Token": self.api.token, "MspSystemID": "339524"}
        with self.assertRaises(OmniLogicException) as ctx:
            await self.api.call_api("GetTelemetryData", params)

        self.assertIn("Failed to parse API response", str(ctx.exception))
        # Total calls: first API call (1) + auth (1) + retry API call (1) = 3
        self.assertEqual(self.api._session.post.call_count, 3)
        _LOGGER.info("✓ test_retry_failure_does_not_infinite_loop passed")

    async def test_no_retry_when_no_token_present(self):
        """Verify that if token is None, ParseError immediately raises OmniLogicException without retrying."""
        self.api.token = None
        ctx_empty = create_mock_response(status=200, text_data="")
        self.api._session.post = MagicMock(side_effect=[ctx_empty])

        params = {}
        with self.assertRaises(OmniLogicException):
            await self.api.call_api("GetTelemetryData", params)

        self.assertEqual(self.api._session.post.call_count, 1)
        _LOGGER.info("✓ test_no_retry_when_no_token_present passed")

    async def test_status_2_not_logged_in_triggers_reauth_and_retry_success(self):
        """Verify that a Status=2 XML response ('You haven\\'t logged in.') triggers re-auth and retries."""
        not_logged_in_xml = (
            '<Response>'
            '<Name>GetMspConfigFile</Name>'
            '<Parameters>'
            '<Parameter dataType="int" name="Status">2</Parameter>'
            '<Parameter dataType="int" name="StatusMessage">You haven\'t logged in.</Parameter>'
            '</Parameters>'
            '</Response>'
        )

        valid_xml = (
            '<Response status="0">'
            '<Parameters>'
            '<Parameter name="Status" dataType="int">0</Parameter>'
            '<Parameter name="StatusMessage" dataType="string">Success</Parameter>'
            '</Parameters>'
            '<MSPConfig>valid_msp_config_data</MSPConfig>'
            '</Response>'
        )

        ctx_auth_err = create_mock_response(status=200, text_data=not_logged_in_xml)
        ctx_reauth = create_mock_response(status=200, json_data={
            "token": "refreshed_auth_token_456",
            "refreshToken": "refresh_456",
            "userID": "12345"
        })
        ctx_success = create_mock_response(status=200, text_data=valid_xml)

        self.api._session.post = MagicMock(side_effect=[ctx_auth_err, ctx_reauth, ctx_success])

        params = {"Token": self.api.token, "MspSystemID": "339524", "Version": 0}
        result = await self.api.call_api("GetMspConfigFile", params)

        self.assertIn("MSPConfig", result)
        self.assertEqual(self.api.token, "refreshed_auth_token_456")
        self.assertEqual(params["Token"], "refreshed_auth_token_456")
        self.assertEqual(self.api._session.post.call_count, 3)
        _LOGGER.info("✓ test_status_2_not_logged_in_triggers_reauth_and_retry_success passed")

    async def asyncTearDown(self):
        await self.api.close()


async def run_live_test(username, password):
    """Run real test against live Hayward OmniLogic Cloud."""
    _LOGGER.info("--- Starting Live Integration Test against Hayward OmniLogic Cloud ---")
    client = OmniLogic(username, password)
    try:
        # 1. Connect and verify valid initial state
        _LOGGER.info("Step 1: Connecting with valid credentials...")
        token, userid = await client.connect()
        _LOGGER.info(f"Connected! UserID: {userid}, Token: {token[:12]}...")
        
        # 2. Get initial telemetry
        _LOGGER.info("Step 2: Fetching telemetry with initial valid token...")
        telemetry1 = await client.get_telemetry_data()
        assert telemetry1 and len(telemetry1) > 0
        _LOGGER.info(f"Received valid telemetry (length {len(telemetry1)})")

        # 3. Deliberately invalidate the token in memory to simulate 72h-96h session expiration
        _LOGGER.info("Step 3: Corrupting token in memory to simulate expired session token...")
        expired_dummy_token = "BOGUS_EXPIRED_TOKEN_SIMULATION_99999"
        client.token = expired_dummy_token
        # Ensure client.token_expiry is in the future so call_api doesn't pre-refresh before the request
        from datetime import datetime, timedelta
        client.token_expiry = datetime.now() + timedelta(hours=10)

        # 4. Call get_telemetry_data again directly!
        # The Hayward API will reject the dummy token with HTTP 200 and empty string.
        # client.call_api() should catch ParseError, refresh the token, and succeed without any error raised!
        _LOGGER.info("Step 4: Calling get_telemetry_data() with invalid token...")
        telemetry2 = await client.get_telemetry_data()
        assert telemetry2 and len(telemetry2) > 0
        assert client.token != expired_dummy_token
        _LOGGER.info(f"SUCCESS! Automatically recovered and refreshed token to: {client.token[:12]}...")
        _LOGGER.info(f"Telemetry retrieved seamlessly: length {len(telemetry2)}")
        _LOGGER.info("=== LIVE INTEGRATION TEST PASSED 100% ===")
        return True
    finally:
        await client.close()


if __name__ == "__main__":
    # Run unit tests first
    print("\n================== RUNNING UNIT TESTS ==================")
    suite = unittest.TestLoader().loadTestsFromTestCase(TestTokenExpiryRetry)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)

    # Run live integration test if credentials provided
    if len(sys.argv) > 2:
        user = sys.argv[1]
        pwd = sys.argv[2]
        print("\n============= RUNNING LIVE HAYWARD TEST =============")
        asyncio.run(run_live_test(user, pwd))
    else:
        print("\nUnit tests passed! Pass username and password as CLI args to run live test.")
