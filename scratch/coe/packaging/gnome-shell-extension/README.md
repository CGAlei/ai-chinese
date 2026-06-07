# GNOME Shell Extension

This directory contains a minimal GNOME Shell extension for focus-aware paste.

Install path:

- `~/.local/share/gnome-shell/extensions/coe-focus-helper@mistermorph.com`

Quick install:

```bash
mkdir -p ~/.local/share/gnome-shell/extensions
cp -r packaging/gnome-shell-extension/coe-focus-helper@mistermorph.com \
  ~/.local/share/gnome-shell/extensions/
```

Then enable it with GNOME Extensions or `gnome-extensions enable coe-focus-helper@mistermorph.com`.

After that, set:

```yaml
output:
  use_gnome_focus_helper: true
```

The extension exports:

- service: `org.gnome.Shell`
- path: `/org/gnome/Shell/Extensions/FocusWmClass`
- interface: `org.gnome.Shell.Extensions.FocusWmClass`
