# -*- coding: utf-8 -*-
"""打印本机局域网 IPv4 地址(供手机同一 Wi-Fi 访问)。"""
import socket


def main():
    try:
        ips = socket.gethostbyname_ex(socket.gethostname())[2]
    except Exception:
        ips = []
    for pref in ("192.168.", "10.", "172."):
        for ip in ips:
            if ip.startswith(pref):
                print(ip)
                return
    for ip in ips:
        if not ip.startswith("127."):
            print(ip)
            return
    print("127.0.0.1")


if __name__ == "__main__":
    main()
