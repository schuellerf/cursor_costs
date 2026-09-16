# Cursor Spend Widget Helper

Unofficial helper. Licensed under [MIT](LICENSE). It only uses **your** local Firefox `cursor.com` session (no API key, no stored token). The dashboard endpoints are undocumented and can change; this is not affiliated with Cursor.

Prints this month’s Cursor spend for the Firefox-logged-in user:

```
Cursor:
$12.34
```

It does **not** use an API key. On Linux it copies Firefox’s `cookies.sqlite` (normal, Flatpak, or Snap profile), reads `WorkosCursorSessionToken` for `cursor.com`, and calls the dashboard spend API with that session.

If the cookie is missing or Cursor rejects it (expired / logged out), stdout is only:

```
Please go to https://cursor.com/dashboard
```

Open that URL **in Firefox**, sign in, then run the script again. Firefox writes a fresh session cookie; the script never stores one itself. Details of what failed go to stderr.

`--directory` must be this repo (so uv does not use some other directory’s venv). For a taskbar widget, discard stderr:

```bash
uv run --directory /path/to/cursor_costs python cursor_spend.py 2>/dev/null
```
