"""Tests for voice_type.network — network connectivity check."""

import urllib.error
from voice_type.network import check_network_available


class TestCheckNetworkAvailable:
    def test_network_available(self, mocker):
        """When urlopen succeeds, returns True."""
        mocker.patch("voice_type.network.urllib.request.urlopen", return_value=mocker.MagicMock())
        assert check_network_available() is True

    def test_network_unavailable_os_error(self, mocker):
        """When urlopen raises OSError, returns False."""
        mocker.patch(
            "voice_type.network.urllib.request.urlopen",
            side_effect=OSError("Network unreachable"),
        )
        assert check_network_available() is False

    def test_network_unavailable_url_error(self, mocker):
        """When urlopen raises URLError, returns False."""
        mocker.patch(
            "voice_type.network.urllib.request.urlopen",
            side_effect=urllib.error.URLError("Connection refused"),
        )
        assert check_network_available() is False

    def test_network_unavailable_timeout(self, mocker):
        """When urlopen raises TimeoutError, returns False."""
        mocker.patch(
            "voice_type.network.urllib.request.urlopen",
            side_effect=TimeoutError("Timed out"),
        )
        assert check_network_available() is False

    def test_custom_timeout(self, mocker):
        """Custom timeout_ms is converted to seconds and passed to urlopen."""
        mock_urlopen = mocker.patch("voice_type.network.urllib.request.urlopen")
        check_network_available(timeout_ms=5000)
        mock_urlopen.assert_called_once_with("https://www.baidu.com", timeout=5.0)

    def test_default_timeout(self, mocker):
        """Default timeout is 3000ms = 3.0 seconds."""
        mock_urlopen = mocker.patch("voice_type.network.urllib.request.urlopen")
        check_network_available()
        mock_urlopen.assert_called_once_with("https://www.baidu.com", timeout=3.0)

    def test_uses_baidu_url(self, mocker):
        """Probes https://www.baidu.com."""
        mock_urlopen = mocker.patch("voice_type.network.urllib.request.urlopen")
        check_network_available()
        call_args = mock_urlopen.call_args
        assert call_args[0][0] == "https://www.baidu.com"
