import os
import subprocess
import sys
import shutil
import time
import re

def print_banner():
    os.system('clear')
    banner = """
\033[1;32m_________________ 
|  _____________  |
| | \033[1;36mespyr cloud\033[1;32m | |
| |_____________| |
|_________________|

\033[1;33mespyr cloud MTU Optimizer\033[0m
"""
    print(banner)

def check_requirements():
    print("\033[1;32m[+] Checking for required tools...\033[0m")
    tools = ["ping", "ping6", "ip"]
    for tool in tools:
        if shutil.which(tool) is None:
            print(f"\033[1;31m[-] {tool} is missing. Installing...\033[0m")
            subprocess.run(["sudo", "apt-get", "update"])
            subprocess.run(["sudo", "apt-get", "install", "-y", tool])

def show_menu():
    print('\033[1;36mSelect IP type:\033[0m')
    print('\033[1;33m1- IPv4\n2- IPv6\033[0m')

    while True:
        ip_type = input("\033[1;34mEnter choice [1-2]: \033[0m").strip()
        if ip_type in ("1", "2"):
            break
        print("\033[1;31mInvalid choice. Please enter 1 or 2.\033[0m")

    dest_ip = input("\033[1;34mEnter destination IP address (default: 1.1.1.1): \033[0m").strip()
    if not dest_ip:
        dest_ip = "1.1.1.1"

    step_size = 1
    return ip_type, dest_ip, step_size

def get_network_interfaces():
    result = subprocess.run(["ip", "-o", "link", "show"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    interfaces = []
    for line in result.stdout.decode().splitlines():
        iface = line.split(":")[1].strip()
        if iface != "lo" and not iface.startswith(("veth", "docker", "br-", "vmnet", "virbr")):
            interfaces.append(iface)
    return interfaces

def find_max_mtu(ip, proto, interface, step):
    min_mtu = 1420
    max_mtu = 1475
    last_success = None

    print(f"\n\033[1;35m[>] Starting MTU discovery for {proto} on {interface} -> {ip}...\033[0m")
    mtu = max_mtu
    while mtu >= min_mtu:
        print(f"\033[1;34m[*] Testing MTU: {mtu} on {interface}...\033[0m", end=' ')
        size = mtu - (28 if proto == "IPv4" else 48)
        ping_cmd = ["ping", "-M", "do", "-c", "1", "-s", str(size), ip, "-W", "1"] \
            if proto == "IPv4" else ["ping6", "-M", "do", "-c", "1", "-s", str(size), ip, "-W", "1"]

        result = subprocess.run(ping_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if result.returncode == 0:
            print("\033[1;32mSuccess\033[0m")
            last_success = mtu
            break
        else:
            print("\033[1;31m❌ Failed\033[0m")

        mtu -= step
        time.sleep(1)

    if last_success:
        print(f"\033[1;35m\n[✔] Maximum working MTU for {interface} is: {last_success}\033[0m")
        print(f"\033[1;33m[~] Setting MTU to {last_success} on {interface}...\033[0m")
        result = subprocess.run(["sudo", "ip", "link", "set", "dev", interface, "mtu", str(last_success)])
        if result.returncode == 0:
            print(f"\033[1;32m[+] MTU successfully set to {last_success} on {interface}\033[0m")
        else:
            print("\033[1;31m[!] Failed to apply MTU on interface:\033[0m", interface)
    else:
        print(f"\033[1;31m[-] No working MTU found for {interface} in range {min_mtu}-{max_mtu}\033[0m")

def main():
    print_banner()
    check_requirements()
    ip_type, ip, step = show_menu()
    proto = "IPv4" if ip_type == "1" else "IPv6"

    interfaces = get_network_interfaces()
    if not interfaces:
        print("\033[1;31m[!] No valid network interfaces found.\033[0m")
        sys.exit(1)

    for interface in interfaces:
        print(f"\n\033[1;36m[*] Processing interface: {interface}\033[0m")
        find_max_mtu(ip, proto, interface, step)

def ask_exit():
    try:
        choice = input("\n\033[1;34m❓ Do you want to exit? (y/n): \033[0m").strip().lower()
        if choice == "y":
            print("\033[1;32m\nGoodbye!\033[0m")
            sys.exit(0)
        else:
            main()
    except KeyboardInterrupt:
        print("\n\033[1;31mDetected another interrupt. Forcing exit.\033[0m")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        ask_exit()
