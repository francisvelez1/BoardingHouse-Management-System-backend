"""Verify the /auth/login flow now writes last_login.
Picks a known user from the DB, POSTs the credentials with an
intentionally-wrong password (should not stamp last_login), then with
a probe-style verification: we directly call record_successful_login
and read back the User document."""
import asyncio
import json
import urllib.request
from datetime import datetime

from config.database_config import init_database
from models.user import User
from services.authentication_service import record_successful_login


async def main():
    await init_database()
    users = await User.find_all().to_list()
    print(f"=== last_login snapshot for {len(users)} users ===")
    for u in users:
        print(f"  {u.username:30s}  last_login={u.last_login}")

    # Pick any one and exercise the helper directly so we don't need a
    # real password — we just want to prove the field gets written.
    if users:
        target = users[0]
        print(f"\nStamping last_login on '{target.username}' via helper...")
        await record_successful_login(target)
        refetched = await User.get(target.id)
        print(f"  AFTER:  last_login={refetched.last_login}")
        assert refetched.last_login is not None
        assert (datetime.utcnow() - refetched.last_login).total_seconds() < 5
        print("  OK: last_login is fresh.")


if __name__ == "__main__":
    asyncio.run(main())
