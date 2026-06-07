# Arch Linux 安装

这篇文档说明如何在 Arch Linux 或 Manjaro 上通过 AUR 的 `makepkg` 路径安装 Coe。

当前推荐主线是：

1. 安装 Arch 运行时依赖
2. 在 `packaging/aur/coe-git/` 里执行 `makepkg`
3. 安装生成的包
4. 初始化配置并启动 `systemd --user` 服务

## 1. 安装基础依赖

先安装构建和运行依赖：

```bash
sudo pacman -S --needed \
  base-devel \
  cmake \
  dbus \
  fcitx5 \
  git \
  go \
  libnotify \
  pipewire \
  pkgconf \
  wl-clipboard \
  ydotool
```

如果你准备走 `fcitx` 模式，`fcitx5` 是必须的。

如果你准备走 `desktop` 模式，至少也需要：

- `pipewire`
- `wl-clipboard`

## 2. 获取源码

```bash
git clone https://github.com/quailyquaily/coe.git
cd coe
```

## 3. 用 AUR 目录打包

仓库里已经带了 AUR 打包目录：

```bash
cd packaging/aur/coe-git
makepkg -si
```

如果你只想先打包不安装：

```bash
makepkg
```

构建完成后会生成类似下面的包文件：

```text
coe-git-r44.3754f8f-2-x86_64.pkg.tar.zst
```

然后手动安装：

```bash
sudo pacman -U ./coe-git-*.pkg.tar.zst
```

## 4. 关于 Arch 上的 Fcitx5 CMake 编译问题

Arch 上较新的 `fcitx5` 头文件已经用了 C++20 特性，比如：

- `std::span`
- `std::source_location`
- `std::string_view::starts_with`

但上游 `packaging/fcitx5/CMakeLists.txt` 里写的是 `C++17`。所以在 Arch 的 `makepkg` 流程里，如果直接原样编译 Fcitx5 模块，就会在 CMake 构建阶段失败。

当前 AUR `PKGBUILD` 的处理方式是：

- 在 `prepare()` 里只修改 AUR 构建副本
- 把 `packaging/fcitx5/CMakeLists.txt` 里的 `CMAKE_CXX_STANDARD 17` 替换成 `20`

这样做的意图是：

- 不改主仓库的默认构建定义
- 只让 Arch 的打包副本启用 C++20
- 避免 `fcitx5` 新头文件在 Arch 上编不过

另外，`cmake --install` 在打包阶段需要通过 `DESTDIR` 环境变量 staging，不能写成 `--destdir` 参数。当前 `PKGBUILD` 已经按 Arch 可用的方式修正。

## 5. 初始化配置

安装完成后，先生成配置：

```bash
coe config init
```

配置文件位置：

```text
~/.config/coe/config.yaml
```

如果你想让 Fcitx5 直接把文本 `CommitString` 到当前输入框，建议改成：

```yaml
runtime:
  mode: fcitx
  target_desktop: gnome
  log_level: info
```

如果你更想走桌面自动粘贴路径，可以保留：

```yaml
runtime:
  mode: desktop
  target_desktop: gnome
  log_level: info
```

## 6. 启动和验证

前台调试：

```bash
coe serve --log-level debug
```

查看当前环境是否满足运行条件：

```bash
coe doctor
```

如果你要用用户服务：

```bash
systemctl --user daemon-reload
systemctl --user enable --now coe.service
systemctl --user status coe.service
```

看日志：

```bash
journalctl --user -u coe.service -f
```

## 7. Fcitx 模式检查

如果你使用 `runtime.mode: fcitx`，检查这几件事：

1. `fcitx5` 进程已经启动
2. Coe 的 Fcitx5 模块已经被安装
3. `coe doctor` 没有报告缺失的 addon config 或 module library

如果模块已经正确安装，常见文件路径会是：

```text
/usr/lib/fcitx5/libcoefcitx.so
/usr/share/fcitx5/addon/coe.conf
```

改完配置或安装完模块后，可以重启 Fcitx5：

```bash
fcitx5 -rd
```

## 8. 桌面模式检查

如果你使用 `runtime.mode: desktop`，检查：

- `wl-copy` 是否存在
- `ydotool` 是否存在
- GNOME 下需要的 portal 和自定义快捷键链路是否正常

最小可用链路通常是：

- `pw-record` 录音
- Coe 通过 portal 或剪贴板回写文本
- 再自动触发粘贴

## 9. 配置 Qwen3-ASR vLLM

如果你想在 Arch 上把 Coe 接到本地 `Qwen3-ASR`，看：

- [qwen3-asr-vllm.md](./qwen3-asr-vllm.md)

## 10. 常见问题

### `makepkg` 时 Fcitx5 模块编译失败

先确认你当前使用的是仓库里的最新 [packaging/aur/coe-git/PKGBUILD](../packaging/aur/coe-git/PKGBUILD)，因为 Arch 下需要依赖 `prepare()` 里的 C++20 替换。

### `Unknown argument --destdir`

说明你用的是旧版 `PKGBUILD`。修正后应该是：

```bash
DESTDIR="${pkgdir}" cmake --install build-fcitx5 --prefix /usr
```

### `coe doctor` 里找不到 Fcitx5 模块

确认包已经安装，而不是只执行了 `makepkg` 却没有 `pacman -U` 或 `makepkg -si`。

### 服务启动了但没有文本上屏

先分开排查：

1. `coe doctor`
2. `coe serve --log-level debug`
3. 看 ASR 是否返回文本
4. 再看 output 阶段是 portal、clipboard 还是 Fcitx commit 出问题
