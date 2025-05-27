import os
import subprocess
import sys
import shutil
import time
import re

def print_banner():
    os.system('clear')
    banner = """
\033[1;34m
_________________ 
|  _____________  |
| | espyr cloud | |
| |_____________| |
|_________________|

\033[1;36mespyr cloud MTU Optimizer\033[0m
"""
    print(banner)

def check_requirements():
    print("\033[1;33mChecking for required tools...\033[0m")
    tools = ["ping", "ping6", "ip"]
    for tool in tools:
        if shutil.which(tool) is None:
            print(f"\033[91m{tool} is missing. Installing...\033[0m")
            subprocess.run(["sudo", "apt-get", "update"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["sudo", "apt-get", "install", "-y", tool], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("\033[1;32mAll required tools are installed.\033[0m")

def show_menu():
    print('''
Select IP type:
1- IPv4
2- IPv6

''')

    while True:
        ip_type = input("\033[1;33mEnter choice [1-2]: \033[0m").strip()
        if ip_type in ("1", "2"):
            break
        print("\033[91mInvalid choice. Please enter 1 or 2.\033[0m")

    dest_ip = input("\033[1;33mEnter destination IP address (default: 1.1.1.1): \033[0m").strip()
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

def save_mtu_setting(interface, mtu):
    print(f"\033[1;35m💾 Saving MTU setting permanently for {interface}...\033[0m")

    if os.path.exists("/etc/netplan/"):
        netplan_files = [f for f in os.listdir("/etc/netplan/") if f.endswith(".yaml")]
        if netplan_files:
            netplan_path = os.path.join("/etc/netplan", netplan_files[0])
            print(f"\033[1;34m🔧 Updating {netplan_path} with MTU: {mtu}\033[0m")
            with open(netplan_path, "r") as f:
                lines = f.readlines()
            with open(netplan_path, "w") as f:
                for line in lines:
                    f.write(line)
                    if line.strip().startswith(interface + ":"):
                        f.write(f"      mtu: {mtu}\n")
            subprocess.run(["sudo", "netplan", "apply"])
            return

    if os.path.exists("/etc/network/interfaces"):
        print("\033[1;34m🔧 Updating /etc/network/interfaces...\033[0m")
        with open("/etc/network/interfaces", "r") as f:
            content = f.read()
        new_content = re.sub(
            rf"(iface {interface} inet[^\n]*\n)", rf"\1    mtu {mtu}\n", content
        )
        with open("/etc/network/interfaces", "w") as f:
            f.write(new_content)
        subprocess.run(["sudo", "ifdown", interface])
        subprocess.run(["sudo", "ifup", interface])
        return

    print("\033[91mCould not detect Netplan or ifupdown. Please set MTU manually.\033[0m")

def find_max_mtu(ip, proto, interface, step):
    min_mtu = 1420
    max_mtu = 1475
    last_success = None

    print(f"\033[1;36m🚀 Starting MTU discovery for {proto} on {interface} -> {ip}...\033[0m")
    mtu = max_mtu
    while mtu >= min_mtu:
        print(f"\033[1;33m📶 Testing MTU: {mtu} on {interface}...\033[0m", end=' ')
        size = mtu - (28 if proto == "IPv4" else 48)
        ping_cmd = ["ping", "-M", "do", "-c", "1", "-s", str(size), ip, "-W", "1"] \
            if proto == "IPv4" else ["ping6", "-M", "do", "-c", "1", "-s", str(size), ip, "-W", "1"]

        result = subprocess.run(ping_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if result.returncode == 0:
            print("\033[1;32mSuccess\033[0m")
            last_success = mtu
            break
        else:
            print("\033[91m❌ Failed\033[0m")

        mtu -= step
        time.sleep(1)

    if last_success:
        print(f"\n\033[1;32m📏 Maximum working MTU for {interface} is: {last_success}\033[0m")
        print(f"\033[1;33m🛠️ Setting MTU to {last_success} on {interface}...\033[0m")
        result = subprocess.run(["sudo", "ip", "link", "set", "dev", interface, "mtu", str(last_success)])
        if result.returncode == 0:
            print(f"\033[1;32m✅ MTU successfully set to {last_success} on {interface}\033[0m")
            save_mtu_setting(interface, last_success)
        else:
            print(f"\033[91mFailed to apply MTU on interface: {interface}\033[0m")
    else:
        print(f"\033[91mNo working MTU found for {interface} in range {min_mtu}-{max_mtu}\033[0m")

def add_cron_job():
    script_path = os.path.abspath(__file__)
    cron_line = f"*/5 * * * * python3 {script_path} >> /var/log/mtu_optimizer.log 2>&1"

    try:
        result = subprocess.run(["crontab", "-l"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        current_cron = result.stdout if result.returncode == 0 else ""

        if cron_line not in current_cron:
            new_cron = current_cron.strip() + "\n" + cron_line + "\n"
            subprocess.run(["bash", "-c", f'echo "{new_cron}" | crontab -'])
            print("\033[92m[+] Cron job added for automatic MTU recheck every 5 minutes.\033[0m")
        else:
            print("\033[94m[!] Cron job already exists.\033[0m")

    except Exception as e:
        print(f"\033[91m[!] Failed to set cron job: {e}\033[0m")

def main():
    print_banner()
    check_requirements()
    add_cron_job()
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
        choice = input("\n\n\033[1;33m❓ Do you want to exit? (y/n): \033[0m").strip().lower()
        if choice == "y":
            print("\n\033[1;32mGoodbye!\033[0m")
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
