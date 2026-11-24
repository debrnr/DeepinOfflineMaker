#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""常用龙芯软件清单。每项: id, 显示名, 分类, 说明, 主包列表。
制作工具据此从 deepin loong64 源下载主包+依赖，存到 soft 目录。
目标机图形工具读取 soft/manifest.json 列出可安装软件。
"""

SOFTWARE = [
    # 办公
    {'id': 'wps', 'name': 'WPS Office', 'cat': '办公',
     'desc': '龙芯版办公套件（文字/表格/演示），本地使用无需登录。',
     'pkgs': [], 'deb': 'wps-office_12.8.2.18605.AK.preload.sw_loongarch64.deb',
     'source': 'loongapps'},
    {'id': 'libreoffice', 'name': 'LibreOffice 全套', 'cat': '办公',
     'desc': '开源办公套件：Writer/Calc/Impress/Draw/Base。',
     'pkgs': ['libreoffice', 'libreoffice-writer', 'libreoffice-calc',
              'libreoffice-impress', 'libreoffice-draw', 'libreoffice-base']},
    # 压缩
    {'id': 'archive', 'name': '7-Zip / unrar', 'cat': '实用工具',
     'desc': '压缩解压：7z、rar、zip 等格式。',
     'pkgs': ['7zip', 'unrar', 'deepin-compressor']},
    # 输入法
    {'id': 'wubi', 'name': 'fcitx5 五笔输入法', 'cat': '输入法',
     'desc': '五笔98/大五笔 + 中文插件（搜狗五笔无 loong64 原生版的替代）。',
     'pkgs': ['fcitx5-table-wubi98', 'fcitx5-table-wubi-large',
              'fcitx5-chinese-addons', 'fcitx5-config-qt']},
    # FTP
    {'id': 'ftp', 'name': 'FTP 服务器 + 客户端', 'cat': '网络',
     'desc': 'ProFTPD/vsftpd 服务端 + FileZilla 图形客户端。',
     'pkgs': ['proftpd-core', 'vsftpd', 'filezilla']},
    # PDF
    {'id': 'pdf', 'name': 'PDF 工具集', 'cat': '办公',
     'desc': 'PDF 阅读/编辑/注释 + 虚拟打印机（打印成 PDF）。',
     'pkgs': ['okular', 'xournalpp', 'pdfarranger', 'libreoffice-draw',
              'printer-driver-cups-pdf', 'mupdf-tools', 'deepin-reader']},
    # 同步
    {'id': 'sync', 'name': 'Syncthing 文件同步', 'cat': '网络',
     'desc': '开源点对点文件同步，可做多人共享目录。',
     'pkgs': ['syncthing']},
    # 字体
    {'id': 'fonts', 'name': '中文字体', 'cat': '实用工具',
     'desc': '思源黑体/文泉驿等中文字体。',
     'pkgs': ['fonts-noto-cjk', 'fonts-wqy-microhei']},
]

DEFAULT_SELECTED = ['wps', 'libreoffice', 'archive', 'wubi', 'pdf', 'fonts']

# 龙芯应用合作社 WPS 直链（与使用合作社版本一致，非 365 限流版）
WPS_DIRECT_URL = ('https://app.loongapps.cn/api/file/loongapps/upload/file/'
                  'wps-office_12.8.2.18605.AK.preload.sw_loongarch64.deb')


def get_by_id(sid):
    for s in SOFTWARE:
        if s['id'] == sid:
            return s
    return None


def software_manifest(selected_ids):
    """生成目标机图形工具读取的 manifest.json 数据。"""
    import datetime
    items = []
    for sid in selected_ids:
        s = get_by_id(sid)
        if not s:
            continue
        items.append({
            'id': s['id'], 'name': s['name'], 'cat': s['cat'], 'desc': s['desc'],
        })
    return {
        'generated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'items': items,
    }
