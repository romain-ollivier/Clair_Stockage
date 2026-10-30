from __future__ import annotations
import argparse
import json
import os
import queue
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog,messagebox,ttk

from . import __version__
from .ai import Cancelled,LocalAdvisor,model_context
from .browse import Entry,Navigation,folders,list_directory,sorted_entries
from .layout import band,size_text,treemap,share_text
from .report import describe,factual_report
from .scanner import local_drives,scan
from .widgets import ExplorerList,clipped

BG,INK,MUTED,ACCENT='#ffffff','#1d2939','#667085','#2477c5'


class StorageApp:
    def __init__(self,root,demo=False):
        self.root,self.demo=root,demo
        self.result=None
        self.nav=Navigation()
        self.events=queue.Queue()
        self.stop_scan=threading.Event()
        self.stop_listing=threading.Event()
        self.advisor=LocalAdvisor()
        self.closed=self.scanning=self.ai_busy=False
        self.entries=[]
        self.sort_by,self.descending='size',True
        self.list_generation=0
        self.ai_window=None
        self.last_snapshot=self.last_ai=None
        self.map_boxes=[]
        self.pending_filter=None
        root.title('Clair Stockage')
        root.geometry('1240x800');root.minsize(980,640)
        root.configure(bg=BG);root.protocol('WM_DELETE_WINDOW',self.close)
        self.styles();self.build()
        root.after(100,self.drain)
        if demo:
            from .demo import example
            self.install_result(example())

    @property
    def current(self):return self.nav.current

    def styles(self):
        s=ttk.Style(self.root);s.theme_use('clam')
        self.root.option_add('*Font',('Segoe UI',10))
        s.configure('TFrame',background=BG)
        s.configure('TLabel',background=BG,foreground=INK)
        s.configure('Muted.TLabel',foreground=MUTED,font=('Segoe UI',9))
        s.configure('TButton',padding=(12,8),background='#f1f4f8',foreground=INK,borderwidth=0)
        s.map('TButton',background=[('active','#e4edf7')])
        s.configure('Accent.TButton',background=ACCENT,foreground='white')
        s.map('Accent.TButton',background=[('active','#1d64a5')])
        s.configure('TEntry',padding=7,fieldbackground='#f8fafc',bordercolor='#e3e8ef')
        s.configure('Side.TFrame',background='#f8fafc')

    def build(self):
        outer=ttk.Frame(self.root);outer.pack(fill='both',expand=True)
        side=tk.Frame(outer,bg='#f8fafc',width=190);side.pack(side='left',fill='y');side.pack_propagate(False)
        tk.Label(side,text='Clair',font=('Segoe UI',23,'bold'),bg='#f8fafc',fg=INK).pack(anchor='w',padx=22,pady=(25,0))
        tk.Label(side,text='STOCKAGE',font=('Segoe UI',9,'bold'),bg='#f8fafc',fg=MUTED).pack(anchor='w',padx=24,pady=(2,25))
        def side_button(label,command):
            tk.Button(side,text=label,command=command,anchor='w',bg='#f8fafc',fg=INK,relief='flat',activebackground='#e9eff7',bd=0,padx=22,pady=12).pack(fill='x')
        side_button('▣   Ce PC',lambda:self.navigate(0))
        self.drives=local_drives()
        for path in self.drives:side_button('▱   '+path,lambda p=path:self.open_place(p))
        ttk.Separator(side).pack(fill='x',padx=18,pady=15)
        side_button('⌂   Dossier personnel',lambda:self.open_place(str(Path.home())))
        side_button('＋   Choisir un dossier',self.pick_folder)
        side_button('↻   Tous les disques',lambda:self.begin_scan(self.drives))
        side_button('ⓘ   Accès et couverture',self.show_access)
        tk.Label(side,text='Lecture seule\nAucune suppression',bg='#f8fafc',fg=MUTED,justify='left',font=('Segoe UI',9)).pack(side='bottom',anchor='w',padx=22,pady=22)
        main=ttk.Frame(outer,padding=(22,18));main.pack(fill='both',expand=True)
        tools=ttk.Frame(main);tools.pack(fill='x')
        self.back_button=ttk.Button(tools,text='←',width=3,command=self.back)
        self.back_button.pack(side='left')
        self.forward_button=ttk.Button(tools,text='→',width=3,command=self.forward)
        self.forward_button.pack(side='left',padx=4)
        self.up_button=ttk.Button(tools,text='↑',width=3,command=self.up)
        self.up_button.pack(side='left')
        self.address=tk.StringVar()
        address=ttk.Entry(tools,textvariable=self.address);address.pack(side='left',fill='x',expand=True,padx=10)
        address.bind('<Return>',lambda _:self.open_address())
        self.query=tk.StringVar()
        search=ttk.Entry(tools,textvariable=self.query,width=23);search.pack(side='right')
        ttk.Label(tools,text='Rechercher ici',style='Muted.TLabel').pack(side='right',padx=(6,8))
        search.insert(0,'')
        search.bind('<Escape>',lambda _:self.query.set(''))
        self.query.trace_add('write',self.filter_changed)
        self.breadcrumbs=ttk.Frame(main);self.breadcrumbs.pack(fill='x',pady=(10,18))
        heading=ttk.Frame(main);heading.pack(fill='x')
        self.title=tk.StringVar(value='Votre stockage, simplement.')
        ttk.Label(heading,textvariable=self.title,font=('Segoe UI',23,'bold')).pack(side='left')
        self.ai_button=ttk.Button(heading,text='Bilan IA',command=self.open_ai,style='Accent.TButton',state='disabled')
        self.ai_button.pack(side='right')
        ttk.Button(heading,text='Choisir un dossier…',command=self.pick_folder).pack(side='right',padx=8)
        self.summary=tk.StringVar(value='Choisissez un disque ou un dossier à explorer.')
        ttk.Label(main,textvariable=self.summary,style='Muted.TLabel').pack(anchor='w',pady=(5,15))
        modebar=ttk.Frame(main);modebar.pack(fill='x',pady=(0,10))
        self.mode=tk.StringVar(value='list')
        ttk.Radiobutton(modebar,text='Liste',variable=self.mode,value='list',command=self.show_view).pack(side='left')
        ttk.Radiobutton(modebar,text='Carte',variable=self.mode,value='map',command=self.show_view).pack(side='left',padx=12)
        ttk.Label(modebar,text='Double-clic pour entrer · recherche dans ce dossier',style='Muted.TLabel').pack(side='left',padx=10)
        self.cancel_button=ttk.Button(modebar,text='Arrêter le scan',command=self.cancel_scan,state='disabled')
        self.cancel_button.pack(side='right')
        ttk.Button(modebar,text='Actualiser',command=self.refresh).pack(side='right',padx=6)
        ttk.Button(modebar,text='Analyse complète',command=self.full_scan).pack(side='right',padx=6)
        self.view=ttk.Frame(main);self.view.pack(fill='both',expand=True)
        self.list=ExplorerList(self.view,self.open_entry,self.select_entry,self.sort_entries)
        self.list.pack(fill='both',expand=True)
        self.map=tk.Canvas(self.view,bg='white',highlightthickness=0)
        self.map.bind('<Configure>',lambda _:self.draw_map())
        self.map.bind('<Double-Button-1>',self.open_map)
        self.map.bind('<Motion>',self.hover_map)
        self.legend=ttk.Frame(main);self.legend.pack(fill='x',pady=(13,5))
        for color,text in (('#43a890','< 100 Mo'),('#d7bd49','≥ 100 Mo'),('#ef9a46','≥ 1 Go'),('#e95a64','≥ 10 Go')):
            tk.Label(self.legend,text='● '+text,bg='white',fg=color,font=('Segoe UI',9,'bold')).pack(side='left',padx=(0,16))
        ttk.Label(self.legend,text='Couleur = taille, pas danger',style='Muted.TLabel').pack(side='right')
        self.progress=ttk.Progressbar(main,mode='indeterminate');self.progress.pack(fill='x',pady=7)
        self.status=tk.StringVar(value='Prêt · aucun scan automatique')
        ttk.Label(main,textvariable=self.status,style='Muted.TLabel',wraplength=1000).pack(anchor='w')
        self.set_navigation_state()

    def show_access(self):
        from .permissions import is_admin
        lines=['Droits : '+('administrateur' if is_admin() else 'utilisateur standard'),
               'Pour élargir les accès : fermez cette fenêtre puis lancez Launch-Admin.cmd.',
               'Les fichiers cachés et système sont inclus si Windows autorise leur lecture.',
               'Aucune permission ni propriété de fichier ne sera modifiée.',
               'Les liens accessibles sont résolus ; les dossiers déjà mesurés affichent une référence sans double compte.',
               'Tailles logiques : elles peuvent différer de l’espace réellement occupé.',
               '1 Mo = 1 000 000 octets ; 1 Go = 1 000 Mo.']
        if self.result:
            node=self.result.nodes[self.current]
            lines += ['', 'Dossier : '+node.name,
                      f'{node.errors} erreur(s) ; {node.skipped} élément(s) ignoré(s).',
                      'Parcours : '+self.result.reason,
                      'Couverture : '+('complète selon le parcours' if node.complete else 'partielle ; tailles minimales, % sur les octets recensés'),
                      '', 'Exemples d’erreurs du scan (30 maximum) :']
            lines += [e['path']+' : '+e['reason'] for e in self.result.error_examples]
        window=tk.Toplevel(self.root);window.title('Accès et couverture');window.geometry('800x480')
        text=tk.Text(window,wrap='word',padx=20,pady=20,font=('Segoe UI',10))
        scroll=ttk.Scrollbar(window,command=text.yview);scroll.pack(side='right',fill='y')
        text.configure(yscrollcommand=scroll.set);text.pack(fill='both',expand=True)
        text.insert('1.0','\n\n'.join(lines));text.configure(state='disabled')

    def work(self,kind,function):
        def run():
            try:self.events.put((kind,function()))
            except Cancelled:pass
            except Exception as exc:self.events.put(('error',(kind,str(exc))))
        threading.Thread(target=run,daemon=True).start()

    def open_place(self,path):
        if self.result:
            for node in self.result.nodes[1:]:
                if os.path.normcase(os.path.abspath(node.path))==os.path.normcase(os.path.abspath(path)):
                    self.navigate(node.id);return
        self.begin_scan([path])

    def pick_folder(self):
        if self.scanning:return
        path=filedialog.askdirectory(title='Dossier à explorer')
        if path:self.open_place(path)

    def open_address(self):
        path=self.address.get().strip()
        if path.casefold()=='ce pc':self.navigate(0)
        elif os.path.isdir(path):self.open_place(path)
        else:messagebox.showinfo('Dossier introuvable','Saisissez le chemin d’un dossier existant.')

    def begin_scan(self,roots,full=True):
        if self.scanning or self.ai_busy:
            messagebox.showinfo('Opération en cours','Attendez la fin du bilan IA ou arrêtez le scan en cours.');return
        if not roots:return
        self.stop_listing.set();self.list_generation+=1
        self.stop_scan=threading.Event();self.scanning=True
        self.result=None;self.entries=[];self.visible=[];self.last_snapshot=self.last_ai=None
        self.list.set_entries([],0)
        self.ai_button.configure(state='disabled');self.cancel_button.configure(state='normal')
        self.progress.start(12)
        self.title.set('Analyse du stockage…')
        self.summary.set('Calcul en cascade en cours · tailles provisoires · navigation disponible à la fin.')
        self.address.set(' ; '.join(roots))
        self.status.set('Lecture des tailles…')
        self.draw_map()
        options={'max_entries':float('inf'),'max_directories':float('inf'),'max_seconds':float('inf')} if full else {}
        self.work('scan',lambda:scan(roots,self.stop_scan,progress=lambda p:self.events.put(('progress',p)),**options))

    def full_scan(self):
        roots=[self.result.nodes[i].path for i in self.result.root.children] if self.result else self.drives
        self.begin_scan(roots,full=True)

    def show_scan_progress(self,value):
        self.status.set(f"{value['files']:,} fichiers · {size_text(value['bytes'])} recensés · {value['elapsed']:.0f} s · calcul en cours")
        entries=[Entry('d'+str(e['id']),e['name'],e['bytes'] or None,'folder',e['path'],complete=False) for e in value.get('folders',[])]
        self.list.parent_complete=False
        self.list.set_entries(sorted_entries(entries,by='size',descending=True),value['bytes'])

    def cancel_scan(self):
        self.stop_scan.set();self.status.set('Arrêt demandé ; préparation des résultats partiels…')

    def install_result(self,result):
        self.result=result;self.scanning=False
        self.progress.stop();self.cancel_button.configure(state='disabled');self.ai_button.configure(state='normal')
        initial=1 if len(result.root.children)==1 else 0
        self.nav=Navigation(initial)
        self.navigate(initial,remember=False)

    def navigate(self,node_id,remember=True):
        if not self.result:return
        if remember:self.nav.visit(node_id)
        node=self.result.nodes[node_id]
        self.address.set(node.path or 'Ce PC')
        name=node.name if node_id else 'Ce PC'
        self.title.set(('Démo · ' if self.result.demo else '')+(name if len(name)<=30 else name[:29]+'…'))
        self.summary.set(('≥ ' if not node.complete else '')+size_text(node.total_bytes)+' recensés · '+('base partielle · % approximatifs · ' if not node.complete else '')+f'{node.directories:,} sous-dossiers · {node.files:,} fichiers')
        self.query.set('')
        self.update_breadcrumbs();self.set_navigation_state()
        self.stop_listing.set();self.stop_listing=threading.Event()
        self.list_generation+=1;generation=self.list_generation
        self.entries=folders(self.result,node_id);self.render_entries()
        self.status.set('Chargement des fichiers de ce dossier…')
        result=self.result;stop=self.stop_listing
        self.work('listing',lambda:(generation,*list_directory(result,node_id,stop)))

    def update_breadcrumbs(self):
        for widget in self.breadcrumbs.winfo_children():widget.destroy()
        chain=[];key=self.current
        while key is not None:
            chain.append(key);key=self.result.nodes[key].parent
        chain=list(reversed(chain))
        if len(chain)>6:chain=[0]+chain[-5:]
        for index,key in enumerate(chain):
            if index:ttk.Label(self.breadcrumbs,text='›',style='Muted.TLabel').pack(side='left',padx=3)
            name='Ce PC' if key==0 else self.result.nodes[key].name
            label=name if len(name)<22 else name[:19]+'…'
            ttk.Button(self.breadcrumbs,text=label,command=lambda k=key:self.navigate(k)).pack(side='left')

    def set_navigation_state(self):
        for button,enabled in ((self.back_button,self.nav.position>0),
                               (self.forward_button,self.nav.position<len(self.nav.history)-1),
                               (self.up_button,self.result is not None and self.current!=0)):
            button.configure(state='normal' if enabled else 'disabled')

    def back(self):
        if self.result:self.navigate(self.nav.back(),remember=False)

    def forward(self):
        if self.result:self.navigate(self.nav.forward(),remember=False)

    def up(self):
        if self.result:
            parent=self.result.nodes[self.current].parent
            if parent is not None:self.navigate(parent)

    def refresh(self):
        if self.result:
            roots=[self.result.nodes[i].path for i in self.result.root.children]
            self.begin_scan(roots)

    def filter_changed(self,*_):
        if self.pending_filter:self.root.after_cancel(self.pending_filter)
        self.pending_filter=self.root.after(100,self.render_entries)

    def render_entries(self):
        self.pending_filter=None
        self.visible=sorted_entries(self.entries,self.query.get(),self.sort_by,self.descending)
        total=self.result.nodes[self.current].total_bytes if self.result else 0
        self.list.parent_complete=self.result.nodes[self.current].complete if self.result else True
        self.list.set_entries(self.visible,total)
        self.draw_map()

    def sort_entries(self,key):
        self.descending=not self.descending if self.sort_by==key else key=='size'
        self.sort_by=key;self.render_entries()

    def open_entry(self,entry):
        if self.scanning:return
        if entry.kind=='folder':
            if entry.node_id is not None:
                node=self.result.nodes[entry.node_id]
                self.navigate(node.reference if node.reference is not None else entry.node_id)
            else:self.begin_scan([entry.path])
        else:self.select_entry(entry)  # Never execute/open document contents.

    def select_entry(self,entry):
        if self.scanning or not self.result:return
        size='Non mesuré' if entry.size is None else ('≥ ' if not entry.complete else '')+size_text(entry.size)
        node=self.result.nodes[self.current]
        part=share_text(entry.size,node.total_bytes,node.complete and entry.complete) if entry.counted else '—'
        self.status.set(entry.name+' · '+size+' · '+part+' du dossier parent'+(' · base partielle' if not node.complete else '')+(' · '+entry.reason if entry.reason else ''))

    def show_view(self):
        self.list.pack_forget();self.map.pack_forget()
        (self.list if self.mode.get()=='list' else self.map).pack(fill='both',expand=True)
        self.draw_map()

    def draw_map(self):
        if not hasattr(self,'map'):return
        c=self.map;c.delete('all');self.map_boxes=[]
        width,height=max(500,c.winfo_width()),max(300,c.winfo_height())
        entries=[e for e in getattr(self,'visible',[]) if e.size and e.size>0 and e.counted]
        shown=entries[:45]
        items=[(i,e.size) for i,e in enumerate(shown)]
        remainder=sum(e.size for e in entries[45:])
        if remainder:items.append((-1,remainder))
        for key,x,y,w,h in treemap(items,0,0,width,height):
            entry=shown[key] if key>=0 else None
            size=entry.size if entry else remainder
            pad=min(2,w/4,h/4)
            c.create_rectangle(x+pad,y+pad,x+w-pad,y+h-pad,fill=band(size)[0],outline='')
            self.map_boxes.append((x,y,w,h,entry))
            if w>90 and h>55:
                name=entry.name if entry else 'Autres éléments'
                c.create_text(x+12,y+16,text=clipped(name,self.list.font,w-25),anchor='w',font=self.list.bold,fill=INK)
                c.create_text(x+12,y+38,text=size_text(size)+' · '+share_text(size,self.result.nodes[self.current].total_bytes,self.result.nodes[self.current].complete),anchor='w',font=self.list.font,fill=INK)
        if not items:c.create_text(width/2,height/2,text='Choisissez un dossier à analyser.' if not self.result else 'Aucune taille accessible dans cette vue.',fill=MUTED,font=('Segoe UI',13))

    def map_entry(self,event):
        return next((e for x,y,w,h,e in self.map_boxes if x<=event.x<x+w and y<=event.y<y+h),None)

    def open_map(self,event):
        entry=self.map_entry(event)
        if entry:self.open_entry(entry)

    def hover_map(self,event):
        entry=self.map_entry(event)
        if entry:self.select_entry(entry)

    def open_ai(self):
        if not self.result:return
        if self.ai_window and self.ai_window.winfo_exists():
            self.ai_window.deiconify();self.ai_window.lift();return
        window=tk.Toplevel(self.root);self.ai_window=window
        window.title('Bilan du dossier · Clair Stockage');window.geometry('800x700');window.minsize(660,540)
        window.configure(bg=BG)
        frame=ttk.Frame(window,padding=20);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='Comprendre ce dossier',font=('Segoe UI',20,'bold')).pack(anchor='w')
        self.ai_scope=tk.StringVar(value=self.address.get())
        ttk.Label(frame,textvariable=self.ai_scope,style='Muted.TLabel',wraplength=740).pack(anchor='w',pady=(5,14))
        bar=ttk.Frame(frame);bar.pack(fill='x')
        self.model=tk.StringVar(value='qwen3:8b')
        self.model_box=ttk.Combobox(bar,textvariable=self.model,values=[],state='readonly',width=24);self.model_box.pack(side='left')
        self.test_button=ttk.Button(bar,text='Tester Ollama',command=self.test_ollama);self.test_button.pack(side='left',padx=8)
        self.analyze_button=ttk.Button(bar,text='Analyser ce dossier',command=self.analyze_ai,style='Accent.TButton');self.analyze_button.pack(side='right')
        self.ai_status=tk.StringVar(value='Le bilan mesuré est disponible sans Ollama.')
        ttk.Label(frame,textvariable=self.ai_status,style='Muted.TLabel',wraplength=740).pack(anchor='w',pady=12)
        self.include_files=tk.BooleanVar(value=True)
        ttk.Checkbutton(frame,text='Inclure les noms de fichiers et marqueurs techniques pour identifier les usages',variable=self.include_files).pack(anchor='w')
        box=ttk.Frame(frame);box.pack(fill='both',expand=True,pady=12)
        self.ai_text=tk.Text(box,wrap='word',bg='#f8fafc',fg=INK,relief='flat',padx=16,pady=14,spacing3=7)
        scroll=ttk.Scrollbar(box,command=self.ai_text.yview);self.ai_text.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');self.ai_text.pack(fill='both',expand=True)
        buttons=ttk.Frame(frame);buttons.pack(fill='x')
        ttk.Button(buttons,text='Voir les données envoyées',command=self.show_payload).pack(side='left')
        ttk.Button(buttons,text='Exporter le bilan…',command=self.export).pack(side='right')
        self.local_report()
        window.protocol('WM_DELETE_WINDOW',lambda:window.withdraw() if self.ai_busy else self.close_ai_window())
        self.test_ollama()

    def close_ai_window(self):
        if self.ai_window:self.ai_window.destroy()
        self.ai_window=None

    def put_report(self,text):
        if self.ai_window and self.ai_window.winfo_exists():
            self.ai_text.configure(state='normal');self.ai_text.delete('1.0','end');self.ai_text.insert('end',text);self.ai_text.configure(state='disabled')

    def local_report(self):
        self.last_snapshot=describe(self.result,self.current,self.include_files.get(),max_nodes=8)
        self.ai_scope.set(self.address.get());self.last_ai=None
        self.put_report(factual_report(self.last_snapshot))

    def ai_controls(self,busy):
        self.ai_busy=busy
        if self.ai_window and self.ai_window.winfo_exists():
            for button in (self.test_button,self.analyze_button):button.configure(state='disabled' if busy else 'normal')

    def test_ollama(self):
        if self.ai_busy:return
        self.ai_controls(True);self.ai_status.set('Connexion à Ollama et lecture des modèles locaux…')
        self.work('diagnosis',self.advisor.diagnose)

    def analyze_ai(self):
        if self.ai_busy or not self.result:return
        self.local_report();snapshot=self.last_snapshot;model=self.model.get()
        self.ai_controls(True);self.ai_status.set('Exploration des noms et marqueurs techniques… puis analyse en plusieurs étapes, plusieurs minutes possibles.')
        result=self.result;node_id=self.current;include_files=self.include_files.get()
        def analyze():
            from .exploration import explore,attach
            enriched=attach(snapshot,explore(result,node_id,include_files,stop=self.advisor.stop))
            self.events.put(('analysis_evidence',enriched))
            return self.advisor.analyze(model,enriched,progress=lambda text:self.events.put(('analysis_progress',text)))
        self.work('analysis',analyze)

    def show_payload(self):
        if not self.last_snapshot:return
        window=tk.Toplevel(self.root);window.title('Métadonnées du bilan · exploration et lots');window.geometry('760x600')
        text=tk.Text(window,wrap='word',padx=15,pady=15);text.pack(fill='both',expand=True)
        data=dict(self.last_snapshot)
        if 'exploration' in data:
            from .exploration import batches
            data['analysis_batches']=batches(data['exploration'])
        else:
            data['note']='L’exploration détaillée des noms est préparée lorsque vous lancez Analyser.'
        text.insert('end',json.dumps(data,ensure_ascii=False,indent=2));text.configure(state='disabled')

    def export(self):
        if not self.last_snapshot:return
        path=filedialog.asksaveasfilename(defaultextension='.json',initialfile='clair-stockage-bilan.json')
        if path:
            try:
                with open(path,'w',encoding='utf-8') as file:json.dump({'version':__version__,'snapshot':self.last_snapshot,'ai':self.last_ai},file,ensure_ascii=False,indent=2)
            except OSError as exc:messagebox.showerror('Export impossible',str(exc))

    def drain(self):
        if self.closed:return
        try:
            for _ in range(40):
                kind,value=self.events.get_nowait()
                if kind=='scan':self.install_result(value)
                elif kind=='progress':self.show_scan_progress(value)
                elif kind=='listing':
                    generation,entries,note=value
                    if generation!=self.list_generation:continue
                    self.entries=entries;self.render_entries()
                    node=self.result.nodes[self.current]
                    self.status.set(note or f"{len(entries):,} éléments · tailles logiques · "+('relevé partiel' if not node.complete else 'parcours terminé'))
                elif kind=='diagnosis':
                    self.ai_controls(False)
                    if self.ai_window and self.ai_window.winfo_exists():
                        models=value['models'];self.model_box.configure(values=models)
                        if self.model.get() not in models:self.model.set(models[0] if models else '')
                        self.ai_status.set(value['connection']+f" · {len(models)} modèle(s) local(aux)")
                elif kind=='analysis_evidence':
                    self.last_snapshot=value
                elif kind=='analysis_progress':
                    if self.ai_window and self.ai_window.winfo_exists():self.ai_status.set(value)
                elif kind=='analysis':
                    self.last_ai=value;self.ai_controls(False);self.put_report(value['text'])
                    if self.ai_window and self.ai_window.winfo_exists():self.ai_status.set(f"Bilan terminé · {value.get('model_folder_count',0)} dossiers examinés par l’IA · interprétation à vérifier · aucune action exécutée")
                elif kind=='error':
                    origin,error=value
                    if origin=='scan':
                        self.scanning=False;self.progress.stop();self.cancel_button.configure(state='disabled')
                    elif origin in ('analysis','diagnosis'):
                        self.ai_controls(False)
                        if self.ai_window and self.ai_window.winfo_exists():self.ai_status.set(error)
                    self.status.set(error)
        except queue.Empty:pass
        self.root.after(100,self.drain)

    def close(self):
        if self.closed:return
        self.closed=True;self.stop_scan.set();self.stop_listing.set();self.advisor.close();self.root.destroy()


def main():
    parser=argparse.ArgumentParser(description='Clair Stockage — explorateur visuel en lecture seule')
    parser.add_argument('--demo',action='store_true');args=parser.parse_args()
    root=tk.Tk();app=StorageApp(root,args.demo)
    try:root.mainloop()
    finally:app.stop_scan.set();app.stop_listing.set();app.advisor.close()


if __name__=='__main__':main()
