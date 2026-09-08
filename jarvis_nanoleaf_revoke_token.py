
from getpass import getpass
import requests

DEFAULT_IP = "192.168.0.113"
PORT = 16021

print("=== Nanoleaf Token Revoker ===")
print("Use this for the token that was exposed/pasted somewhere.")
print()

host = input(f"Nanoleaf IP [{DEFAULT_IP}]: ").strip() or DEFAULT_IP
token = getpass("OLD token to revoke: ").strip()

if not token:
    raise SystemExit("No token entered.")

url = f"http://{host}:{PORT}/api/v1/{token}"

try:
    r = requests.delete(url, timeout=3)

    if r.status_code == 204:
        print("PASS: old token revoked.")
    elif r.status_code == 401:
        print("The token was already invalid/revoked.")
    else:
        print(f"Nanoleaf returned HTTP {r.status_code}: {r.text[:200]}")
except Exception as e:
    print("Request failed:", e)
