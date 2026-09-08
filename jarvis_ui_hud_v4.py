"""Native Tk HUD for Jarvis. Drawing and widget updates stay on the UI thread."""
import math
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path

BG = "#050d15"
PANEL = "#091923"
EDGE = "#294e61"
CYAN = "#83dcf4"
WHITE = "#deeff5"
MUTED = "#799eaf"
FONT = "Bahnschrift"


def hud_layout(width,height):
    """Use one physical-pixel scale for geometry and fonts, independent of Tk DPI."""
    scale=min(width/1600,height/920)
    return scale,280*scale,220*scale,22*scale


def panel(canvas, x, y, w, h, fill=PANEL, outline=EDGE, tag="scene"):
    cut = 9
    coords = (x+cut,y, x+w-cut,y, x+w,y+cut, x+w,y+h-cut,
              x+w-cut,y+h, x+cut,y+h, x,y+h-cut, x,y+cut)
    canvas.create_polygon(coords, fill=fill, outline=outline, width=1, tags=tag)
    for ax, ay, bx, by in ((x+cut,y,x+48,y), (x+w-48,y,x+w-cut,y),
                           (x+cut,y+h,x+48,y+h), (x+w-48,y+h,x+w-cut,y+h)):
        canvas.create_line(ax,ay,bx,by, fill="#67b5d1", width=1, tags=tag)


class Transcript(tk.Frame):
    """Selectable transcript with bounded history and proper scroll behaviour."""
    def __init__(self, parent):
        super().__init__(parent, bg=PANEL)
        self.text = tk.Text(self, bg=PANEL, fg=WHITE, bd=0, highlightthickness=0,
                            wrap="word", font=("Segoe UI", 12), padx=16, pady=12,
                            insertwidth=0, selectbackground="#25526a", cursor="arrow",
                            spacing1=5, spacing3=12, state="disabled")
        self.text.pack(side="left", fill="both", expand=True)
        bar = tk.Scrollbar(self, command=self.text.yview, bg="#16323f", troughcolor=PANEL,
                           activebackground="#438299", bd=0, width=9, highlightthickness=0)
        bar.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=bar.set)
        for role, color in (("user", "#c7f3ef"), ("assistant", CYAN), ("system", MUTED), ("error", "#f3a18e")):
            self.text.tag_configure(role, foreground=color, font=(FONT, 10, "bold"), spacing1=14, spacing3=4)
        self.text.tag_configure("body", foreground=WHITE, lmargin1=0, lmargin2=0)
        self.text.tag_configure("quiet", foreground=MUTED)
        self.last = None

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self.last = None

    def add_message(self, role, message):
        message = str(message).strip()
        if not message:
            return
        stamp = time.monotonic()
        if self.last and self.last[:2] == (role, message) and stamp-self.last[2] < 2:
            return
        self.last = (role, message, stamp)
        bottom = self.text.yview()[1] >= .96
        self.text.configure(state="normal")
        label = {"assistant": "JARVIS", "user": "YOU", "error": "SYSTEM / ATTENTION"}.get(role, "SYSTEM")
        self.text.insert("end", label + "   /   " + time.strftime("%H:%M") + "\n", role)
        self.text.insert("end", message + "\n", "quiet" if role == "system" else "body")
        if int(self.text.index("end-1c").split(".")[0]) > 2400:
            self.text.delete("1.0", "401.0")
        self.text.configure(state="disabled")
        if bottom:
            self.text.see("end")


class Reactor(tk.Canvas):
    def __init__(self, parent):
        super().__init__(parent, bg=BG, highlightthickness=0, bd=0, width=250, height=250)
        self.phase = 0
        self.talking = False

    def set_talking(self, talking):
        self.talking = bool(talking)

    def pulse_once(self):
        pass  # Visual state is read from the real speech event, not an invented timer.

    def draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        x, y, r = w/2, h/2, min(w,h)*.46
        self.phase += .022 if not self.talking else .072
        for ratio, color, width in ((1,"#153747",1),(.95,"#356d82",2),(.87,"#122f3d",1),(.72,"#29596d",1),
                                    (.62,"#123240",8),(.55,"#5cbad6",2),(.47,"#173e50",6),(.40,"#225773",1)):
            rr = r*ratio
            self.create_oval(x-rr,y-rr,x+rr,y+rr,outline=color,width=width)
        for index in range(72):
            a = math.tau*index/72
            inner = .89 if index%6 == 0 else .91
            self.create_line(x+math.cos(a)*r*inner,y+math.sin(a)*r*inner,
                             x+math.cos(a)*r*.93,y+math.sin(a)*r*.93,
                             fill="#6ba7bb" if index%6 == 0 else "#244b5c", width=1)
        for k in range(4):
            self.create_arc(x-r*.97,y-r*.97,x+r*.97,y+r*.97,start=k*90+self.phase*24,
                            extent=55,style="arc",outline="#64b4d0",width=3)
        for k in range(10):
            self.create_arc(x-r*.68,y-r*.68,x+r*.68,y+r*.68,start=k*36-self.phase*18,
                            extent=20,style="arc",outline=CYAN if self.talking else "#5da8bf",width=max(5,int(r*.09)))
        for rr in range(30, 4, -5):
            ratio = rr/80
            color = "#" + "{:02x}{:02x}{:02x}".format(12+rr//2,43+rr,60+rr*2)
            self.create_oval(x-r*ratio,y-r*ratio,x+r*ratio,y+r*ratio,fill=color,outline="")
        points = []
        for a in (-math.pi/2, math.pi/6, 5*math.pi/6):
            points.extend((x+math.cos(a)*r*.34, y+math.sin(a)*r*.34))
        self.create_polygon(points, fill="#0f354c", outline="#b7f1fc", width=2)
        self.create_line(x,y-r*.24,x,y+r*.14,fill="#7fe3ff",width=2)
        self.create_line(x-r*.22,y+r*.14,x,y-r*.03,x+r*.22,y+r*.14,fill="#7fe3ff",width=2)


def create_overlay(Base, AttachmentBar, ghost_filter):
    class JarvisHUD(Base):
        def __init__(self, root, app_instance, app_module):
            self.root, self.app_instance, self.app_module = root, app_instance, app_module
            self.original_log = getattr(app_module, "log", None)
            self.original_speak = getattr(app_module, "speak", None)
            self.ui_thread = threading.get_ident()
            self.events = queue.Queue(maxsize=3000)
            self.mode = "chat"
            self.alive = True
            self.started = time.monotonic()
            self.media_title, self.media_artist = "No playback information", "Refresh to check Spotify"
            self.media_progress = 0
            self.media_pending = False
            self.cpu, self.memory = None, None
            self.layout_job = None
            self._jobs = set()
            self.speech = False
            self.telemetry = None
            try:
                import psutil
                self.telemetry = psutil
                psutil.cpu_percent(interval=None)
            except ImportError:
                pass
            root.configure(bg=BG)
            root.title("JARVIS  /  Cognitive Interface")
            # Preserve the user's maximised state instead of shrinking the existing app.
            if root.state() != "zoomed":
                root.geometry("1440x900")
            root.minsize(1080, 700)
            self.overlay = tk.Canvas(root, bg=BG, highlightthickness=0, bd=0)
            self.overlay.place(x=0,y=0,relwidth=1,relheight=1)
            self.overlay.bind("<Configure>", self._resize)
            self.overlay.bind("<Destroy>", self._destroy, add="+")
            self.reactor = Reactor(self.overlay)
            self.visualizer = self.reactor
            self.chat = Transcript(self.overlay)
            self.info = tk.Text(self.overlay, bg=PANEL, fg=WHITE, bd=0, padx=24,pady=22,
                                highlightthickness=0, font=("Segoe UI",12), wrap="word", state="disabled")
            self.info.tag_configure("title",foreground=CYAN,font=(FONT,18),spacing3=22)
            self.attachment_bar = AttachmentBar(self.overlay, root)
            self.input_box = tk.Text(self.overlay, height=2,bg="#0b1e2a",fg=WHITE,insertbackground=CYAN,
                                    bd=0,highlightthickness=0,font=("Segoe UI",12),padx=8,pady=8,wrap="word",
                                    selectbackground="#244f66")
            self.input_box.bind("<Return>", self._enter_to_send)
            self.input_box.bind("<Control-Return>", self._control_enter)
            self.input_box.bind("<KeyPress>", self._activity, add="+")
            self.buttons = {}
            for key, label, command, kind in (
                ("chat","01    PRIMARY CHAT",lambda:self.show_view("chat"),"nav"),
                ("status","02    SYSTEM STATUS",lambda:self.show_view("status"),"nav"),
                ("briefs","03    KEY BRIEFS",lambda:self.show_view("briefs"),"nav"),
                ("new","+     NEW CONVERSATION",self.new_chat,"quiet"),
                ("attach","+",self.add_attachments,"quiet"),
                ("send","SEND  ↗",self.send_message,"send"),
                ("stop","STOP",self.stop_speaking,"stop"),
                ("sleep","STANDBY",self.sleep_mode,"quiet"),
                ("media","REFRESH",self.refresh_media,"quiet"),
                ("resume","RESUME",self.resume_voice,"quiet"),
            ):
                self.buttons[key] = self.button(label,command,kind)
            self._patch_log()
            # Route the existing app's UI log queue consumer through this transcript.
            # This also receives maintainer notifications that bypass app.log().
            self.original_append_log = getattr(app_instance,"append_log",None)
            if callable(self.original_append_log):
                def append_proxy(message):
                    self.handle_log(message)
                    self.original_append_log(message)
                app_instance.append_log = append_proxy
            self.say("system", "Cognitive interface ready. Voice, chat and system controls connected.")
            self._later(100,self._layout)
            self._later(80,self._drain)
            self._later(500,self._status_tick)
            self._later(60,self._animate)

        def _later(self,ms,callback):
            if not self.alive:
                return
            holder = []
            def run():
                self._jobs.discard(holder[0])
                if self.alive:
                    callback()
            job = self.root.after(ms,run)
            holder.append(job)
            self._jobs.add(job)
            return job

        def _destroy(self,event):
            if event.widget is not self.overlay:
                return
            self.alive = False
            for job in tuple(self._jobs):
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
            if self.app_module.log is getattr(self,"log_proxy",None):
                self.app_module.log = self.original_log

        def button(self,text,command,kind):
            bg, fg = {"send":("#154f4b","#bcf4e7"),"stop":("#301f27","#efa499"),
                      "nav":("#0a1c28",CYAN),"quiet":("#0c202b",MUTED)}[kind]
            button = tk.Button(self.overlay,text=text,command=command,bg=bg,fg=fg,
                               activebackground="#1d4050",activeforeground=WHITE,bd=0,relief="flat",
                               font=(FONT,10),cursor="hand2",highlightthickness=1,
                               highlightbackground=EDGE,highlightcolor=CYAN,takefocus=True)
            button.bind("<Enter>",lambda e:button.configure(bg="#1b3c4b"))
            button.bind("<Leave>",lambda e:button.configure(bg=bg))
            return button

        def text(self,x,y,text,size=12,fill=MUTED,anchor="nw",tag="scene",**options):
            return self.overlay.create_text(x,y,text=text,anchor=anchor,fill=fill,
                                             font=(FONT,-max(10,round(size*self.scale*1.3))),tags=tag,**options)

        def _resize(self,event):
            if event.widget is self.overlay:
                if self.layout_job:
                    try:self.root.after_cancel(self.layout_job)
                    except tk.TclError:pass
                    self._jobs.discard(self.layout_job)
                self.layout_job = self._later(100,self._layout)

        def _layout(self):
            self.layout_job = None
            c = self.overlay
            w,h = c.winfo_width(),c.winfo_height()
            if w<100 or h<100:return
            self.scale,left,right,gap = hud_layout(w,h)
            s=self.scale
            # Negative Tk font sizes are pixels: don't apply OS point scaling a
            # second time after scaling the canvas for a high-DPI monitor.
            self.chat.text.configure(font=("Segoe UI",-max(12,round(17*s))),
                                      padx=round(16*s),pady=round(12*s),spacing1=round(5*s),spacing3=round(12*s))
            for role in ("user","assistant","system","error"):
                self.chat.text.tag_configure(role,font=(FONT,-max(10,round(13*s)),"bold"),
                                            spacing1=round(14*s),spacing3=round(4*s))
            self.input_box.configure(font=("Segoe UI",-max(12,round(17*s))))
            self.info.configure(font=("Segoe UI",-max(12,round(17*s))))
            self.info.tag_configure("title",font=(FONT,-max(16,round(24*s))))
            for key,button in self.buttons.items():
                button.configure(font=(FONT,-max(10,round((13 if key not in ("new","resume") else 11)*s))))
            x = left+gap
            cw = w-x-right-gap*2
            top = max(42,52*s)
            header_h = max(95,112*s)
            chat_y = top+header_h+gap
            composer_h = max(76,86*s)
            bottom = h-max(36,46*s)
            composer_y = bottom-composer_h
            chat_h = max(200,composer_y-chat_y-gap)
            self.bounds = (x,chat_y,cw,chat_h,composer_y,composer_h,w,h)
            c.delete("scene")
            c.delete("motion")
            # Restrained architectural lines create depth without image assets.
            for i in range(1,8):
                yy = h*.40 + (i/7)**2*h*.63
                c.create_line(0,yy,w/2,yy-25*s,w,yy,fill="#0b202b",tags="scene")
            for i in range(-5,7):
                c.create_line(w/2+i*36,h*.44,w/2+i*w*.18,h,fill="#10222d",tags="scene")
            for ox in (-100,w-250):
                for j in range(4):
                    c.create_polygon(ox+j*72,0,ox+46+j*72,0,ox+145+j*52,h,ox+117+j*52,h,
                                     fill="#07121d",outline="#0c1d29",tags="scene")
            c.create_line(0,8,w*.28,30,w*.78,30,w,8,fill="#315568",tags="scene")
            c.create_line(0,h-8,w*.28,h-28,w*.78,h-28,w,h-8,fill="#294c60",tags="scene")
            self.text(22,16,"J.A.R.V.I.S.",11,CYAN)
            self.text(w-22,16,"LOCAL ASSISTANT   /   COGNITIVE INTERFACE",9,MUTED,anchor="ne")
            rx = gap
            size = min(left-gap*2,250*s)
            self.reactor.place(x=(left-size)/2,y=top+4,width=size,height=size)
            self.text(left/2,top+size+20*s,"COGNITIVE CORE",14,CYAN,anchor="n")
            self.voice_id = self.text(left/2,top+size+48*s,"SYSTEM ONLINE",9,MUTED,anchor="n")
            nav_y = top+size+100*s
            for i,key in enumerate(("chat","status","briefs")):
                self.buttons[key].place(x=gap,y=nav_y+i*59*s,width=left-gap*1.5,height=max(38,48*s))
            self.buttons["new"].place(x=gap,y=nav_y+192*s,width=left-gap*1.5,height=38*s)
            c.create_line(gap,bottom-144*s,left-gap/2,bottom-144*s,fill=EDGE,tags="scene")
            self.text(gap,bottom-122*s,"IDENTITY",8)
            self.name_id = self.text(gap,bottom-99*s,"Sir",17,WHITE)
            self.text(gap,bottom-54*s,"VOICE CONTROL",8)
            self.buttons["resume"].place(x=gap,y=bottom-29*s,width=left-gap*1.5,height=28*s)
            panel(c,x,top,cw,header_h)
            self.core_status_id = self.text(x+24*s,top+19*s,"COGNITIVE CORE STATUS: OPERATIONAL",10,MUTED)
            self.greeting_id = self.text(x+24*s,top+48*s,"How can Jarvis help today?",27,CYAN)
            panel(c,x,chat_y,cw,chat_h,fill=PANEL)
            self.text(x+20*s,chat_y+15*s,"CONVERSATION  /  PRIMARY CHANNEL",9,MUTED)
            self.text(x+cw-20*s,chat_y+15*s,"●  LOCAL",9,"#6cc9b3",anchor="ne")
            self.chat.place(x=x+8,y=chat_y+44*s,width=cw-16,height=chat_h-53*s)
            if self.mode != "chat":
                self.chat.place_forget()
                self.info.place(x=x+8,y=chat_y+44*s,width=cw-16,height=chat_h-53*s)
            else:
                self.info.place_forget()
            panel(c,x,composer_y,cw,composer_h,fill="#0b1e2a",outline="#427b91")
            has_files = bool(self.attachment_bar.paths)
            chip_h = 31 if has_files else 0
            if has_files:self.attachment_bar.place(x=x+12,y=composer_y+4,width=cw-24,height=chip_h)
            else:self.attachment_bar.place_forget()
            by = composer_y+chip_h+14*s
            bh = composer_h-chip_h-28*s
            bw = max(65,78*s)
            self.buttons["attach"].place(x=x+12*s,y=by,width=32*s,height=bh)
            # Three visible action buttons preserve an immediate stop control.
            for i,key in enumerate(("send","stop","sleep")):
                self.buttons[key].place(x=x+cw-(3-i)*(bw+7*s)-10*s,y=by,width=bw,height=bh)
            self.input_box.place(x=x+50*s,y=by-2,width=cw-3*(bw+7*s)-76*s,height=bh+4)
            self.text(x+8,bottom+11*s,"ENTER TO SEND   /   SHIFT + ENTER FOR A NEW LINE",8)
            self.clock_id = self.text(w-gap,bottom+11*s,time.strftime("%H:%M:%S"),10,CYAN,anchor="ne")
            sx = x+cw+gap
            sw = w-sx-gap
            self.stat_ids = {}
            for i,label in enumerate(("CPU LOAD","MEMORY USAGE")):
                yy = top+i*140*s
                self.text(sx,yy,label,11,MUTED)
                panel(c,sx,yy+28*s,sw,91*s,fill="#0d2431",outline="#396879")
                val = self.text(sx+16*s,yy+43*s,"—",30,CYAN)
                bar = c.create_rectangle(sx+12*s,yy+103*s,sx+12*s,yy+107*s,fill=CYAN,outline="",tags="scene")
                c.create_line(sx+12*s,yy+107*s,sx+sw-12*s,yy+107*s,fill=EDGE,tags="scene")
                self.stat_ids[label] = (val,bar,sx+12*s,yy+103*s,sw-24*s)
            self.text(sx,top+303*s,"SESSION",10)
            self.uptime_id = self.text(sx,top+329*s,"00:00:00",18,WHITE)
            self.text(sx,top+375*s,"MODEL",10)
            model = str(getattr(self.app_module,"OLLAMA_MODEL","Local model"))
            self.text(sx,top+400*s,model,11,CYAN,width=sw)
            my = max(top+460*s,bottom-207*s)
            self.text(sx,my,"MEDIA",11)
            panel(c,sx,my+28*s,sw,139*s,fill="#0c222f",outline="#396879")
            self.media_title_id = self.text(sx+14*s,my+43*s,self.media_title,13,CYAN,width=sw-28*s)
            self.media_artist_id = self.text(sx+14*s,my+83*s,self.media_artist,9,MUTED,width=sw-28*s)
            self.buttons["media"].place(x=sx+12*s,y=my+123*s,width=sw-24*s,height=28*s)
            self.wave_bounds = (x+cw*.72,top+18*s,cw*.24,24*s)
            self._update_stats()
            self.show_view(self.mode,relayout=False)

        def _control_enter(self,event):
            self.send_message()
            return "break"

        def _activity(self,event=None):
            module = sys.modules.get("jarvis_maintainer_v1")
            if module and hasattr(module,"touch_activity"):
                module.touch_activity()

        def _patch_log(self):
            def proxy(message):
                if self.original_log:
                    self.original_log(message)
                # The original append_log callback handles queued messages. If the
                # host has no log consumer (preview/custom app), use our own queue.
                if not callable(getattr(self.app_instance,"append_log",None)):
                    self.handle_log(message)
            self.log_proxy = proxy
            self.app_module.log = proxy

        def handle_log(self,message):
            self._put("log",str(message))

        def _put(self,kind,value):
            try:self.events.put_nowait((kind,value))
            except queue.Full:
                # Backpressure in the display does not discard the host's original log.
                pass

        def say(self,role,text):
            self._put("message",(role,str(text)))

        def log_message(self,role,text):
            self.say(role,text)

        def _drain(self):
            for _ in range(100):
                try:kind,value=self.events.get_nowait()
                except queue.Empty:break
                if kind=="message":
                    role,text=value
                    if role!="user" or not ghost_filter(text):self.chat.add_message(role,text)
                elif kind=="log":
                    # Base parser only calls log_message, which queues for the next pass.
                    Base.handle_log(self,value)
                elif kind=="media":
                    self.media_pending=False
                    self.media_title,self.media_artist=value
                    self.overlay.itemconfigure(self.media_title_id,text=self.media_title)
                    self.overlay.itemconfigure(self.media_artist_id,text=self.media_artist)
                    self.buttons["media"].configure(text="REFRESH",state="normal")
            self._later(80,self._drain)

        def _status_tick(self):
            event = getattr(self.app_module,"speaking_now",None)
            self.speech = bool(event and hasattr(event,"is_set") and event.is_set())
            self.reactor.set_talking(self.speech)
            if self.telemetry:
                try:
                    self.cpu = self.telemetry.cpu_percent(interval=None)
                    self.memory = self.telemetry.virtual_memory().percent
                except Exception:self.cpu=self.memory=None
            self._update_stats()
            self._later(1000,self._status_tick)

        def _update_stats(self):
            if not hasattr(self,"stat_ids"):return
            c=self.overlay
            for key,value in (("CPU LOAD",self.cpu),("MEMORY USAGE",self.memory)):
                label,bar,x,y,width=self.stat_ids[key]
                c.itemconfigure(label,text=f"{value:.0f}%" if value is not None else "N/A")
                c.coords(bar,x,y,x+width*(max(0,min(100,value))/100 if value is not None else 0),y+4*self.scale)
            sleep = getattr(self.app_module,"sleep_requested",None)
            standby = bool(sleep and hasattr(sleep,"is_set") and sleep.is_set())
            c.itemconfigure(self.voice_id,text="STANDBY" if standby else "VOICE ACTIVE" if self.speech else "SYSTEM ONLINE")
            c.itemconfigure(self.core_status_id,text="COGNITIVE CORE STATUS: "+("STANDBY" if standby else "SPEAKING" if self.speech else "OPERATIONAL"))
            c.itemconfigure(self.name_id,text=str(getattr(self.app_module,"USER_SPOKEN_NAME","Sir")))
            elapsed=int(time.monotonic()-self.started)
            c.itemconfigure(self.uptime_id,text=f"{elapsed//3600:02}:{elapsed//60%60:02}:{elapsed%60:02}")
            c.itemconfigure(self.clock_id,text=time.strftime("%H:%M:%S"))

        def _animate(self):
            # Reuse the static scene; redraw only small reactor/wave regions at 20 FPS.
            if self.root.state() not in ("iconic","withdrawn") and hasattr(self,"wave_bounds"):
                self.reactor.draw()
                self.overlay.delete("motion")
                x,y,w,h=self.wave_bounds
                phase=time.monotonic()*3
                points=[]
                for i in range(81):
                    u=i/80
                    amplitude=(.75 if self.speech else .12)*math.exp(-((u-.5)*4)**2)
                    points.extend((x+u*w,y+h+math.sin(u*42+phase)*amplitude*h))
                self.overlay.create_line(points,fill=CYAN,width=1.5,smooth=True,tags="motion")
            self._later(50,self._animate)

        def show_view(self,mode,relayout=True):
            self.mode=mode
            for key in ("chat","status","briefs"):
                self.buttons[key].configure(fg=CYAN if key==mode else MUTED,
                                            highlightbackground="#65afc4" if key==mode else EDGE)
            if not hasattr(self,"bounds"):return
            x,y,w,h,*_=self.bounds
            if mode=="chat":
                self.info.place_forget()
                self.chat.place(x=x+8,y=y+44*self.scale,width=w-16,height=h-53*self.scale)
                return
            self.chat.place_forget()
            self.info.place(x=x+8,y=y+44*self.scale,width=w-16,height=h-53*self.scale)
            module=sys.modules.get("jarvis_maintainer_v1")
            title="SYSTEM STATUS" if mode=="status" else "KEY BRIEFS"
            if mode=="status":
                maintenance = module.maintainer_status() if module and hasattr(module,"maintainer_status") else "Maintenance status is unavailable in this session."
                body=("Local model\n"+str(getattr(self.app_module,"OLLAMA_MODEL","Unavailable"))+"\n\n"+
                      "Self maintenance\n"+maintenance+"\n\n"+
                      "Interface\nVoice, attachments, chat, Stop and Standby use the existing Jarvis controls.\n\n"+
                      "System readings\nCPU and memory cards show live PC readings when psutil is installed. N/A means unavailable.")
            else:
                history=module.recent_changes() if module and hasattr(module,"recent_changes") else "No maintenance history is available in this session."
                body="RECENT MAINTENANCE\n\n"+history+"\n\nSESSION NOTES\n\nYour conversation remains in Primary Chat."
            self.info.configure(state="normal")
            self.info.delete("1.0","end")
            self.info.insert("end",title+"\n","title")
            self.info.insert("end",body)
            self.info.configure(state="disabled")

        def new_chat(self):
            self.show_view("chat")
            Base.new_chat(self)

        def add_attachments(self):
            Base.add_attachments(self)
            self._layout()

        def send_message(self):
            self._activity()
            self.show_view("chat")
            Base.send_message(self)
            self._layout()

        def stop_speaking(self):
            self._activity()
            # Keep the established emergency-stop path, not only the animation.
            interrupt=sys.modules.get("jarvis_interrupt_v1")
            if interrupt and callable(getattr(interrupt,"request_stop",None)):
                interrupt.request_stop(self.app_module,reason="hud_stop_button")
            else:
                stop=getattr(self.app_module,"stop_speaking_now",None)
                if callable(stop):stop()
                else:
                    stop=getattr(self.app_module,"stop_talking_event",None)
                    if hasattr(stop,"set"):stop.set()
            self.reactor.set_talking(False)
            self.say("system","Stop requested.")

        def sleep_mode(self):
            self._activity()
            Base.sleep_mode(self)

        def resume_voice(self):
            self._activity()
            clear=getattr(self.app_module,"clear_sleep_mode",None)
            if not callable(clear):clear=getattr(self.app_module,"reset_sleep_mode",None)
            if not callable(clear):clear=getattr(self.app_module,"wake_from_sleep_if_needed",None)
            if callable(clear):
                clear()
                self.say("system","Standby cleared. Ready for your wake word.")
            else:
                self.say("system","Use your normal wake word to resume Jarvis.")

        def refresh_media(self):
            if self.media_pending:return
            self.media_pending=True
            self.buttons["media"].configure(text="CHECKING…",state="disabled")
            def read():
                module=sys.modules.get("jarvis_spotify_v2")
                title,artist="No active playback","Spotify not connected or idle"
                try:
                    if module and callable(getattr(module,"current_player",None)):
                        player=module.current_player()
                        item=(player or {}).get("item") or {}
                        if item:
                            title=str(item.get("name","Unknown track"))
                            artist=", ".join(str(a.get("name","")) for a in item.get("artists",[]))
                except Exception:title,artist="Playback unavailable","Try refreshing again later"
                self._put("media",(title,artist))
            threading.Thread(target=read,daemon=True,name="JarvisHUDMedia").start()

    return JarvisHUD
