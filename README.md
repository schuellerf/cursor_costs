# Cursor Spend Widget Helper

Prints this month’s Cursor spend for the Firefox-logged-in user:

```
Cursor:
$139.08
```

It does **not** use an API key. On Linux it copies Firefox’s `cookies.sqlite` (normal, Flatpak, or Snap profile), reads `WorkosCursorSessionToken` for `cursor.com`, and calls the dashboard spend API with that session.

If the cookie is missing or Cursor rejects it (expired / logged out), stdout is only:

```
Please go to https://cursor.com/dashboard
```

Open that URL **in Firefox**, sign in, then run the script again. Firefox writes a fresh session cookie; the script never stores one itself. Details of what failed go to stderr.

From any directory (uses this repo’s uv project, not the cwd venv):

For showing in a taskbar widget you might want to ignore stderr:
```bash
bash -c 'uv run --directory /home/fschulle/git/cursor_costs python cursor_spend.py 2>/dev/null'
```
