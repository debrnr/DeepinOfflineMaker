#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""常用打印机驱动目录（deepin loong64）。

数据源：
  - deepin 官方 loong64 源：CUPS / Gutenprint / Brother / Epson / splix /
    foo2zjs / OKI / 富士施乐 等开源驱动；
  - 星火商店 loong64：瑞印万能驱动、奔图、联想、HPLIP、极印、Brother 标签机
    等厂商 deb 直链。

每项结构兼容 catalog item，并额外带 match / driver_type，供目标机做设备匹配。
"""
import os
import catalog

SOURCE = 'printer'
CAT = '打印机驱动'

# 星火直链兜底（目录缓存里取不到时使用；版本以缓存为准）
FALLBACK = {
    'com.brocadesoft.ruiyin': 'https://cdn.d.store.deepinos.org.cn/loong64-store/office/com.brocadesoft.ruiyin/com.brocadesoft.ruiyin_1.3.0.0_loong64.deb',
    'com.pantum.pantum': 'https://cdn.d.store.deepinos.org.cn/loong64-store/tools/com.pantum.pantum/com.pantum.pantum_8.0.25-1%2Buos_loong64.deb',
    'com.hp.hplip': 'https://cdn.d.store.deepinos.org.cn/loong64-store/others/com.hp.hplip/com.hp.hplip_3.24.12.1_loong64.deb',
    'com.hp.uld-hp': 'https://cdn.d.store.deepinos.org.cn/loong64-store/others/com.hp.uld-hp/com.hp.uld-hp_00.11_loong64.deb',
    'lenovo-printer-driver': 'https://cdn.d.store.deepinos.org.cn/loong64-store/others/lenovo-printer-driver/lenovo-printer-driver_2.5-6_loong64.deb',
    'printer-driver-jiyin-350-400-series': 'https://cdn.d.store.deepinos.org.cn/loong64-store/tools/printer-driver-jiyin-350-400-series/printer-driver-jiyin-350-400-series_2.0.3_loong64.deb',
    'ptp900wpdrv': 'https://cdn.d.store.deepinos.org.cn/loong64-store/tools/ptp900wpdrv/ptp900wpdrv_1.0.2-0_loong64.deb',
}


# (id, 显示名, 类型, 说明, pkgs, spark_id, match)
_DEFS = [
    ('print-base', '打印基础环境（CUPS + 图形配置）', '基础环境',
     'CUPS 打印服务、过滤器、网络发现、系统打印设置。装任何打印机前都建议先装。',
     ['cups', 'cups-client', 'cups-filters', 'cups-browsed',
      'system-config-printer', 'foomatic-db-compressed-ppds'], '', []),

    ('print-ruiyin', '瑞印万能打印驱动（个人版）', '通用兜底',
     '国产通用打印驱动，兼容绝大多数网络/存量打印机，找不到专用驱动时优先用它。',
     [], 'com.brocadesoft.ruiyin', ['ruiyin', 'universal', '万能', 'unknown']),

    ('print-gutenprint', 'Gutenprint 通用驱动', '通用兜底',
     '开源通用驱动，覆盖大量 Canon / Epson / HP / Lexmark / Ricoh 等型号。',
     ['printer-driver-gutenprint'], '',
     ['canon', '佳能', 'epson', '爱普生', 'lexmark', 'ricoh', '理光',
      'hp', 'hewlett', '惠普', '04b8', '03f0', '0583']),

    ('print-hplip', '惠普 HPLIP 驱动', '品牌专用',
     'HPLIP 龙芯版，覆盖 HP 专业级激光/一体机/页宽打印机。',
     [], 'com.hp.hplip', ['hp', 'hewlett', '惠普', '03f0']),

    ('print-hp-uld', '惠普 hp-uld 打印驱动', '品牌专用',
     'HP 通用打印驱动补充包，配合 HPLIP 使用。',
     [], 'com.hp.uld-hp', ['hp', '惠普', '03f0']),

    ('print-pantum', '奔图打印机驱动', '品牌专用',
     '奔图 Pantum 龙芯版驱动，信创单位常见机型。',
     [], 'com.pantum.pantum', ['pantum', '奔图']),

    ('print-lenovo', '联想打印驱动', '品牌专用',
     '联想 Lenovo 龙芯版打印驱动集合。',
     [], 'lenovo-printer-driver', ['lenovo', '联想']),

    ('print-brother', '兄弟激光打印机驱动', '品牌专用',
     'Brother 激光打印机开源驱动 brlaser。',
     ['printer-driver-brlaser'], '', ['brother', '兄弟', '04f9']),

    ('print-brother-label', 'Brother PT-P900w 标签机驱动', '品牌专用',
     '兄弟 PT-P900w 标签打印机专用驱动。',
     [], 'ptp900wpdrv', ['pt-p900', 'ptp900', '标签']),

    ('print-epson', '爱普生 Epson 驱动', '品牌专用',
     'Epson 喷墨/一体机开源驱动 escpr。',
     ['printer-driver-escpr'], '', ['epson', '爱普生', '04b8']),

    ('print-samsung', '三星 / 施乐 GDI 驱动', '品牌专用',
     'splix + foo2zjs，覆盖三星、部分施乐/柯美、HP 老款 GDI 机型。',
     ['printer-driver-splix', 'printer-driver-foo2zjs'], '',
     ['samsung', '三星', 'xerox', '施乐', 'konica', 'minolta', '04e8']),

    ('print-oki', 'OKI / 富士施乐 / 京瓷驱动', '品牌专用',
     'OKI、富士施乐、京瓷等机型开源驱动。',
     ['printer-driver-oki', 'printer-driver-fujixerox'], '',
     ['oki', 'fujixerox', '富士施乐', 'ricoh', '理光', 'kyocera', '京瓷']),

    ('print-canon-bjnp', '佳能 BJNP 网络打印支持', '品牌专用',
     'Canon BJNP 网络打印后端，配合 Gutenprint 使用。',
     ['cups-backend-bjnp'], '', ['canon', '佳能', 'bjnp', '0583']),

    ('print-jiyin', '极印系列打印驱动', '品牌专用',
     '极印 350/400 系列龙芯打印芯片一体机驱动。',
     [], 'printer-driver-jiyin-350-400-series', ['jiyin', '极印']),

    ('print-cups-pdf', '虚拟 PDF 打印机', '实用工具',
     '把任意文档“打印”成 PDF，无实体打印机也能用。',
     ['printer-driver-cups-pdf'], '', ['pdf', 'virtual']),
]

DEFAULT_IDS = [
    'print-base', 'print-ruiyin', 'print-gutenprint', 'print-hplip',
    'print-pantum', 'print-lenovo', 'print-brother', 'print-epson',
    'print-samsung', 'print-canon-bjnp',
]


def _spark_by_id(cache_dir):
    cached = catalog.load_cache(cache_dir or '.') or {}
    return {it.get('id'): it for it in (cached.get('items') or [])}


def all_items(cache_dir=None):
    spark = _spark_by_id(cache_dir)
    out = []
    for did, name, dtype, desc, pkgs, spark_pkg, match in _DEFS:
        url, deb_file, ver, size, upd = '', '', '', '', ''
        if spark_pkg:
            sid = next((k for k in spark if k.endswith(':' + spark_pkg)), None)
            src = spark.get(sid) or {}
            url = src.get('deb_url') or FALLBACK.get(spark_pkg, '')
            deb_file = src.get('deb_file') or os.path.basename(url.split('?')[0])
            ver = src.get('version', '')
            size = src.get('size', '')
            upd = src.get('update', '')
        out.append({
            'id': did,
            'name': name,
            'cat': CAT,
            'desc': desc + ('　版本 %s · %s' % (ver, size) if ver else ''),
            'source': SOURCE,
            'pkgs': list(pkgs),
            'deb_url': url,
            'deb_file': deb_file,
            'version': ver,
            'size': size,
            'update': upd,
            'tags': dtype,
            'driver_type': dtype,
            'match': list(match),
        })
    return out


def by_id(items=None):
    return {it['id']: it for it in (items if items is not None else all_items())}


def defaults():
    return list(DEFAULT_IDS)
