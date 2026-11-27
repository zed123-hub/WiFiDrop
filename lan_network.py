"""Find directly attached private IPv4 networks without contacting a remote service."""
import ipaddress
import re
import socket
import subprocess
import sys


LOCAL_RANGES = tuple(ipaddress.IPv4Network(cidr) for cidr in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16"))


def is_lan(address):
    return any(address in block for block in LOCAL_RANGES)


def command_output(*args):
    return subprocess.check_output(args, stderr=subprocess.DEVNULL, timeout=4,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).decode("ascii", "replace")


def windows_interfaces(output):
    interfaces, default_routes = {}, []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 5 or not fields[-1].isdigit():
            continue
        try:
            address = ipaddress.IPv4Address(fields[-2])
            if not is_lan(address):
                continue
            network = ipaddress.IPv4Network((fields[0], fields[1]))
        except ValueError:
            continue
        if network.prefixlen == 0:
            default_routes.append((int(fields[-1]), str(address)))
        # On-link routes have a localized word in the gateway column. Match by
        # interface address and exact network instead of relying on that word.
        elif network.prefixlen < 32 and address in network and not re.match(r"^\d+\.", fields[2]):
            current = interfaces.get(str(address))
            if current is None or current.prefixlen < network.prefixlen:
                interfaces[str(address)] = network
    return interfaces, [addr for _, addr in sorted(default_routes)]


def unix_interfaces():
    interfaces, preferred = {}, []
    if sys.platform == "darwin":
        output = command_output("/sbin/ifconfig", "-a")
        interface = ""
        try:
            route = command_output("/sbin/route", "-n", "get", "default")
        except (OSError, subprocess.SubprocessError):
            route = ""
        default = re.search(r"^\s*interface:\s*(\S+)", route, re.MULTILINE)
        for line in output.splitlines():
            if line and not line[0].isspace():
                interface = line.split(":", 1)[0]
            match = re.match(r"\s*inet\s+([\d.]+)\s+netmask\s+(0x[\da-fA-F]+)", line)
            if match:
                address = ipaddress.IPv4Address(match[1])
                if is_lan(address):
                    mask = str(ipaddress.IPv4Address(int(match[2], 16)))
                    interfaces[str(address)] = ipaddress.IPv4Network((address, mask), strict=False)
                    if default and default[1] == interface:
                        preferred.insert(0, str(address))
                    elif interface.startswith("en"):
                        preferred.append(str(address))
    else:
        # A small fallback for source users on Linux. Windows and macOS use
        # their actual interface masks above, including on an offline Wi-Fi.
        import fcntl
        import struct
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            for _, name in socket.if_nameindex():
                request = struct.pack("256s", name.encode()[:15])
                try:
                    address = ipaddress.IPv4Address(fcntl.ioctl(sock, 0x8915, request)[20:24])
                    mask = str(ipaddress.IPv4Address(fcntl.ioctl(sock, 0x891b, request)[20:24]))
                except OSError:
                    continue
                if is_lan(address):
                    interfaces[str(address)] = ipaddress.IPv4Network((address, mask), strict=False)
    return interfaces, preferred


def local_networks():
    try:
        if sys.platform == "win32":
            interfaces, preferred = windows_interfaces(command_output("route.exe", "print", "-4"))
        else:
            interfaces, preferred = unix_interfaces()
    except (OSError, ValueError, ImportError, subprocess.SubprocessError):
        return {}
    # Put the active router's interface first for the QR code.
    return {addr: interfaces[addr] for addr in dict.fromkeys([*preferred, *interfaces]) if addr in interfaces}
