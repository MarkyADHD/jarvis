
"""
One-time Spotify Control V2 setup.

Before running:
1. Create an app at https://developer.spotify.com/dashboard
2. Add this Redirect URI to the app:
   http://127.0.0.1:8888/callback
3. Copy your Spotify Client ID.
4. In PowerShell:
   setx JARVIS_SPOTIFY_CLIENT_ID "YOUR_CLIENT_ID"
5. Close/reopen PowerShell.
6. Run this script.

This uses OAuth Authorization Code with PKCE.
No Spotify client secret is required.
"""

import os
import sys

import jarvis_spotify_v2 as spotify


def main():
    cid = os.getenv("JARVIS_SPOTIFY_CLIENT_ID", "").strip()

    if not cid:
        print("JARVIS_SPOTIFY_CLIENT_ID is not set.")
        print()
        print('Run:')
        print('setx JARVIS_SPOTIFY_CLIENT_ID "YOUR_SPOTIFY_CLIENT_ID"')
        print()
        print("Then CLOSE and reopen PowerShell before running this again.")
        raise SystemExit(1)

    print("Opening Spotify authorization in your browser...")
    print("Leave this window open.")
    print()

    ok, message = spotify.authorize_interactive()

    print(message)

    if not ok:
        raise SystemExit(1)

    print()
    print("Spotify Control V2 is ready.")
    print("You can now say:")
    print('Jarvis play Not Like Us by Kendrick Lamar on Spotify')


if __name__ == "__main__":
    main()
