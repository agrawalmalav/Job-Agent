from __future__ import annotations

import bcrypt
import streamlit as st


def get_auth_users() -> dict:
    try:
        users = st.secrets["auth"]["users"]
    except Exception:
        return {}
    return dict(users)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def login_required() -> None:
    if st.session_state.get("authenticated") is True:
        return

    st.title("Job Search Agent")
    st.subheader("Login")

    users = get_auth_users()
    if not users:
        st.warning(
            "No dashboard users are configured. Add [auth.users.<username>] entries "
            "to Streamlit secrets or local .streamlit/secrets.toml."
        )
        st.stop()

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")

    if not submitted:
        st.stop()

    user = users.get(username.strip())
    password_hash = user.get("password_hash") if user else None
    if user and password_hash and verify_password(password, password_hash):
        st.session_state["authenticated"] = True
        st.session_state["username"] = username.strip()
        st.session_state["display_name"] = user.get("display_name") or username.strip()
        st.rerun()

    st.error("Invalid username or password.")
    st.stop()


def logout_button() -> None:
    display_name = st.session_state.get("display_name") or st.session_state.get("username") or "User"
    st.sidebar.caption(f"Logged in as {display_name}")
    if st.sidebar.button("Log out"):
        for key in ("authenticated", "username", "display_name"):
            st.session_state.pop(key, None)
        st.rerun()
