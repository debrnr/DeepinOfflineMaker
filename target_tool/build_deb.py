#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 Windows 上手工构建标准 .deb (ar + control.tar.gz + data.tar.gz)。"""
import os, sys, io, gzip, tarfile, time

SRC = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(SRC), 'src', 'assets', 'deepin-offline-upgrade_1.4_all.deb')

PKG = 'deepin-offline-upgrade'
VER = '1.4'
CONTROL = f'''Package: {PKG}
Version: {VER}
Section: utils
Priority: optional
Architecture: all
Depends: python3, python3-gi, gir1.2-gtk-3.0, apt, policykit-1
Maintainer: offline-tools <offline@local>
Description: deepin 离线升级、软件安装与打印机驱动工具
 无网络的图形化工具，含“离线升级”“软件安装”“打印机驱动”三页。
 软件与打印机驱动主包、依赖分目录，安装时自动合并为本地 apt 源。
 打印机页可检测 USB/网络打印机并按品牌推荐驱动。
 增量更新包插入后启动时自动提示本次更新内容。
 双击安装后，从应用菜单启动“离线工具”即可。

'''

ICON_SVG = '''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
  <circle cx="32" cy="32" r="30" fill="#1f5fa9"/>
  <path d="M32 14 v26" stroke="#fff" stroke-width="6" stroke-linecap="round"/>
  <path d="M20 28 l12 12 12-12" fill="none" stroke="#fff" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M18 50 h28" stroke="#9ecbff" stroke-width="5" stroke-linecap="round"/>
</svg>
'''

DESKTOP = '''[Desktop Entry]
Type=Application
Version=1.0
Name=离线工具
Name[en_US]=Offline Tool
Comment=无网络的离线增量升级、软件安装与打印机驱动
Comment[en_US]=Offline upgrade, software and printer drivers
Exec=/usr/bin/deepin-offline-upgrade
Icon=deepin-offline-upgrade
Terminal=false
Categories=System;Settings;
Keywords=upgrade;offline;离线;升级;
'''

POSTINST = '''#!/bin/sh
set -e
chmod 755 /usr/bin/deepin-offline-upgrade
chmod 755 /usr/lib/deepin-offline-upgrade/helper.sh
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
fi
exit 0
'''

def tar_gz(members):
    """members: list of (arcname, bytes, mode) -> bytes of gzip(tar)"""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode='w', format=tarfile.GNU_FORMAT) as tf:
        for name, data, mode in members:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = mode
            info.mtime = int(time.time())
            info.uid = 0
            info.gid = 0
            info.uname = 'root'
            info.gname = 'root'
            tf.addfile(info, io.BytesIO(data))
    return gzip.compress(raw.getvalue(), mtime=0)

def ar_member(name, data):
    # GNU ar 成员头: name[16] mtime[12] uid[6] gid[6] mode[8] size[10] "`\n"
    hdr = (name + '/').ljust(16).encode('ascii')
    hdr += b'0'.ljust(12) + b'0'.ljust(6) + b'0'.ljust(6)
    hdr += b'100644'.ljust(8) + str(len(data)).encode('ascii').ljust(10)
    hdr += b'`\n'
    assert len(hdr) == 60, len(hdr)
    blob = hdr + data
    if len(data) % 2 == 1:
        blob += b'\n'
    return blob

def read_src(fn):
    with open(os.path.join(SRC, fn), 'rb') as f:
        return f.read()

def main():
    # control.tar.gz
    control_members = [
        ('./control', CONTROL.encode('utf-8'), 0o644),
        ('./postinst', POSTINST.encode('utf-8'), 0o755),
    ]
    control_tar = tar_gz(control_members)

    # data.tar.gz
    data_members = [
        ('./usr/bin/deepin-offline-upgrade', read_src('deepin-offline-upgrade.py'), 0o755),
        ('./usr/lib/deepin-offline-upgrade/helper.sh', read_src('helper.sh'), 0o755),
        ('./usr/share/applications/deepin-offline-upgrade.desktop', DESKTOP.encode('utf-8'), 0o644),
        ('./usr/share/icons/hicolor/scalable/apps/deepin-offline-upgrade.svg', ICON_SVG.encode('utf-8'), 0o644),
    ]
    data_tar = tar_gz(data_members)

    out = io.BytesIO()
    out.write(b'!<arch>\n')
    out.write(ar_member('debian-binary', b'2.0\n'))
    out.write(ar_member('control.tar.gz', control_tar))
    out.write(ar_member('data.tar.gz', data_tar))
    with open(OUT, 'wb') as f:
        f.write(out.getvalue())
    print('built:', OUT)
    print('size:', os.path.getsize(OUT), 'bytes')

if __name__ == '__main__':
    main()
