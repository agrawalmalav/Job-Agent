from __future__ import annotations

import getpass
import sys

import bcrypt


def main() -> None:
    password = getpass.getpass("Enter password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Error: passwords do not match.")
        sys.exit(1)
    if not password:
        print("Error: password cannot be empty.")
        sys.exit(1)

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    print("\nGenerated bcrypt hash:\n")
    print(password_hash)
    print("\nExample Streamlit secrets block:\n")
    print("[auth.users.example_user]")
    print('display_name = "Example User"')
    print(f'password_hash = "{password_hash}"')


if __name__ == "__main__":
    main()
