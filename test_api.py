"""
Check that .env exists and API keys are set (without printing secrets).
Run: python test_api.py
"""

import os
from pathlib import Path

from dotenv import load_dotenv

def main():
    root = Path(__file__).resolve().parent
    env_path = root / ".env"
    print("Project root:", root)
    print(".env path:", env_path)
    print(".env exists:", env_path.exists())
    if not env_path.exists():
        print("Create .env from .env.example and add testnet/mainnet API keys.")
        return
    load_dotenv(env_path)
    use_testnet = os.getenv("USE_TESTNET", "true").lower() in ("true", "1", "yes")
    if use_testnet:
        api_key = (os.getenv("BINANCE_TESTNET_API_KEY") or os.getenv("BINANCE_API_KEY") or "").strip()
        api_secret = (os.getenv("BINANCE_TESTNET_API_SECRET") or os.getenv("BINANCE_API_SECRET") or "").strip()
        mode = "TESTNET (demo)"
    else:
        api_key = (os.getenv("BINANCE_MAINNET_API_KEY") or os.getenv("BINANCE_API_KEY") or "").strip()
        api_secret = (os.getenv("BINANCE_MAINNET_API_SECRET") or os.getenv("BINANCE_API_SECRET") or "").strip()
        mode = "MAINNET (live)"
    print("USE_TESTNET:", use_testnet, "->", mode)
    print("API key:", "SET" if api_key else "NOT SET")
    print("API secret:", "SET" if api_secret else "NOT SET")
    if not api_key or not api_secret:
        print("Tip: Use BINANCE_TESTNET_* / BINANCE_MAINNET_* in .env and set USE_TESTNET to switch.")

if __name__ == "__main__":
    main()
