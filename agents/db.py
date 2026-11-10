import os
import re
import sys
import pandas as pd
import snowflake.connector
from getpass import getpass
from dotenv import load_dotenv

load_dotenv()


def _env(name, default=None):
    """An environment setting, with blank values (e.g. an unset GitHub secret) treated as missing."""
    value = (os.getenv(name) or "").strip().strip('"').strip("'")
    return value or default


def _clean_pem(text):
    """Accept the key however it was pasted: with literal \\n, CRLF line endings,
    on one line, or without the BEGIN/END lines."""
    text = text.replace("\\n", "\n").replace("\r", "").strip()
    if "PUBLIC KEY" in text:
        raise RuntimeError("SNOWFLAKE_PRIVATE_KEY holds the public key (.pub). "
                           "Use the private key file (.p8) instead.")
    m = re.search(r"-----BEGIN ([A-Z ]+)-----(.*?)-----END \1-----", text, re.S)
    label, body = (m.group(1), m.group(2)) if m else ("PRIVATE KEY", text)
    body = re.sub(r"\s+", "", body)
    lines = [body[i:i + 64] for i in range(0, len(body), 64)]
    return f"-----BEGIN {label}-----\n" + "\n".join(lines) + f"\n-----END {label}-----\n"


def _private_key():
    """Key-pair login. The key comes from SNOWFLAKE_PRIVATE_KEY (its text, used in CI and
    hosted apps) or SNOWFLAKE_PRIVATE_KEY_FILE (a path, used locally). None if neither is set."""
    pem = _env("SNOWFLAKE_PRIVATE_KEY")
    path = _env("SNOWFLAKE_PRIVATE_KEY_FILE")
    if not pem and path:
        with open(os.path.expanduser(path), encoding="utf-8") as f:
            pem = f.read()
    if not pem:
        return None
    from cryptography.hazmat.primitives import serialization
    try:
        key = serialization.load_pem_private_key(_clean_pem(pem).encode(), password=None)
    except ValueError as e:
        raise RuntimeError("SNOWFLAKE_PRIVATE_KEY could not be read. Paste the whole .p8 file, "
                           f"including the BEGIN/END lines ({e})") from None
    return key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def get_connection(schema="RAW"):
    """Connect using settings from .env (see sql/01_setup.sql for the account setup)."""
    missing = [k for k in ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER") if not _env(k)]
    if missing:
        raise RuntimeError("Missing Snowflake settings: " + ", ".join(missing))

    params = dict(
        account=_env("SNOWFLAKE_ACCOUNT"),
        user=_env("SNOWFLAKE_USER"),
        role=_env("SNOWFLAKE_ROLE"),
        warehouse=_env("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        database=_env("SNOWFLAKE_DATABASE", "TRANSITWISE_DB"),
        schema=schema,
        login_timeout=30,
    )
    key = _private_key()
    if key:
        params.update(private_key=key, authenticator="SNOWFLAKE_JWT")
    elif _env("SNOWFLAKE_PASSWORD"):
        params["password"] = _env("SNOWFLAKE_PASSWORD")
    elif sys.stdin.isatty():
        params["password"] = getpass("Snowflake password: ")
    else:
        raise RuntimeError("No Snowflake login found: set SNOWFLAKE_PRIVATE_KEY "
                           "(or SNOWFLAKE_PRIVATE_KEY_FILE / SNOWFLAKE_PASSWORD).")
    return snowflake.connector.connect(**{k: v for k, v in params.items() if v is not None})


def query_df(conn, sql, params=None):
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [c[0] for c in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=cols)
