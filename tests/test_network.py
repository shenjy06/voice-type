"""Tests for voice_type.network — network connectivity check."""

import urllib.error
from voicetype.network import check_network_available, PROBE_URLS, DEFAULT_TIMEOUT_MS


class TestCheckNetworkAvailable:
    def test_network_available(self, mocker):
        """When any urlopen succeeds, returns True."""
        mocker.patch(
            "voicetype.network.urllib.request.urlopen",
            return_value=mocker.MagicMock(),
        )
        assert check_network_available() is True

    def test_network_unavailable_os_error(self, mocker):
        """When every urlopen raises OSError, returns False."""
        mocker.patch(
            "voicetype.network.urllib.request.urlopen",
            side_effect=OSError("Network unreachable"),
        )
        assert check_network_available() is False

    def test_network_unavailable_url_error(self, mocker):
        """When every urlopen raises URLError, returns False."""
        mocker.patch(
            "voicetype.network.urllib.request.urlopen",
            side_effect=urllib.error.URLError("Connection refused"),
        )
        assert check_network_available() is False

    def test_network_unavailable_timeout(self, mocker):
        """When every urlopen raises TimeoutError, returns False."""
        mocker.patch(
            "voicetype.network.urllib.request.urlopen",
            side_effect=TimeoutError("Timed out"),
        )
        assert check_network_available() is False

    def test_one_probe_succeeding_is_enough(self, mocker):
        """A single successful probe returns True even if others fail."""
        responses = [OSError("fail"), mocker.MagicMock(), OSError("fail")]

        def _side(url, *args, **kwargs):
            result = responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        mocker.patch(
            "voicetype.network.urllib.request.urlopen", side_effect=_side
        )
        assert check_network_available() is True

    def test_custom_timeout_passed_to_urlopen(self, mocker):
        """Custom timeout_ms is converted to seconds and passed to urlopen."""
        mock_urlopen = mocker.patch(
            "voicetype.network.urllib.request.urlopen",
            return_value=mocker.MagicMock(),
        )
        check_network_available(timeout_ms=5000)
        assert mock_urlopen.call_count == len(PROBE_URLS)
        for _, kwargs in mock_urlopen.call_args_list:
            assert kwargs["timeout"] == 5.0

    def test_default_timeout(self, mocker):
        """Default timeout is DEFAULT_TIMEOUT_MS, in seconds."""
        mock_urlopen = mocker.patch(
            "voicetype.network.urllib.request.urlopen",
            return_value=mocker.MagicMock(),
        )
        check_network_available()
        expected = DEFAULT_TIMEOUT_MS / 1000.0
        assert mock_urlopen.call_count == len(PROBE_URLS)
        for _, kwargs in mock_urlopen.call_args_list:
            assert kwargs["timeout"] == expected

    def test_probes_all_configured_urls(self, mocker):
        """Every PROBE_URL is probed (in parallel)."""
        mock_urlopen = mocker.patch(
            "voicetype.network.urllib.request.urlopen",
            side_effect=OSError("offline"),
        )
        check_network_available()
        probed = {call.args[0].full_url for call in mock_urlopen.call_args_list}
        assert probed == set(PROBE_URLS)

    def test_uses_head_request(self, mocker):
        """Probes use HEAD to avoid downloading response bodies."""
        mock_urlopen = mocker.patch(
            "voicetype.network.urllib.request.urlopen",
            return_value=mocker.MagicMock(),
        )
        check_network_available()
        for call in mock_urlopen.call_args_list:
            assert call.args[0].get_method() == "HEAD"
