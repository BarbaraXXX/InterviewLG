import argparse
import asyncio
import getpass

from interview_agent.admin_auth import create_admin_user
from interview_agent.db import init_db


async def _create_user(username: str) -> int:
    password = getpass.getpass("Admin password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match")
    await init_db()
    return await create_admin_user(username, password)


def main() -> int:
    parser = argparse.ArgumentParser(prog="interview-agent-admin")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create-user", help="Create an admin user")
    create_parser.add_argument("username")

    args = parser.parse_args()
    if args.command == "create-user":
        admin_id = asyncio.run(_create_user(args.username))
        print(f"Admin user created: id={admin_id} username={args.username}")
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
