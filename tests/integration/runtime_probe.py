"""Exercise the public ``tg`` boundary against a real Telegram session."""

client = globals()["client"]
functions = globals()["functions"]
types = globals()["types"]

assert client.is_connected()
assert client.flood_sleep_threshold > 0
me = await client.get_me()  # noqa: F704
assert me is not None and me.id
full_user = await client(functions.users.GetFullUserRequest(id=types.InputUserSelf()))  # noqa: F704
assert full_user.users and full_user.users[0].id == me.id
print(f"telegram=ok id={me.id}")
