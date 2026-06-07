# Development

[简体中文](./zh/development.md) | [日本語](./ja/development.md)

This page collects source-build and local development workflows. User-facing install and configuration docs stay in [`install.md`](./install.md) and [`configuration.md`](./configuration.md).

## Prerequisites

Common development commands assume:

- Go toolchain
- `git`
- `cmake`
- `pkg-config`

For the Fcitx5 module you also need:

- a C++ compiler
- `pkg-config` packages `Fcitx5Core` and `dbus-1`

## Test And Run

Run the Go test suite:

```bash
go test ./...
```

Useful source-based commands:

```bash
go run ./cmd/coe doctor
go run ./cmd/coe config init
go run ./cmd/coe serve --log-level debug
```

If you already have a generated config, `coe serve --log-level debug` is the fastest way to inspect runtime behavior locally.

## Local Release Bundle

To exercise the installer against local artifacts instead of GitHub Releases:

```bash
./scripts/build-release-bundle.sh dev
./scripts/install.sh --bundle ./dist/release/coe_dev_linux_amd64.tar.gz
```

You can also install from the extracted bundle directory:

```bash
./scripts/install.sh --bundle ./dist/release/bundle-amd64
```

Notes:

- `./scripts/build-release-bundle.sh <version> [arch] [output-dir]`
- default output dir is `dist/release`
- the bundle builder also stages the Fcitx5 runtime assets
- `--bundle` reuses the normal install flow and only skips the download step

## Fcitx5 Module

To build the module directly:

```bash
./scripts/build-fcitx-module.sh
```

For a system-style install layout:

```bash
./scripts/build-fcitx-module.sh --system
```

For module-specific behavior, install paths, and packaging details, see [`packaging/fcitx5/README.md`](../packaging/fcitx5/README.md).
