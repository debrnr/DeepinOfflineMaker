#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""增量更新：对比项目基线，找出系统/软件更新，并生成可网盘分发的更新包。"""
import os, json, datetime

import catalog
import printer_drivers
import project
from repo import Repo, download_all
from builder import write_local_repo, build_delivery
from vercmp import is_newer
from pipeline import _safe_deb_name, _download_software, _download_printers

INFO_NAME = 'update-info.json'


def _newer(a, b):
    """版本号比较，非 Debian 风格版本退回字符串判断。"""
    if not a or not b:
        return bool(a) and a != b
    try:
        return is_newer(a, b)
    except Exception:
        return a != b


def _latest(repo, name):
    cands = repo.by_name.get(name) or []
    if not cands:
        return None, None
    best_v, best_st = cands[0]
    for v, st in cands[1:]:
        if is_newer(v, best_v):
            best_v, best_st = v, st
    return best_v, best_st


def check_updates(proj, cache_dir, log=print):
    """返回 (report, repo, base)。report 里含 system / software 两个候选列表。"""
    report = {
        'generated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'iso': proj.get('iso', ''),
        'project_created': proj.get('created', ''),
        'system': [], 'software': [], 'notes': [], 'errors': [],
    }

    # ---------- 软件：刷新星火目录，按 id / 目录更新时间比对 ----------
    old_items = list(proj.get('selected_items') or []) + list(proj.get('printer_items') or [])
    spark = None
    if old_items:
        try:
            spark = catalog.fetch_spark(log)
            catalog.save_cache(spark, cache_dir)
        except Exception as e:
            cached = catalog.load_cache(cache_dir)
            spark = (cached or {}).get('items') or []
            report['errors'].append('星火目录刷新失败，使用缓存：%s' % e)
            log('星火目录刷新失败，改用缓存。')
        by_id = {}
        for it in list(spark) + catalog.builtin_items() + printer_drivers.all_items(cache_dir):
            by_id.setdefault(it.get('id'), it)
        for old in old_items:
            sid = old.get('id')
            new = by_id.get(sid)
            if not new and spark:
                for it in spark:
                    if it.get('name') == old.get('name'):
                        new = it
                        break
            if not new:
                report['notes'].append('%s：目录中已找不到，保留原包' % old.get('name', sid))
                continue
            ov, nv = old.get('version') or '', new.get('version') or ''
            ou, nu = old.get('update') or '', new.get('update') or ''
            reason = ''
            changed = False
            if ov and nv and ov != nv:
                changed = _newer(nv, ov)
                reason = '%s → %s' % (ov, nv)
            elif nu and ou and nu > ou:
                changed = True
                reason = '目录更新 %s → %s' % (ou[:10], nu[:10])
            elif nv and not ov and nu:
                changed = nu > '9999-01-01'  # 旧内置项无版本记录时不误报
                reason = '新版本 %s' % nv
            if changed:
                report['software'].append({
                    'id': sid, 'name': new.get('name', ''),
                    'cat': new.get('cat', ''), 'old_version': ov,
                    'new_version': nv, 'reason': reason,
                    'item': new,
                })
        fixed = [x.get('name') for x in old_items
                 if (x.get('source') == 'builtin' and x.get('deb_url'))]
        if fixed:
            report['notes'].append('固定直链软件（%s）版本不随目录变化；如需新版请在星火目录里勾选同名应用。'
                                   % '、'.join(fixed))

    # ---------- 系统：源内版本 vs 基线（ISO + 上次交付） ----------
    log('加载 deepin 源索引，对比系统更新 ...')
    repo = Repo(log=log)
    repo.load(cache_dir=cache_dir)
    base = dict(proj.get('iso_manifest') or {})
    for d in proj.get('delivered') or []:
        n, v = d.get('Package', ''), d.get('Version', '')
        if n and v and (n not in base or is_newer(v, base[n])):
            base[n] = v
    log('系统基线：%d 个包' % len(base))
    for name, cands in repo.by_name.items():
        if name.endswith(('-dbg', '-dbgsym')):
            continue
        best_v, _ = _latest(repo, name)
        if not best_v or name not in base:
            continue
        if is_newer(best_v, base[name]):
            report['system'].append({
                'id': 'sys:' + name, 'name': name, 'cat': '系统更新',
                'old_version': base[name], 'new_version': best_v,
                'reason': '%s → %s' % (base[name], best_v),
            })
    report['system'].sort(key=lambda x: x['name'])
    log('检查完成：系统更新 %d 个，软件更新 %d 个' % (
        len(report['system']), len(report['software'])))
    return report, repo, base


def build_update_package(report, repo, base, proj, cfg, emit):
    """按勾选生成更新包目录。返回 (统计字典)。"""
    log = lambda m: emit('log', m)
    out_dir = cfg['out_dir']
    os.makedirs(out_dir, exist_ok=True)
    sys_ids = set(cfg.get('system_ids') or [])
    soft_ids = set(cfg.get('software_ids') or [])
    workers = int(cfg.get('workers', 6))

    sys_wanted = [(u['name'], u['new_version']) for u in report['system'] if u['id'] in sys_ids]
    soft_items = []
    printer_update_items = []
    by_sid = {u['id']: u for u in report['software']}
    for sid in soft_ids:
        u = by_sid.get(sid)
        if not u:
            continue
        it = u['item']
        if it.get('source') == 'printer' or it.get('cat') == '打印机驱动':
            printer_update_items.append(it)
        else:
            soft_items.append(it)

    log('=== 下载系统更新（%d 个）→ updata/ ===' % len(sys_wanted))
    updata_dir = os.path.join(out_dir, 'updata')
    stanzas = repo.resolve(sys_wanted, installed=base, with_deps=True) if sys_wanted else []
    failed = download_all(stanzas, updata_dir, workers=workers, log=log,
                          progress=lambda d, t, n: emit('progress', '', done=d, total=t, name='系统 ' + n))
    ok_system = [s for s in stanzas if os.path.isfile(os.path.join(updata_dir, _safe_deb_name(s)))]
    if ok_system:
        write_local_repo(updata_dir, ok_system, version_label='增量系统更新')

    log('=== 下载软件更新（%d 个）→ %s ===' % (len(soft_items), cfg.get('soft_dir_name') or 'offline-soft'))
    soft_cfg = dict(cfg)
    soft_cfg['software_items'] = soft_items
    soft_ok, _deps, soft_failed, soft_dir, deps_dir = _download_software(
        soft_cfg, repo, emit, out_dir, base)
    failed += soft_failed

    printer_ok = 0
    printer_dir = ''
    if printer_update_items:
        log('=== 下载打印机驱动更新（%d 项）→ %s ===' % (
            len(printer_update_items), cfg.get('printer_dir_name') or 'printer-drivers'))
        pcfg = dict(cfg)
        pcfg['printer_items'] = printer_update_items
        printer_ok, _, printer_failed, printer_dir, _ = _download_printers(
            pcfg, repo, emit, out_dir, base, printer_update_items)
        failed += printer_failed

    sw_updates = [{'name': by_sid[sid]['name'],
                   'old_version': by_sid[sid]['old_version'],
                   'new_version': by_sid[sid]['new_version']}
                  for sid in soft_ids if sid in by_sid]
    info = {
        'type': 'incremental-update',
        'generated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'base_iso': proj.get('iso', ''),
        'system_updates': len(sys_wanted),
        'software_updates': sw_updates,
        'printer_updates': [x.get('name', '') for x in printer_update_items],
        'message': '本次更新包含 %d 个系统更新、%d 个软件更新、%d 项打印机驱动。请打开“离线工具”安装。'
                   % (len(sys_wanted), len(sw_updates), len(printer_update_items)),
    }
    with open(os.path.join(out_dir, INFO_NAME), 'w', encoding='utf-8') as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    readme = '''# deepin 离线增量更新包

生成时间：%s
基准 ISO：%s

## 本次内容
- 系统更新：%d 个（在 `updata/`）
- 软件更新：%d 个（在 `%s/`，依赖在独立目录）
- 打印机驱动更新：%d 项（在 `%s/`）

## 目标机使用
1. 整个文件夹拷到 U 盘插到内网机器。
2. 若机器还没装过图形工具，先双击 `tool/` 里的 deb 安装。
3. 打开“离线工具”，会自动提示本次有更新；在
   “离线升级”页升级系统，“软件安装”页安装/覆盖软件，
   “打印机驱动”页检测并安装新驱动。
4. 完成后重启。全程无需外网、无需命令行。

## 再下一次增量（请勿删除 project.json）
本目录里的 `project.json` 是更新后的新基线：记录了 ISO 清单加上历次已交付包的版本。
请连同整个目录一起保存或上传网盘，不要删它；下次打开制作工具时，
在“增量更新 / 网盘分享”页点“从交付目录载入”选中本目录即可接着做下一批增量。
若未自动载入，也可点“载入项目”直接选 project.json。

## 分享
本目录自包含，可直接压缩后放网盘分享给同样环境的同学。
''' % (info['generated'], info['base_iso'], len(sys_wanted), len(sw_updates),
       os.path.basename(soft_dir) if soft_dir else 'offline-soft',
       len(printer_update_items),
       os.path.basename(printer_dir) if printer_dir else 'printer-drivers')
    build_delivery(out_dir, updata_dir,
                   tool_deb_src=cfg.get('tool_deb'), docs_src=cfg.get('docs_src'),
                   soft_src=None, readme_text=readme, log=log)

    # 更新基线：下次检查不再重复报同样的更新
    try:
        new_proj = dict(proj)
        new_proj['created'] = info['generated']
        new_proj['out_dir'] = out_dir
        merged = {d.get('Package'): d.get('Version') for d in (proj.get('delivered') or [])}
        for s in ok_system:
            n, v = s.get('Package'), s.get('Version')
            if n and (n not in merged or is_newer(v, merged[n])):
                merged[n] = v
        new_proj['delivered'] = [{'Package': n, 'Version': v} for n, v in merged.items()]
        new_items = {it.get('id'): it for it in (proj.get('selected_items') or [])}
        new_printers = {it.get('id'): it for it in (proj.get('printer_items') or [])}
        for sid, u in by_sid.items():
            if sid not in soft_ids:
                continue
            it = u['item']
            if it.get('source') == 'printer' or it.get('cat') == '打印机驱动':
                new_printers[sid] = it
            else:
                new_items[sid] = it
        new_proj['selected_items'] = list(new_items.values())
        new_proj['printer_items'] = list(new_printers.values())
        saved = project.save_project(new_proj, cache_dir=cfg.get('cache_dir'), out_dir=out_dir)
        log('已更新基线快照：%s' % ', '.join(os.path.basename(p) for p in saved))
    except Exception as e:
        log('[警告] 更新基线失败: %s' % e)

    return {
        'system': len(ok_system), 'software': soft_ok, 'printers': printer_ok,
        'failed': failed, 'out_dir': out_dir, 'message': info['message'],
    }
