import pytest
from unittest.mock import patch, MagicMock
from shared.cli.doctor import check_dns, check_tcp_connection, check_tls_handshake, inspect_environment, run_diagnostics

def test_check_dns_success():
    with patch("socket.gethostbyname", return_value="1.2.3.4"):
        ok, ip = check_dns("api.stlouisfed.org")
        assert ok is True
        assert ip == "1.2.3.4"

def test_check_dns_failure():
    with patch("socket.gethostbyname", side_effect=Exception("Name or service not known")):
        ok, msg = check_dns("invalid.example.com")
        assert ok is False
        assert "Name or service not known" in msg

def test_check_tcp_success():
    with patch("socket.socket") as mock_sock_cls:
        mock_sock = MagicMock()
        mock_sock_cls.return_value = mock_sock
        ok, msg = check_tcp_connection("8.8.8.8", 53)
        assert ok is True
        assert msg == "Connected"

def test_check_tls_handshake_success():
    with patch("ssl.create_default_context") as mock_ssl_ctx:
        mock_ctx = MagicMock()
        mock_ssock = MagicMock()
        mock_ssock.version.return_value = "TLSv1.3"
        mock_ctx.wrap_socket.return_value.__enter__.return_value = mock_ssock
        mock_ssl_ctx.return_value = mock_ctx

        ok, msg = check_tls_handshake("api.stlouisfed.org", 443)
        assert ok is True
        assert "TLS Handshake OK" in msg

def test_inspect_environment():
    info = inspect_environment()
    assert "platform" in info
    assert "is_wsl" in info
    assert "in_container" in info

def test_run_diagnostics_all_pass():
    with patch("shared.cli.doctor.check_dns", return_value=(True, "1.2.3.4")), \
         patch("shared.cli.doctor.check_tls_handshake", return_value=(True, "TLSv1.3")), \
         patch("shared.cli.doctor.check_tcp_connection", return_value=(True, "Connected")):
        code = run_diagnostics()
        assert code == 0

def test_run_diagnostics_failure_returns_1():
    with patch("shared.cli.doctor.check_dns", return_value=(False, "Failed")):
        code = run_diagnostics()
        assert code == 1
