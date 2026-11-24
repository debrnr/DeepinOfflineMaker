#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DeepinOfflineMaker - Windows 下制作 deepin loong64 离线升级包 + 软件包的图形工具。"""
import os, sys, queue, threading, traceback, datetime, shutil, tempfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


def resource_path(*parts):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, *parts)
    return os.path.join(APP_DIR, *parts)


_DATA_DIR = None


def data_dir():
    """可写数据目录：存放软件目录缓存、仓库索引和项目基线。

    单文件（--onefile）版运行时资源解压到临时目录，退出即被删除，
    因此缓存和 project 基线绝不能写在 resource_path('cache') 里。
    优先用 exe 同目录的 DOM-data/（U 盘可随身携带），不可写时退回
    %LOCALAPPDATA%/DeepinOfflineMaker。首次运行把内置的目录缓存复制过来。
    """
    global _DATA_DIR
    if _DATA_DIR:
        return _DATA_DIR
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = APP_DIR
    candidates = [
        os.path.join(base, 'DOM-data'),
        os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'),
                     'DeepinOfflineMaker'),
    ]
    for d in candidates:
        try:
            os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, '.write-test')
            with open(probe, 'w', encoding='utf-8') as f:
                f.write('ok')
            os.remove(probe)
            builtin = os.path.join(resource_path('cache'), 'catalog-spark.json')
            seeded = os.path.join(d, 'catalog-spark.json')
            if not os.path.isfile(seeded) and os.path.isfile(builtin):
                shutil.copy2(builtin, seeded)
            _DATA_DIR = d
            return d
        except Exception:
            continue
    _DATA_DIR = tempfile.gettempdir()
    return _DATA_DIR


import catalog
import software_list
import printer_drivers
import project
import updates

BG = '#f4f6f9'; CARD = '#ffffff'; ACCENT = '#1f5fa9'
TEXT = '#1f2933'; MUTED = '#6b7280'


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('deepin 离线升级包制作工具')
        self.geometry('1020x800')
        self.configure(bg=BG)
        self.q = queue.Queue()
        self.running = False
        self.refreshing = False
        self.checking = False

        self.var_mode = tk.StringVar(value='update')
        self.var_new_iso = tk.StringVar()
        self.var_old_iso = tk.StringVar()
        self.var_out = tk.StringVar()
        self.var_workers = tk.StringVar(value='6')

        # 软件目录
        self.catalog_items = []
        self.selected_ids = set(software_list.DEFAULT_SELECTED)
        self.item_by_iid = {}
        self.src_vars = {'builtin': tk.BooleanVar(value=True),
                         'spark': tk.BooleanVar(value=True),
                         'apt': tk.BooleanVar(value=False)}
        self.var_search = tk.StringVar()
        self.var_cat = tk.StringVar(value='全部')
        self.var_source = tk.StringVar(value='全部')
        self.var_soft_dir = tk.StringVar(value='offline-soft')
        self.var_deps = tk.StringVar(value='subdir')

        # 打印机驱动
        self.printer_items = printer_drivers.all_items(data_dir())
        self.selected_printer_ids = set(printer_drivers.defaults())
        self.printer_by_iid = {}
        self.var_printer_dir = tk.StringVar(value='printer-drivers')

        # 增量更新
        self.proj = None
        self.report = None
        self.repo_upd = None
        self.base_upd = None
        self.var_upd_out = tk.StringVar()
        self.sys_items = {}
        self.soft_upd_items = {}
        self.sys_sel = set()
        self.soft_upd_sel = set()

        self._style()
        self._build()
        self.after(100, self._poll)
        self.after(200, self._load_cached_catalog)
        self.after(250, self._load_last_project)

    def _style(self):
        st = ttk.Style(self)
        try:
            st.theme_use('vista')
        except Exception:
            pass
        st.configure('TFrame', background=BG)
        st.configure('Card.TFrame', background=CARD, relief='flat')
        st.configure('TLabel', background=BG, foreground=TEXT, font=('Microsoft YaHei UI', 10))
        st.configure('Card.TLabel', background=CARD, foreground=TEXT, font=('Microsoft YaHei UI', 10))
        st.configure('Title.TLabel', background=BG, foreground=ACCENT, font=('Microsoft YaHei UI', 17, 'bold'))
        st.configure('Sub.TLabel', background=BG, foreground=MUTED, font=('Microsoft YaHei UI', 9))
        st.configure('Head.TLabel', background=CARD, foreground=ACCENT, font=('Microsoft YaHei UI', 11, 'bold'))
        st.configure('TButton', font=('Microsoft YaHei UI', 10))
        st.configure('TRadiobutton', background=CARD, foreground=TEXT, font=('Microsoft YaHei UI', 10))
        st.configure('TCheckbutton', background=CARD, foreground=TEXT, font=('Microsoft YaHei UI', 10))
        st.configure('TEntry', font=('Microsoft YaHei UI', 10))
        st.configure('Accent.TButton', font=('Microsoft YaHei UI', 11, 'bold'))
        st.configure('Treeview', font=('Microsoft YaHei UI', 9), rowheight=23)

    def _build(self):
        head = ttk.Frame(self)
        head.pack(fill='x', padx=18, pady=(12, 4))
        ttk.Label(head, text='deepin 离线升级包制作工具', style='Title.TLabel').pack(anchor='w')
        ttk.Label(head, text='模拟“刚装好 ISO 后联网会升级的内容”；软件目录可在线刷新，主包与依赖分目录，支持定期增量更新网盘分发',
                  style='Sub.TLabel').pack(anchor='w', pady=(2, 0))

        nb = ttk.Notebook(self)
        nb.pack(fill='both', expand=True, padx=18, pady=8)
        cfg_page = ttk.Frame(nb, padding=12)
        soft_page = ttk.Frame(nb, padding=12)
        printer_page = ttk.Frame(nb, padding=12)
        upd_page = ttk.Frame(nb, padding=12)
        nb.add(cfg_page, text='  升级包配置  ')
        nb.add(soft_page, text='  软件目录与下载  ')
        nb.add(printer_page, text='  打印机驱动  ')
        nb.add(upd_page, text='  增量更新 / 网盘分享  ')

        self._build_config_page(cfg_page)
        self._build_soft_page(soft_page)
        self._build_printer_page(printer_page)
        self._build_update_page(upd_page)
        self._on_mode()

    # ---------------- 第 1 页 ----------------
    def _build_config_page(self, page):
        left = ttk.Frame(page)
        left.pack(side='left', fill='both', expand=True)
        right = ttk.Frame(page)
        right.pack(side='right', fill='both', padx=(12, 0))

        ttk.Label(left, text='① 打包模式', style='Head.TLabel').pack(anchor='w')
        modef = ttk.Frame(left, style='Card.TFrame')
        modef.pack(fill='x', pady=(6, 10))
        ttk.Radiobutton(modef, text='增量更新（推荐）— 以 ISO 版本为基准，抓源里比它新的包',
                        variable=self.var_mode, value='update', command=self._on_mode).pack(anchor='w', pady=3)
        ttk.Radiobutton(modef, text='全量 — ISO 内所有包，任何旧版本可升（体积大）',
                        variable=self.var_mode, value='full', command=self._on_mode).pack(anchor='w', pady=3)
        ttk.Radiobutton(modef, text='两版本对比（兼容旧用法）— 需另选旧 ISO',
                        variable=self.var_mode, value='diff', command=self._on_mode).pack(anchor='w', pady=3)

        ttk.Label(left, text='② 新版本 ISO（必选）', style='Head.TLabel').pack(anchor='w')
        f1 = ttk.Frame(left, style='Card.TFrame')
        f1.pack(fill='x', pady=(6, 10))
        ttk.Entry(f1, textvariable=self.var_new_iso).pack(side='left', fill='x', expand=True)
        ttk.Button(f1, text='浏览', command=self._pick_new, width=8).pack(side='left', padx=(6, 0))

        self.old_frame = ttk.Frame(left, style='Card.TFrame')
        ttk.Label(self.old_frame, text='③ 旧版本 ISO / 清单（仅“两版本对比”需要）',
                  style='Head.TLabel').pack(anchor='w')
        f2 = ttk.Frame(self.old_frame, style='Card.TFrame')
        f2.pack(fill='x', pady=(6, 8))
        ttk.Entry(f2, textvariable=self.var_old_iso).pack(side='left', fill='x', expand=True)
        ttk.Button(f2, text='浏览', command=self._pick_old, width=8).pack(side='left', padx=(6, 0))

        self.out_frame = ttk.Frame(left, style='Card.TFrame')
        self.out_frame.pack(fill='x')
        ttk.Label(self.out_frame, text='③ 输出目录', style='Head.TLabel').pack(anchor='w')
        f3 = ttk.Frame(self.out_frame, style='Card.TFrame')
        f3.pack(fill='x', pady=(6, 8))
        ttk.Entry(f3, textvariable=self.var_out).pack(side='left', fill='x', expand=True)
        ttk.Button(f3, text='浏览', command=self._pick_out, width=8).pack(side='left', padx=(6, 0))
        f4 = ttk.Frame(self.out_frame, style='Card.TFrame')
        f4.pack(fill='x')
        ttk.Label(f4, text='下载线程：', style='Card.TLabel').pack(side='left')
        ttk.Spinbox(f4, from_=2, to=20, textvariable=self.var_workers, width=5).pack(side='left', padx=(4, 0))
        ttk.Label(f4, text='  （镜像限流会自动切换）', style='Card.TLabel', foreground=MUTED).pack(side='left')

        self.btn_start = ttk.Button(left, text='开始制作', style='Accent.TButton', command=self._start)
        self.btn_start.pack(fill='x', pady=(14, 2), ipady=6)
        self.btn_open = ttk.Button(left, text='打开输出目录', command=self._open_out, state='disabled')
        self.btn_open.pack(fill='x', pady=(4, 0))

        ttk.Label(right, text='进度', style='Head.TLabel').pack(anchor='w')
        self.pbar = ttk.Progressbar(right, mode='determinate', length=250)
        self.pbar.pack(fill='x', pady=(6, 4))
        self.lbl_prog = ttk.Label(right, text='等待开始...', style='Sub.TLabel', wraplength=240)
        self.lbl_prog.pack(anchor='w', pady=(0, 10))
        ttk.Label(right, text='日志', style='Head.TLabel').pack(anchor='w')
        logf = ttk.Frame(right, style='Card.TFrame')
        logf.pack(fill='both', expand=True, pady=(6, 0))
        self.log = tk.Text(logf, width=46, height=32, font=('Consolas', 9),
                           bg='#1e1e1e', fg='#d4d4d4', wrap='word', relief='flat')
        self.log.pack(fill='both', expand=True, padx=1, pady=1)
        self.log.configure(state='disabled')

    # ---------------- 第 2 页 ----------------
    def _build_soft_page(self, page):
        ttk.Label(page, text='① 软件目录来源', style='Head.TLabel').pack(anchor='w')
        srcbar = ttk.Frame(page, style='Card.TFrame')
        srcbar.pack(fill='x', pady=(6, 6))
        ttk.Label(srcbar, text='来源：', style='Card.TLabel').pack(side='left')
        for key, txt in (('builtin', '内置精选'), ('spark', '星火商店 loong64'), ('apt', 'deepin 官方源')):
            ttk.Checkbutton(srcbar, text=txt, variable=self.src_vars[key],
                            command=self._apply_filter).pack(side='left', padx=(4, 2))
        self.btn_refresh = ttk.Button(srcbar, text='刷新目录', command=self._refresh_catalog)
        self.btn_refresh.pack(side='left', padx=(12, 4))
        self.lbl_cat_status = ttk.Label(srcbar, text='正在载入缓存...', style='Card.TLabel',
                                        foreground=MUTED)
        self.lbl_cat_status.pack(side='left', padx=(6, 0))

        filterbar = ttk.Frame(page, style='Card.TFrame')
        filterbar.pack(fill='x', pady=(0, 8))
        ttk.Label(filterbar, text='搜索：', style='Card.TLabel').pack(side='left')
        ent = ttk.Entry(filterbar, textvariable=self.var_search, width=22)
        ent.pack(side='left', padx=(2, 8))
        ent.bind('<KeyRelease>', lambda e: self._apply_filter())
        ttk.Label(filterbar, text='分类：', style='Card.TLabel').pack(side='left')
        self.cb_cat = ttk.Combobox(filterbar, textvariable=self.var_cat, width=12, state='readonly')
        self.cb_cat.pack(side='left', padx=(2, 8))
        self.cb_cat.bind('<<ComboboxSelected>>', lambda e: self._apply_filter())
        ttk.Label(filterbar, text='来源：', style='Card.TLabel').pack(side='left')
        self.cb_source = ttk.Combobox(filterbar, textvariable=self.var_source, width=10, state='readonly',
                                      values=['全部', '内置精选', '星火商店', 'deepin源'])
        self.cb_source.set('全部')
        self.cb_source.pack(side='left', padx=(2, 8))
        self.cb_source.bind('<<ComboboxSelected>>', lambda e: self._apply_filter())
        ttk.Label(filterbar, text='（双击行勾选/取消）', style='Card.TLabel',
                  foreground=MUTED).pack(side='left')

        ttk.Label(page, text='② 勾选要下载的软件', style='Head.TLabel').pack(anchor='w')
        wrap = ttk.Frame(page, style='Card.TFrame')
        wrap.pack(fill='both', expand=True, pady=(6, 8))
        self.tree = ttk.Treeview(wrap, columns=('sel', 'name', 'cat', 'source', 'desc'),
                                 show='headings', selectmode='none')
        for col, text, width, stretch in (
                ('sel', '选', 34, False), ('name', '软件名称', 210, False),
                ('cat', '分类', 88, False), ('source', '来源', 88, False),
                ('desc', '说明 / 版本 / 大小', 420, True)):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, stretch=stretch, anchor='w')
        sb = ttk.Scrollbar(wrap, orient='vertical', command=self.tree.yview)
        sb.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side='left', fill='both', expand=True)
        self.tree.bind('<Double-1>', self._on_tree_toggle)

        bar = ttk.Frame(page, style='Card.TFrame')
        bar.pack(fill='x', pady=(0, 6))
        ttk.Button(bar, text='全选结果', command=self._select_visible).pack(side='left', padx=(0, 5))
        ttk.Button(bar, text='清空选择', command=self._clear_selection).pack(side='left', padx=(0, 5))
        ttk.Button(bar, text='恢复推荐', command=self._restore_default).pack(side='left')
        self.lbl_sel = ttk.Label(bar, text='已选 0 项', style='Card.TLabel', foreground=ACCENT)
        self.lbl_sel.pack(side='left', padx=(12, 0))

        outbar = ttk.Frame(page, style='Card.TFrame')
        outbar.pack(fill='x')
        ttk.Label(outbar, text='③ 软件主包目录：', style='Card.TLabel').pack(side='left')
        ttk.Entry(outbar, textvariable=self.var_soft_dir, width=16).pack(side='left', padx=(2, 12))
        ttk.Label(outbar, text='依赖包放：', style='Card.TLabel').pack(side='left')
        ttk.Combobox(outbar, textvariable=self.var_deps, width=26, state='readonly',
                     values=['软件目录下的 deps/（推荐）', '独立目录 soft-deps/', '并入 updata/ 升级目录']
                     ).pack(side='left', padx=(2, 0))

    # ---------------- 打印机驱动页 ----------------
    def _build_printer_page(self, page):
        ttk.Label(page, text='① 常用打印机驱动（deepin loong64）', style='Head.TLabel').pack(anchor='w')
        ttk.Label(page,
                  text='默认已勾常用驱动；“瑞印万能驱动”用于未知型号/网络打印机。下载后目标机“打印机驱动”页可检测设备并一键安装。',
                  style='Sub.TLabel', wraplength=900).pack(anchor='w', pady=(4, 8))

        wrap = ttk.Frame(page, style='Card.TFrame')
        wrap.pack(fill='both', expand=True, pady=(0, 8))
        self.printer_tree = ttk.Treeview(
            wrap, columns=('sel', 'name', 'type', 'desc'), show='headings', selectmode='none')
        for col, text, width, stretch in (
                ('sel', '选', 34, False), ('name', '驱动', 240, False),
                ('type', '类型', 110, False), ('desc', '说明 / 版本 / 大小', 520, True)):
            self.printer_tree.heading(col, text=text)
            self.printer_tree.column(col, width=width, stretch=stretch, anchor='w')
        sb = ttk.Scrollbar(wrap, orient='vertical', command=self.printer_tree.yview)
        sb.pack(side='right', fill='y')
        self.printer_tree.configure(yscrollcommand=sb.set)
        self.printer_tree.pack(side='left', fill='both', expand=True)
        self.printer_tree.bind('<Double-1>', self._on_printer_toggle)

        bar = ttk.Frame(page, style='Card.TFrame')
        bar.pack(fill='x', pady=(0, 8))
        ttk.Button(bar, text='全选', command=lambda: self._printer_select_all(True)).pack(side='left', padx=(0, 5))
        ttk.Button(bar, text='清空', command=lambda: self._printer_select_all(False)).pack(side='left', padx=(0, 5))
        ttk.Button(bar, text='恢复推荐', command=self._printer_restore).pack(side='left')
        self.lbl_printer_sel = ttk.Label(bar, text='已选 0 项', style='Card.TLabel', foreground=ACCENT)
        self.lbl_printer_sel.pack(side='left', padx=(12, 0))

        outbar = ttk.Frame(page, style='Card.TFrame')
        outbar.pack(fill='x')
        ttk.Label(outbar, text='驱动目录：', style='Card.TLabel').pack(side='left')
        ttk.Entry(outbar, textvariable=self.var_printer_dir, width=22).pack(side='left', padx=(2, 8))
        ttk.Label(outbar, text='依赖自动放在该目录的 deps/ 子目录，目标机安装时自动加入 apt 源。',
                  style='Card.TLabel', foreground=MUTED).pack(side='left')
        self._apply_printer_filter()

    # ---------------- 第 3 页 ----------------
    def _build_update_page(self, page):
        ttk.Label(page, text='① 当前基线项目（上次制作完整包时自动生成）', style='Head.TLabel').pack(anchor='w')
        pbar = ttk.Frame(page, style='Card.TFrame')
        pbar.pack(fill='x', pady=(6, 6))
        self.lbl_project = ttk.Label(pbar, text='尚未载入基线，请先用第 1 页制作一次完整包',
                                     style='Card.TLabel', foreground=MUTED, wraplength=800)
        self.lbl_project.pack(side='left', fill='x', expand=True)
        ttk.Button(pbar, text='载入项目', command=self._pick_project, width=10).pack(side='left', padx=(6, 2))
        ttk.Button(pbar, text='从交付目录载入', command=self._pick_project_dir, width=14).pack(side='left', padx=2)
        ttk.Button(pbar, text='重载缓存', command=self._load_last_project, width=10).pack(side='left')
        ttk.Label(page, text='提示：每次生成完整包或增量包都会写 project.json 到输出目录，它是下一次增量的基线；保存/分享时请连同它一起保留。'
                             '半年后打开本页会自动载入上次基线，若换了电脑就用上面两个按钮从 U 盘或网盘下载的交付目录里载入。',
                  style='Card.TLabel', foreground=MUTED, wraplength=880).pack(anchor='w', pady=(0, 8))

        cbar = ttk.Frame(page, style='Card.TFrame')
        cbar.pack(fill='x', pady=(0, 8))
        self.btn_check = ttk.Button(cbar, text='检查更新（联网）', style='Accent.TButton',
                                    command=self._check_updates)
        self.btn_check.pack(side='left')
        self.lbl_upd_status = ttk.Label(cbar, text='点“检查更新”对比星火目录与 deepin 源',
                                        style='Card.TLabel', foreground=MUTED)
        self.lbl_upd_status.pack(side='left', padx=(12, 0))

        ttk.Label(page, text='② 勾选本次要下载的更新（默认全选，双击行切换）', style='Head.TLabel').pack(anchor='w')
        nb = ttk.Notebook(page)
        nb.pack(fill='both', expand=True, pady=(6, 8))
        sysf = ttk.Frame(nb, padding=6)
        softf = ttk.Frame(nb, padding=6)
        nb.add(sysf, text='  系统更新  ')
        nb.add(softf, text='  软件更新  ')

        self.sys_tree = self._make_upd_tree(sysf,
            (('sel', '选', 36, False), ('name', '包名', 210, False),
             ('old', '已装/上次版本', 190, False), ('new', '最新版本', 190, True)))
        self.soft_tree = self._make_upd_tree(softf,
            (('sel', '选', 36, False), ('name', '软件', 200, False),
             ('old', '旧版本', 130, False), ('new', '新版本', 160, False),
             ('reason', '变化', 320, True)))
        self.sys_tree.bind('<Double-1>', lambda e: self._toggle_upd(e, self.sys_tree, self.sys_items, self.sys_sel))
        self.soft_tree.bind('<Double-1>', lambda e: self._toggle_upd(e, self.soft_tree,
                                                                     self.soft_upd_items, self.soft_upd_sel))

        dlbar = ttk.Frame(page, style='Card.TFrame')
        dlbar.pack(fill='x', pady=(0, 6))
        ttk.Label(dlbar, text='更新包目录：', style='Card.TLabel').pack(side='left')
        ttk.Entry(dlbar, textvariable=self.var_upd_out, width=52).pack(side='left', padx=(2, 6))
        ttk.Button(dlbar, text='浏览', command=self._pick_upd_out, width=7).pack(side='left', padx=(0, 8))
        self.btn_dl_upd = ttk.Button(dlbar, text='下载更新包', style='Accent.TButton',
                                     command=self._download_updates)
        self.btn_dl_upd.pack(side='left')

        logf = ttk.Frame(page, style='Card.TFrame')
        logf.pack(fill='x')
        self.upd_log = tk.Text(logf, height=5, font=('Consolas', 9), bg='#1e1e1e',
                               fg='#d4d4d4', wrap='word', relief='flat')
        self.upd_log.pack(fill='x', padx=1, pady=1)
        self.upd_log.configure(state='disabled')

    def _make_upd_tree(self, parent, cols):
        wrap = ttk.Frame(parent, style='Card.TFrame')
        wrap.pack(fill='both', expand=True)
        tree = ttk.Treeview(wrap, columns=tuple(c[0] for c in cols), show='headings', selectmode='none')
        for col, text, width, stretch in cols:
            tree.heading(col, text=text)
            tree.column(col, width=width, stretch=stretch, anchor='w')
        sb = ttk.Scrollbar(wrap, orient='vertical', command=tree.yview)
        sb.pack(side='right', fill='y')
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side='left', fill='both', expand=True)
        return tree

    # ---------------- 软件目录 ----------------
    def _load_cached_catalog(self):
        try:
            items = catalog.load_catalog(data_dir(), sources=('builtin', 'spark'),
                                         refresh=False, log=lambda m: None)
            self.catalog_items = items
            self._apply_filter()
            self.printer_items = printer_drivers.all_items(data_dir())
            self._apply_printer_filter()
            self.lbl_cat_status.configure(text='缓存 %d 项；点“刷新目录”从星火商店取最新 loong64 软件' % len(items))
        except Exception as e:
            self.lbl_cat_status.configure(text='目录载入失败：%s' % e)

    def _apply_filter(self):
        source = {'内置精选': 'builtin', '星火商店': 'spark', 'deepin源': 'apt'}.get(
            self.var_source.get(), '')
        sources = [k for k, v in self.src_vars.items() if v.get()]
        items = [it for it in self.catalog_items if it.get('source') in sources]
        items = catalog.filter_items(items, self.var_search.get(),
                                     '' if self.var_cat.get() == '全部' else self.var_cat.get(), source)
        cats = sorted({it.get('cat', '') for it in self.catalog_items if it.get('source') in sources})
        self.cb_cat.configure(values=['全部'] + cats)
        if self.var_cat.get() not in ['全部'] + cats:
            self.var_cat.set('全部')
        self.tree.delete(*self.tree.get_children())
        self.item_by_iid.clear()
        for it in items:
            iid = str(it['id'])
            self.tree.insert('', 'end', iid=iid, values=(
                '☑' if it['id'] in self.selected_ids else '☐', it.get('name', ''),
                it.get('cat', ''), catalog.SOURCE_LABELS.get(it.get('source'), it.get('source', '')),
                it.get('desc', '')))
            self.item_by_iid[iid] = it
        self.lbl_sel.configure(text='已选 %d 项' % len(self.selected_ids))

    def _toggle_iid(self, iid):
        it = self.item_by_iid.get(iid)
        if not it:
            return
        sid = it['id']
        if sid in self.selected_ids:
            self.selected_ids.discard(sid); mark = '☐'
        else:
            self.selected_ids.add(sid); mark = '☑'
        self.tree.set(iid, 'sel', mark)
        self.lbl_sel.configure(text='已选 %d 项' % len(self.selected_ids))

    def _on_tree_toggle(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            self._toggle_iid(iid)

    def _select_visible(self):
        for iid in self.tree.get_children():
            it = self.item_by_iid.get(iid)
            if it:
                self.selected_ids.add(it['id'])
                self.tree.set(iid, 'sel', '☑')
        self.lbl_sel.configure(text='已选 %d 项' % len(self.selected_ids))

    def _clear_selection(self):
        self.selected_ids.clear(); self._apply_filter()

    def _restore_default(self):
        self.selected_ids = set(software_list.DEFAULT_SELECTED); self._apply_filter()

    # ---------------- 打印机驱动 ----------------
    def _apply_printer_filter(self):
        self.printer_tree.delete(*self.printer_tree.get_children())
        self.printer_by_iid.clear()
        for it in self.printer_items:
            iid = str(it['id'])
            self.printer_tree.insert('', 'end', iid=iid, values=(
                '☑' if iid in self.selected_printer_ids else '☐',
                it.get('name', ''), it.get('driver_type', ''), it.get('desc', '')))
            self.printer_by_iid[iid] = it
        self.lbl_printer_sel.configure(text='已选 %d 项' % len(self.selected_printer_ids))

    def _on_printer_toggle(self, event):
        iid = self.printer_tree.identify_row(event.y)
        if not iid:
            return
        if iid in self.selected_printer_ids:
            self.selected_printer_ids.discard(iid); mark = '☐'
        else:
            self.selected_printer_ids.add(iid); mark = '☑'
        self.printer_tree.set(iid, 'sel', mark)
        self.lbl_printer_sel.configure(text='已选 %d 项' % len(self.selected_printer_ids))

    def _printer_select_all(self, val):
        if val:
            self.selected_printer_ids = {it['id'] for it in self.printer_items}
        else:
            self.selected_printer_ids.clear()
        self._apply_printer_filter()

    def _printer_restore(self):
        self.selected_printer_ids = set(printer_drivers.defaults())
        self._apply_printer_filter()

    def _refresh_catalog(self):
        if self.refreshing or self.running:
            return
        self.refreshing = True
        self.btn_refresh.configure(state='disabled', text='刷新中...')
        self.lbl_cat_status.configure(text='正在从网络更新软件目录（约十几秒）...')
        threading.Thread(target=self._refresh_worker, daemon=True).start()

    def _refresh_worker(self):
        def log(m):
            self.q.put(('catalog_log', m, {}))
        try:
            sources = [k for k, v in self.src_vars.items() if v.get()]
            repo = None
            if 'apt' in sources:
                from repo import Repo
                repo = Repo(log=log)
                repo.load(cache_dir=data_dir())
            items = catalog.load_catalog(data_dir(), sources=sources,
                                         refresh=True, log=log, repo=repo)
            self.q.put(('catalog_done', items, {}))
        except Exception:
            self.q.put(('catalog_error', traceback.format_exc(), {}))

    # ---------------- 增量更新 ----------------
    def _load_last_project(self):
        proj = project.load_last(data_dir())
        self._set_project(proj, from_last=True)

    def _load_fresh_project(self, out_dir):
        """刚生成完包，优先读交付目录里的 project.json（缓存可能写在只读位置而失败）。"""
        return (project.load_from_dir(out_dir) if out_dir else None) or \
               project.load_last(data_dir())

    def _set_project(self, proj, from_last=False):
        self.proj = proj
        if not proj:
            self.lbl_project.configure(text='尚未找到基线项目：请先用第 1 页制作一次完整包，或点“载入项目”选择 project.json',
                                       foreground=MUTED)
            return
        self.lbl_project.configure(text=project.summary(proj), foreground=TEXT)
        if not self.var_upd_out.get():
            base = proj.get('out_dir') or os.path.expanduser('~')
            self.var_upd_out.set(base.rstrip('\\/') + '-更新-' + datetime.date.today().strftime('%Y%m%d'))
        if from_last:
            self._upd_log('已载入上次基线：%s' % proj.get('created', '?'))

    def _pick_project(self):
        p = filedialog.askopenfilename(title='选择 project.json（在交付包根目录）',
                                       filetypes=[('项目快照', 'project.json'),
                                                  ('JSON 文件', '*.json'), ('所有文件', '*.*')])
        if not p:
            return
        proj = project.load_file(p) or project.load_from_dir(os.path.dirname(p))
        if not proj:
            messagebox.showerror('错误', '这个文件不是有效的项目快照。')
            return
        self._set_project(proj)

    def _pick_project_dir(self):
        """网盘/U 盘场景：直接选整个交付目录，自动找里面的 project.json。"""
        d = filedialog.askdirectory(title='选择上次生成的交付目录（内含 project.json）')
        if not d:
            return
        proj = project.load_from_dir(d) or project.load_file(os.path.join(d, 'project.json'))
        if not proj:
            # 再试一层：用户可能选了交付目录的上级
            for sub in sorted(os.listdir(d)):
                p = os.path.join(d, sub)
                if os.path.isdir(p):
                    proj = project.load_from_dir(p)
                    if proj:
                        break
        if not proj:
            messagebox.showerror('错误', '该目录里没找到有效的 project.json。\n'
                                        '请确认选的是工具生成的完整交付目录，且 project.json 没被删掉。')
            return
        self._set_project(proj)

    def _pick_upd_out(self):
        p = filedialog.askdirectory(title='选择更新包输出目录')
        if p:
            self.var_upd_out.set(p)

    def _upd_log(self, msg):
        self.upd_log.configure(state='normal')
        self.upd_log.insert('end', str(msg) + '\n')
        self.upd_log.see('end')
        self.upd_log.configure(state='disabled')

    def _check_updates(self):
        if self.checking or not self.proj:
            messagebox.showinfo('提示', '请先制作一次完整包或载入项目快照。')
            return
        self.checking = True
        self.btn_check.configure(state='disabled', text='检查中...')
        self.lbl_upd_status.configure(text='正在对比星火目录与 deepin 源，请稍候...')
        threading.Thread(target=self._check_worker, daemon=True).start()

    def _check_worker(self):
        def log(m):
            self.q.put(('upd_log', m, {}))
        try:
            report, repo, base = updates.check_updates(self.proj, data_dir(), log=log)
            self.q.put(('upd_report', report, {'repo': repo, 'base': base}))
        except Exception:
            self.q.put(('upd_error', traceback.format_exc(), {}))

    def _show_report(self, report, repo, base):
        self.report = report
        self.repo_upd = repo
        self.base_upd = base
        self.sys_items.clear(); self.soft_upd_items.clear()
        self.sys_sel.clear(); self.soft_upd_sel.clear()
        for tree in (self.sys_tree, self.soft_tree):
            tree.delete(*tree.get_children())

        for u in report['system']:
            iid = u['id']
            self.sys_items[iid] = u
            self.sys_sel.add(iid)
            self.sys_tree.insert('', 'end', iid=iid, values=(
                '☑', u['name'], u.get('old_version', ''), u.get('new_version', '')))
        for u in report['software']:
            iid = u['id']
            self.soft_upd_items[iid] = u
            self.soft_upd_sel.add(iid)
            self.soft_tree.insert('', 'end', iid=iid, values=(
                '☑', u['name'], u.get('old_version', '') or '-',
                u.get('new_version', '') or '-', u.get('reason', '')))
        n = len(report['system']) + len(report['software'])
        self.lbl_upd_status.configure(text='检查完成：系统更新 %d 项，软件更新 %d 项' % (
            len(report['system']), len(report['software'])))
        if not n:
            self.lbl_upd_status.configure(text='暂无更新，已是最新状态。')
        for note in report.get('notes', []) + report.get('errors', []):
            self._upd_log('提示：' + note)

    def _toggle_upd(self, event, tree, items, sel):
        iid = tree.identify_row(event.y)
        if not iid or iid not in items:
            return
        if iid in sel:
            sel.discard(iid); mark = '☐'
        else:
            sel.add(iid); mark = '☑'
        tree.set(iid, 'sel', mark)

    def _download_updates(self):
        if not self.report or self.repo_upd is None:
            messagebox.showinfo('提示', '请先点“检查更新”。')
            return
        if not self.sys_sel and not self.soft_upd_sel:
            messagebox.showinfo('提示', '请至少勾选一项更新。')
            return
        out = self.var_upd_out.get().strip()
        if not out:
            messagebox.showerror('错误', '请选择更新包输出目录。')
            return
        if os.path.exists(out) and os.listdir(out):
            if not messagebox.askyesno('确认', '输出目录非空，继续可能覆盖同名文件。是否继续？'):
                return
        cfg = {
            'out_dir': out, 'workers': self.var_workers.get(),
            'system_ids': list(self.sys_sel), 'software_ids': list(self.soft_upd_sel),
            'soft_dir_name': self.var_soft_dir.get().strip() or 'offline-soft',
            'deps_dir_choice': self._deps_key(),
            'cache_dir': data_dir(),
            'tool_deb': resource_path('assets', 'deepin-offline-upgrade_1.4_all.deb'),
            'docs_src': resource_path('assets', 'docs'),
        }
        self.btn_dl_upd.configure(state='disabled', text='下载中...')
        threading.Thread(target=self._upd_download_worker,
                         args=(cfg,), daemon=True).start()

    def _upd_download_worker(self, cfg):
        try:
            r = updates.build_update_package(self.report, self.repo_upd, self.base_upd,
                                             self.proj, cfg,
                                             lambda level, msg, **kw: self.q.put(
                                                 ('upd_log' if level == 'log' else 'progress', msg, kw)))
            self.q.put(('upd_done', r['message'], r))
        except Exception:
            self.q.put(('upd_error', traceback.format_exc(), {}))

    # ---------------- 通用 ----------------
    def _on_mode(self):
        if self.var_mode.get() == 'diff':
            self.old_frame.pack(fill='x', pady=(2, 8), before=self.out_frame)
        else:
            self.old_frame.pack_forget()

    def _pick_new(self):
        p = filedialog.askopenfilename(title='选择 ISO', filetypes=[('ISO 镜像', '*.iso'), ('所有文件', '*.*')])
        if p:
            self.var_new_iso.set(p)
            if not self.var_out.get():
                self.var_out.set(os.path.join(os.path.dirname(p),
                                  os.path.splitext(os.path.basename(p))[0] + '-离线升级包'))

    def _pick_old(self):
        p = filedialog.askopenfilename(title='选择旧 ISO 或清单',
                                       filetypes=[('ISO/清单', '*.iso *.txt *.packages'), ('所有文件', '*.*')])
        if p:
            self.var_old_iso.set(p)

    def _pick_out(self):
        p = filedialog.askdirectory(title='选择输出目录')
        if p:
            self.var_out.set(p)

    def _open_out(self):
        p = self.var_out.get()
        if p and os.path.isdir(p):
            os.startfile(p)

    def _log(self, msg):
        self.log.configure(state='normal')
        self.log.insert('end', str(msg) + '\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def _deps_key(self):
        return {'软件目录下的 deps/（推荐）': 'subdir',
                '独立目录 soft-deps/': 'sibling',
                '并入 updata/ 升级目录': 'updata'}.get(self.var_deps.get(), 'subdir')

    def _start(self):
        if self.running:
            return
        new_iso = self.var_new_iso.get().strip()
        out = self.var_out.get().strip()
        if not new_iso or not os.path.isfile(new_iso):
            messagebox.showerror('错误', '请选择有效的新版本 ISO。')
            return
        if not out:
            messagebox.showerror('错误', '请选择输出目录。')
            return
        mode = self.var_mode.get()
        old = self.var_old_iso.get().strip()
        if mode == 'diff' and (not old or not os.path.isfile(old)):
            messagebox.showerror('错误', '“两版本对比”需选择旧 ISO 或清单。')
            return
        if os.path.exists(out) and os.listdir(out):
            if not messagebox.askyesno('确认', '输出目录非空，继续可能覆盖同名文件。是否继续？'):
                return
        os.makedirs(out, exist_ok=True)
        soft_name = self.var_soft_dir.get().strip().strip('\\/') or 'offline-soft'
        selected = [it for it in self.catalog_items if it['id'] in self.selected_ids]
        selected_printers = [it for it in self.printer_items
                             if it['id'] in self.selected_printer_ids]

        cfg = {
            'new_iso': new_iso, 'mode': mode, 'out_dir': out,
            'workers': self.var_workers.get(),
            'old_iso': old if mode == 'diff' and old.lower().endswith('.iso') else None,
            'old_manifest': old if mode == 'diff' and not old.lower().endswith('.iso') else None,
            'cache_dir': data_dir(),
            'tool_deb': resource_path('assets', 'deepin-offline-upgrade_1.4_all.deb'),
            'docs_src': resource_path('assets', 'docs'),
            'software_items': selected,
            'printer_items': selected_printers,
            'printer_dir_name': self.var_printer_dir.get().strip().strip('\\/') or 'printer-drivers',
            'soft_dir_name': soft_name,
            'deps_dir_choice': self._deps_key(),
        }
        self.running = True
        self.btn_start.configure(state='disabled', text='制作中...')
        self.btn_refresh.configure(state='disabled')
        self.btn_open.configure(state='disabled')
        self.log.configure(state='normal'); self.log.delete('1.0', 'end'); self.log.configure(state='disabled')
        self.pbar['value'] = 0
        threading.Thread(target=self._worker, args=(cfg,), daemon=True).start()

    def _worker(self, cfg):
        try:
            from pipeline import run_pipeline
            run_pipeline(cfg, lambda level, msg, **kw: self.q.put((level, msg, kw)))
        except Exception:
            self.q.put(('error', traceback.format_exc(), {}))
        finally:
            self.q.put(('finished', '', {}))

    def _poll(self):
        try:
            while True:
                level, msg, kw = self.q.get_nowait()
                if level in ('log', 'catalog_log'):
                    self._log(msg)
                elif level == 'upd_log':
                    self._upd_log(msg)
                elif level == 'progress':
                    done, total = kw.get('done', 0), kw.get('total', 0)
                    if total:
                        self.pbar['maximum'] = total; self.pbar['value'] = done
                        self.lbl_prog.configure(text='%d / %d  %s' % (done, total, str(kw.get('name', ''))[:40]))
                elif level == 'catalog_done':
                    self.catalog_items = msg
                    self.printer_items = printer_drivers.all_items(data_dir())
                    self.refreshing = False
                    self.btn_refresh.configure(state='normal', text='刷新目录')
                    self._apply_filter()
                    self._apply_printer_filter()
                    self.lbl_cat_status.configure(text='目录已更新：%d 项' % len(msg))
                elif level == 'catalog_error':
                    self.refreshing = False
                    self.btn_refresh.configure(state='normal', text='刷新目录')
                    self.lbl_cat_status.configure(text='刷新失败，仍可用缓存目录')
                    self._log('[目录刷新错误]\n' + msg)
                elif level == 'upd_report':
                    self.checking = False
                    self.btn_check.configure(state='normal', text='检查更新（联网）')
                    self._show_report(msg, kw.get('repo'), kw.get('base'))
                elif level == 'upd_done':
                    self.btn_dl_upd.configure(state='normal', text='下载更新包')
                    self.lbl_upd_status.configure(text=msg)
                    # 生成后基线已前移，立刻刷新界面；否则不重开工具再检查会重复报同一批更新
                    self._set_project(self._load_fresh_project(kw.get('out_dir', '')), from_last=True)
                    messagebox.showinfo('更新包已生成', msg + '\n\n目录：' + kw.get('out_dir', '') +
                                        '\n\n基线已更新，下次检查不会再报这一批；请保留目录里的 project.json。')
                elif level == 'upd_error':
                    self.checking = False
                    self.btn_check.configure(state='normal', text='检查更新（联网）')
                    self.btn_dl_upd.configure(state='normal', text='下载更新包')
                    self._upd_log('[错误]\n' + msg)
                    messagebox.showerror('出错', msg[:600])
                elif level == 'done':
                    self.lbl_prog.configure(text=msg)
                    self.btn_open.configure(state='normal')
                    self._set_project(self._load_fresh_project(kw.get('out_dir', '')), from_last=True)
                    messagebox.showinfo('完成', msg + '\n\n目录里的 project.json 是下次做增量的基线，请保留。')
                elif level == 'error':
                    self._log('[错误]\n' + msg)
                    messagebox.showerror('出错', msg[:600])
                elif level == 'finished':
                    self.running = False
                    self.btn_start.configure(state='normal', text='开始制作')
                    self.btn_refresh.configure(state='normal', text='刷新目录')
        except queue.Empty:
            pass
        self.after(120, self._poll)


def main():
    App().mainloop()


if __name__ == '__main__':
    main()
