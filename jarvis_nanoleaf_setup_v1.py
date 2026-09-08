
from getpass import getpass
from pathlib import Path
import sys

import jarvis_nanoleaf_v1 as n


DEFAULT_IP = "192.168.0.113"


def main():
    print("=== Jarvis Nanoleaf Setup V1 ===")
    print()
    print("Your token will be entered locally and will NOT be printed.")
    print()

    current = n.load_config()
    default_ip = str(current.get("host", "") or DEFAULT_IP)

    host = input(f"Nanoleaf IP [{default_ip}]: ").strip() or default_ip
    token = getpass("Nanoleaf auth token: ").strip()

    if not token:
        print("No token entered.")
        raise SystemExit(1)

    print()
    print("Testing connection...")

    info = n._probe(host, token, n.DEFAULT_PORT)

    if info is None:
        print("FAIL: token/IP combination did not authenticate.")
        print("Check the IP and make sure this is a fresh token for this device.")
        raise SystemExit(1)

    name = str(info.get("name", "Nanoleaf"))
    model = str(info.get("model", "") or "")
    firmware = str(info.get("firmwareVersion", "") or "")

    saved = n.save_config(
        host=host,
        token=token,
        port=n.DEFAULT_PORT,
        device_name=name,
    )

    print("PASS: connected to Nanoleaf.")
    print("Name:", name)
    if model:
        print("Model:", model)
    if firmware:
        print("Firmware:", firmware)

    print()
    if saved.get("token_storage") == "windows_dpapi":
        print("Token stored locally using Windows DPAPI.")
    else:
        print("DPAPI was unavailable, so the token was NOT written to disk.")
        print("Set JARVIS_NANOLEAF_TOKEN as an environment variable instead.")

    print("Config:", n.CONFIG_PATH)


if __name__ == "__main__":
    main()
