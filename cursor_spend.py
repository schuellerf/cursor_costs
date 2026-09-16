#!/usr/bin/env python3
import glob
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import traceback
import urllib.error
import urllib.parse
import urllib.request


class SmartRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Custom redirect handler to preserve POST data and sync Origin headers on redirects."""

    def http_error_308(self, req, fp, code, msg, headers):
        return self.http_error_302(req, fp, code, msg, headers)

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if code in (307, 308) and req.get_method() == "POST":
            new_headers = {k: v for k, v in req.headers.items()}
            parsed_new = urllib.parse.urlparse(newurl)
            new_origin = f"{parsed_new.scheme}://{parsed_new.netloc}"
            new_headers["Origin"] = new_origin
            new_headers["Referer"] = f"{new_origin}/settings"
            return urllib.request.Request(
                newurl,
                data=req.data,
                headers=new_headers,
                origin_req_host=req.origin_req_host,
                method="POST",
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def get_firefox_cursor_cookie():
    """Finds and extracts WorkosCursorSessionToken from Firefox profiles on Linux."""
    search_patterns = [
        os.path.expanduser("~/.mozilla/firefox/*/cookies.sqlite"),
        os.path.expanduser(
            "~/.var/app/org.mozilla.firefox/data/mozilla/firefox/*/cookies.sqlite"
        ),
        os.path.expanduser(
            "~/snap/firefox/common/.mozilla/firefox/*/cookies.sqlite"
        ),
    ]

    cookie_files = []
    for pattern in search_patterns:
        cookie_files.extend(glob.glob(pattern))

    if not cookie_files:
        return None

    cookie_files.sort(key=os.path.getmtime, reverse=True)

    for db_path in cookie_files:
        temp_db = os.path.join(
            tempfile.gettempdir(), "cursor_firefox_cookies.sqlite"
        )
        try:
            shutil.copy2(db_path, temp_db)
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT value FROM moz_cookies 
                WHERE name = 'WorkosCursorSessionToken' 
                ORDER BY lastAccessed DESC LIMIT 1
            """)
            row = cursor.fetchone()
            conn.close()
            os.remove(temp_db)

            if row and row[0]:
                return row[0]
        except Exception as e:
            sys.stderr.write(f"Error reading DB {db_path}: {e}\n")
            if os.path.exists(temp_db):
                os.remove(temp_db)
            continue

    return None


def browser_headers(cookie):
    return {
        "Content-Type": "application/json",
        "Cookie": f"WorkosCursorSessionToken={cookie}",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
        "Origin": "https://cursor.com",
        "Referer": "https://cursor.com/settings",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }


def dashboard_json(opener, cookie, url, payload=None, method=None):
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        method = method or "POST"
    req = urllib.request.Request(
        url,
        data=data,
        headers=browser_headers(cookie),
        method=method or "GET",
    )
    with opener.open(req, timeout=5) as response:
        return json.loads(response.read().decode())


def cookie_user_id(cookie):
    token = urllib.parse.unquote(cookie)
    prefix = token.split("::", 1)[0]
    return prefix or None


def cents_to_dollars(value):
    try:
        return float(value) / 100.0
    except (TypeError, ValueError):
        return 0.0


def member_spend_cents(member):
    if not isinstance(member, dict):
        return 0
    for key in ("overallSpendCents", "spendCents"):
        if member.get(key) is not None:
            return member[key]
    return 0


def spend_for_current_user(opener, cookie, team_id, spend_data):
    members = spend_data.get("teamMemberSpend") or []
    team = dashboard_json(
        opener,
        cookie,
        "https://cursor.com/api/dashboard/team",
        {"teamId": team_id},
    )
    user_id = team.get("userId")
    for member in members:
        if member.get("userId") == user_id:
            return cents_to_dollars(member_spend_cents(member))
    sys.stderr.write(
        f"Error: no teamMemberSpend row for userId {user_id}.\n"
    )
    return None


def usage_fallback(opener, cookie):
    user_id = cookie_user_id(cookie)
    if not user_id:
        sys.stderr.write(
            "Error: not on a Cursor team and session token has no user id.\n"
        )
        return None
    url = "https://cursor.com/api/usage?" + urllib.parse.urlencode(
        {"user": user_id}
    )
    data = dashboard_json(opener, cookie, url)
    for model in data.values():
        if isinstance(model, dict):
            for key in ("spendCents", "overallSpendCents"):
                if model.get(key) is not None:
                    return cents_to_dollars(model[key])
    sys.stderr.write(
        "Error: not on a Cursor team; /api/usage has no spend in cents.\n"
    )
    return None


def resolve_team_id(opener, cookie):
    override = os.environ.get("CURSOR_TEAM_ID")
    if override:
        try:
            return int(override)
        except ValueError:
            print("Cursor Err: Bad Team")
            sys.stderr.write(
                "Error: CURSOR_TEAM_ID must be an integer.\n"
            )
            return False

    teams_data = dashboard_json(
        opener,
        cookie,
        "https://cursor.com/api/dashboard/teams",
        {},
    )
    teams = teams_data.get("teams") or []
    if not teams:
        return None
    return teams[0].get("id")


def main():
    cookie = get_firefox_cursor_cookie()
    if not cookie:
        print("Cursor Err: No Cookie")
        sys.stderr.write(
            "Error: WorkosCursorSessionToken not found in Firefox cookies.\n"
        )
        return

    opener = urllib.request.build_opener(SmartRedirectHandler)

    try:
        team_id = resolve_team_id(opener, cookie)
        if team_id is False:
            return

        if team_id is None:
            spend = usage_fallback(opener, cookie)
            if spend is None:
                print("Cursor Err: No Team")
                return
            print(f"Cursor: ${spend:.2f}")
            return

        spend_data = dashboard_json(
            opener,
            cookie,
            "https://cursor.com/api/dashboard/get-team-spend",
            {"teamId": team_id},
        )
        spend = spend_for_current_user(opener, cookie, team_id, spend_data)
        if spend is None:
            print("Cursor Err: No User")
            return
        print(f"Cursor: ${spend:.2f}")

    except urllib.error.HTTPError as e:
        print(f"Cursor Err: {e.code}")
        try:
            body = e.read().decode("utf-8")
            sys.stderr.write(
                f"HTTPError {e.code} ({e.reason}):\n{body}\n"
            )
        except Exception:
            sys.stderr.write(f"HTTPError {e.code} ({e.reason})\n")

    except urllib.error.URLError as e:
        print("Cursor Err: Network")
        sys.stderr.write(f"URLError: {e.reason}\n")

    except Exception:
        print("Cursor Err: Unknown")
        traceback.print_exc(file=sys.stderr)


if __name__ == "__main__":
    main()
