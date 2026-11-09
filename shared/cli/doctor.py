import sys
import socket
import ssl
import os
from typing import Dict, List, Tuple

TARGET_HOSTS = [
    ("Google DNS", "8.8.8.8", 53),
    ("FRED API", "api.stlouisfed.org", 443),
    ("Yahoo Finance API", "query1.finance.yahoo.com", 443),
    ("GitHub", "github.com", 443)
]

def check_dns(host: str, timeout: float = 3.0) -> Tuple[bool, str]:
    try:
        ip = socket.gethostbyname(host)
        return True, ip
    except Exception as e:
        return False, str(e)

def check_tcp_connection(host: str, port: int, timeout: float = 3.0) -> Tuple[bool, str]:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.close()
        return True, "Connected"
    except Exception as e:
        return False, str(e)

def check_tls_handshake(host: str, port: int = 443, timeout: float = 3.0) -> Tuple[bool, str]:
    try:
        context = ssl.create_default_context()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        with context.wrap_socket(sock, server_hostname=host) as ssock:
            ssock.connect((host, port))
            version = ssock.version()
        return True, f"TLS Handshake OK ({version})"
    except Exception as e:
        return False, str(e)

def inspect_environment() -> Dict[str, str]:
    info = {
        "platform": sys.platform,
        "is_wsl": "microsoft" in os.uname().release.lower() if hasattr(os, "uname") else False,
        "in_container": os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv")
    }
    
    resolv_conf = "/etc/resolv.conf"
    if os.path.exists(resolv_conf):
        try:
            with open(resolv_conf, "r") as f:
                nameservers = [line.strip() for line in f if line.startswith("nameserver")]
                info["resolv_nameservers"] = ", ".join(nameservers)
        except Exception:
            info["resolv_nameservers"] = "unreadable"
            
    return info

def run_diagnostics() -> int:
    print("==================================================")
    print("        THE TERMINAL - ENVIRONMENT DOCTOR         ")
    print("==================================================")
    
    env_info = inspect_environment()
    print(f"Platform: {env_info['platform']}")
    print(f"WSL Detected: {env_info['is_wsl']}")
    print(f"Container Environment: {env_info['in_container']}")
    if "resolv_nameservers" in env_info:
        print(f"DNS Nameservers: {env_info['resolv_nameservers']}")
    print("--------------------------------------------------")
    print("1. DNS Resolution Checks:")
    dns_failed = 0
    for name, host, _ in TARGET_HOSTS:
        if host == "8.8.8.8":
            continue
        ok, detail = check_dns(host)
        status = "[PASS]" if ok else "[FAIL]"
        print(f"  {status} {name} ({host}) -> {detail}")
        if not ok:
            dns_failed += 1

    print("\n2. Outbound Egress & TLS Checks:")
    egress_failed = 0
    for name, host, port in TARGET_HOSTS:
        if port == 443:
            ok, detail = check_tls_handshake(host, port)
        else:
            ok, detail = check_tcp_connection(host, port)
        status = "[PASS]" if ok else "[FAIL]"
        print(f"  {status} {name} ({host}:{port}) -> {detail}")
        if not ok:
            egress_failed += 1

    print("--------------------------------------------------")
    if dns_failed == 0 and egress_failed == 0:
        print("RESULT: ALL NETWORK CHECKS PASSED. Environment is fully online.")
        return 0
    
    print("RESULT: NETWORK CONNECTIVITY ISSUES DETECTED.")
    print("\nRECOMMENDED REMEDIATIONS FOR WSL2 / DOCKER:")
    if env_info.get("is_wsl") or env_info.get("in_container"):
        print("1. Enable WSL2 Mirrored Networking:")
        print("   Create or edit '%USERPROFILE%\\.wslconfig' on Windows with:")
        print("   [wsl2]")
        print("   networkingMode=mirrored")
        print("   dnsTunneling=true")
        print("   autoProxy=true")
        print("\n2. Restart WSL:")
        print("   Run `wsl --shutdown` in PowerShell and reopen WSL.")
        print("\n3. If using VPN or corporate firewall:")
        print("   Ensure Docker Desktop 'Use WSL 2 based engine' and DNS fallbacks are configured.")
    return 1

if __name__ == "__main__":
    sys.exit(run_diagnostics())
