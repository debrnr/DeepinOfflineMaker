#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离线更新“项目快照”：记住基线（ISO 清单 + 上次交付的包版本）和勾选的软件。

快照同时写到两处：
  <cache>/last-project.json      工具下次打开自动载入
  <输出目录>/project.json        随交付包一起分发（网盘分享后可继续做下一次更新）
"""
import os, json, datetime

FORMAT = 'deepin-offline-maker-project'
VERSION = 1
LAST_NAME = 'last-project.json'
PROJECT_NAME = 'project.json'


def make_project(cfg, iso_manifest, delivered_stanzas, selected_items, out_dir,
                 printer_items=None):
    return {
        'format': FORMAT,
        'version': VERSION,
        'created': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'iso': os.path.basename(cfg.get('new_iso', '')),
        'mode': cfg.get('mode', 'update'),
        'iso_manifest': dict(iso_manifest or {}),
        'delivered': [
            {'Package': s.get('Package', ''), 'Version': s.get('Version', '')}
            for s in (delivered_stanzas or []) if s.get('Package')
        ],
        'selected_items': list(selected_items or []),
        'printer_items': list(printer_items or []),
        'printer_dir_name': cfg.get('printer_dir_name') or 'printer-drivers',
        'out_dir': out_dir,
        'soft_dir_name': cfg.get('soft_dir_name') or 'offline-soft',
        'deps_dir_choice': cfg.get('deps_dir_choice') or 'subdir',
    }


def save_project(proj, cache_dir=None, out_dir=None):
    """写快照。返回写入的文件列表。"""
    written = []
    data = json.dumps(proj, ensure_ascii=False, indent=1)
    if cache_dir:
        try:
            os.makedirs(cache_dir, exist_ok=True)
            p = os.path.join(cache_dir, LAST_NAME)
            with open(p, 'w', encoding='utf-8') as f:
                f.write(data)
            written.append(p)
        except Exception:
            pass
    if out_dir:
        try:
            os.makedirs(out_dir, exist_ok=True)
            p = os.path.join(out_dir, PROJECT_NAME)
            with open(p, 'w', encoding='utf-8') as f:
                f.write(data)
            written.append(p)
        except Exception:
            pass
    return written


def _valid(d):
    return isinstance(d, dict) and d.get('format') == FORMAT and isinstance(d.get('iso_manifest'), dict)


def load_last(cache_dir):
    if not cache_dir:
        return None
    p = os.path.join(cache_dir, LAST_NAME)
    return load_file(p)


def load_file(path):
    try:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
        return d if _valid(d) else None
    except Exception:
        return None


def load_from_dir(out_dir):
    if not out_dir:
        return None
    return load_file(os.path.join(out_dir, PROJECT_NAME))


def summary(proj):
    if not proj:
        return '无项目快照'
    items = proj.get('selected_items') or []
    printers = proj.get('printer_items') or []
    return '%s ｜ %s ｜ %d 个系统基线包 ｜ %d 个软件 ｜ %d 项打印驱动 ｜ %s' % (
        proj.get('iso', '?'), proj.get('mode', '?'),
        len(proj.get('iso_manifest') or {}), len(items), len(printers),
        proj.get('created', '?'))
