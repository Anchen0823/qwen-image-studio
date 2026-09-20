"""Native desktop client for the shared Qwen Image queue."""
import json
import os
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageOps
from engine import ROOT, Store, Runner, split_prompts

BG, PANEL, FIELD, BORDER = '#101018', '#191923', '#232330', '#30303e'
TEXT, MUTED, ACCENT, SOFT = '#f0eef8', '#9693aa', '#b5a2ff', '#302b46'
STATES = dict(queued='等待中', running='生成中', completed='已完成', failed='失败',
              cancelled='已取消', interrupted='已中断')


class Studio(tk.Tk):
    def __init__(self, store=None, autorun=True):
        super().__init__()
        self.store = store or Store()
        self.runner = Runner(self.store)
        self.autorun, self.closing = autorun, False
        self.signature = self.last_completed = self.source = self.current = None
        self.edit = ''
        self.title('Qwen Image Studio · 创作工作台')
        self.geometry('1440x940')
        self.minsize(1180, 820)
        self.configure(bg=BG)
        if (ROOT / 'studio.ico').exists():
            self.iconbitmap(str(ROOT / 'studio.ico'))
        self.option_add('*Font', ('Microsoft YaHei UI', 10))
        self.theme()
        self.build()
        self.load_settings()
        self.refresh_history()
        if self.history_paths:
            self.show_image(self.history_paths[0])
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(200, self.poll)

    def theme(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', background=PANEL, foreground=TEXT, bordercolor=BORDER,
                        lightcolor=BORDER, darkcolor=BORDER, font=('Microsoft YaHei UI', 10))
        style.configure('TProgressbar', troughcolor=FIELD, background=ACCENT, borderwidth=0)
        style.configure('Vertical.TScrollbar', background=FIELD, troughcolor=PANEL,
                        arrowcolor=MUTED, borderwidth=0, arrowsize=12)
        style.map('Vertical.TScrollbar', background=[('active', SOFT)])
        style.configure('TNotebook', background=BG, borderwidth=0)
        style.configure('TNotebook.Tab', padding=(18, 9), background=BG, foreground=MUTED)
        style.map('TNotebook.Tab', background=[('selected', PANEL)], foreground=[('selected', ACCENT)])
        style.configure('Treeview', background=PANEL, fieldbackground=PANEL,
                        foreground=TEXT, rowheight=34, borderwidth=0)
        style.configure('Treeview.Heading', background=FIELD, foreground=MUTED, relief='flat', padding=7)
        style.map('Treeview', background=[('selected', SOFT)], foreground=[('selected', TEXT)])

    def label(self, parent, text='', size=10, color=TEXT, **kw):
        return tk.Label(parent, text=text, bg=parent['bg'], fg=color,
                        font=('Microsoft YaHei UI', size), **kw)

    def button(self, parent, text, command, primary=False, small=False):
        return tk.Button(parent, text=text, command=command, bg=ACCENT if primary else FIELD,
                         fg=BG if primary else TEXT, activebackground='#c8baff' if primary else SOFT,
                         activeforeground=BG if primary else TEXT, relief='flat', bd=0,
                         padx=12 if small else 18, pady=6 if small else 10,
                         cursor='hand2', disabledforeground=MUTED)

    def text_box(self, parent, height=8):
        frame = tk.Frame(parent, bg=FIELD, highlightbackground=BORDER, highlightthickness=1)
        text = tk.Text(frame, width=1, height=height, wrap='char', bg=FIELD, fg=TEXT,
                       insertbackground=ACCENT, selectbackground=SOFT, relief='flat', bd=0,
                       padx=14, pady=12, spacing1=3, spacing3=4, undo=True)
        scroll = ttk.Scrollbar(frame, orient='vertical', command=text.yview)
        scroll.pack(side='right', fill='y')
        text.pack(side='left', fill='both', expand=True)
        text.configure(yscrollcommand=scroll.set)
        return frame, text

    def build(self):
        header = tk.Frame(self, bg=BG, padx=26, pady=18)
        header.pack(fill='x')
        self.label(header, 'Q', 28, ACCENT).pack(side='left', padx=(0, 14))
        brand = tk.Frame(header, bg=BG)
        brand.pack(side='left')
        self.label(brand, 'Qwen Image Studio', 19).pack(anchor='w')
        self.label(brand, '把灵感写下来，让画面慢慢发生。', 9, MUTED).pack(anchor='w', pady=(3, 0))
        self.label(header, '●  本地创作    /    QWEN 2.1', 10, ACCENT, padx=16, pady=8).pack(side='right')
        content = tk.Frame(self, bg=BG)
        content.pack(fill='both', expand=True, padx=24)
        content.grid_columnconfigure(1, weight=1)
        content.grid_rowconfigure(0, weight=1)
        left = tk.Frame(content, bg=PANEL, padx=20, pady=18, width=410)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 18))
        left.grid_propagate(False)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(3, weight=1, minsize=150)
        title = tk.Frame(left, bg=PANEL)
        title.grid(row=0, column=0, sticky='ew')
        self.label(title, '创作描述', 15).pack(side='left')
        self.counter = self.label(title, '0 字 · 0 个任务', 9, MUTED)
        self.counter.pack(side='right')
        self.label(left, '自动换行 · Enter 换行 · Ctrl+Enter 入队', 9, MUTED).grid(row=1, column=0, sticky='w', pady=(6, 10))
        modes = tk.Frame(left, bg=PANEL)
        modes.grid(row=2, column=0, sticky='ew', pady=(0, 10))
        self.batch_var = tk.BooleanVar(value=False)
        self.single_button = self.button(modes, '单个任务', lambda: self.set_mode(False), small=True)
        self.single_button.pack(side='left', fill='x', expand=True, padx=(0, 4))
        self.batch_button = self.button(modes, '批量任务', lambda: self.set_mode(True), small=True)
        self.batch_button.pack(side='left', fill='x', expand=True, padx=(4, 0))
        frame, self.prompt = self.text_box(left, height=8)
        frame.grid(row=3, column=0, sticky='nsew')
        self.prompt.bind('<<Modified>>', self.prompt_changed)
        self.prompt.bind('<Control-Return>', lambda e: (self.submit(), 'break')[1])
        self.hint = self.label(left, '每个任务可使用多行描述。', 9, MUTED, anchor='w')
        self.hint.grid(row=4, column=0, sticky='ew', pady=(7, 4))
        settings_frame = tk.Frame(left, bg=PANEL)
        settings_frame.grid(row=5, column=0, rowspan=6, sticky='ew', pady=(0, 12))
        settings_canvas = tk.Canvas(settings_frame, bg=PANEL, height=255, highlightthickness=0)
        settings_scroll = ttk.Scrollbar(settings_frame, orient='vertical', command=settings_canvas.yview)
        settings_scroll.pack(side='right', fill='y')
        settings_canvas.pack(side='left', fill='x', expand=True)
        settings_canvas.configure(yscrollcommand=settings_scroll.set)
        self.bind('<Configure>', lambda e: settings_canvas.configure(height=max(240,min(365,e.height-570)))
                  if e.widget is self else None)
        options = tk.Frame(settings_canvas, bg=PANEL)
        options.grid_columnconfigure(0, weight=1)
        window = settings_canvas.create_window((0,0), window=options, anchor='nw')
        options.bind('<Configure>', lambda e: settings_canvas.configure(scrollregion=settings_canvas.bbox('all')))
        settings_canvas.bind('<Configure>', lambda e: settings_canvas.itemconfigure(window, width=e.width))
        def scroll_options(event):
            if str(event.widget).startswith(str(settings_frame)):
                settings_canvas.yview_scroll(-int(event.delta/120), 'units')
        self.bind('<MouseWheel>', scroll_options)
        quick = tk.Frame(options, bg=PANEL)
        quick.grid(row=0, column=0, sticky='ew', pady=(0, 12))
        for name, prompt in [('摄影', '雨后黄昏的江南街巷，暖色灯光倒映在青石板上。\n电影摄影，自然光，细腻质感。'),
                              ('海报', '一张极简咖啡海报，奶油色背景，陶瓷咖啡杯。\n优雅排版，标题文字“慢一点，也很好”。')]:
            self.button(quick, name, lambda p=prompt: self.set_prompt(p), small=True).pack(side='left', padx=(0, 6))
        self.button(quick, '导入文本', self.import_text, small=True).pack(side='right')
        ref = tk.Frame(options, bg=PANEL)
        ref.grid(row=1, column=0, sticky='ew', pady=(0, 8))
        self.label(ref, '参考图', 11).pack(side='left')
        self.button(ref, '添加', self.pick_reference, small=True).pack(side='right')
        self.button(ref, '移除', self.clear_reference, small=True).pack(side='right', padx=5)
        self.reference_label = self.label(options, '未添加 · 文生图模式', 9, MUTED, wraplength=330, anchor='w')
        self.reference_label.grid(row=2, column=0, sticky='ew', pady=(0, 10))
        params = tk.Frame(options, bg=PANEL)
        params.grid(row=3, column=0, sticky='ew')
        for i in range(3):
            params.grid_columnconfigure(i, weight=1, uniform='params')
        self.width_var, self.height_var = tk.StringVar(value='512'), tk.StringVar(value='512')
        self.steps_var, self.seed_var = tk.StringVar(value='40'), tk.StringVar(value='-1')
        self.copies_var = tk.StringVar(value='1')
        for i, (label, var) in enumerate([('宽度', self.width_var), ('高度', self.height_var), ('步数', self.steps_var),
                                         ('随机种子', self.seed_var), ('每任务份数', self.copies_var)]):
            cell = tk.Frame(params, bg=PANEL)
            cell.grid(row=i//3, column=i%3, sticky='ew', padx=(0, 8), pady=(0, 10))
            self.label(cell, label, 9, MUTED).pack(anchor='w', pady=(0, 4))
            tk.Entry(cell, width=1, textvariable=var, bg=FIELD, fg=TEXT, insertbackground=ACCENT,
                     relief='flat', bd=0).pack(fill='x', ipady=8)
        ratio = tk.Frame(options, bg=PANEL)
        ratio.grid(row=4, column=0, sticky='ew')
        for name, dims in [('1:1 方形', (512,512)), ('3:4 竖图', (576,768)), ('16:9 横图', (768,432))]:
            self.button(ratio, name, lambda d=dims: self.set_size(*d), small=True).pack(side='left', padx=(0,5))
        self.label(options, '-1 随机种子 · 8GB 显存建议 512×512', 9, MUTED).grid(row=5, column=0, sticky='w', pady=(10, 12))
        self.generate_button = self.button(left, '＋  加入队列并生成', self.submit, primary=True)
        self.generate_button.grid(row=11, column=0, sticky='ew')
        self.label(left, '自动依次运行 · 任务保存在本机', 9, MUTED).grid(row=12, column=0, pady=(8,0))
        self.set_mode(False)

        right = tk.Frame(content, bg=BG)
        right.grid(row=0, column=1, sticky='nsew')
        toolbar = tk.Frame(right, bg=BG)
        toolbar.pack(fill='x', pady=(0, 10))
        self.label(toolbar, '作品预览', 15).pack(side='left')
        self.image_info = self.label(toolbar, '等待你的第一张作品', 9, MUTED)
        self.image_info.pack(side='left', padx=14)
        self.button(toolbar, '另存为', self.export, small=True).pack(side='right')
        self.button(toolbar, '作品目录', lambda: os.startfile(self.store.outputs), small=True).pack(side='right', padx=8)
        self.canvas = tk.Canvas(right, bg=PANEL, highlightthickness=1, highlightbackground=BORDER, height=280)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda e: self.draw())
        status = tk.Frame(right, bg=BG)
        status.pack(fill='x', pady=(10, 6))
        self.status = self.label(status, '就绪', 10, MUTED, anchor='w')
        self.status.pack(side='left', fill='x', expand=True)
        self.queue_count = self.label(status, '0 个等待', 9, ACCENT)
        self.queue_count.pack(side='right')
        self.progress = ttk.Progressbar(right, mode='determinate')
        self.progress.pack(fill='x', pady=(0, 14))
        self.tabs = ttk.Notebook(right, height=205)
        self.tabs.pack(fill='x')
        queue_page, gallery = tk.Frame(self.tabs, bg=PANEL), tk.Frame(self.tabs, bg=PANEL)
        self.tabs.add(queue_page, text='任务队列')
        self.tabs.add(gallery, text='作品历史')
        commands = tk.Frame(queue_page, bg=PANEL, padx=8, pady=6)
        commands.pack(fill='x')
        self.pause_button = self.button(commands, '暂停队列', self.toggle_pause, small=True)
        self.pause_button.pack(side='left')
        self.button(commands, '取消选中', self.cancel_selected, small=True).pack(side='left', padx=5)
        self.button(commands, '重试', self.retry_selected, small=True).pack(side='left')
        self.button(commands, '任务详情', self.details, small=True).pack(side='right')
        self.jobs = self.table(queue_page, ('state','prompt','size','progress'),
                               [('状态',75),('提示词',330),('尺寸',90),('进度',70)])
        self.jobs.bind('<Double-1>', lambda e: self.details())
        self.jobs.bind('<<TreeviewSelect>>', self.select_job)
        for state, color in [('completed','#9bd6b0'),('failed','#f39eab'),('running',ACCENT),('cancelled',MUTED)]:
            self.jobs.tag_configure(state, foreground=color)
        commands = tk.Frame(gallery, bg=PANEL, padx=8, pady=6)
        commands.pack(fill='x')
        self.label(commands, '选择作品，继续创作', 9, MUTED).pack(side='left')
        self.button(commands, '复用参数', self.reuse, small=True).pack(side='right')
        self.button(commands, '刷新', self.refresh_history, small=True).pack(side='right', padx=6)
        self.history = self.table(gallery, ('name','prompt'), [('作品',205),('提示词',350)])
        self.history.bind('<<TreeviewSelect>>', self.select_history)
        self.toast = self.label(self, '本地模型  /  离线推理  /  文件保存在 outputs', 9, MUTED, anchor='w')
        self.toast.pack(fill='x', padx=26, pady=12)

    def table(self, parent, columns, headings):
        frame = tk.Frame(parent, bg=PANEL)
        frame.pack(fill='both', expand=True)
        tree = ttk.Treeview(frame, columns=columns, show='headings', selectmode='browse', height=3)
        scroll = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        scroll.pack(side='right', fill='y')
        tree.pack(side='left', fill='both', expand=True)
        tree.configure(yscrollcommand=scroll.set)
        for key, (name, width) in zip(columns, headings):
            tree.heading(key, text=name, anchor='w')
            tree.column(key, width=width, minwidth=50, stretch=key=='prompt')
        return tree

    def set_mode(self, batch):
        self.batch_var.set(batch)
        self.single_button.configure(bg=FIELD if batch else SOFT, fg=MUTED if batch else ACCENT)
        self.batch_button.configure(bg=SOFT if batch else FIELD, fg=ACCENT if batch else MUTED)
        self.hint.configure(text='用独立一行 --- 分隔任务；任务内可换行。' if batch else '每个任务可使用多行描述。')
        self.prompt_changed()

    def prompt_changed(self, event=None):
        text = self.prompt.get('1.0','end-1c')
        count = len(split_prompts(text)) if self.batch_var.get() else int(bool(text.strip()))
        self.counter.configure(text=f'{len(text)} 字 · {count} 个任务')
        if self.prompt.edit_modified():
            self.prompt.edit_modified(False)

    def set_prompt(self, text):
        self.prompt.delete('1.0','end')
        self.prompt.insert('1.0',text)
        self.prompt_changed()

    def set_size(self, w, h):
        self.width_var.set(w)
        self.height_var.set(h)

    def import_text(self):
        path = filedialog.askopenfilename(filetypes=[('UTF-8 文本','*.txt *.md')])
        if path:
            try:
                text = Path(path).read_text(encoding='utf-8-sig')
                self.set_prompt(text)
                self.set_mode(len(split_prompts(text)) > 1)
            except Exception as error:
                messagebox.showerror('导入失败',str(error))

    def pick_reference(self):
        path = filedialog.askopenfilename(filetypes=[('图片','*.png *.jpg *.jpeg *.webp *.bmp')])
        if path:
            try:
                with Image.open(path) as im:
                    im.verify()
                self.edit = path
                self.reference_label.configure(text='图片编辑 · '+Path(path).name,fg=ACCENT)
            except Exception as error:
                messagebox.showerror('图片无法读取',str(error))

    def clear_reference(self):
        self.edit = ''
        self.reference_label.configure(text='未添加 · 文生图模式',fg=MUTED)

    def submit(self):
        try:
            text = self.prompt.get('1.0','end-1c')
            prompts = split_prompts(text) if self.batch_var.get() else [text]
            copies = int(self.copies_var.get())
            if not 1 <= copies <= 20:
                raise ValueError('每个任务份数需为 1–20。')
            specs = [dict(prompt=p,width=self.width_var.get(),height=self.height_var.get(),
                          steps=self.steps_var.get(),seed=self.seed_var.get(),edit=self.edit)
                     for p in prompts for _ in range(copies)]
            ids = self.store.add(specs)
            self.save_settings()
            self.tabs.select(0)
            self.toast.configure(text=f'已加入 {len(ids)} 个任务。'+('队列已暂停，点击“继续队列”开始。' if self.store.paused else '将按顺序自动生成。'),fg=ACCENT)
            self.refresh_jobs()
            if self.autorun:
                self.runner.start()
            return ids
        except Exception as error:
            messagebox.showerror('任务未添加',str(error))
            return []

    def toggle_pause(self):
        self.store.pause(not self.store.paused)
        self.toast.configure(text='已暂停：当前任务完成后停止，等待任务会保留。' if self.store.paused else '队列已继续。',fg=MUTED)
        self.refresh_jobs()

    def selected(self):
        selection = self.jobs.selection()
        return self.store.get(selection[0]) if selection else None

    def cancel_selected(self):
        job = self.selected()
        if job:
            self.store.cancel(job['id'])
            self.refresh_jobs()

    def retry_selected(self):
        job = self.selected()
        if job:
            try:
                self.store.retry(job['id'])
                self.refresh_jobs()
            except ValueError as error:
                self.toast.configure(text=str(error),fg=MUTED)

    def select_job(self,event=None):
        job = self.selected()
        if job and job['status']=='completed':
            self.show_image(Path(job['spec']['output']))

    def details(self):
        job = self.selected()
        if not job:
            return
        dialog = tk.Toplevel(self)
        dialog.title('任务详情 · '+job['id'])
        dialog.geometry('680x560')
        dialog.configure(bg=PANEL)
        self.label(dialog,STATES[job['status']]+'  /  '+job['id'],12).pack(anchor='w',padx=20,pady=18)
        frame,text = self.text_box(dialog,height=12)
        frame.pack(fill='both',expand=True,padx=20)
        spec = job['spec']
        text.insert('1.0',spec['prompt']+'\n\n'+f"尺寸 {spec['width']} × {spec['height']}  ·  步数 {spec['steps']}  ·  种子 {spec['seed']}\n参考图：{spec['edit'] or '无'}\n输出：{spec['output']}\n"+(f"\n错误：{job['error']}" if job['error'] else ''))
        text.configure(state='disabled')
        row = tk.Frame(dialog,bg=PANEL)
        row.pack(fill='x',padx=20,pady=15)
        self.button(row,'复用为新任务',lambda:(self.apply_spec(spec),dialog.destroy()),True).pack(side='left')
        self.button(row,'打开日志',lambda:self.open_log(spec)).pack(side='right')

    def open_log(self,spec):
        path = Path(spec['output']).with_suffix('.log')
        if path.exists():
            os.startfile(path)
        else:
            messagebox.showinfo('日志','该任务尚未开始，暂无日志。')

    def refresh_jobs(self):
        jobs = self.store.list()
        signature = [(j['id'],j['status'],j['progress'],j['phase'],j['cancel']) for j in jobs]
        if signature != self.signature:
            selected = self.jobs.selection()
            self.jobs.delete(*self.jobs.get_children())
            ordered = [j for j in jobs if j['status']=='running'] + [j for j in jobs if j['status']=='queued']
            ordered += [j for j in reversed(jobs) if j['status'] not in ('running','queued')]
            for job in ordered:
                spec = job['spec']
                self.jobs.insert('','end',iid=job['id'],tags=(job['status'],),values=(
                    '取消中' if job['cancel'] and job['status']=='running' else STATES[job['status']],
                    spec['prompt'].replace('\n',' ')[:100],f"{spec['width']}×{spec['height']}",f"{job['progress']}%"))
            if selected and self.jobs.exists(selected[0]):
                self.jobs.selection_set(selected)
            self.signature = signature
        running = next((j for j in jobs if j['status']=='running'),None)
        pending = sum(j['status']=='queued' for j in jobs)
        self.queue_count.configure(text=f'{pending} 个等待 · {sum(j["status"]=="completed" for j in jobs)} 个完成')
        paused = self.store.paused
        self.pause_button.configure(text='继续队列' if paused else '暂停队列')
        if running:
            seconds = int(time.time()-running['started'])
            self.status.configure(text=f"{running['phase']} · {seconds//60:02}:{seconds%60:02}"+(' · 完成本张后暂停' if paused else ''))
            self.progress.configure(value=running['progress'])
        else:
            self.status.configure(text='队列已暂停 · 等待任务已保存' if paused else ('等待开始' if pending else '队列空闲 · 可以继续添加灵感'))
            self.progress.configure(value=0)
        completed = [j for j in jobs if j['status']=='completed']
        latest = max(completed,key=lambda j:j['finished'] or 0) if completed else None
        if latest and latest['id'] != self.last_completed:
            self.last_completed = latest['id']
            self.refresh_history()
            self.show_image(Path(latest['spec']['output']))
        return jobs

    def poll(self):
        if self.closing:
            if self.runner.thread and self.runner.thread.is_alive():
                self.after(150,self.poll)
            else:
                self.destroy()
            return
        try:
            jobs = self.refresh_jobs()
            if self.autorun and any(j['status'] in ('queued','running') for j in jobs):
                self.runner.start()
            if self.runner.last_error:
                self.toast.configure(text='队列错误：'+self.runner.last_error,fg='#f39eab')
        except Exception as error:
            self.toast.configure(text='读取队列失败：'+str(error),fg='#f39eab')
        self.after(500,self.poll)

    def show_image(self,path):
        if self.current == path:
            return
        try:
            with Image.open(path) as im:
                self.source = ImageOps.exif_transpose(im).convert('RGB')
            self.current = path
            self.image_info.configure(text=f'{self.source.width} × {self.source.height}  ·  PNG')
            self.draw()
        except (OSError,ValueError) as error:
            self.toast.configure(text='无法读取预览：'+str(error),fg=MUTED)

    def draw(self):
        self.canvas.delete('all')
        w,h = self.canvas.winfo_width(),self.canvas.winfo_height()
        if self.source:
            preview = ImageOps.contain(self.source,(max(1,w-32),max(1,h-32)),Image.Resampling.LANCZOS)
            self.photo = ImageTk.PhotoImage(preview)
            self.canvas.create_image(w/2,h/2,image=self.photo)
        else:
            self.canvas.create_oval(w/2-48,h/2-90,w/2+48,h/2+6,outline=SOFT,width=2)
            self.canvas.create_text(w/2,h/2-42,text='✦',fill=ACCENT,font=('Segoe UI Symbol',40))
            self.canvas.create_text(w/2,h/2+42,text='下一张作品，从一个想法开始',fill=TEXT,font=('Microsoft YaHei UI',18))
            self.canvas.create_text(w/2,h/2+79,text='写下描述，或者一次加入一组灵感',fill=MUTED,font=('Microsoft YaHei UI',10))

    def refresh_history(self):
        self.history_paths = sorted(self.store.outputs.glob('*.png'),reverse=True)
        self.history.delete(*self.history.get_children())
        for i,path in enumerate(self.history_paths):
            try:
                spec = json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
                prompt = spec['prompt'].replace('\n',' ')[:100]
            except (OSError,ValueError,KeyError):
                prompt = ''
            self.history.insert('','end',iid=str(i),values=(path.stem,prompt))

    def select_history(self,event=None):
        selected = self.history.selection()
        if selected:
            self.show_image(self.history_paths[int(selected[0])])

    def apply_spec(self,spec):
        self.set_mode(False)
        self.set_prompt(spec['prompt'])
        self.set_size(spec['width'],spec['height'])
        self.steps_var.set(spec['steps'])
        self.seed_var.set(spec['seed'])
        self.copies_var.set('1')
        self.edit = spec.get('edit','')
        self.reference_label.configure(text='图片编辑 · '+Path(self.edit).name if self.edit else '未添加 · 文生图模式')

    def reuse(self):
        if self.current:
            try:
                self.apply_spec(json.loads(self.current.with_suffix('.json').read_text(encoding='utf-8')))
            except Exception as error:
                messagebox.showerror('复用失败',str(error))

    def export(self):
        if self.source is None:
            self.toast.configure(text='先生成或选择一张作品。',fg=MUTED)
            return
        target = filedialog.asksaveasfilename(defaultextension='.png',initialfile=self.current.name,filetypes=[('PNG 图片','*.png')])
        if target:
            try:
                self.source.save(target,format='PNG')
            except Exception as error:
                messagebox.showerror('保存失败',str(error))

    def save_settings(self):
        settings = dict(prompt=self.prompt.get('1.0','end-1c'),width=self.width_var.get(),height=self.height_var.get(),
                        steps=self.steps_var.get(),seed=self.seed_var.get(),batch=self.batch_var.get(),copies=self.copies_var.get())
        (self.store.root/'settings.json').write_text(json.dumps(settings,ensure_ascii=False,indent=2),encoding='utf-8')

    def load_settings(self):
        try:
            values = json.loads((self.store.root/'settings.json').read_text(encoding='utf-8'))
            self.set_prompt(values['prompt'])
            self.set_size(values['width'],values['height'])
            self.steps_var.set(values['steps'])
            self.seed_var.set(values['seed'])
            self.copies_var.set(values.get('copies','1'))
            self.set_mode(values.get('batch',False))
        except (OSError,ValueError,KeyError):
            pass

    def close(self):
        if self.runner.thread and self.runner.thread.is_alive():
            if not messagebox.askyesno('退出工作台','当前生成会中断，排队任务会保存，重新打开后继续。确定退出？'):
                return
        self.save_settings()
        self.closing = True
        self.runner.stop()
        self.toast.configure(text='正在停止推理并保存队列…',fg=MUTED)


if __name__=='__main__':
    Studio().mainloop()
