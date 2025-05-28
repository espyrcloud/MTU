import os
import subprocess
import sys
import shutil
import time
import json

CONFIG_FILE = os.path.expanduser("~/.mtu_optimizer_config.json")

def print_banner():
    os.system('clear')
    banner = """
_________________
|  _____________  |
| | espyr cloud | |
| |_____________| |
|_________________|

espyr cloud MTU Optimizer
"""
    print(banner)

def check_requirements():
    print("Checking for required tools...")
    tools = ["ping", "ip"]
    for tool in tools:
        if shutil.which(tool) is None:
            print(f"{tool} is missing. Installing...")
            subprocess.run(["sudo", "apt-get", "update"])
            subprocess.run(["sudo", "apt-get", "install", "-y", tool])

def save_config(data):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Error saving config: {e}")

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
    return None

def show_menu():
    print('''
Select option:
1- Optimize MTU automatically for IPv4
2- Select interface manually and set MTU
''')
    while True:
        choice = input("Enter choice [1-2]: ").strip()
        if choice in ("1", "2"):
            break
        print("Invalid choice. Please enter 1 or 2.")

    if choice == "1":
        dest_ip = input("Enter destination IPv4 address (default: 1.1.1.1): ").strip()
        if not dest_ip:
            dest_ip = "1.1.1.1"
        step_size = 1
        return choice, dest_ip, step_size
    else:
        return choice, None, None

def get_network_interfaces():
    interfaces = []
    result = subprocess.run(["ip", "-o", "addr", "show"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    lines = result.stdout.splitlines()

    iface_dict = {}

    for line in lines:
        parts = line.split()
        iface = parts[1]
        if iface == "lo" or iface.startswith(("veth", "docker", "br-", "vmnet", "virbr")):
            continue

        if iface not in iface_dict:
            iface_dict[iface] = []

        if parts[2] == "inet":
            iface_dict[iface].append(parts[3])

    for iface, addrs in iface_dict.items():
        if addrs:
            interfaces.append(iface)

    return interfaces

def find_max_mtu(ip, interface, step):
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
        if interface != "eth0":
            last_success -= 40
            if last_success < min_mtu:
                last_success = min_mtu
        print(f"Maximum working MTU for {interface} is: {last_success}")
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
        print("No valid network interfaces found.")
        return

    print("\nAvailable network interfaces:")
    for idx, iface in enumerate(interfaces, 1):
        print(f"{idx}. {iface}")

    while True:
        choice = input("Select interface by number: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(interfaces):
            selected_iface = interfaces[int(choice) - 1]
            break
        print("Invalid selection. Try again.")

    while True:
        mtu_value = input(f"Enter desired MTU value for {selected_iface}: ").strip()
        if mtu_value.isdigit() and 500 <= int(mtu_value) <= 9000:
            mtu_value = int(mtu_value)
            break
        print("Invalid MTU. Must be a number between 500 and 9000.")

    print(f"Setting MTU to {mtu_value} on {selected_iface}...")
    result = subprocess.run(["sudo", "ip", "link", "set", "dev", selected_iface, "mtu", str(mtu_value)])
    if result.returncode == 0:
        print(f"MTU successfully set to {mtu_value} on {selected_iface}")
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
            print("[*] Cron job already exists.")
            return

        new_cron = cron_jobs + "\n" + cron_line + "\n"
        proc = subprocess.run(["crontab", "-"], input=new_cron, text=True)
        if proc.returncode == 0:
            print("[+] Cron job added to run every 5 minutes.")
        else:
            print("[!] Failed to add cron job.")
    except Exception as e:
        print(f"[!] Error adding cron job: {e}")

def main(no_interact=False):
    print_banner()
    check_requirements()

    if not no_interact:
        choice, ip, step = show_menu()
        save_config({"choice": choice, "ip": ip, "step": step})
    else:
        cfg = load_config()
        if not cfg:
            print("No saved configuration found, please run interactively first.")
            sys.exit(1)
        choice = cfg.get("choice")
        ip = cfg.get("ip")
        step = cfg.get("step")

    if choice == "2":
        manual_mtu_set()
        return

    interfaces = get_network_interfaces()
    if not interfaces:
        print("No valid network interfaces found.")
        sys.exit(1)

    for interface in interfaces:
        print(f"\n[*] Processing interface: {interface}")
        find_max_mtu(ip, interface, step)

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
        print("\nInterrupted by user. Exiting...")
        sys.exit(0)
