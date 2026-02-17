import socket

# Ask user for target and port
target = input("Enter the target host (e.g. www.example.com): ")
port = int(input("Enter the port you want to scan: "))

print(f"Scanning {target} on port {port}...")

def scan_port(host, port):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)  # timeout in seconds
        result = sock.connect_ex((host, port))
        if result == 0:
            print(f"Port {port} is OPEN on {host}")
        else:
            print(f"Port {port} is CLOSED on {host}")
        sock.close()
    except Exception as e:
        print(f"Error: {e}")

scan_port(target, port)