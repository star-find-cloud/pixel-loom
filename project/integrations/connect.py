"""Compatibility helper; explicitly register this installation with a chosen client."""
import argparse
from pixel_workbench.integration import main

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("client", choices=("codex", "claude-desktop", "both"))
    args = parser.parse_args()
    main(["--install", args.client])
