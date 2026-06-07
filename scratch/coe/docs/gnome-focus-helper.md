# GNOME Focus Helper

Coe can choose a different paste shortcut when the focused target is a terminal-like app. On GNOME, the clean way to do that is a small GNOME Shell extension that exposes the focused window `wm_class` over D-Bus.

This is GNOME-only. It is not a cross-desktop interface.

## Why It Exists

`Ctrl+V` works in many GUI text fields. It does not work in many terminals. Terminals usually want `Ctrl+Shift+V` or `Shift+Insert`.

Wayland and the portal APIs let Coe inject a paste shortcut. They do not tell Coe what the current target app is. A GNOME Shell extension can answer that question because Shell already knows the focused window.

## D-Bus Contract

Service:

- `org.gnome.Shell`

Path:

- `/org/gnome/Shell/Extensions/FocusWmClass`

Interface:

- `org.gnome.Shell.Extensions.FocusWmClass`

Method:

- `Get() -> (wm_class)`

Return values:

- `wm_class`
  WM class of the currently focused window.

The Go side treats an empty string as "unknown" and falls back to the default paste shortcut.

Example probe:

```bash
gdbus call --session \
  --dest org.gnome.Shell \
  --object-path /org/gnome/Shell/Extensions/FocusWmClass \
  --method org.gnome.Shell.Extensions.FocusWmClass.Get
```

## Shell Side

The extension should read the current focus from Mutter / GNOME Shell:

- `global.display.focus_window`
- `window.get_wm_class()`
- `notify::focus-window`

The extension caches the current `wm_class` in memory and only answers the focused-window query. It does not inject input itself.

## Coe Side

When `output.use_gnome_focus_helper: true`:

1. Coe connects to the session bus.
2. Coe calls `Get()` before auto-paste.
3. Coe classifies the target.
4. If the target looks terminal-like, Coe uses `output.terminal_paste_shortcut`.
5. Otherwise Coe uses `output.paste_shortcut`.

Current built-in terminal-like matchers include:

- `ptyxis`
- `kgx`
- `gnome-console`
- `gnome-terminal`
- `wezterm`
- `alacritty`
- `kitty`
- `foot`
- `ghostty`
- `terminal`
- `codex`

This matcher list is intentionally simple. It can be expanded later.

## Failure Mode

If the helper is disabled, missing, or errors at runtime:

- Coe falls back to `output.paste_shortcut`
- Coe does not block dictation
- startup logs will show a warning if the helper was enabled but unavailable

## Example Config

```yaml
output:
  enable_auto_paste: true
  paste_shortcut: ctrl+v
  terminal_paste_shortcut: ctrl+shift+v
  use_gnome_focus_helper: true
```

New default configs already enable `use_gnome_focus_helper: true`.
