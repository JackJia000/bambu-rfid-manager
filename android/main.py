#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bambu Lab RFID Tag Manager - Android Pro Version
集成完整PN532协议支持
"""

import os
import sys
import json
import time
import threading
from datetime import datetime

# Kivy导入
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelHeader
from kivy.clock import Clock
from kivy.graphics import Color, RoundedRectangle
from kivy.utils import get_color_from_hex
from kivy.core.window import Window
from kivy.logger import Logger

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入PN532协议
try:
    from pn532 import PN532Protocol, NTAG215, BambuTagParser, PN532Error
    HAS_PN532 = True
except ImportError as e:
    HAS_PN532 = False
    Logger.error(f"PN532导入失败: {e}")

# Android导入
try:
    from android.permissions import request_permissions, Permission
    IS_ANDROID = True
except ImportError:
    IS_ANDROID = False
    Logger.info("非Android环境，使用模拟模式")

# 串口导入
try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False
    Logger.warning("缺少pyserial库")

# 主题配色
class Theme:
    BG = get_color_from_hex('#0d1117')
    SURFACE = get_color_from_hex('#161b22')
    CARD = get_color_from_hex('#21262d')
    TEXT = get_color_from_hex('#c9d1d9')
    TEXT_SEC = get_color_from_hex('#8b949e')
    BLUE = get_color_from_hex('#58a6ff')
    GREEN = get_color_from_hex('#3fb950')
    RED = get_color_from_hex('#f85149')
    ORANGE = get_color_from_hex('#d29922')
    PURPLE = get_color_from_hex('#a371f7')

class StyledLabel(Label):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.color = Theme.TEXT
        self.font_size = '14sp'
        self.markup = True
        self.valign = 'middle'

class StyledButton(Button):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ''
        self.background_color = Theme.BLUE
        self.color = (1, 1, 1, 1)
        self.font_size = '14sp'
        self.size_hint_y = None
        self.height = '48dp'

class Card(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = '15dp'
        self.spacing = '10dp'
        self.size_hint_y = None
        self.bind(minimum_height=self.setter('height'))
        with self.canvas.before:
            Color(*Theme.CARD)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[12])
        self.bind(pos=self.update_rect, size=self.update_rect)
    
    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size

class RFIDWorker(threading.Thread):
    """RFID工作线程"""
    def __init__(self, manager, operation, **kwargs):
        super().__init__(daemon=True)
        self.manager = manager
        self.operation = operation
        self.kwargs = kwargs
    
    def run(self):
        try:
            if self.operation == 'read':
                self.do_read()
            elif self.operation == 'write':
                self.do_write()
            elif self.operation == 'clone':
                self.do_clone()
            elif self.operation == 'format':
                self.do_format()
        except Exception as e:
            Clock.schedule_once(lambda dt: self.manager.on_error(str(e)), 0)
    
    def do_read(self):
        """执行读取"""
        Clock.schedule_once(lambda dt: self.manager.update_status("正在初始化..."), 0)
        
        if not self.manager.pn532.sam_configuration():
            raise Exception("SAM配置失败")
        
        Clock.schedule_once(lambda dt: self.manager.update_progress(20), 0)
        Clock.schedule_once(lambda dt: self.manager.update_status("等待标签..."), 0)
        
        target = self.manager.pn532.read_passive_target_id(timeout=5.0)
        if not target:
            raise Exception("未检测到标签，请检查标签是否放置正确")
        
        Clock.schedule_once(lambda dt: self.manager.update_progress(40), 0)
        Clock.schedule_once(lambda dt: self.manager.update_status(f"检测到标签: {target['uid_hex']}"), 0)
        
        uid = target['uid']
        ntag = NTAG215(self.manager.pn532, uid)
        
        pages = {}
        for page in range(4, 21):
            data = ntag.read_page(page)
            if data:
                pages[page] = data
            progress = 40 + int((page - 4) / 16 * 40)
            Clock.schedule_once(lambda dt, p=progress: self.manager.update_progress(p), 0)
        
        Clock.schedule_once(lambda dt: self.manager.update_progress(90), 0)
        
        parsed = BambuTagParser.parse(pages)
        
        tag_data = {
            'uid': target['uid_hex'],
            'tag_type': 'NTAG215',
            'material': parsed.get('material', 'Unknown'),
            'color': parsed.get('color', 'Unknown'),
            'nozzle_temp': parsed.get('nozzle_temp', 0),
            'bed_temp': parsed.get('bed_temp', 0),
            'total_weight': parsed.get('total_weight', 0),
            'remaining_weight': parsed.get('remaining_weight', 0),
            'is_bambu_tag': parsed.get('is_bambu_tag', False),
            'is_encrypted': parsed.get('is_encrypted', True),
            'raw_pages': parsed.get('raw_pages', {}),
            'timestamp': datetime.now().isoformat()
        }
        
        Clock.schedule_once(lambda dt: self.manager.update_progress(100), 0)
        Clock.schedule_once(lambda dt: self.manager.on_read_complete(tag_data), 0)
    
    def do_write(self):
        """执行写入"""
        data = self.kwargs.get('data', {})
        Clock.schedule_once(lambda dt: self.manager.update_status("等待放置空白标签..."), 0)
        
        target = self.manager.pn532.read_passive_target_id(timeout=5.0)
        if not target:
            raise Exception("未检测到标签")
        
        Clock.schedule_once(lambda dt: self.manager.update_progress(30), 0)
        ntag = NTAG215(self.manager.pn532, target['uid'])
        
        ndef_data = json.dumps(data).encode('utf-8')
        
        if not ntag.write_ndef_message(ndef_data):
            raise Exception("写入失败")
        
        Clock.schedule_once(lambda dt: self.manager.update_progress(100), 0)
        Clock.schedule_once(lambda dt: self.manager.on_write_complete(), 0)
    
    def do_clone(self):
        """执行克隆"""
        Clock.schedule_once(lambda dt: self.manager.update_status("克隆功能开发中..."), 0)
        time.sleep(1)
        Clock.schedule_once(lambda dt: self.manager.on_clone_complete(), 0)
    
    def do_format(self):
        """执行格式化"""
        Clock.schedule_once(lambda dt: self.manager.update_status("等待标签..."), 0)
        
        target = self.manager.pn532.read_passive_target_id(timeout=5.0)
        if not target:
            raise Exception("未检测到标签")
        
        ntag = NTAG215(self.manager.pn532, target['uid'])
        
        if not ntag.erase_user_memory():
            raise Exception("格式化失败")
        
        Clock.schedule_once(lambda dt: self.manager.on_format_complete(), 0)

class BambuRFIDManager(BoxLayout):
    """主管理器类"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = '10dp'
        self.spacing = '10dp'
        
        self.serial_port = None
        self.pn532 = None
        self.current_tag = None
        self.tag_history = []
        self.worker = None
        self.is_connected = False
        
        Window.clearcolor = Theme.BG
        self.build_ui()
        
        if IS_ANDROID:
            Clock.schedule_once(self.request_permissions, 1)
    
    def request_permissions(self, dt):
        """请求权限"""
        try:
            request_permissions([
                Permission.INTERNET,
                Permission.WRITE_EXTERNAL_STORAGE,
                Permission.READ_EXTERNAL_STORAGE,
            ], self.on_permissions_result)
        except Exception as e:
            self.log(f"权限请求失败: {e}")
    
    def on_permissions_result(self, permissions, grants):
        """权限请求回调"""
        if all(grants):
            self.log("所有权限已授予")
        else:
            self.log("部分权限被拒绝")
    
    def build_ui(self):
        """构建UI"""
        title = StyledLabel(
            text='[b]Bambu Lab RFID Manager Pro[/b]',
            font_size='22sp',
            size_hint_y=None,
            height='56dp',
            color=Theme.BLUE
        )
        self.add_widget(title)
        
        self.tabs = TabbedPanel(
            do_default_tab=False,
            tab_width='100dp',
            background_color=Theme.SURFACE,
            tab_height='42dp'
        )
        
        conn_tab = TabbedPanelHeader(text='[b]连接[/b]')
        conn_tab.content = self.build_connection_tab()
        self.tabs.add_widget(conn_tab)
        
        read_tab = TabbedPanelHeader(text='[b]读取[/b]')
        read_tab.content = self.build_read_tab()
        self.tabs.add_widget(read_tab)
        
        write_tab = TabbedPanelHeader(text='[b]写入[/b]')
        write_tab.content = self.build_write_tab()
        self.tabs.add_widget(write_tab)
        
        data_tab = TabbedPanelHeader(text='[b]数据[/b]')
        data_tab.content = self.build_data_tab()
        self.tabs.add_widget(data_tab)
        
        log_tab = TabbedPanelHeader(text='[b]日志[/b]')
        log_tab.content = self.build_log_tab()
        self.tabs.add_widget(log_tab)
        
        self.add_widget(self.tabs)
        
        self.status_bar = StyledLabel(
            text='就绪 - 请连接设备',
            size_hint_y=None,
            height='32dp',
            color=Theme.TEXT_SEC,
            font_size='12sp'
        )
        self.add_widget(self.status_bar)
    
    def build_connection_tab(self):
        """构建连接标签页"""
        layout = BoxLayout(orientation='vertical', spacing='15dp', padding='15dp')
        
        card = Card()
        card.add_widget(StyledLabel(text='[b]设备连接[/b]', font_size='16sp', color=Theme.BLUE))
        
        port_box = BoxLayout(size_hint_y=None, height='45dp', spacing='10dp')
        port_box.add_widget(StyledLabel(text='串口:', size_hint_x=0.25))
        
        self.port_input = TextInput(
            text='/dev/ttyUSB0',
            multiline=False,
            background_color=(0.15, 0.15, 0.15, 1),
            foreground_color=Theme.TEXT,
            cursor_color=Theme.BLUE,
            padding=('12dp', '12dp'),
            font_name='monospace'
        )
        port_box.add_widget(self.port_input)
        
        refresh_btn = Button(
            text='R',
            size_hint_x=0.15,
            background_color=Theme.SURFACE,
            background_normal=''
        )
        refresh_btn.bind(on_press=self.refresh_ports)
        port_box.add_widget(refresh_btn)
        
        card.add_widget(port_box)
        
        self.connect_btn = StyledButton(text='连接设备')
        self.connect_btn.bind(on_press=self.toggle_connection)
        card.add_widget(self.connect_btn)
        
        self.fw_label = StyledLabel(
            text='固件: 未连接',
            color=Theme.TEXT_SEC,
            font_size='12sp'
        )
        card.add_widget(self.fw_label)
        
        layout.add_widget(card)
        
        info_card = Card()
        info_card.add_widget(StyledLabel(text='[b]硬件信息[/b]', font_size='16sp'))
        
        info_text = (
            "支持PN532 NFC模块 (UART模式)\n"
            "支持NTAG215/216标签\n"
            "USB-TTL转接板 (CH340/CP2102)\n\n"
            "接线说明:\n"
            "PN532 VCC -> 3.3V/5V\n"
            "PN532 GND -> GND\n"
            "PN532 TXD -> RXD\n"
            "PN532 RXD -> TXD\n\n"
            "注意: 确保PN532设置为UART模式"
        )
        
        info_label = StyledLabel(
            text=info_text,
            color=Theme.TEXT_SEC,
            font_size='13sp'
        )
        info_card.add_widget(info_label)
        
        layout.add_widget(info_card)
        layout.add_widget(Label())
        
        scroll = ScrollView()
        scroll.add_widget(layout)
        return scroll
    
    def build_read_tab(self):
        """构建读取标签页"""
        layout = BoxLayout(orientation='vertical', spacing='12dp', padding='15dp')
        
        self.read_btn = StyledButton(
            text='读取标签',
            disabled=True,
            background_color=Theme.GREEN
        )
        self.read_btn.bind(on_press=self.start_read)
        layout.add_widget(self.read_btn)
        
        self.progress = ProgressBar(max=100, value=0, size_hint_y=None, height='6dp')
        layout.add_widget(self.progress)
        
        self.uid_label = StyledLabel(
            text='UID: 等待读取...',
            font_size='20sp',
            color=Theme.BLUE,
            size_hint_y=None,
            height='40dp'
        )
        layout.add_widget(self.uid_label)
        
        info_card = Card()
        info_card.add_widget(StyledLabel(text='[b]标签信息[/b]', font_size='16sp', color=Theme.GREEN))
        
        grid = GridLayout(cols=2, spacing='10dp', size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))
        
        self.info_labels = {}
        labels = [
            ('type', '类型', 'Unknown'),
            ('material', '材料', '--'),
            ('color', '颜色', '--'),
            ('temp', '温度', '--'),
            ('weight', '重量', '--'),
            ('crypto', '加密', '--')
        ]
        
        for key, label, default in labels:
            grid.add_widget(StyledLabel(
                text=f'{label}:',
                size_hint_y=None,
                height='35dp',
                color=Theme.TEXT_SEC
            ))
            lbl = StyledLabel(text=default, size_hint_y=None, height='35dp', font_size='15sp')
            self.info_labels[key] = lbl
            grid.add_widget(lbl)
        
        info_card.add_widget(grid)
        layout.add_widget(info_card)
        
        layout.add_widget(StyledLabel(
            text='[b]原始内存数据[/b]',
            size_hint_y=None,
            height='30dp',
            color=Theme.ORANGE
        ))
        
        self.raw_text = TextInput(
            multiline=True,
            readonly=True,
            background_color=(0.1, 0.1, 0.1, 1),
            foreground_color=Theme.TEXT,
            font_name='monospace',
            font_size='12sp',
            padding=('10dp', '10dp')
        )
        layout.add_widget(self.raw_text)
        
        return layout
    
    def build_write_tab(self):
        """构建写入标签页"""
        layout = BoxLayout(orientation='vertical', spacing='15dp', padding='15dp')
        
        write_card = Card()
        write_card.add_widget(StyledLabel(text='[b]写入新标签[/b]', font_size='16sp', color=Theme.PURPLE))
        
        form = GridLayout(cols=2, spacing='12dp', size_hint_y=None)
        form.bind(minimum_height=form.setter('height'))
        
        form.add_widget(StyledLabel(text='材料类型:', size_hint_y=None, height='45dp'))
        self.w_material = Spinner(
            text='PLA',
            values=['PLA', 'PETG', 'ABS', 'ASA', 'TPU', 'PC', 'PA', 'Custom'],
            background_color=(0.2, 0.2, 0.2, 1),
            size_hint_y=None,
            height='45dp'
        )
        form.add_widget(self.w_material)
        
        form.add_widget(StyledLabel(text='颜色:', size_hint_y=None, height='45dp'))
        self.w_color = TextInput(
            text='#FF0000',
            multiline=False,
            background_color=(0.2, 0.2, 0.2, 1),
            foreground_color=Theme.TEXT,
            size_hint_y=None,
            height='45dp'
        )
        form.add_widget(self.w_color)
        
        form.add_widget(StyledLabel(text='喷嘴温度(C):', size_hint_y=None, height='45dp'))
        self.w_nozzle = TextInput(
            text='200',
            multiline=False,
            input_filter='int',
            background_color=(0.2, 0.2, 0.2, 1),
            foreground_color=Theme.TEXT,
            size_hint_y=None,
            height='45dp'
        )
        form.add_widget(self.w_nozzle)
        
        form.add_widget(StyledLabel(text='热床温度(C):', size_hint_y=None, height='45dp'))
        self.w_bed = TextInput(
            text='60',
            multiline=False,
            input_filter='int',
            background_color=(0.2, 0.2, 0.2, 1),
            foreground_color=Theme.TEXT,
            size_hint_y=None,
            height='45dp'
        )
        form.add_widget(self.w_bed)
        
        form.add_widget(StyledLabel(text='总重量(g):', size_hint_y=None, height='45dp'))
        self.w_total = TextInput(
            text='1000',
            multiline=False,
            input_filter='int',
            background_color=(0.2, 0.2, 0.2, 1),
            foreground_color=Theme.TEXT,
            size_hint_y=None,
            height='45dp'
        )
        form.add_widget(self.w_total)
        
        form.add_widget(StyledLabel(text='剩余重量(g):', size_hint_y=None, height='45dp'))
        self.w_remain = TextInput(
            text='1000',
            multiline=False,
            input_filter='int',
            background_color=(0.2, 0.2, 0.2, 1),
            foreground_color=Theme.TEXT,
            size_hint_y=None,
            height='45dp'
        )
        form.add_widget(self.w_remain)
        
        write_card.add_widget(form)
        
        warning = StyledLabel(
            text='注意: 自定义标签可能无法被Bambu AMS识别',
            color=Theme.ORANGE,
            font_size='12sp'
        )
        write_card.add_widget(warning)
        
        self.write_btn = StyledButton(text='写入标签', disabled=True, background_color=Theme.PURPLE)
        self.write_btn.bind(on_press=self.start_write)
        write_card.add_widget(self.write_btn)
        
        layout.add_widget(write_card)
        
        self.clone_btn = StyledButton(text='克隆标签', disabled=True, background_color=Theme.ORANGE)
        self.clone_btn.bind(on_press=self.start_clone)
        layout.add_widget(self.clone_btn)
        
        self.format_btn = StyledButton(text='格式化标签', disabled=True, background_color=Theme.RED)
        self.format_btn.bind(on_press=self.start_format)
        layout.add_widget(self.format_btn)
        
        layout.add_widget(Label())
        
        scroll = ScrollView()
        scroll.add_widget(layout)
        return scroll
    
    def build_data_tab(self):
        """构建数据标签页"""
        layout = BoxLayout(orientation='vertical', padding='15dp', spacing='10dp')
        
        toolbar = BoxLayout(size_hint_y=None, height='50dp', spacing='10dp')
        
        export_btn = StyledButton(text='导出JSON')
        export_btn.bind(on_press=self.export_data)
        toolbar.add_widget(export_btn)
        
        clear_btn = StyledButton(text='清空', background_color=Theme.RED)
        clear_btn.bind(on_press=self.clear_history)
        toolbar.add_widget(clear_btn)
        
        layout.add_widget(toolbar)
        
        self.stats_label = StyledLabel(
            text='已读取: 0 | 已写入: 0',
            size_hint_y=None,
            height='30dp',
            color=Theme.TEXT_SEC
        )
        layout.add_widget(self.stats_label)
        
        self.history_text = TextInput(
            multiline=True,
            readonly=True,
            background_color=(0.12, 0.12, 0.12, 1),
            foreground_color=Theme.TEXT,
            font_name='monospace',
            font_size='12sp'
        )
        layout.add_widget(self.history_text)
        
        return layout
    
    def build_log_tab(self):
        """构建日志标签页"""
        layout = BoxLayout(orientation='vertical', padding='15dp', spacing='10dp')
        
        self.log_text = TextInput(
            multiline=True,
            readonly=True,
            background_color=(0.1, 0.1, 0.1, 1),
            foreground_color=Theme.TEXT_SEC,
            font_size='11sp',
            font_name='monospace'
        )
        layout.add_widget(self.log_text)
        
        clear_btn = StyledButton(text='清空日志', size_hint_y=None, background_color=Theme.SURFACE)
        clear_btn.bind(on_press=lambda x: setattr(self.log_text, 'text', ''))
        layout.add_widget(clear_btn)
        
        return layout
    
    def log(self, message):
        """添加日志"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.log_text.text += f'[{timestamp}] {message}\n'
        self.status_bar.text = message
        Logger.info(message)
    
    def refresh_ports(self, instance):
        """刷新串口列表"""
        if HAS_SERIAL:
            try:
                ports = serial.tools.list_ports.comports()
                if ports:
                    port_list = [p.device for p in ports]
                    self.port_input.text = port_list[0]
                    self.log(f"找到串口: {', '.join(port_list)}")
                else:
                    self.log("未找到串口")
            except Exception as e:
                self.log(f"刷新失败: {e}")
        else:
            self.log("串口库不可用")
    
    def toggle_connection(self, instance):
        """切换连接"""
        if self.is_connected:
            self.disconnect()
        else:
            self.connect()
    
    def connect(self):
        """连接设备"""
        if not HAS_SERIAL:
            self.show_error("缺少串口库(pyserial)")
            return
        
        if not HAS_PN532:
            self.show_error("缺少PN532协议库")
            return
        
        port = self.port_input.text
        self.log(f"正在连接 {port}...")
        
        try:
            self.serial_port = serial.Serial(
                port=port,
                baudrate=115200,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            
            self.pn532 = PN532Protocol(self.serial_port, debug=False)
            
            self.log("配置SAM...")
            if not self.pn532.sam_configuration():
                raise Exception("SAM配置失败")
            
            version = self.pn532.get_firmware_version()
            if version:
                fw_str = f"IC:{version['ic']:02X} Ver:{version['ver']}.{version['rev']}"
                self.fw_label.text = f'固件: {fw_str}'
                self.fw_label.color = Theme.GREEN
                self.log(f"连接成功 - {fw_str}")
            else:
                self.log("连接成功 - 无法获取版本")
            
            self.is_connected = True
            self.connect_btn.text = '断开连接'
            self.connect_btn.background_color = Theme.RED
            self.read_btn.disabled = False
            self.write_btn.disabled = False
            self.clone_btn.disabled = False
            self.format_btn.disabled = False
            
        except Exception as e:
            self.log(f"连接失败: {e}")
            self.show_error(f"连接失败: {e}")
            if self.serial_port:
                self.serial_port.close()
                self.serial_port = None
    
    def disconnect(self):
        """断开连接"""
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=1)
        
        if self.serial_port:
            self.serial_port.close()
            self.serial_port = None
        
        self.pn532 = None
        self.is_connected = False
        
        self.connect_btn.text = '连接设备'
        self.connect_btn.background_color = Theme.BLUE
        self.read_btn.disabled = True
        self.write_btn.disabled = True
        self.clone_btn.disabled = True
        self.format_btn.disabled = True
        self.fw_label.text = '固件: 未连接'
        self.fw_label.color = Theme.TEXT_SEC
        
        self.log("已断开连接")
    
    def start_read(self, instance):
        """开始读取"""
        if not self.is_connected or not self.pn532:
            self.show_error("请先连接设备")
            return
        
        self.read_btn.disabled = True
        self.progress.value = 0
        
        self.worker = RFIDWorker(self, 'read')
        self.worker.start()
    
    def start_write(self, instance):
        """开始写入"""
        if not self.is_connected:
            self.show_error("请先连接设备")
            return
        
        data = {
            'material': self.w_material.text,
            'color': self.w_color.text,
            'nozzle_temp': int(self.w_nozzle.text or 0),
            'bed_temp': int(self.w_bed.text or 0),
            'total_weight': int(self.w_total.text or 0),
            'remaining_weight': int(self.w_remain.text or 0)
        }
        
        self.write_btn.disabled = True
        self.worker = RFIDWorker(self, 'write', data=data)
        self.worker.start()
    
    def start_clone(self, instance):
        """开始克隆"""
        if not self.current_tag:
            self.show_error("请先读取一个标签")
            return
        
        self.clone_btn.disabled = True
        self.worker = RFIDWorker(self, 'clone', source_data=self.current_tag)
        self.worker.start()
    
    def start_format(self, instance):
        """开始格式化"""
        content = BoxLayout(orientation='vertical', padding='20dp')
        content.add_widget(StyledLabel(
            text='确定要格式化标签吗？\n此操作将清空所有数据！',
            color=Theme.RED
        ))
        
        def confirm(instance):
            popup.dismiss()
            self.format_btn.disabled = True
            self.worker = RFIDWorker(self, 'format')
            self.worker.start()
        
        btn_box = BoxLayout(size_hint_y=None, height='50dp', spacing='10dp')
        yes_btn = StyledButton(text='确认', background_color=Theme.RED)
        yes_btn.bind(on_press=confirm)
        no_btn = StyledButton(text='取消', background_color=Theme.SURFACE)
        no_btn.bind(on_press=lambda x: popup.dismiss())
        
        btn_box.add_widget(yes_btn)
        btn_box.add_widget(no_btn)
        content.add_widget(btn_box)
        
        popup = Popup(
            title='警告',
            content=content,
            size_hint=(0.85, 0.3),
            background_color=Theme.CARD
        )
        popup.open()
    
    def update_progress(self, value):
        """更新进度条"""
        self.progress.value = value
    
    def update_status(self, message):
        """更新状态"""
        self.status_bar.text = message
        self.log(message)
    
    def on_read_complete(self, tag_data):
        """读取完成回调"""
        self.current_tag = tag_data
        self.tag_history.append(tag_data)
        
        self.uid_label.text = f'UID: [b]{tag_data["uid"]}[/b]'
        self.info_labels['type'].text = tag_data['tag_type']
        self.info_labels['material'].text = tag_data['material']
        self.info_labels['color'].text = tag_data['color']
        self.info_labels['temp'].text = f"{tag_data['nozzle_temp']}C / {tag_data['bed_temp']}C"
        self.info_labels['weight'].text = f"{tag_data['remaining_weight']}g / {tag_data['total_weight']}g"
        
        if tag_data['is_encrypted']:
            self.info_labels['crypto'].text = '已加密'
            self.info_labels['crypto'].color = Theme.RED
        else:
            self.info_labels['crypto'].text = '未加密'
            self.info_labels['crypto'].color = Theme.GREEN
        
        raw_text = f"时间戳: {tag_data['timestamp']}\n"
        raw_text += f"Bambu标签: {'是' if tag_data['is_bambu_tag'] else '否'}\n\n"
        for page, data in tag_data.get('raw_pages', {}).items():
            raw_text += f"{page}: {data}\n"
        self.raw_text.text = raw_text
        
        self.clone_btn.disabled = False
        self.update_history()
        self.update_stats()
        
        self.read_btn.disabled = False
        self.log(f"读取完成: {tag_data['uid']}")
    
    def on_write_complete(self):
        """写入完成回调"""
        self.write_btn.disabled = False
        self.log("写入完成")
        self.show_message("标签写入成功！")
    
    def on_clone_complete(self):
        """克隆完成回调"""
        self.clone_btn.disabled = False
        self.log("克隆完成")
        self.show_message("标签克隆成功！")
    
    def on_format_complete(self):
        """格式化完成回调"""
        self.format_btn.disabled = False
        self.log("格式化完成")
        self.show_message("标签已格式化")
    
    def on_error(self, error):
        """错误回调"""
        self.log(f"错误: {error}")
        self.show_error(error)
        self.read_btn.disabled = False
        self.write_btn.disabled = False
        self.clone_btn.disabled = False
        self.format_btn.disabled = False
        self.progress.value = 0
    
    def update_history(self):
        """更新历史记录"""
        text = ''
        for i, tag in enumerate(self.tag_history[-30:], 1):
            time_str = tag['timestamp'][11:19]
            text += f"{i:2d}. {time_str} | {tag['uid']} | {tag['material']}\n"
        self.history_text.text = text
    
    def update_stats(self):
        """更新统计"""
        self.stats_label.text = f"已读取: {len(self.tag_history)}"
    
    def export_data(self, instance):
        """导出数据"""
        try:
            filename = f'/sdcard/bambu_tags_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
            with open(filename, 'w') as f:
                json.dump(self.tag_history, f, indent=2, default=str)
            self.log(f"已导出: {filename}")
            self.show_message(f"导出成功\n{filename}")
        except Exception as e:
            self.show_error(f"导出失败: {e}")
    
    def clear_history(self, instance):
        """清空历史"""
        self.tag_history.clear()
        self.history_text.text = ''
        self.update_stats()
        self.log("历史已清空")
    
    def show_error(self, message):
        """显示错误"""
        popup = Popup(
            title='错误',
            content=StyledLabel(text=message, color=Theme.RED),
            size_hint=(0.85, 0.25),
            background_color=Theme.CARD
        )
        popup.open()
    
    def show_message(self, message):
        """显示消息"""
        popup = Popup(
            title='完成',
            content=StyledLabel(text=message, color=Theme.GREEN),
            size_hint=(0.85, 0.25),
            background_color=Theme.CARD
        )
        popup.open()

class BambuRFIDApp(App):
    def build(self):
        self.title = 'Bambu RFID Pro'
        return BambuRFIDManager()
    
    def on_pause(self):
        return True

if __name__ == '__main__':
    BambuRFIDApp().run()
