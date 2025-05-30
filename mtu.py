import os
import subprocess
import sys
import shutil
import time
import json

CONFIG_FILE = os.path.expanduser("~/.mtu_optimizer_config.json")
MANUAL_CONFIG_FILE = os.path.expanduser("~/.mtu_optimizer_manual.json")

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
    tools = ["ping", "ip"]
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
2- Select interface manually and set MTU
''')
    while True:
        ip_type = input("Enter choice [1-2]: ").strip()
        if ip_type in ("1", "2"):
            break
        print("\033[1;31mInvalid choice. Please enter 1 or 2.\033[0m")

    if ip_type == "1":
        dest_ip = input("Enter destination IP address (default: 1.1.1.1): ").strip()
        if not dest_ip:
            dest_ip = "1.1.1.1"
        step_size = 1
        return ip_type, dest_ip, step_size
    else:
        return ip_type, None, None

def get_network_interfaces():
    interfaces = []
    result = subprocess.run(["ip", "-o", "addr", "show"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    lines = result.stdout.splitlines()

    iface_set = set()

    for line in lines:
        parts = line.split()
        iface = parts[1]
        if iface == "lo" or iface.startswith(("veth", "docker", "br-", "vmnet", "virbr")):
            continue
        iface_set.add(iface)

    return list(iface_set)
def reset_mtu(interface):
    subprocess.run(["sudo", "ip", "link", "set", "dev", interface, "mtu", "1500"])
    time.sleep(0.5) 

def find_max_mtu(ip, interface, step):
    reset_mtu(interface)
    min_mtu = 1420
    max_mtu = 1475
    last_success = None
    print(f"Starting MTU discovery for IPv4 on {interface} -> {ip}...")
    mtu = max_mtu
    while mtu >= min_mtu:
        print(f"Testing MTU: {mtu} on {interface}...", end=' ')
        size = mtu - 28
        ping_cmd = ["ping", "-M", "do", "-c", "1", "-s", str(size), ip, "-W", "1"]

        result = subprocess.run(ping_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if result.returncode == 0:
            print("Success")
            last_success = mtu
            break
        else:
            print("Failed")

        mtu -= step
        time.sleep(1)

    if last_success:
        if interface not in ["eth0","eth1","ens33", "ens3", "ens","ens160"]:
            last_success -= 50
            if last_success < min_mtu:
                last_success = min_mtu
        print(f"\nMaximum working MTU for {interface} is: {last_success}")
        print(f"Setting MTU temporarily to {last_success} on {interface}...")
        result = subprocess.run(["sudo", "ip", "link", "set", "dev", interface, "mtu", str(last_success)])
        if result.returncode == 0:
            print(f"MTU successfully set to {last_success} on {interface}")
        else:
            print("Failed to apply MTU on interface:", interface)
    else:
        print(f"No working MTU found for {interface} in range {min_mtu}-{max_mtu}")

def manual_mtu_set():
    interfaces = get_network_interfaces()
    if not interfaces:
        print("\033[1;31m[!] No valid network interfaces found.\033[0m")
        return

    print("\nAvailable network interfaces:")
    for idx, iface in enumerate(interfaces, 1):
        print(f"{idx}. {iface}")

    while True:
        choice = input("Select interface by number: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(interfaces):
            selected_iface = interfaces[int(choice) - 1]
            break
        print("\033[1;31mInvalid selection. Try again.\033[0m")

    while True:
        mtu_value = input(f"Enter desired MTU value for {selected_iface}: ").strip()
        if mtu_value.isdigit() and 500 <= int(mtu_value) <= 9000:
            mtu_value = int(mtu_value)
            break
        print("\033[1;31mInvalid MTU. Must be a number between 500 and 9000.\033[0m")

    print(f"Setting MTU to {mtu_value} on {selected_iface}...")
    result = subprocess.run(["sudo", "ip", "link", "set", "dev", selected_iface, "mtu", str(mtu_value)])
    if result.returncode == 0:
        print(f"MTU successfully set to {mtu_value} on {selected_iface}")
        manual_data = {
            "interface": selected_iface,
            "mtu": mtu_value
        }
        try:
            with open(MANUAL_CONFIG_FILE, "w") as f:
                json.dump(manual_data, f)
            print(f"\033[1;32m[+] Manual MTU config saved for {selected_iface}\033[0m")
        except Exception as e:
            print(f"\033[1;31m[!] Failed to save manual config: {e}\033[0m")
    else:
        print("Failed to apply MTU on interface:", selected_iface)

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

    if ip_type == "2":
        manual_mtu_set()
        return

    manual_config = {}
    skip_manual_interface = None

    if os.path.exists(MANUAL_CONFIG_FILE):
        try:
            with open(MANUAL_CONFIG_FILE) as f:
                manual_config = json.load(f)
        except Exception as e:
            print(f"\033[1;31m[!] Error reading manual config: {e}\033[0m")

    if not no_interact and manual_config:
        iface = manual_config.get("interface")
        mtu = manual_config.get("mtu")
        print(f"\n\033[1;33m[!] Manual MTU detected for interface {iface} (MTU={mtu})\033[0m")
        answer = input(f"Do you want to override manual setting and let script auto-optimize {iface}? [y/N]: ").strip().lower()
        if answer == "y":
            try:
                os.remove(MANUAL_CONFIG_FILE)
                print(f"\033[1;32m[+] Manual MTU config removed. Script will now manage {iface} automatically.\033[0m")
            except Exception as e:
                print(f"\033[1;31m[!] Failed to delete manual config: {e}\033[0m")
        else:
            skip_manual_interface = iface
    elif no_interact and manual_config:
        skip_manual_interface = manual_config.get("interface")

    interfaces = get_network_interfaces()
    if not interfaces:
        print("\033[1;31m[!] No valid network interfaces found.\033[0m")
        sys.exit(1)

    for interface in interfaces:
        real_interface = interface.split("@")[0]

        if skip_manual_interface and real_interface == skip_manual_interface:
            print(f"\033[1;34m[*] Skipping {real_interface} due to manual MTU setting.\033[0m")
            continue

        print(f"\n[*] Processing interface: {real_interface}")
        find_max_mtu(ip, real_interface, step)

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
