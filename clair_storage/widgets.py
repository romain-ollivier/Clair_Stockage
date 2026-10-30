"""Minimal explorer list: virtual rows, storage bars and names only."""
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from .layout import band, size_text, parent_share, share_text

INK, MUTED = '#1d2939', '#667085'


def clipped(text, font, width):
    if font.measure(text) <= width:
        return text
    left, right = 0, len(text)
    while left < right:
        middle = (left+right+1)//2
        if font.measure(text[:middle]+'…') <= width:
            left = middle
        else:
            right = middle-1
    return text[:left]+'…'


class ExplorerList(ttk.Frame):
    ROW = 48
    def __init__(self, parent, on_open, on_select, on_sort):
        super().__init__(parent)
        self.entries=[]
        self.total=0
        self.selected=None
        self.on_open,self.on_select,self.on_sort=on_open,on_select,on_sort
        self.font=tkfont.Font(family='Segoe UI',size=10)
        self.bold=tkfont.Font(family='Segoe UI',size=10,weight='bold')
        self.small=tkfont.Font(family='Segoe UI',size=9)
        self.header=tk.Canvas(self,height=37,bg='#f8fafc',highlightthickness=0)
        self.header.pack(fill='x')
        frame=ttk.Frame(self);frame.pack(fill='both',expand=True)
        self.canvas=tk.Canvas(frame,bg='white',highlightthickness=0,yscrollincrement=self.ROW)
        scroll=ttk.Scrollbar(frame,command=self.scroll)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda _:self.draw())
        self.header.bind('<Configure>',lambda _:self.draw_header())
        self.header.bind('<Button-1>',self.sort_click)
        self.canvas.bind('<Button-1>',self.select)
        self.canvas.bind('<Double-Button-1>',self.open)
        self.canvas.bind('<MouseWheel>',self.wheel)
        self.canvas.bind('<Button-4>',lambda _:self.scroll('scroll',-1,'units'))
        self.canvas.bind('<Button-5>',lambda _:self.scroll('scroll',1,'units'))
        self.canvas.bind('<Return>',lambda _:self.on_open(self.selected) if self.selected else None)
        self.canvas.bind('<Up>',lambda _:self.move(-1))
        self.canvas.bind('<Down>',lambda _:self.move(1))
        self.canvas.configure(takefocus=True)

    def columns(self):
        width=max(520,self.canvas.winfo_width())
        return width,max(235,width*.43),max(345,width*.65)

    def set_entries(self,entries,total):
        self.entries=entries
        self.total=total
        self.selected=None
        self.canvas.configure(scrollregion=(0,0,1,len(entries)*self.ROW))
        self.canvas.yview_moveto(0)
        self.draw()

    def draw_header(self):
        c=self.header;c.delete('all')
        width,start,end=self.columns()
        for x,text in ((20,'Nom'),(start,'% du dossier parent'),(width-25,'Taille')):
            c.create_text(x,18,text=text,anchor='e' if text=='Taille' else 'w',fill=MUTED,font=self.small)
        c.create_line(0,36,width,36,fill='#e7ecf1')

    def draw(self):
        c=self.canvas;c.delete('rows')
        self.draw_header()
        width,start,end=self.columns()
        first=max(0,int(c.canvasy(0)//self.ROW))
        count=max(1,int(c.winfo_height()/self.ROW)+3)
        for index in range(first,min(len(self.entries),first+count)):
            item=self.entries[index];y=index*self.ROW
            bg='#eaf4ff' if item==self.selected else ('white' if index%2==0 else '#fcfdfe')
            c.create_rectangle(0,y,width,y+self.ROW,fill=bg,outline='',tags='rows')
            if item.kind=='folder':
                c.create_rectangle(18,y+14,29,y+20,fill='#f2c361',outline='',tags='rows')
                c.create_rectangle(17,y+18,40,y+34,fill='#f5cf7b',outline='#dfb358',tags='rows')
            else:
                c.create_rectangle(21,y+12,37,y+34,fill='#edf2f8',outline='#b8c5d4',tags='rows')
                for line in (20,25,30):c.create_line(25,y+line,33,y+line,fill='#a5b5c8',tags='rows')
            c.create_text(54,y+24,text=clipped(item.name,self.font,start-75),anchor='w',fill=INK,font=self.font,tags='rows')
            if item.size is not None:
                ratio=(parent_share(item.size,self.total) or 0) if item.counted else 0
                color=band(item.size)[0]
                c.create_rectangle(start,y+19,end,y+29,fill='#edf1f5',outline='',tags='rows')
                if ratio:c.create_rectangle(start,y+19,start+(end-start)*ratio,y+29,fill=color,outline='',tags='rows')
                c.create_text(end+12,y+24,text=share_text(item.size,self.total,getattr(self,'parent_complete',True) and item.complete) if item.counted else 'Lien',anchor='w',fill=MUTED,font=self.small,tags='rows')
                size=('≥ ' if not item.complete else '')+size_text(item.size)
            else:size='Non mesuré'
            c.create_text(width-25,y+24,text=size,anchor='e',fill=MUTED if item.size is None else INK,font=self.font,tags='rows')
        if not self.entries:
            c.create_text(width/2,max(80,c.winfo_height()/2),text='Aucun élément à afficher.',fill=MUTED,font=self.font,tags='rows')

    def sort_click(self,event):
        width,start,end=self.columns()
        self.on_sort('name' if event.x<start else 'size')

    def scroll(self,*args):
        self.canvas.yview(*args);self.draw()

    def wheel(self,event):
        self.scroll('scroll',int(-event.delta/120) or (-1 if event.delta>0 else 1),'units')

    def select(self,event):
        self.canvas.focus_set()
        index=int(self.canvas.canvasy(event.y)//self.ROW)
        if 0<=index<len(self.entries):
            self.selected=self.entries[index];self.on_select(self.selected);self.draw()

    def open(self,event):
        index=int(self.canvas.canvasy(event.y)//self.ROW)
        if 0<=index<len(self.entries):self.on_open(self.entries[index])

    def move(self,direction):
        if not self.entries:return
        index=self.entries.index(self.selected) if self.selected in self.entries else 0
        index=max(0,min(len(self.entries)-1,index+direction))
        self.selected=self.entries[index];self.on_select(self.selected)
        top=self.canvas.canvasy(0)
        if index*self.ROW<top or (index+1)*self.ROW>top+self.canvas.winfo_height():
            self.canvas.yview_moveto(index/max(1,len(self.entries)))
        self.draw()
