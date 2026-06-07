# 开发

[English](../development.md) | [日本語](../ja/development.md)

这里集中放源码构建和本地开发流程。面向普通用户的安装和配置说明仍然放在 [install.md](../install.md) 和 [configuration.md](../configuration.md)。

## 前置条件

常见开发命令默认需要：

- Go toolchain
- `git`
- `cmake`
- `pkg-config`

如果要构建 Fcitx5 模块，还需要：

- C++ 编译器
- `pkg-config` 包 `Fcitx5Core` 和 `dbus-1`

## 测试与本地运行

运行 Go 测试：

```bash
go test ./...
```

常用源码运行命令：

```bash
go run ./cmd/coe doctor
go run ./cmd/coe config init
go run ./cmd/coe serve --log-level debug
```

如果你已经有配置文件，`coe serve --log-level debug` 是本地观察运行时行为最快的入口。

## 本地 Release Bundle

如果你想用本地产物走安装流程，而不是从 GitHub Releases 下载：

```bash
./scripts/build-release-bundle.sh dev
./scripts/install.sh --bundle ./dist/release/coe_dev_linux_amd64.tar.gz
```

也可以直接从解压后的 bundle 目录安装：

```bash
./scripts/install.sh --bundle ./dist/release/bundle-amd64
```

说明：

- `./scripts/build-release-bundle.sh <version> [arch] [output-dir]`
- 默认输出目录是 `dist/release`
- bundle 构建脚本会一并打包 Fcitx5 runtime 资源
- `--bundle` 复用正常安装流程，只是跳过下载步骤

## Fcitx5 模块

直接构建模块：

```bash
./scripts/build-fcitx-module.sh
```

如果你想用 system 风格的安装路径布局：

```bash
./scripts/build-fcitx-module.sh --system
```

模块细节、安装路径和打包说明见 [packaging/fcitx5/README.md](../../packaging/fcitx5/README.md)。
