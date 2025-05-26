import os
import subprocess
import sys
import shutil
import time
import re

try:
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

    def exit():
        exit = input("\n\n do you want to exit ? (y/n) > ")
        if exit == "y":
            sys.exit(1)
        else:
            main()
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
        print(f"💾 Saving MTU setting permanently for {interface}...")

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

        print(" Could not detect Netplan or ifupdown. Please set MTU manually.")


    def find_max_mtu(ip, proto, interface, step):
        min_mtu = 1420
        max_mtu = 1475
        last_success = None

        print(f"🚀 Starting MTU discovery for {proto} on {interface} -> {ip}...")
        mtu = max_mtu
        while mtu >= min_mtu:
            print(f"📶 Testing MTU: {mtu} on {interface}...", end=' ')
            size = mtu - (28 if proto == "IPv4" else 48)
            ping_cmd = ["ping", "-M", "do", "-c", "1", "-s", str(size), ip, "-W", "1"] \
                if proto == "IPv4" else ["ping6", "-M", "do", "-c", "1", "-s", str(size), ip, "-W", "1"]

            result = subprocess.run(ping_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            if result.returncode == 0:
                print("Success")
                last_success = mtu
                break
            else:
                print("❌ Failed")

            mtu -= step
            time.sleep(1)

        if last_success:
            print(f"\n📏 Maximum working MTU for {interface} is: {last_success}")
            print(f"🛠️ Setting MTU to {last_success} on {interface}...")
            result = subprocess.run(["sudo", "ip", "link", "set", "dev", interface, "mtu", str(last_success)])
            if result.returncode == 0:
                print(f"✅ MTU successfully set to {last_success} on {interface}")
                save_mtu_setting(interface, last_success)
            else:
                print("Failed to apply MTU on interface:", interface)
        else:
            print(f"No working MTU found for {interface} in range {min_mtu}-{max_mtu}")


    def main():
        print_banner()
        check_requirements()
        ip_type, ip, step = show_menu()
        proto = "IPv4" if ip_type == "1" else "IPv6"

        interfaces = get_network_interfaces()
        if not interfaces:
            print("No valid network interfaces found.")
            sys.exit(1)

        for interface in interfaces:
            print(f"\n Processing interface: {interface}")
            find_max_mtu(ip, proto, interface, step)


    if __name__ == "__main__":
        main()
except KeyboardInterrupt:
    exit()
