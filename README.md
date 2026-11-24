# DeepinOfflineMaker

> Windows tool for building **offline incremental update packages, offline software bundles and printer drivers** for deepin 25 on LoongArch (`loong64`) machines that have no internet access.

给无外网的内网信创机做的离线交付工具：在有外网的 Windows 电脑上放一份 deepin 25 loong64 ISO，工具分析 ISO 自带包清单，把「刚装好系统本应联网升级」的包、勾选的常用软件、以及打印机驱动连同依赖一起下载打包；目标机上双击装一个图形工具，全程不用命令行、不用敲 apt。

## 它能做什么

- **离线增量升级**：以 ISO 内 `live/filesystem.packages` 为基准，按 Debian 版本规则找出官方源里更新的包，只下变化的部分（不是旧 ISO 与新 ISO 对比）。
- **离线软件安装**：软件目录来自星火商店 `loong64-store` JSON 目录（12 类约 637 个应用）、内置精选、deepin 官方源；主包与依赖分目录存放，各自建本地 apt 索引。
- **打印机驱动**：内置 15 项 loong64 驱动（CUPS 基础环境、瑞印万能、Gutenprint、HPLIP、奔图、联想、Brother、Epson、OKI、Canon BJNP 等）；目标机可检测 USB / 网络打印机并按品牌推荐、一键安装。
- **定期增量 + 网盘分发**：每次生成都会写 `project.json` 基线快照。半年后打开工具点「检查更新」即可只下这半年新增的系统/软件更新，生成自包含的增量包，整目录压缩传网盘给同样环境的同学；目标机工具启动时自动提示「有更新」。

## 快速开始

Windows 图形界面，双击即用：

| 版本 | 生成方式 | 说明 |
|---|---|---|
| 单文件便携版 | `build-portable.bat` | 一个 exe，拷到任意 Windows 机器即可，不需要附属目录 |
| 目录版 | `build.bat` | 启动更快，需连同 `_internal/` 一起拷贝 |

两种版本功能一致，都内置 v1.4 目标机图形工具 deb 和 loong64 软件目录缓存。

源码运行（需要带 tkinter 的 Python 3.14）：

```bat
python src\app.py
```

详细使用步骤、目录结构、参数说明见 **[使用说明.md](使用说明.md)**。

## 交付目录长这样

```
<输出目录>/
├── updata/            离线升级源（系统更新 deb + Packages/Packages.gz/Release）
├── offline-soft/      勾选的软件主包 + manifest.json
│   └── deps/          软件依赖（独立本地 apt 源）
├── printer-drivers/   打印机驱动 + manifest.json
│   └── deps/          驱动依赖
├── tool/              deepin-offline-upgrade_1.4_all.deb（双击安装）
├── docs/
├── project.json       基线快照 —— 下次做增量的依据，请勿删除
├── update-info.json   仅增量包有，目标机据此弹「有更新」提示
└── 使用说明.md
```

目标机工具是 GTK3 图形界面，有「离线升级 / 软件安装 / 打印机驱动」三页，安装动作通过 `pkexec` 提权调用 `helper.sh`，用临时本地 apt 源，不改动系统原有软件源配置。

## 数据来源

| 用途 | 来源 |
|---|---|
| 系统更新与依赖 | deepin 25 (crimson/beige) loong64 官方仓库 `Packages.gz`，含 USTC / 清华 / 华为云 / 官方社区镜像兜底 |
| 软件目录 | 星火商店 `https://cdn.d.store.deepinos.org.cn/loong64-store/{分类}/applist.json` |
| 内置精选 | WPS、LibreOffice、7-Zip、fcitx5 五笔、FTP、PDF、字体等（人工维护，离线可用） |
| 打印机驱动 | deepin loong64 源 + 星火商店 loong64 驱动 deb 直链 |

龙芯应用合作社前端没有稳定的公开列表接口，论坛帖子也不适合机器解析，因此这两处的常用软件由内置精选维护。

## 项目结构

```
src/            Windows 制作端（tkinter GUI + 下载/依赖解析/流程编排）
  app.py          四页图形界面
  catalog.py      软件目录聚合与缓存
  printer_drivers.py  打印机驱动目录与品牌匹配
  repo.py         仓库索引、Debian 版本比较、镜像兜底下载
  pipeline.py     完整交付包生成
  updates.py      增量更新检测与增量包生成
  project.py      基线快照
  iso_reader.py   ISO 包清单读取
  builder.py      本地 apt 索引与交付目录组装
  assets/         内置目标机 deb 与说明文档
  cache/          软件目录缓存 catalog-spark.json（随仓库提供，打开即见 600+ 应用）
target_tool/    deepin 目标机 GTK 工具、helper.sh、deb 构建脚本
tools/          GitHub API 备用同步脚本
build*.bat      Windows 打包脚本
git-push.bat    一键提交并同步两端
LICENSE         MIT 开源许可证
```

## 构建

| 脚本 | 产物 |
|---|---|
| `build.bat` | 目录版（启动快，需连同 `_internal/` 拷贝） |
| `build-portable.bat` | 单文件便携版（一个 exe，拷到任意 Windows 机器） |

打包脚本顶部的 `PY` / `SRC` / `DIST` 按本机环境写死，换机器时请改成实际路径。目标机 `.deb` 可随时用 `python target_tool\build_deb.py` 重新生成。

## 仓库地址与同步

| 平台 | 地址 |
|---|---|
| GitHub | https://github.com/debrnr/DeepinOfflineMaker |
| Gitee | https://gitee.com/debrnr/deepin-offline-maker |

改完代码后双击 `git-push.bat` 即可一键提交并同步两端：

- **Gitee**：国内直连，`git push gitee main`，通常几秒完成。
- **GitHub**：优先 `git push github main`。若本机代理把 `github.com` 的 git 通道掐断（表现为 `CONNECT tunnel failed 502` / `schannel: missing close_notify`），脚本会自动改走 `tools\push_github_api.py`，用 `api.github.com` 的 REST API 把全部跟踪文件（含二进制 `.deb`）做成一次提交推上去。
- 也可单独执行 `python tools\push_github_api.py`，或附加 `<owner> <repo>` 指定其它仓库。

凭据由 Git Credential Manager 提供，不写进仓库；GitHub 需用 Personal Access Token 代替密码。GitHub 连接器（GitHub App）默认只授权账号下原有仓库，若要让它也能写这个新仓库，需在 GitHub 的 Settings → Applications → Installed GitHub Apps 中把该仓库加入授权范围。

## 适用范围与注意

- 仅适用于 **loong64（龙芯）架构的 deepin 25.x**；其它架构/发行版不适用。
- 制作端需要外网（下 ISO 对应源、星火目录）；目标机全程离线。
- 搜狗五笔无 loong64 原生版，内置精选用 fcitx5 五笔替代；WinRAR 用 7-Zip + unrar 替代。
- 目标机上的 `pkexec` 提权、USB/网络打印机识别、apt 本地源安装需在实机首次验证；出问题看 `/tmp/deepin-offline-upgrade-install.log`。
- `project.json` 是下一次增量的唯一比较基准，压缩存档或网盘分享时请连同整个目录保留。

## 许可证

[MIT](LICENSE) — 可自由使用、修改、分发（含商用），只需保留版权与许可声明。
