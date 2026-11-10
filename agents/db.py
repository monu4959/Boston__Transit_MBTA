import os
import pandas as pd
import snowflake.connector
from getpass import getpass
from dotenv import load_dotenv

load_dotenv()


def _private_key():
    """Key-pair login. The key comes from SNOWFLAKE_PRIVATE_KEY (its text, used in CI and
    hosted apps) or SNOWFLAKE_PRIVATE_KEY_FILE (a path, used locally). None if neither is set."""
    pem = os.getenv("SNOWFLAKE_PRIVATE_KEY")
    path = os.getenv("SNOWFLAKE_PRIVATE_KEY_FILE")
    if not pem and path:
        with open(os.path.expanduser(path), "rb") as f:
            pem = f.read()
    if not pem:
        return None
    from cryptography.hazmat.primitives import serialization
    key = serialization.load_pem_private_key(pem.encode() if isinstance(pem, str) else pem, password=None)
    return key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def get_connection(schema="RAW"):
    """Connect using settings from .env (see sql/01_setup.sql for the account setup)."""
    missing = [k for k in ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER") if not os.getenv(k)]
    if missing:
        raise RuntimeError("Missing Snowflake settings in .env: " + ", ".join(missing))

    params = dict(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        role=os.getenv("SNOWFLAKE_ROLE"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        database=os.getenv("SNOWFLAKE_DATABASE", "TRANSITWISE_DB"),
        schema=schema,
        login_timeout=30,
    )
    key = _private_key()
    if key:
        params.update(private_key=key, authenticator="SNOWFLAKE_JWT")
    else:
        params["password"] = os.getenv("SNOWFLAKE_PASSWORD") or getpass("Snowflake password: ")
    return snowflake.connector.connect(**{k: v for k, v in params.items() if v is not None})


def query_df(conn, sql, params=None):
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [c[0] for c in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=cols)
