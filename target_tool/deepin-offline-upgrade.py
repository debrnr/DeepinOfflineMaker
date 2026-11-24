#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""deepin 离线工具 - 图形界面 (普通用户运行)
三页：离线升级 / 软件安装 / 打印机驱动。重活交给 pkexec helper.sh。
路径约定：本程序在 <交付>/tool/ 下，升级包在 ../updata，
软件主包在 ../offline-soft（兼容旧版 ../soft），驱动在 ../printer-drivers，
依赖目录由各自 manifest.json 指定。
"""
import os, sys, re, json, glob, subprocess, GLib
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

HELPER = '/usr/lib/deepin-offline-upgrade/helper.sh'
LOG_PATH = '/tmp/deepin-offline-upgrade-install.log'
STATUS_PATH = '/tmp/deepin-offline-upgrade.status'
INFO_STAMP = '/tmp/deepin-offline-upgrade.info-shown'
APP_TITLE = 'deepin 离线工具'


def find_dir(name):
    """查找交付目录下的子目录（updata / soft）。"""
    cands = []
    for base in (os.path.expanduser('~/Desktop'), '/media', '/run/media', '/mnt',
                 os.path.expanduser('~')):
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            if os.path.basename(root).lower() == name:
                cands.append(root)
            if root.count(os.sep) - base.count(os.sep) > 4:
                dirs[:] = []
    seen = set(); out = []
    for c in cands:
        if c not in seen:
            seen.add(c); out.append(c)
    return out


def find_update_info():
    """查找 U 盘交付包根目录的 update-info.json（增量更新包标记）。"""
    out = []
    for base in (os.path.expanduser('~/Desktop'), '/media', '/run/media', '/mnt',
                 os.path.expanduser('~')):
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            if 'update-info.json' in files:
                out.append(os.path.join(root, 'update-info.json'))
            if root.count(os.sep) - base.count(os.sep) > 4:
                dirs[:] = []
    return out


def has_deb(d):
    return bool(d and glob.glob(os.path.join(d, '*.deb')))


def soft_meta(soft_dir):
    """读取软件目录 manifest，返回 (软件条目, 依赖目录列表)。"""
    items, deps = [], []
    mf = os.path.join(soft_dir, 'manifest.json') if soft_dir else ''
    meta = {}
    if mf and os.path.isfile(mf):
        try:
            with open(mf, encoding='utf-8') as f:
                meta = json.load(f)
        except Exception:
            meta = {}
    items = meta.get('items') or []
    rel = meta.get('deps_dir')
    if rel:
        p = os.path.normpath(os.path.join(soft_dir, rel))
        if has_deb(p) and p not in deps:
            deps.append(p)
    # 兼容旧交付包：软件目录同级若存在独立 soft-deps，自动带上
    # 打印机驱动目录不用这个兼容，避免把软件包依赖混进来
    if meta.get('kind') != 'printer-drivers':
        sibling = os.path.join(os.path.dirname(soft_dir or '.'), 'soft-deps')
        if has_deb(sibling) and sibling not in deps:
            deps.append(sibling)
    return items, deps


def run_cmd(argv, timeout=6):
    try:
        p = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           timeout=timeout)
        return p.stdout.decode('utf-8', errors='replace')
    except Exception:
        return ''


def detect_printers():
    """检测 USB / CUPS 网络 / 已配置打印机，返回设备字典列表。"""
    devices = []
    seen = set()
    words = ('printer', 'print', 'mfp', 'scan', 'hp', 'hewlett', 'canon', 'epson',
             'brother', 'pantum', 'lenovo', 'samsung', 'ricoh', 'kyocera',
             'xerox', 'lexmark', 'jiyin', 'okidata', 'fujixerox')

    def sysfs_read(path, name):
        try:
            with open(os.path.join(path, name), encoding='utf-8', errors='replace') as f:
                return f.read().strip()
        except OSError:
            return ''

    for path in glob.glob('/sys/bus/usb/devices/*'):
        vid = sysfs_read(path, 'idVendor').lower()
        pid = sysfs_read(path, 'idProduct').lower()
        prod = sysfs_read(path, 'product')
        man = sysfs_read(path, 'manufacturer')
        cls = sysfs_read(path, 'bDeviceClass').lower()
        text = (man + ' ' + prod).lower()
        if not (vid or prod):
            continue
        if cls != '07' and not any(w in text for w in words):
            continue
        key = (vid, pid, prod)
        if key in seen:
            continue
        seen.add(key)
        devices.append({
            'kind': 'USB', 'name': (man + ' ' + prod).strip() or 'USB 打印设备',
            'ids': [vid, pid], 'uri': '',
        })

    for line in run_cmd(['lpinfo', '-v']).splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) < 2:
            continue
        kind, uri = parts
        if '://' not in uri or uri.lower() in ('beh', 'ipp', 'ipps', 'lpd', 'socket'):
            continue
        if uri in seen:
            continue
        seen.add(uri)
        devices.append({
            'kind': 'USB(CUPS)' if uri.lower().startswith('usb://') else kind,
            'name': uri, 'ids': [], 'uri': uri,
        })

    for line in run_cmd(['lpstat', '-v']).splitlines():
        if not line.startswith('device for '):
            continue
        rest = line[len('device for '):]
        if ':' not in rest:
            continue
        name, uri = rest.split(':', 1)
        uri = uri.strip()
        key = 'cfg:' + uri
        if key in seen:
            continue
        seen.add(key)
        devices.append({
            'kind': '已配置', 'name': name.strip(), 'ids': [], 'uri': uri,
        })
    return devices


def recommend_printer_ids(devices, driver_items):
    """按 VID/PID、品牌、型号关键字推荐驱动 id。"""
    by_id = {it.get('id'): it for it in (driver_items or [])}
    result = []

    def add(did):
        if did in by_id and did not in result:
            result.append(did)

    add('print-base')
    if not devices:
        add('print-ruiyin')
        add('print-gutenprint')
        return result

    text = ' '.join(
        [str(d.get('name', '')) + ' ' + str(d.get('uri', '')) + ' ' +
         ' '.join(d.get('ids') or []) for d in devices]).lower()
    scored = []
    for it in driver_items:
        score = 0
        for token in (it.get('match') or []):
            t = str(token).lower()
            if t and t in text:
                score += 3 if len(t) >= 4 else 2
        if score:
            scored.append((score, it.get('id')))
    scored.sort(key=lambda x: -x[0])
    for _score, did in scored[:3]:
        add(did)
    add('print-ruiyin')
    add('print-gutenprint')
    return result


def mklabel(text, size=10, bold=False, color=None):
    l = Gtk.Label()
    markup = '<span size="%d" weight="%s"' % (size * 1024, 'bold' if bold else 'normal')
    if color:
        markup += ' foreground="%s"' % color
    markup += '>%s</span>' % text
    l.set_markup(markup)
    l.set_xalign(0)
    l.set_line_wrap(True)
    return l


class TaskRunner:
    """封装 pkexec 调用 + 日志/状态轮询，通过回调通知 GUI。"""
    def __init__(self, on_log, on_done):
        self.on_log = on_log
        self.on_done = on_done
        self.proc = None
        self.running = False
        self.log_pos = 0

    def start(self, action, target, extras=None):
        try:
            os.remove(STATUS_PATH)
        except OSError:
            pass
        self.running = True
        self.log_pos = 0
        args = ['pkexec', HELPER, action, target] + list(extras or [])
        try:
            self.proc = subprocess.Popen(args,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            self.running = False
            self.on_done(False, '启动失败：%s' % e)
            return False
        GLib.timeout_add(200, self._poll)
        return True

    def _poll(self):
        status = ''
        try:
            with open(STATUS_PATH, encoding='utf-8', errors='replace') as f:
                status = f.read().strip()
        except OSError:
            pass
        try:
            with open(LOG_PATH, 'rb') as f:
                f.seek(self.log_pos)
                chunk = f.read()
                self.log_pos = f.tell()
            if chunk:
                self.on_log(chunk.decode('utf-8', errors='replace'))
        except OSError:
            pass
        if status.startswith('OK'):
            self.running = False
            self.on_done(True, '')
            return False
        if status.startswith('FAIL'):
            rc = status.split(':')[1] if ':' in status else '?'
            self.running = False
            self.on_done(False, rc)
            return False
        if self.proc.poll() is not None and not status:
            self.running = False
            self.on_done(False, str(self.proc.returncode))
            return False
        return True


class App(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title=APP_TITLE)
        self.set_default_size(780, 640)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.runner = None

        box = Gtk.Box(orientation=Gtk.Vertical, spacing=0)
        self.add(box)
        head = Gtk.Box(orientation=Gtk.Vertical, spacing=4)
        head.pack_start(mklabel(APP_TITLE, 17, True, '#ffffff'), False, False, 0)
        head.pack_start(mklabel('无需外网的离线升级与软件安装', 10, False, '#dbe9ff'), False, False, 0)
        head.override_background_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(0.12, 0.37, 0.65, 1.0))
        for c in head.get_children():
            c.override_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(1, 1, 1, 1))
        head.set_margin_bottom(10)
        box.pack_start(head, False, False, 0)

        self.nb = Gtk.Notebook()
        box.pack_start(self.nb, True, True, 0)
        self.nb.append_page(self.build_upgrade(), Gtk.Label(label='  离线升级  '))
        self.nb.append_page(self.build_soft(), Gtk.Label(label='  软件安装  '))
        self.nb.append_page(self.build_printer(), Gtk.Label(label='  打印机驱动  '))
        self.connect('delete-event', lambda w, e: True if self._busy() else False)
        self.show_all()
        self.maybe_notify_update()

    def maybe_notify_update(self):
        """增量更新包插上机器后，启动时提示“有更新”。同一个包只提示一次。"""
        for p in find_update_info():
            try:
                with open(p, encoding='utf-8') as f:
                    info = json.load(f)
            except Exception:
                continue
            if info.get('type') != 'incremental-update':
                continue
            stamp = info.get('generated', '') + '|' + p
            try:
                if os.path.isfile(INFO_STAMP) and open(INFO_STAMP, encoding='utf-8').read().strip() == stamp:
                    continue
            except Exception:
                pass
            msg = info.get('message') or '本次 U 盘里有新的离线更新包。'
            sw = info.get('software_updates') or []
            if sw:
                msg += '\n\n软件更新：\n' + '\n'.join(
                    '• %s  %s → %s' % (x.get('name', ''), x.get('old_version', '') or '-',
                                       x.get('new_version', '') or '-') for x in sw[:12])
            pr = info.get('printer_updates') or []
            if pr:
                msg += '\n\n打印机驱动更新：\n' + '\n'.join('• %s' % x for x in pr[:12])
            msg += '\n\n请在“离线升级”页安装系统更新，在“软件安装”页安装软件更新，' \
                   '在“打印机驱动”页安装新驱动。'
            self.show_info(msg)
            try:
                with open(INFO_STAMP, 'w', encoding='utf-8') as f:
                    f.write(stamp)
            except Exception:
                pass
            break

    def _busy(self):
        return self.runner is not None and self.runner.running

    def build_upgrade(self):
        v = Gtk.Box(orientation=Gtk.Vertical, spacing=10)
        v.set_border_width(16)
        v.pack_start(mklabel('系统离线增量升级', 13, True, '#1f5fa9'), False, False, 0)
        d = Gtk.Label(label='把本机从“刚装好 ISO”的状态升级到最新。升级包在 updata 目录，工具会自动查找。')
        d.set_xalign(0); d.set_line_wrap(True)
        v.pack_start(d, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Horizontal, spacing=8)
        row.pack_start(mklabel('升级包目录：', 10), False, False, 0)
        self.up_combo = Gtk.ComboBoxText()
        for x in find_dir('updata'):
            self.up_combo.append_text(x)
        self.up_combo.set_active(0)
        row.pack_start(self.up_combo, True, True, 0)
        b = Gtk.Button.new_with_label('刷新')
        b.connect('clicked', lambda w: self.refresh_dirs())
        row.pack_start(b, False, False, 0)
        v.pack_start(row, False, False, 0)

        self.up_info = mklabel('', 10)
        v.pack_start(self.up_info, False, False, 0)
        self.update_upgrade_info()

        self.up_start = Gtk.Button.new_with_label('开始升级')
        self.up_start.get_style_context().add_class('suggested-action')
        self.up_start.connect('clicked', self.on_upgrade)
        v.pack_start(self.up_start, False, False, 0)

        v.pack_start(mklabel('运行日志', 11, True), False, False, 4)
        self.up_sw, self.up_tbuf = self.make_log_view()
        v.pack_start(self.up_sw, True, True, 0)
        return v

    def build_soft(self):
        v = Gtk.Box(orientation=Gtk.Vertical, spacing=10)
        v.set_border_width(16)
        v.pack_start(mklabel('常用软件离线安装', 13, True, '#1f5fa9'), False, False, 0)
        d = Gtk.Label(label='勾选软件后点“安装选中软件”，依赖目录会自动加入安装源。软件主包在 offline-soft（兼容旧 soft）。')
        d.set_xalign(0); d.set_line_wrap(True)
        v.pack_start(d, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Horizontal, spacing=8)
        row.pack_start(mklabel('软件目录：', 10), False, False, 0)
        self.soft_combo = Gtk.ComboBoxText()
        for x in find_dir('offline-soft') + find_dir('soft'):
            self.soft_combo.append_text(x)
        self.soft_combo.set_active(0)
        row.pack_start(self.soft_combo, True, True, 0)
        b = Gtk.Button.new_with_label('刷新')
        b.connect('clicked', lambda w: self.refresh_dirs())
        row.pack_start(b, False, False, 0)
        v.pack_start(row, False, False, 0)

        self.soft_info = mklabel('', 10)
        v.pack_start(self.soft_info, False, False, 0)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.set_shadow_type(Gtk.ShadowType.IN)
        self.store = Gtk.ListStore(bool, str, str, str)
        tv = Gtk.TreeView(model=self.store)
        ren = Gtk.CellRendererToggle()
        ren.connect('toggled', self.on_soft_toggle)
        tv.append_column(Gtk.TreeViewColumn('安装', ren, active=0))
        tv.append_column(Gtk.TreeViewColumn('软件', Gtk.CellRendererText(), text=1))
        tv.append_column(Gtk.TreeViewColumn('分类', Gtk.CellRendererText(), text=2))
        tv.append_column(Gtk.TreeViewColumn('说明', Gtk.CellRendererText(), text=3))
        sw.add(tv)
        sw.set_min_content_height(180)
        v.pack_start(sw, True, True, 0)

        bbox = Gtk.Box(orientation=Gtk.Horizontal, spacing=8)
        self.soft_start = Gtk.Button.new_with_label('安装选中软件')
        self.soft_start.get_style_context().add_class('suggested-action')
        self.soft_start.connect('clicked', self.on_install)
        bbox.pack_start(self.soft_start, False, False, 0)
        a = Gtk.Button.new_with_label('全选')
        a.connect('clicked', lambda w: self.soft_select_all(True))
        bbox.pack_start(a, False, False, 0)
        n = Gtk.Button.new_with_label('清空')
        n.connect('clicked', lambda w: self.soft_select_all(False))
        bbox.pack_start(n, False, False, 0)
        v.pack_start(bbox, False, False, 0)

        self.soft_sw, self.soft_tbuf = self.make_log_view()
        v.pack_start(self.soft_sw, True, True, 0)
        self.load_soft_manifest()
        return v

    def build_printer(self):
        v = Gtk.Box(orientation=Gtk.Vertical, spacing=8)
        v.set_border_width(16)
        v.pack_start(mklabel('打印机驱动检测与离线安装', 13, True, '#1f5fa9'), False, False, 0)
        d = Gtk.Label(label='自动检测 USB / 网络打印机，按品牌推荐驱动；也可手动勾选。全程不访问外网。')
        d.set_xalign(0); d.set_line_wrap(True)
        v.pack_start(d, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Horizontal, spacing=8)
        row.pack_start(mklabel('驱动目录：', 10), False, False, 0)
        self.pr_combo = Gtk.ComboBoxText()
        for x in find_dir('printer-drivers'):
            self.pr_combo.append_text(x)
        self.pr_combo.set_active(0)
        row.pack_start(self.pr_combo, True, True, 0)
        b = Gtk.Button.new_with_label('刷新')
        b.connect('clicked', lambda w: self.refresh_dirs())
        row.pack_start(b, False, False, 0)
        v.pack_start(row, False, False, 0)

        self.pr_info = mklabel('', 10)
        v.pack_start(self.pr_info, False, False, 0)

        bbox = Gtk.Box(orientation=Gtk.Horizontal, spacing=8)
        self.pr_detect = Gtk.Button.new_with_label('检测打印机')
        self.pr_detect.connect('clicked', self.on_detect_printers)
        bbox.pack_start(self.pr_detect, False, False, 0)
        self.pr_auto = Gtk.Button.new_with_label('一键检测并安装')
        self.pr_auto.get_style_context().add_class('suggested-action')
        self.pr_auto.connect('clicked', self.on_auto_printer)
        bbox.pack_start(self.pr_auto, False, False, 0)
        v.pack_start(bbox, False, False, 0)

        v.pack_start(mklabel('检测到的设备', 11, True), False, False, 2)
        dsw = Gtk.ScrolledWindow()
        dsw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        dsw.set_shadow_type(Gtk.ShadowType.IN)
        self.det_store = Gtk.ListStore(str, str, str)
        dtv = Gtk.TreeView(model=self.det_store)
        for title, col, width in (('类型', 0, 100), ('设备', 1, 320), ('推荐驱动', 2, 320)):
            dtv.append_column(Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=col))
        dtv.get_columns()[1].set_max_width(width)
        dsw.add(dtv)
        dsw.set_min_content_height(100)
        v.pack_start(dsw, False, False, 0)

        v.pack_start(mklabel('可用驱动（双击行勾选）', 11, True), False, False, 2)
        psw = Gtk.ScrolledWindow()
        psw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        psw.set_shadow_type(Gtk.ShadowType.IN)
        self.pr_store = Gtk.ListStore(bool, str, str, str, str)
        ptv = Gtk.TreeView(model=self.pr_store)
        ren = Gtk.CellRendererToggle()
        ren.connect('toggled', self.on_printer_toggle)
        ptv.append_column(Gtk.TreeViewColumn('安装', ren, active=0))
        ptv.append_column(Gtk.TreeViewColumn('驱动', Gtk.CellRendererText(), text=2))
        ptv.append_column(Gtk.TreeViewColumn('类型', Gtk.CellRendererText(), text=3))
        ptv.append_column(Gtk.TreeViewColumn('说明', Gtk.CellRendererText(), text=4))
        ptv.connect('row-activated', self.on_printer_row)
        psw.add(ptv)
        psw.set_min_content_height(150)
        v.pack_start(psw, True, True, 0)

        pbtn = Gtk.Box(orientation=Gtk.Horizontal, spacing=8)
        self.pr_start = Gtk.Button.new_with_label('安装选中驱动')
        self.pr_start.get_style_context().add_class('suggested-action')
        self.pr_start.connect('clicked', self.on_install_printers)
        pbtn.pack_start(self.pr_start, False, False, 0)
        for label, val in (('全选', True), ('清空', False)):
            bb = Gtk.Button.new_with_label(label)
            bb.connect('clicked', lambda w, x=val: self.printer_select_all(x))
            pbtn.pack_start(bb, False, False, 0)
        rb = Gtk.Button.new_with_label('恢复推荐')
        rb.connect('clicked', lambda w: self._printer_preselect())
        pbtn.pack_start(rb, False, False, 0)
        v.pack_start(pbtn, False, False, 0)

        self.pr_sw, self.pr_tbuf = self.make_log_view()
        v.pack_start(self.pr_sw, True, True, 0)
        self.load_printer_manifest()
        return v

    def make_log_view(self):
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.set_shadow_type(Gtk.ShadowType.IN)
        buf = Gtk.TextBuffer()
        tv = Gtk.TextView(buffer=buf)
        tv.set_editable(False); tv.set_monospace(True)
        tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        sw.add(tv)
        sw.set_min_content_height(110)
        return sw, buf

    # ---------------- 打印机驱动 ----------------
    def load_printer_manifest(self):
        self.pr_store.clear()
        self.det_store.clear()
        d = self.pr_combo.get_active_text()
        items, deps = soft_meta(d)
        self.printer_meta = list(items)
        self.printer_by_id = {it.get('id'): it for it in items}
        for it in items:
            self.pr_store.append([False, it.get('id', ''), it.get('name', ''),
                                  it.get('driver_type', ''), it.get('desc', '')])
        if items:
            extra = '；依赖目录：%s' % ', '.join(os.path.basename(x) for x in deps) if deps else ''
            self.pr_info.set_markup('<b>共 %d 项驱动可用</b>%s' % (len(items), extra))
            self._printer_preselect()
        else:
            n = len(glob.glob(os.path.join(d, '*.deb'))) if d else 0
            self.pr_info.set_markup('目录内有 %d 个 deb，将整目录安装。' % n if n else
                                    '<span foreground="#c00">未找到打印机驱动目录，请插好 U 盘或点“刷新”。</span>')

    def _printer_preselect(self):
        ids = set(recommend_printer_ids([], self.printer_meta))
        for row in self.pr_store:
            row[0] = row[1] in ids

    def on_printer_toggle(self, renderer, path):
        it = self.pr_store.get_iter(path)
        self.pr_store.set_value(it, 0, not self.pr_store.get_value(it, 0))

    def on_printer_row(self, tree, path, col):
        self.on_printer_toggle(None, path)

    def printer_select_all(self, val):
        for row in self.pr_store:
            row[0] = val

    def on_detect_printers(self, widget):
        devices = detect_printers()
        self.det_store.clear()
        for dev in devices:
            ids = recommend_printer_ids([dev], self.printer_meta)
            names = ', '.join(self.printer_by_id[x].get('name', x)
                              for x in ids if x != 'print-base')
            self.det_store.append([dev.get('kind', ''), dev.get('name', ''), names])
        if devices:
            self.pr_info.set_markup('<b>检测到 %d 个设备</b>，已按品牌推荐驱动，可点“一键检测并安装”。' % len(devices))
        else:
            self.pr_info.set_markup('<span foreground="#c00">未检测到打印机。请检查连接，或直接手动勾选通用驱动安装。</span>')

    def on_auto_printer(self, widget):
        devices = detect_printers()
        ids = recommend_printer_ids(devices, self.printer_meta)
        names = [self.printer_by_id[x].get('name', x) for x in ids if x in self.printer_by_id]
        if devices:
            dev_text = '\n'.join('• %s：%s' % (d.get('kind', ''), d.get('name', ''))
                                 for d in devices[:8])
            msg = '检测到 %d 个打印设备：\n%s\n\n推荐安装：\n%s\n\n是否继续？' % (
                len(devices), dev_text, '\n'.join('• ' + n for n in names))
        else:
            msg = '没有检测到打印机。将安装通用打印环境和万能驱动：\n%s\n\n是否继续？' % (
                '\n'.join('• ' + n for n in names))
        dlg = Gtk.MessageDialog(self, 0, Gtk.MessageType.QUESTION,
                                Gtk.ButtonsType.OK_CANCEL, msg)
        resp = dlg.run()
        dlg.destroy()
        if resp != Gtk.ResponseType.OK:
            return
        for row in self.pr_store:
            row[0] = row[1] in ids
        self.on_install_printers(None)

    def on_install_printers(self, widget):
        d = self.pr_combo.get_active_text()
        if not d or not has_deb(d):
            self.show_error('请先选择包含打印机驱动的目录（printer-drivers）。')
            return
        selected = [row[1] for row in self.pr_store if row[0]]
        if not selected:
            self.show_error('请至少勾选一项驱动。')
            return
        names = []
        for sid in selected:
            it = self.printer_by_id.get(sid) or {}
            if it.get('deb_file'):
                names.append(it['deb_file'])
            else:
                names.extend(it.get('pkgs') or [])
        if not names:
            self.show_error('选中项没有可安装的 deb，请重新勾选。')
            return
        _, deps = soft_meta(d)
        self.run_task('printer', d, deps + ['--'] + names,
                      self.pr_tbuf, self.pr_start, '安装选中驱动')

    def refresh_dirs(self):
        for combo, names in ((self.up_combo, ('updata',)),
                             (self.soft_combo, ('offline-soft', 'soft')),
                             (self.pr_combo, ('printer-drivers',))):
            combo.remove_all()
            found = []
            for name in names:
                for x in find_dir(name):
                    if x not in found:
                        found.append(x)
                        combo.append_text(x)
            if len(combo.get_model()):
                combo.set_active(0)
        self.update_upgrade_info()
        self.load_soft_manifest()
        self.load_printer_manifest()

    def update_upgrade_info(self):
        d = self.up_combo.get_active_text()
        n = len(glob.glob(os.path.join(d, '*.deb'))) if d else 0
        self.up_info.set_markup('<b>找到 %d 个升级包</b>' % n if n else
                                '<span foreground="#c00">未找到升级包，请插好U盘或点“刷新”。</span>')

    def load_soft_manifest(self):
        self.store.clear()
        d = self.soft_combo.get_active_text()
        items, deps = soft_meta(d)
        for it in items:
            self.store.append([False, it.get('name', ''), it.get('cat', ''), it.get('desc', '')])
        if items:
            extra = '；依赖目录：%s' % ', '.join(os.path.basename(x) for x in deps) if deps else ''
            self.soft_info.set_markup('<b>共 %d 个软件可用</b>%s' % (len(items), extra))
        else:
            n = len(glob.glob(os.path.join(d, '*.deb'))) if d else 0
            self.soft_info.set_markup('目录内有 %d 个 deb，将整目录安装。' % n if n else
                                      '<span foreground="#c00">未找到软件目录。</span>')

    def on_soft_toggle(self, renderer, path):
        it = self.store.get_iter(path)
        self.store.set_value(it, 0, not self.store.get_value(it, 0))

    def soft_select_all(self, val):
        for row in self.store:
            row[0] = val

    def on_upgrade(self, widget):
        d = self.up_combo.get_active_text()
        if not d or not has_deb(d):
            self.show_error('请先选择包含升级包的 updata 目录。')
            return
        self.run_task('upgrade', d, [], self.up_tbuf, self.up_start, '开始升级')

    def on_install(self, widget):
        d = self.soft_combo.get_active_text()
        if not d or not has_deb(d):
            self.show_error('请先选择包含软件的目录（offline-soft 或 soft）。')
            return
        selected = [row[1] for row in self.store if row[0]]
        if len(self.store) and not selected:
            self.show_error('请至少勾选一个软件。')
            return
        _, deps = soft_meta(d)
        self.run_task('install', d, deps, self.soft_tbuf, self.soft_start, '安装选中软件')

    def run_task(self, action, target, extras, buf, button, label):
        if self._busy():
            return
        buf.set_text('')
        self.runner = TaskRunner(
            on_log=lambda t: GLib.idle_add(self.append_log, buf, t),
            on_done=lambda ok, info: GLib.idle_add(self.task_done, ok, info, button, label))
        self.up_start.set_sensitive(False)
        self.soft_start.set_sensitive(False)
        self.pr_start.set_sensitive(False)
        self.pr_auto.set_sensitive(False)
        self.runner.start(action, target, extras)

    def append_log(self, buf, text):
        buf.insert(buf.get_end_iter(), text)
        return False

    def task_done(self, ok, info, button, label):
        button.set_label(label)
        self.up_start.set_sensitive(True)
        self.soft_start.set_sensitive(True)
        self.pr_start.set_sensitive(True)
        self.pr_auto.set_sensitive(True)
        self.runner = None
        if ok:
            self.show_info('完成！建议重启电脑使更新生效。')
        else:
            self.show_error('操作返回码 %s；已完成的依然有效，可重试。\n日志：%s' % (info, LOG_PATH))

    def show_info(self, msg):
        d = Gtk.MessageDialog(self, 0, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, msg)
        d.run(); d.destroy()

    def show_error(self, msg):
        d = Gtk.MessageDialog(self, 0, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, msg)
        d.run(); d.destroy()


def main():
    App()
    Gtk.main()


if __name__ == '__main__':
    main()
