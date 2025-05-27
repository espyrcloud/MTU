import os
import subprocess
import sys
import shutil
import time
import re
import json

CONFIG_FILE = os.path.expanduser("~/.mtu_optimizer_config.json")

def print_banner():
    os.system('clear')
    banner = """
\033[1;34m
_________________
|  _____________  |
| | espyr cloud | |
| |_____________| |
|_________________|

espyr cloud MTU Optimizer
\033[0m
"""
    print(banner)

def check_requirements():
    print("\033[1;33mChecking for required tools...\033[0m")
    tools = ["ping", "ping6", "ip"]
    for tool in tools:
        if shutil.which(tool) is None:
            print(f"\033[1;31m{tool} is missing. Installing...\033[0m")
            subprocess.run(["sudo", "apt-get", "update"])
            subprocess.run(["sudo", "apt-get", "install", "-y", tool])

def save_config(data):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"\033[1;31mError saving config: {e}\033[0m")

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except Exception as e:
            print(f"\033[1;31mError loading config: {e}\033[0m")
    return None

def show_menu():
    print('''
Select IP type:
1- IPv4
2- IPv6
''')
    while True:
        ip_type = input("Enter choice [1-2]: ").strip()
        if ip_type in ("1", "2"):
            break
        print("\033[1;31mInvalid choice. Please enter 1 or 2.\033[0m")

    dest_ip = input("Enter destination IP address (default: 1.1.1.1): ").strip()
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
    print(f"\033[1;33m💾 Saving MTU setting permanently for {interface}...\033[0m")

    if os.path.exists("/etc/netplan/"):
        netplan_files = [f for f in os.listdir("/etc/netplan/") if f.endswith(".yaml")]
        if netplan_files:
            netplan_path = os.path.join("/etc/netplan", netplan_files[0])
            print(f"\033[1;33m🔧 Updating {netplan_path} with MTU: {mtu}\033[0m")
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
        print("\033[1;33m🔧 Updating /etc/network/interfaces...\033[0m")
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

    print("\033[1;31mCould not detect Netplan or ifupdown. Please set MTU manually.\033[0m")

def find_max_mtu(ip, proto, interface, step):
    min_mtu = 1420
    max_mtu = 1475
    last_success = None

    print(f"\033[1;36m🚀 Starting MTU discovery for {proto} on {interface} -> {ip}...\033[0m")
    mtu = max_mtu
    while mtu >= min_mtu:
        print(f"\033[1;34m📶 Testing MTU: {mtu} on {interface}...\033[0m", end=' ')
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
        print(f"\n\033[1;33m📏 Maximum working MTU for {interface} is: {last_success}\033[0m")
        print(f"\033[1;33m🛠️ Setting MTU to {last_success} on {interface}...\033[0m")
        result = subprocess.run(["sudo", "ip", "link", "set", "dev", interface, "mtu", str(last_success)])
        if result.returncode == 0:
            print(f"\033[1;32m✅ MTU successfully set to {last_success} on {interface}\033[0m")
            save_mtu_setting(interface, last_success)
        else:
            print(f"\033[1;31mFailed to apply MTU on interface: {interface}\033[0m")
    else:
        print(f"\033[1;31mNo working MTU found for {interface} in range {min_mtu}-{max_mtu}\033[0m")

def add_cron_job():
    python_path = shutil.which("python3") or "python3"
    script_path = os.path.abspath(sys.argv[0])

    cron_line = f"*/5 * * * * {python_path} {script_path} --no-interact >> ~/mtu_optimizer.log 2>&1"
    try:
        existing_cron = subprocess.run(["crontab", "-l"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        cron_jobs = existing_cron.stdout if existing_cron.returncode == 0 else ""

        if cron_line in cron_jobs:
            print("\033[1;33m[*] Cron job already exists.\033[0m")
            return

        new_cron = cron_jobs + "\n" + cron_line + "\n"
        proc = subprocess.run(["crontab", "-"], input=new_cron, text=True)
        if proc.returncode == 0:
            print("\033[1;32m[+] Cron job added to run every 5 minutes.\033[0m")
        else:
            print("\033[1;31m[!] Failed to add cron job.\033[0m")
    except Exception as e:
        print(f"\033[1;31m[!] Error adding cron job: {e}\033[0m")

def main(no_interact=False):
    print_banner()
    check_requirements()

    if not no_interact:
        ip_type, ip, step = show_menu()
        save_config({"ip_type": ip_type, "ip": ip, "step": step})
    else:
        cfg = load_config()
        if not cfg:
            print("\033[1;31m[!] No saved configuration found, please run interactively first.\033[0m")
            sys.exit(1)
        ip_type = cfg.get("ip_type")
        ip = cfg.get("ip")
        step = cfg.get("step")

    proto = "IPv4" if ip_type == "1" else "IPv6"

    interfaces = get_network_interfaces()
    if not interfaces:
        print("\033[1;31m[!] No valid network interfaces found.\033[0m")
        sys.exit(1)

    for interface in interfaces:
        print(f"\n\033[1;36m[*] Processing interface: {interface}\033[0m")
        find_max_mtu(ip, proto, interface, step)

    if not no_interact:
        add_cron_job()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="espyr cloud MTU optimizer")
    parser.add_argument("--no-interact", action="store_true", help="Run without user interaction (for cron)")
    args = parser.parse_args()
    try:
        main(no_interact=args.no_interact)
    except KeyboardInterrupt:
        print("\n\033[1;31mInterrupted by user. Exiting...\033[0m")
        sys.exit(0)
