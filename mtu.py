import os
import subprocess
import sys
import shutil
import time


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
    tools = ["ping", "ping6", "ip"]
    for tool in tools:
        if shutil.which(tool) is None:
            print(f"{tool} is missing. Installing...")
            subprocess.run(["sudo", "apt-get", "update"])
            subprocess.run(["sudo", "apt-get", "install", "-y", tool])


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
        print("Invalid choice. Please enter 1 or 2.")

    dest_ip = input("Enter destination IP address (default: 1.1.1.1) : ").strip()
    if not dest_ip:
        dest_ip = "1.1.1.1".strip()


    iface_default = input("Your current network interface is detected as: eth0 Is this correct? (Y/n):  ").strip().lower()
    if iface_default == "y":
        interface = "eth0"
    elif iface_default == "n": 
        interface = input("Enter interface name : ").strip()
        if not interface:
            print("❌ No interface entered. Exiting.")
            sys.exit(1)
    else:
        print("❌ Invalid input. Exiting.")
        sys.exit(1)    
    while True:
        try:
            step_size = int(input("Enter step size (1-10) >>  "))
            if 1 <= step_size <= 10:
                break
        except ValueError:
            pass
        print("❌ Invalid step size. Enter a number between 1 and 10.")

    return ip_type, dest_ip, interface, step_size


def save_mtu_setting(interface, mtu):
    print("💾 Saving MTU setting permanently...")

    if os.path.exists("/etc/netplan/"):
        netplan_files = [f for f in os.listdir("/etc/netplan/") if f.endswith(".yaml")]
        if netplan_files:
            netplan_path = os.path.join("/etc/netplan", netplan_files[0])
            print(f"🔧 Updating {netplan_path} with MTU: {mtu}")
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
        print("🔧 Updating /etc/network/interfaces...")
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

    print("Could not detect Netplan or ifupdown. Please set MTU manually.")


def find_max_mtu(ip, proto, interface, step):
    min_mtu = 1000
    max_mtu = 1500
    last_success = max_mtu

    print(f"🚀 Starting MTU discovery for {proto} on {ip}...")
    subprocess.run(["sudo", "ip", "link", "set", "dev", interface, "mtu", str(max_mtu)])

    mtu = min_mtu
    while mtu <= max_mtu:
        print(f"📶 Testing MTU: {mtu}...", end=' ')
        size = mtu - (28 if proto == "IPv4" else 48)
        ping_cmd = ["ping", "-M", "do", "-c", "1", "-s", str(size), ip, "-W", "1"] \
            if proto == "IPv4" else ["ping6", "-M", "do", "-c", "1", "-s", str(size), ip, "-W", "1"]

        result = subprocess.run(ping_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if result.returncode == 0:
            print(" Success")
            last_success = mtu
        else:
            print(" Failed")
            break

        mtu += step
        time.sleep(1)

    final_mtu = last_success - 2
    print(f"\n Maximum working MTU for {proto} is: {last_success}")
    print(f" Setting MTU to {final_mtu} on {interface}...")
    result = subprocess.run(["sudo", "ip", "link", "set", "dev", interface, "mtu", str(final_mtu)])
    if result.returncode == 0:
        print(f"✅ MTU successfully set to {final_mtu}")
        save_mtu_setting(interface, final_mtu)
    else:
        print(" Failed to apply MTU")


def main():
    print_banner()
    check_requirements()
    ip_type, ip, interface, step = show_menu()
    proto = "IPv4" if ip_type == "1" else "IPv6"
    find_max_mtu(ip, proto, interface, step)


if __name__ == "__main__":
    main()
