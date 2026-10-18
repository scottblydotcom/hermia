"""The one rule every host address must pass, wherever it enters hermia."""


def reject_login_in_host(url: str, where: str) -> None:
    """Raise ValueError if ``url`` carries a login (``user:password@host``).

    Some HTTP clients, requests among them, turn a login written into an address into Basic
    auth. hermia never designed for that: such an address leaks the password into every error,
    banner and saved result row (hermia-emsn). An Ollama base URL never needs an "@", so any
    "@" is refused. The message deliberately does not repeat the address -- it holds the
    password. hermia authenticates with a bearer token only: auth.bearer.key_env in a
    ``fleet:`` file, auth_header_env in a TUI ``hosts:`` file. Username/password (Basic) logins
    have no supported replacement.
    """
    if "@" in url:
        raise ValueError(
            f"{where}: the host address contains '@', i.e. a login written into the address "
            "(user:password@host). hermia does not accept logins in host addresses: they leak "
            "into its output and saved results. hermia sends only a bearer token, set per host in "
            "a fleet file from an environment variable: auth.bearer.key_env in a 'fleet:' file, "
            "auth_header_env in a 'hosts:' file. Username/password logins are not supported."
        )
