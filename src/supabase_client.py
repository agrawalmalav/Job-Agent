from __future__ import annotations

import os


def get_supabase_client():
    url = os.getenv("SUPABASE_URL")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not service_role_key:
        raise RuntimeError(
            "Supabase is selected, but SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing."
        )

    try:
        from supabase import create_client
    except ImportError as exc:
        raise RuntimeError("supabase is not installed. Run pip install -r requirements.txt.") from exc

    return create_client(url, service_role_key)
