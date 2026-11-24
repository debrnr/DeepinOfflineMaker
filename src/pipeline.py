#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""编排：ISO -> 清单 -> (源内更新/全量/两版对比) -> 下载 -> 本地源 -> 交付目录。

软件部分支持从 catalog 勾选：主包放 offline-soft，依赖放独立目录，
互不混淆；目标机图形工具读取 manifest.json 安装。供 GUI 后台线程调用。
"""
import os, re, json, datetime
from iso_reader import read_manifest_from_iso, parse_manifest, diff_manifests
from repo import Repo, download_all
from builder import write_local_repo, build_delivery
from vercmp import is_newer
import catalog
import software_list
import project

README_TMPL = '''# deepin 离线增量升级包（%s）

由 DeepinOfflineMaker 自动生成。

## 目录结构
- `updata/`       : 离线升级源（系统更新 deb + Packages/Packages.gz/Release）
- `%s/` : 勾选的软件主包（含 manifest.json）
- `%s/` : 软件依赖包（独立 apt 源，安装时自动取用）
- `%s/` : 打印机驱动（含 manifest.json 与 deps/，目标机可检测安装）
- `tool/`         : 图形工具 deb（双击安装）
- `docs/`         : 详细说明
- `project.json`  : **基线快照，请勿删除**（下次做增量更新全靠它）
- `使用说明.md`

## 使用（目标机，无需外网）
1. 把整个文件夹拷到 U 盘插到目标机。
2. 双击 `tool/` 里的 deb 安装图形工具。
3. 从菜单打开工具：
   - “离线升级”页：按向导把系统升级到最新。
   - “软件安装”页：勾选软件点安装，依赖自动处理。
   - “打印机驱动”页：检测打印机，按品牌一键安装驱动。

## 半年后再做增量包（重要）
`project.json` 记录了本次交付的所有包版本和勾选的软件，是下一次增量的比较基准。
请连同整个目录一起保存或上传网盘，**不要删掉它**，也不要只把 deb 拷给别人。

下次（例如半年后）在有外网的电脑上：
1. 打开本工具，切到“增量更新 / 网盘分享”页；
2. 若已自动显示基线项目，直接用；否则点“从交付目录载入”选中本目录（或点“载入项目”选 project.json）；
3. 点“检查更新（联网）”，工具会列出这半年里源内新增的系统更新和软件新版本；
4. 勾选要下载的更新，点“下载更新包”，生成的新目录照样整包拷 U 盘、可继续传网盘；
5. 生成后基线会自动前移，下次不会重复报同一批更新。

## 生成信息
- ISO：%s
- 模式：%s
- 升级包：%d 个
- 打印机驱动包：%d 个
- 生成时间：%s
'''


def _safe_deb_name(s):
    return '%s_%s_%s.deb' % (
        re.sub(r'[^\w+.\-]', '_', s.get('Package', 'pkg')),
        re.sub(r'[^\w+.\-]', '_', s.get('Version', '0')),
        s.get('Architecture', '') or 'all')


def _best_stanza(repo, name):
    cands = repo.by_name.get(name, [])
    if not cands:
        return None
    best = cands[0]
    for v, st in cands[1:]:
        if is_newer(v, best[0]):
            best = (v, st)
    return best[1]


def _rel_dir(base, target):
    """目标机 manifest 里记录依赖目录（相对软件目录，POSIX 风格）。"""
    try:
        return os.path.relpath(target, base).replace(os.sep, '/')
    except ValueError:
        return target


def _selected_items(cfg):
    """优先用 GUI 传来的完整目录项；兼容旧的 software_ids。"""
    items = cfg.get('software_items')
    if isinstance(items, list) and items:
        return [x for x in items if isinstance(x, dict)]
    ids = cfg.get('software_ids') or []
    out = []
    for sid in ids:
        for it in catalog.builtin_items():
            if it['id'] == sid:
                out.append(it)
                break
    return out


def _dep_names_from_deb(path, item, repo, log):
    """读 deb 的 Depends，映射成仓库里可下载的包名->最新版本。"""
    dep_text = catalog.deb_depends(path)
    if not dep_text and item.get('id') == 'wps':
        # 老版 WPS 无 control 可读时的兜底
        dep_text = ('libgtk-3-0, libnotify4, libnss3, libxss1, libxtst6, '
                    'xdg-utils, libatspi2.0-0, libsecret-1-0, libcups2')
    got = {}
    for alts in Repo.parse_dep(dep_text):
        for name in alts:
            if name in repo.by_name:
                cands = repo.by_name[name]
                best_v = cands[0][0]
                for v, _ in cands[1:]:
                    if is_newer(v, best_v):
                        best_v = v
                got[name] = best_v
                break
    return got


def _download_item_set(cfg, repo, emit, out_dir, installed_base, items,
                       dir_name, deps_choice, label, manifest_kind):
    """通用下载：主包一个目录、依赖一个目录，各自建 apt 索引和 manifest。"""
    log = lambda m: emit('log', m)
    if not items:
        return 0, [], [], '', ''

    main_dir = os.path.join(out_dir, dir_name)
    if deps_choice == 'updata':
        deps_dir = os.path.join(out_dir, 'updata')
    elif deps_choice == 'sibling':
        sibling = 'soft-deps' if manifest_kind == 'software' else dir_name + '-deps'
        deps_dir = os.path.join(out_dir, sibling)
    else:
        deps_dir = os.path.join(main_dir, 'deps')
    os.makedirs(main_dir, exist_ok=True)

    log('=== 下载%s（%d 项）→ %s ===' % (label, len(items), dir_name))
    main_stanzas = {}
    dep_wanted = {}
    direct = []
    for it in items:
        name = it.get('name', it.get('id', '?'))
        if it.get('deb_url') and it.get('deb_file'):
            direct.append((it, os.path.join(main_dir, it['deb_file'])))
            log('  直链%s：%s' % (label, name))
            continue
        for pkg in (it.get('pkgs') or []):
            st = _best_stanza(repo, pkg)
            if st:
                main_stanzas[(st.get('Package'), st.get('Version'))] = st
                log('  仓库主包：%s %s' % (pkg, st.get('Version', '')))
            else:
                log('  [警告] 仓库无此包: %s' % pkg)

    failed = []
    ok_direct = 0
    for it, dest in direct:
        if os.path.isfile(dest) and os.path.getsize(dest) > 0:
            log('  已存在，跳过：%s' % os.path.basename(dest))
            ok_direct += 1
        else:
            log('  下载 %s ...' % it.get('name', os.path.basename(dest)))
            try:
                catalog.download_direct(it['deb_url'], dest, log)
                ok_direct += 1
                log('  完成：%s' % os.path.basename(dest))
            except Exception as e:
                failed.append((os.path.basename(dest), str(e)))
                log('  失败：%s' % e)
                continue
        try:
            for n, v in _dep_names_from_deb(dest, it, repo, log).items():
                dep_wanted.setdefault(n, v)
        except Exception as e:
            log('  [警告] 读取依赖失败 %s: %s' % (os.path.basename(dest), e))

    wanted = [(n, v) for n, v in main_stanzas] + list(dep_wanted.items())
    all_stanzas = repo.resolve(wanted, installed=installed_base, with_deps=True)
    main_keys = set(main_stanzas)
    main_dl = [s for s in all_stanzas if (s.get('Package'), s.get('Version')) in main_keys]
    dep_stanzas = [s for s in all_stanzas if (s.get('Package'), s.get('Version')) not in main_keys]
    log('%s主包 %d 个仓库包 + %d 个直链包；依赖 %d 个仓库包' % (
        label, len(main_dl), ok_direct, len(dep_stanzas)))

    progress = lambda d, t, n: emit('progress', '', done=d, total=t, name=label + ' ' + n)
    failed += download_all(main_dl, main_dir, workers=int(cfg.get('workers', 6)),
                           log=log, progress=progress)
    failed += download_all(dep_stanzas, deps_dir, workers=int(cfg.get('workers', 6)),
                           log=log, progress=progress)

    if main_dl:
        write_local_repo(main_dir, main_dl, version_label='offline ' + label)
    if dep_stanzas and deps_dir != os.path.join(out_dir, 'updata'):
        write_local_repo(deps_dir, dep_stanzas, version_label='offline ' + label + ' dependencies')

    manifest = {
        'kind': manifest_kind,
        'generated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'deps_dir': _rel_dir(main_dir, deps_dir),
        'soft_dir': dir_name,
        'items': [catalog.item_to_manifest(it) for it in items],
    }
    with open(os.path.join(main_dir, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    log('%s清单已写入 %s/manifest.json，依赖目录：%s' % (
        label, dir_name, _rel_dir(main_dir, deps_dir)))

    main_ok = ok_direct + len([s for s in main_dl
                               if os.path.isfile(os.path.join(main_dir, _safe_deb_name(s)))])
    return main_ok, dep_stanzas, failed, main_dir, deps_dir


def _download_software(cfg, repo, emit, out_dir, installed_base, items_override=None):
    items = items_override if items_override is not None else _selected_items(cfg)
    soft_name = cfg.get('soft_dir_name') or 'offline-soft'
    return _download_item_set(cfg, repo, emit, out_dir, installed_base, items,
                              soft_name, cfg.get('deps_dir_choice') or 'subdir',
                              '软件', 'software')


def _download_printers(cfg, repo, emit, out_dir, installed_base, items_override=None):
    items = items_override if items_override is not None else (cfg.get('printer_items') or [])
    dir_name = cfg.get('printer_dir_name') or 'printer-drivers'
    return _download_item_set(cfg, repo, emit, out_dir, installed_base, items,
                              dir_name, 'subdir', '打印机驱动', 'printer-drivers')


def run_pipeline(cfg, emit):
    def log(msg):
        emit('log', msg)
    def prog(done, total, name):
        emit('progress', '', done=done, total=total, name=name)

    new_iso = cfg['new_iso']
    mode = cfg['mode']          # full | update | diff
    out_dir = cfg['out_dir']
    workers = int(cfg.get('workers', 6))
    cache_dir = cfg.get('cache_dir')

    log('=== 步骤 1：读取 ISO 包清单 ===')
    new_manifest = read_manifest_from_iso(new_iso, log=log)
    log('ISO 清单：%d 个包' % len(new_manifest))

    repo = Repo(log=log)
    log('=== 步骤 2：加载仓库索引 ===')
    repo.load(cache_dir=cache_dir)

    installed_base = {}
    mode_txt = '全量'
    version_label = os.path.basename(new_iso)

    if mode == 'full':
        log('模式：全量（ISO 内所有包）')
        target = [(n, new_manifest[n]) for n in sorted(new_manifest)]
        stanzas = [s for n, v in target for s in [repo.find_exact(n, v)] if s]
        log('=== 步骤 3：准备 %d 个包 ===' % len(stanzas))
    elif mode == 'update':
        log('模式：ISO 基准 → 源内更新（模拟装机后联网升级）')
        updates = repo.find_updates(new_manifest, log=log)
        target = [(n, v) for n, v, s in updates]
        installed_base = dict(new_manifest)
        mode_txt = '增量更新'
        version_label = '%s → 最新（装机后更新）' % os.path.basename(new_iso)
        log('=== 步骤 3：解析更新包及依赖 ===')
        stanzas = repo.resolve(target, installed=installed_base, with_deps=True)
    else:
        log('模式：两版本对比（兼容）')
        old_src = cfg.get('old_iso') or cfg.get('old_manifest')
        if not old_src:
            raise RuntimeError('diff 模式需提供旧 ISO 或旧清单')
        old_manifest = (read_manifest_from_iso(old_src, log=log) if old_src.lower().endswith('.iso')
                        else parse_manifest(old_src))
        changed, _ = diff_manifests(new_manifest, old_manifest)
        target = [(n, new_manifest[n]) for n in changed]
        installed_base = dict(old_manifest)
        mode_txt = '版本对比'
        version_label = '%s (对比基准)' % os.path.basename(new_iso)
        log('=== 步骤 3：解析变化包及依赖 ===')
        stanzas = repo.resolve(target, installed=installed_base, with_deps=True)

    log('共需下载 %d 个升级包（含依赖）' % len(stanzas))
    updata_dir = os.path.join(out_dir, 'updata')
    failed = download_all(stanzas, updata_dir, workers=workers, log=log, progress=prog)

    soft_ok, dep_stanzas, soft_failed, soft_dir, deps_dir = _download_software(
        cfg, repo, emit, out_dir, dict(new_manifest))
    failed += soft_failed

    printer_items = cfg.get('printer_items') or []
    printer_ok, _, printer_failed, printer_dir, _printer_deps_dir = (0, [], [], '', '')
    if printer_items:
        printer_ok, _, printer_failed, printer_dir, _printer_deps_dir = _download_printers(
            cfg, repo, emit, out_dir, dict(new_manifest), printer_items)
        failed += printer_failed

    # 索引：并入 updata 的软件包依赖与升级包写进同一个源，其余各自独立
    ok_stanzas = [s for s in stanzas if os.path.isfile(os.path.join(updata_dir, _safe_deb_name(s)))]
    upgrade_baseline = list(ok_stanzas)   # 只记系统升级包，不把软件依赖算进系统基线
    if deps_dir == updata_dir:
        ok_deps = [s for s in dep_stanzas
                   if os.path.isfile(os.path.join(updata_dir, _safe_deb_name(s)))]
        seen = {(s.get('Package'), s.get('Version')) for s in ok_stanzas}
        ok_stanzas += [s for s in ok_deps if (s.get('Package'), s.get('Version')) not in seen]
        log('软件依赖已并入 updata，统一重建索引（%d 条）' % len(ok_stanzas))
    write_local_repo(updata_dir, ok_stanzas, version_label=version_label)

    log('=== 步骤 4：生成交付目录 ===')
    soft_name = os.path.basename(soft_dir) if soft_dir else '(未选择)'
    deps_name = os.path.basename(deps_dir) if deps_dir else '(未选择)'
    printer_name = os.path.basename(printer_dir) if printer_dir else '(未选择)'
    readme = README_TMPL % (mode_txt, soft_name, deps_name, printer_name,
                            os.path.basename(new_iso), mode_txt, len(ok_stanzas),
                            printer_ok, datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))
    build_delivery(out_dir, updata_dir,
                   tool_deb_src=cfg.get('tool_deb'),
                   docs_src=cfg.get('docs_src'),
                   soft_src=None,
                   readme_text=readme, log=log)

    # 保存基线快照：下次打开工具即可“检查更新”
    try:
        snap = project.make_project(cfg, new_manifest, upgrade_baseline,
                                    _selected_items(cfg), out_dir, printer_items)
        paths = project.save_project(snap, cache_dir=cache_dir, out_dir=out_dir)
        log('已保存更新基线：%s' % ', '.join(os.path.basename(p) for p in paths))
    except Exception as e:
        log('[警告] 保存更新基线失败: %s' % e)

    total_size = 0
    for root, _, files in os.walk(out_dir):
        for fn in files:
            total_size += os.path.getsize(os.path.join(root, fn))
    emit('done', '完成：升级包 %d 个，软件主包 %d 个，打印机驱动包 %d 个，总 %.2f GB' % (
        len(ok_stanzas), soft_ok, printer_ok, total_size / (1024 ** 3)),
        count=len(ok_stanzas), size=total_size, failed=failed, out_dir=out_dir)
    return failed
