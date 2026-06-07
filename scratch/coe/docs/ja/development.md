# 開発

[English](../development.md) | [简体中文](../zh/development.md)

ここにはソースからのビルドとローカル開発フローをまとめます。一般ユーザー向けのインストールと設定は [install.md](../install.md) と [configuration.md](../configuration.md) に残します。

## 前提

通常の開発コマンドでは次を前提にします。

- Go toolchain
- `git`
- `cmake`
- `pkg-config`

Fcitx5 モジュールをビルドするなら、さらに次が必要です。

- C++ コンパイラ
- `pkg-config` パッケージ `Fcitx5Core` と `dbus-1`

## テストとローカル実行

Go のテストを実行:

```bash
go test ./...
```

よく使うソース実行コマンド:

```bash
go run ./cmd/coe doctor
go run ./cmd/coe config init
go run ./cmd/coe serve --log-level debug
```

すでに設定ファイルがあるなら、`coe serve --log-level debug` がローカルの挙動確認には一番速い入口です。

## ローカル Release Bundle

GitHub Releases から取らずにローカル成果物でインストーラを試すには:

```bash
./scripts/build-release-bundle.sh dev
./scripts/install.sh --bundle ./dist/release/coe_dev_linux_amd64.tar.gz
```

展開済み bundle ディレクトリからもインストールできます。

```bash
./scripts/install.sh --bundle ./dist/release/bundle-amd64
```

補足:

- `./scripts/build-release-bundle.sh <version> [arch] [output-dir]`
- デフォルト出力先は `dist/release`
- bundle ビルダーは Fcitx5 runtime asset も一緒に同梱します
- `--bundle` は通常のインストールフローを再利用し、ダウンロードだけを省きます

## Fcitx5 モジュール

モジュールを直接ビルド:

```bash
./scripts/build-fcitx-module.sh
```

system 風のインストールレイアウトで確認したい場合:

```bash
./scripts/build-fcitx-module.sh --system
```

モジュール固有の挙動、インストール先、パッケージングの詳細は [packaging/fcitx5/README.md](../../packaging/fcitx5/README.md) を参照してください。
