import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import json
import os
import sys
import threading
import time
import logging
from datetime import datetime, timedelta
import pystray
from PIL import Image, ImageDraw
import winreg
import winsound
import ctypes

# 配置日志
logging.basicConfig(
    filename='todo_app.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

DATA_FILE = "todos.json"
APP_NAME = "MyTodoApp_LJK"
MUTEX_NAME = "Global\\MyTodoApp_LJK_Mutex"

class TodoApp:
    def __init__(self, start_minimized=False):
        # 确保单例运行
        self.mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if ctypes.windll.kernel32.GetLastError() == 183: # ERROR_ALREADY_EXISTS
            messagebox.showwarning("提示", "程序已经在运行中了！请查看右下角系统托盘。")
            sys.exit(0)
            
        # 初始化界面风格
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        
        self.root = ctk.CTk()
        self.root.title("桌面待办事项 (To-Do)")
        self.root.geometry("700x600")
        self.root.resizable(False, False)
        
        self.tasks = []
        self.load_tasks()
        
        self.setup_ui()
        
        # 启动后台检查线程
        self.running = True
        self.check_thread = threading.Thread(target=self.check_schedule, daemon=True)
        self.check_thread.start()
        
        # 拦截关闭窗口事件
        self.root.protocol('WM_DELETE_WINDOW', self.hide_window)
        self.icon = None
        
        # 如果是开机自启，则直接隐藏到后台
        if start_minimized:
            self.root.after(0, self.hide_window)

    def check_autostart(self):
        """检查是否已经设置了开机自启"""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, APP_NAME)
            winreg.CloseKey(key)
            return True
        except WindowsError:
            return False

    def toggle_autostart(self):
        """切换开机自启状态"""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
            if self.autostart_var.get() == 1:
                # 使用 pythonw 隐藏控制台黑框运行当前脚本，并增加 --minimized 参数使其开机时不弹出界面
                python_w_exe = sys.executable.replace("python.exe", "pythonw.exe")
                script_path = os.path.abspath(sys.argv[0])
                cmd = f'"{python_w_exe}" "{script_path}" --minimized'
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
            else:
                winreg.DeleteValue(key, APP_NAME)
            winreg.CloseKey(key)
        except Exception as e:
            print("设置开机自启失败:", e)

    def sort_tasks(self):
        """将任务进行排序：未提醒的在前（按时间升序），已提醒的在后（按时间降序）"""
        self.tasks.sort(key=lambda x: (x.get('notified', False), x['time']))

    def clear_completed(self):
        """清理所有已提醒的任务"""
        self.tasks = [t for t in self.tasks if not t.get("notified", False)]
        self.save_tasks()
        self.update_task_list()

    def set_quick_time(self, delta_minutes):
        """快捷设置时间"""
        new_time = datetime.now() + timedelta(minutes=delta_minutes)
        self.year_combo.set(str(new_time.year))
        self.month_combo.set(f"{new_time.month:02d}")
        self.day_combo.set(f"{new_time.day:02d}")
        self.hour_combo.set(f"{new_time.hour:02d}")
        self.minute_combo.set(f"{new_time.minute:02d}")

    def reset_time_to_now(self):
        """重置下拉框时间为当前时间"""
        now = datetime.now()
        self.year_combo.set(str(now.year))
        self.month_combo.set(f"{now.month:02d}")
        self.day_combo.set(f"{now.day:02d}")
        self.hour_combo.set(f"{now.hour:02d}")
        self.minute_combo.set(f"{now.minute:02d}")

    def setup_ui(self):
        """初始化现代化的UI界面"""
        # 标题
        title_lbl = ctk.CTkLabel(self.root, text="📝 我的待办事项", font=ctk.CTkFont(size=26, weight="bold"))
        title_lbl.pack(pady=(20, 10))
        
        # 输入区域
        input_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        input_frame.pack(pady=10, padx=20, fill="x")
        
        # 第一行：任务内容
        task_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
        task_frame.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(task_frame, text="任务内容:").pack(side="left", padx=(0, 10))
        self.task_entry = ctk.CTkEntry(task_frame, placeholder_text="输入任务内容... (按 Enter 键可直接添加)")
        self.task_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        # 绑定回车键
        self.task_entry.bind('<Return>', lambda event: self.add_task())
        
        # 第二行：时间选择
        datetime_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
        datetime_frame.pack(fill="x", pady=(0, 10))
        
        now = datetime.now()
        
        ctk.CTkLabel(datetime_frame, text="提醒时间:").pack(side="left", padx=(0, 10))
        
        self.year_combo = ctk.CTkComboBox(datetime_frame, values=[str(y) for y in range(now.year, now.year + 5)], width=75)
        self.year_combo.set(str(now.year))
        self.year_combo.pack(side="left", padx=(0, 2))
        ctk.CTkLabel(datetime_frame, text="年").pack(side="left", padx=(0, 5))
        
        self.month_combo = ctk.CTkComboBox(datetime_frame, values=[f"{m:02d}" for m in range(1, 13)], width=65)
        self.month_combo.set(f"{now.month:02d}")
        self.month_combo.pack(side="left", padx=(0, 2))
        ctk.CTkLabel(datetime_frame, text="月").pack(side="left", padx=(0, 5))
        
        self.day_combo = ctk.CTkComboBox(datetime_frame, values=[f"{d:02d}" for d in range(1, 32)], width=65)
        self.day_combo.set(f"{now.day:02d}")
        self.day_combo.pack(side="left", padx=(0, 2))
        ctk.CTkLabel(datetime_frame, text="日").pack(side="left", padx=(0, 15))
        
        self.hour_combo = ctk.CTkComboBox(datetime_frame, values=[f"{i:02d}" for i in range(24)], width=65)
        self.hour_combo.set(f"{now.hour:02d}")
        self.hour_combo.pack(side="left", padx=(0, 2))
        ctk.CTkLabel(datetime_frame, text=":").pack(side="left", padx=(0, 2))
        
        self.minute_combo = ctk.CTkComboBox(datetime_frame, values=[f"{i:02d}" for i in range(60)], width=65)
        self.minute_combo.set(f"{now.minute:02d}")
        self.minute_combo.pack(side="left", padx=(0, 15))
        
        # 第三行：快捷操作与添加按钮
        action_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
        action_frame.pack(fill="x")
        
        ctk.CTkLabel(action_frame, text="快捷时间:").pack(side="left", padx=(0, 10))
        ctk.CTkButton(action_frame, text="+10分钟", width=60, fg_color="#5bc0de", hover_color="#46b8da", command=lambda: self.set_quick_time(10)).pack(side="left", padx=(0, 5))
        ctk.CTkButton(action_frame, text="+1小时", width=60, fg_color="#5bc0de", hover_color="#46b8da", command=lambda: self.set_quick_time(60)).pack(side="left", padx=(0, 5))
        ctk.CTkButton(action_frame, text="明天此时", width=60, fg_color="#5bc0de", hover_color="#46b8da", command=lambda: self.set_quick_time(24*60)).pack(side="left", padx=(0, 15))
        
        now_btn = ctk.CTkButton(action_frame, text="重置为当前", width=70, fg_color="gray", hover_color="darkgray", command=self.reset_time_to_now)
        now_btn.pack(side="left", padx=(0, 10))
        
        add_btn = ctk.CTkButton(action_frame, text="添加任务", width=120, height=32, font=ctk.CTkFont(weight="bold"), command=self.add_task)
        add_btn.pack(side="right")
        
        # 任务列表区域 (可滚动)
        self.scrollable_frame = ctk.CTkScrollableFrame(self.root, label_text="待办任务列表", label_font=ctk.CTkFont(size=14, weight="bold"))
        self.scrollable_frame.pack(pady=10, padx=20, fill="both", expand=True)
        
        self.task_widgets = []
        self.update_task_list()
        
        # 底部设置区域
        bottom_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        bottom_frame.pack(pady=15, padx=20, fill="x")
        
        self.autostart_var = tk.IntVar(value=1 if self.check_autostart() else 0)
        autostart_cb = ctk.CTkCheckBox(bottom_frame, text="开机自启", variable=self.autostart_var, command=self.toggle_autostart)
        autostart_cb.pack(side="left")
        
        self.sound_var = tk.IntVar(value=1)
        sound_cb = ctk.CTkCheckBox(bottom_frame, text="提前1分钟提示音", variable=self.sound_var)
        sound_cb.pack(side="left", padx=(15, 0))
        
        clear_btn = ctk.CTkButton(bottom_frame, text="清理已完成", width=90, fg_color="#d9534f", hover_color="#c9302c", command=self.clear_completed)
        clear_btn.pack(side="left", padx=(20, 0))
        
        tip_lbl = ctk.CTkLabel(bottom_frame, text="提示: 关闭窗口将隐藏到后台运行", text_color="gray", font=ctk.CTkFont(size=12))
        tip_lbl.pack(side="right")

    def load_tasks(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    self.tasks = json.load(f)
            except Exception:
                self.tasks = []
        else:
            self.tasks = []
        self.sort_tasks()

    def save_tasks(self):
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.tasks, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"保存任务失败: {e}")

    def update_task_list(self):
        # 清除旧组件
        for widget in self.task_widgets:
            widget.destroy()
        self.task_widgets.clear()
        
        now = datetime.now()
        
        # 渲染任务
        for i, task in enumerate(self.tasks):
            frame = ctk.CTkFrame(self.scrollable_frame, fg_color=("gray85", "gray25"))
            frame.pack(fill="x", pady=5, padx=5)
            
            is_notified = task.get("notified", False)
            text_color = "gray" if is_notified else ("black", "white")
            
            # 计算剩余时间
            status_text = "✅ 已提醒"
            if not is_notified:
                try:
                    task_dt = datetime.strptime(task["time"], "%Y-%m-%d %H:%M")
                    delta = task_dt - now
                    if delta.total_seconds() > 0:
                        days = delta.days
                        hours, remainder = divmod(delta.seconds, 3600)
                        minutes, _ = divmod(remainder, 60)
                        
                        if days > 0:
                            status_text = f"⏳ 剩 {days}天{hours}小时"
                        elif hours > 0:
                            status_text = f"⏳ 剩 {hours}小时{minutes}分"
                        else:
                            status_text = f"⏳ 剩 {minutes}分钟"
                    else:
                        status_text = "⏳ 即将提醒"
                except:
                    status_text = "⏳ 待提醒"
            
            lbl_time = ctk.CTkLabel(frame, text=f"[{task['time']}]", font=ctk.CTkFont(weight="bold"), text_color=text_color)
            lbl_time.pack(side="left", padx=(15, 5), pady=10)
            
            lbl_content = ctk.CTkLabel(frame, text=task['content'], text_color=text_color)
            lbl_content.pack(side="left", padx=5, pady=10)
            
            lbl_status = ctk.CTkLabel(frame, text=status_text, text_color=text_color)
            lbl_status.pack(side="left", padx=15, pady=10)
            
            del_btn = ctk.CTkButton(frame, text="删除", width=60, fg_color="#d9534f", hover_color="#c9302c", 
                                    command=lambda index=i: self.delete_task(index))
            del_btn.pack(side="right", padx=15, pady=10)
            
            self.task_widgets.append(frame)

    def add_task(self):
        content = self.task_entry.get().strip()
        y = self.year_combo.get()
        mon = self.month_combo.get()
        d = self.day_combo.get()
        hour = self.hour_combo.get()
        minute = self.minute_combo.get()
        time_str = f"{y}-{mon}-{d} {hour}:{minute}"
        
        if not content:
            messagebox.showwarning("提示", "任务内容不能为空！")
            return
            
        try:
            task_dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
        except ValueError:
            messagebox.showwarning("提示", "日期无效 (例如选择了不存在的31日)！")
            return
            
        if task_dt < datetime.now():
            messagebox.showwarning("提示", "设置的时间不能早于当前时间！")
            return
            
        self.tasks.append({
            "content": content,
            "time": time_str,
            "notified": False
        })
        self.sort_tasks()
        self.save_tasks()
        self.update_task_list()
        self.task_entry.delete(0, tk.END)

    def delete_task(self, index):
        if 0 <= index < len(self.tasks):
            del self.tasks[index]
            self.save_tasks()
            self.update_task_list()

    def check_schedule(self):
        while self.running:
            now = datetime.now()
            changed = False
            for task in self.tasks:
                if not task.get("notified"):
                    try:
                        task_dt = datetime.strptime(task["time"], "%Y-%m-%d %H:%M")
                    except ValueError:
                        try:
                            # 兼容旧版本格式 HH:MM
                            time_obj = datetime.strptime(task["time"], "%H:%M").time()
                            task_dt = datetime.combine(now.date(), time_obj)
                        except ValueError:
                            continue
                            
                    # 预警机制：如果设置了开启，并且离任务还有不到1分钟且未预警过
                    if self.sound_var.get() == 1 and not task.get("pre_warned") and 0 < (task_dt - now).total_seconds() <= 60:
                        try:
                            winsound.MessageBeep(winsound.MB_ICONASTERISK) # 轻微的滴声
                            task["pre_warned"] = True
                            changed = True
                        except:
                            pass

                    # 如果当前时间大于等于任务时间，则正式提醒
                    if now >= task_dt:
                        logging.info(f"Triggered notification for task: {task['content']}")
                        # 在主线程中弹出提醒，将整个 task 传过去以便推迟操作修改
                        self.root.after(0, self.show_popup, task)
                        task["notified"] = True
                        changed = True
            
            if changed:
                self.sort_tasks()
                self.save_tasks()
                self.root.after(0, self.update_task_list)
                
            time.sleep(5) # 提高检查频率到5秒，以便更精准预警

    def show_popup(self, task):
        """在屏幕中央显示提醒弹窗"""
        try:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except:
            pass
            
        popup = ctk.CTkToplevel(self.root)
        popup.title("任务提醒")
        
        # 强制更新窗口以获取正确的屏幕宽高
        popup.update_idletasks()
        
        w = 400
        h = 250
        sw = popup.winfo_screenwidth()
        sh = popup.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        popup.geometry(f"{w}x{h}+{x}+{y}")
        popup.attributes("-topmost", True)  # 保持置顶
        
        lbl_title = ctk.CTkLabel(popup, text="⏰ 提醒时间到！", font=ctk.CTkFont(size=22, weight="bold"), text_color="#f0ad4e")
        lbl_title.pack(pady=(30, 10))
        
        lbl_content = ctk.CTkLabel(popup, text=task["content"], font=ctk.CTkFont(size=18), wraplength=350)
        lbl_content.pack(pady=20, expand=True)
        
        def snooze():
            """推迟 10 分钟"""
            new_dt = datetime.now() + timedelta(minutes=10)
            task["time"] = new_dt.strftime("%Y-%m-%d %H:%M")
            task["notified"] = False
            self.sort_tasks()
            self.save_tasks()
            self.update_task_list()
            popup.destroy()
            
        btn_frame = ctk.CTkFrame(popup, fg_color="transparent")
        btn_frame.pack(pady=(10, 30))
        
        btn_ok = ctk.CTkButton(btn_frame, text="我知道了", command=popup.destroy, width=120, height=40)
        btn_ok.pack(side="left", padx=10)
        
        btn_snooze = ctk.CTkButton(btn_frame, text="推迟 10 分钟", command=snooze, width=120, height=40, fg_color="#5bc0de", hover_color="#46b8da")
        btn_snooze.pack(side="left", padx=10)
        
        # 即使主窗口被隐藏，也能正常显示和聚焦弹窗
        popup.deiconify()
        popup.lift()
        popup.focus_force()

    def create_image(self):
        """生成一个简单的系统托盘图标"""
        image = Image.new('RGBA', (64, 64), color=(0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((4, 4, 60, 60), fill=(30, 144, 255))
        draw.line((16, 32, 28, 44, 48, 20), fill="white", width=6)
        return image

    def hide_window(self):
        """隐藏主窗口并显示系统托盘图标"""
        self.root.withdraw()
        if not self.icon:
            menu = (
                pystray.MenuItem('显示主界面', self.show_window, default=True),
                pystray.MenuItem('退出程序', self.quit_window)
            )
            self.icon = pystray.Icon("todo_app", self.create_image(), "待办事项 (运行中)", menu)
            # 必须在独立线程中运行托盘图标，以免阻塞Tkinter的mainloop
            threading.Thread(target=self.icon.run, daemon=True).start()

    def show_window(self, icon, item):
        """从系统托盘恢复主窗口"""
        if self.icon:
            self.icon.stop()
            self.icon = None
        self.root.after(0, self.root.deiconify)

    def quit_window(self, icon, item):
        """完全退出程序"""
        if self.icon:
            self.icon.stop()
        self.running = False
        self.root.after(0, self.root.destroy)
        self.root.after(0, self.root.quit)

if __name__ == "__main__":
    start_minimized = "--minimized" in sys.argv
    app = TodoApp(start_minimized)
    app.root.mainloop()
