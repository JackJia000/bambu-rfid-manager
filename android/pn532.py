"""
PN532 NFC模块完整协议实现
支持NTAG215/216标签的读写操作
"""

import time
import struct
from enum import IntEnum
from typing import Optional, List, Dict, Tuple, Union

class PN532Command(IntEnum):
    """PN532命令码"""
    DIAGNOSE = 0x00
    GET_FIRMWARE_VERSION = 0x02
    GET_GENERAL_STATUS = 0x04
    READ_REGISTER = 0x06
    WRITE_REGISTER = 0x08
    READ_GPIO = 0x0C
    WRITE_GPIO = 0x0E
    SET_SERIAL_BAUD_RATE = 0x10
    SET_PARAMETERS = 0x12
    SAM_CONFIGURATION = 0x14
    POWER_DOWN = 0x16
    RF_CONFIGURATION = 0x32
    IN_JUMP_FOR_DEP = 0x56
    IN_JUMP_FOR_PSL = 0x46
    IN_LIST_PASSIVE_TARGET = 0x4A
    IN_ATR = 0x50
    IN_PSL = 0x4E
    IN_DATA_EXCHANGE = 0x40
    IN_COMMUNICATE_THRU = 0x42
    IN_DESELECT = 0x44
    IN_RELEASE = 0x52
    IN_SELECT = 0x54
    IN_AUTO_POLL = 0x60
    TG_INIT_AS_TARGET = 0x8C
    TG_SET_GENERAL_BYTES = 0x92
    TG_GET_DATA = 0x86
    TG_SET_DATA = 0x8E
    TG_SET_METADATA = 0x94
    TG_GET_INITIATOR_COMMAND = 0x88
    TG_RESPOND_TO_INITIATOR = 0x90
    TG_GET_TARGET_STATUS = 0x8A

class MifareCommand(IntEnum):
    """Mifare命令"""
    AUTH_A = 0x60
    AUTH_B = 0x61
    READ = 0x30
    WRITE = 0xA0
    TRANSFER = 0xB0
    DECREMENT = 0xC0
    INCREMENT = 0xC1
    RESTORE = 0xC2

class CardType(IntEnum):
    """卡片类型"""
    TYPE_A_106KBPS = 0x00
    TYPE_B_106KBPS = 0x03
    TYPE_212KBPS = 0x01
    TYPE_424KBPS = 0x02

class PN532Error(Exception):
    """PN532错误"""
    pass

class PN532Protocol:
    """PN532协议处理器 - 完整实现"""
    
    # 帧标识
    PREAMBLE = 0x00
    START_CODE_1 = 0x00
    START_CODE_2 = 0xFF
    POSTAMBLE = 0x00
    
    # 方向
    HOST_TO_PN532 = 0xD4
    PN532_TO_HOST = 0xD5
    
    # 超时设置
    ACK_TIMEOUT = 0.1
    RESPONSE_TIMEOUT = 1.0
    READ_TIMEOUT = 2.0
    
    def __init__(self, serial_port, debug=False):
        self.serial = serial_port
        self._debug = debug
        self._sequence = 0
        
    def _debug_print(self, msg: str):
        if self._debug:
            print(f"[PN532] {msg}")
    
    def _calculate_checksum(self, data: bytes) -> int:
        """计算校验和"""
        return ((~sum(data)) + 1) & 0xFF
    
    def _write_frame(self, data: bytes):
        """写入数据帧 - 标准帧格式"""
        length = len(data)
        
        # 构建标准帧
        frame = bytes([
            self.PREAMBLE,
            self.START_CODE_1,
            self.START_CODE_2,
            length,
            ((~length) + 1) & 0xFF,
            self.HOST_TO_PN532
        ]) + data
        
        # 添加校验和与结束码
        checksum = self._calculate_checksum(bytes([self.HOST_TO_PN532]) + data)
        frame += bytes([checksum, self.POSTAMBLE])
        
        self._debug_print(f"发送帧 ({len(frame)}字节): {frame.hex().upper()}")
        self.serial.write(frame)
        self.serial.flush()
    
    def _read_ack(self, timeout: float = ACK_TIMEOUT) -> bool:
        """读取ACK帧"""
        start_time = time.time()
        ack_frame = bytes([0x00, 0x00, 0xFF, 0x00, 0xFF, 0x00])
        
        while (time.time() - start_time) < timeout:
            if self.serial.in_waiting >= len(ack_frame):
                response = self.serial.read(len(ack_frame))
                if response == ack_frame:
                    self._debug_print("收到ACK确认")
                    return True
                elif len(response) >= 3 and response[0:3] == bytes([0x00, 0x00, 0xFF]):
                    self._debug_print(f"收到非ACK帧: {response.hex().upper()}")
                    return False
            time.sleep(0.001)
        
        self._debug_print("ACK超时")
        return False
    
    def _read_response(self, timeout: float = RESPONSE_TIMEOUT) -> Optional[bytes]:
        """读取响应帧"""
        start_time = time.time()
        
        while (time.time() - start_time) < timeout:
            if self.serial.in_waiting:
                # 查找起始码
                first_byte = self.serial.read(1)
                if not first_byte:
                    continue
                    
                if first_byte[0] != self.START_CODE_1:
                    continue
                
                second_byte = self.serial.read(1)
                if not second_byte or second_byte[0] != self.START_CODE_2:
                    continue
                
                length_byte = self.serial.read(1)
                if not length_byte:
                    continue
                length = length_byte[0]
                
                lcs_byte = self.serial.read(1)
                if not lcs_byte:
                    continue
                lcs = lcs_byte[0]
                
                if (length + lcs) & 0xFF != 0:
                    self._debug_print(f"长度校验失败: LEN={length}, LCS={lcs}")
                    continue
                
                data = self.serial.read(length)
                if len(data) != length:
                    self._debug_print(f"数据长度不足: 期望{length}, 实际{len(data)}")
                    continue
                
                dcs_byte = self.serial.read(1)
                if not dcs_byte:
                    continue
                dcs = dcs_byte[0]
                
                if (sum(data) + dcs) & 0xFF != 0:
                    self._debug_print("数据校验和失败")
                    continue
                
                postamble = self.serial.read(1)
                if not postamble or postamble[0] != self.POSTAMBLE:
                    self._debug_print("结束码错误")
                    continue
                
                if data[0] != self.PN532_TO_HOST:
                    self._debug_print(f"错误的方向字节: {data[0]:02X}")
                    continue
                
                self._debug_print(f"收到响应 ({len(data)-1}字节): {data[1:].hex().upper()}")
                return data[1:]
            
            time.sleep(0.001)
        
        self._debug_print("响应超时")
        return None
    
    def send_command(self, cmd: PN532Command, params: bytes = b'', timeout: float = RESPONSE_TIMEOUT) -> Optional[bytes]:
        """发送命令并获取响应"""
        data = bytes([cmd]) + params
        self._write_frame(data)
        
        if not self._read_ack():
            self._debug_print("未收到ACK，重试...")
            self._write_frame(data)
            if not self._read_ack():
                raise PN532Error("发送命令失败：未收到ACK")
        
        response = self._read_response(timeout)
        if response is None:
            raise PN532Error("接收响应超时")
        
        if len(response) < 1:
            raise PN532Error("响应数据为空")
            
        if response[0] != cmd + 1:
            if response[0] == 0x7F:
                raise PN532Error(f"PN532错误响应: {response.hex().upper()}")
            self._debug_print(f"响应命令不匹配: 期望 {cmd+1:02X}, 得到 {response[0]:02X}")
        
        return response[1:]
    
    def sam_configuration(self, mode: int = 0x01, timeout: int = 0x14, irq: bool = False) -> bool:
        """配置SAM"""
        params = bytes([mode, timeout, 0x01 if irq else 0x00])
        try:
            response = self.send_command(PN532Command.SAM_CONFIGURATION, params)
            return response is not None and len(response) == 0
        except Exception as e:
            self._debug_print(f"SAM配置失败: {e}")
            return False
    
    def get_firmware_version(self) -> Optional[Dict[str, any]]:
        """获取固件版本信息"""
        try:
            response = self.send_command(PN532Command.GET_FIRMWARE_VERSION)
            if response and len(response) >= 4:
                return {
                    'ic': response[0],
                    'ver': response[1],
                    'rev': response[2],
                    'support': response[3]
                }
            return None
        except Exception as e:
            self._debug_print(f"获取版本失败: {e}")
            return None
    
    def read_passive_target_id(self, card_baud: int = CardType.TYPE_A_106KBPS, timeout: float = 2.0, max_targets: int = 1) -> Optional[Dict]:
        """读取被动目标ID"""
        params = bytes([max_targets, card_baud])
        
        start_time = time.time()
        while (time.time() - start_time) < timeout:
            try:
                response = self.send_command(PN532Command.IN_LIST_PASSIVE_TARGET, params, timeout=0.5)
                
                if response and len(response) >= 6:
                    num_targets = response[0]
                    if num_targets > 0:
                        target_num = response[1]
                        sens_res = response[2:4]
                        sel_res = response[4]
                        nfcid_length = response[5]
                        
                        if len(response) >= 6 + nfcid_length:
                            uid = response[6:6+nfcid_length]
                            
                            result = {
                                'uid': uid,
                                'uid_hex': uid.hex().upper(),
                                'sens_res': sens_res.hex().upper(),
                                'sel_res': sel_res,
                                'nfcid_length': nfcid_length
                            }
                            
                            if len(response) > 6 + nfcid_length:
                                ats_length = response[6+nfcid_length]
                                if ats_length > 0 and len(response) >= 7 + nfcid_length + ats_length:
                                    ats = response[7+nfcid_length:7+nfcid_length+ats_length]
                                    result['ats'] = ats.hex().upper()
                            
                            return result
                            
            except PN532Error as e:
                self._debug_print(f"检测错误: {e}")
            
            time.sleep(0.05)
        
        return None
    
    def in_data_exchange(self, target_id: int, data: bytes) -> Optional[bytes]:
        """数据交换命令"""
        params = bytes([target_id]) + data
        try:
            response = self.send_command(PN532Command.IN_DATA_EXCHANGE, params)
            if response and len(response) >= 1:
                status = response[0]
                if status == 0x00:
                    return response[1:]
                else:
                    self._debug_print(f"数据交换错误状态: {status:02X}")
                    return None
            return None
        except Exception as e:
            self._debug_print(f"数据交换失败: {e}")
            return None
    
    def mifare_read_block(self, block_number: int, target_id: int = 1) -> Optional[bytes]:
        """读取Mifare块"""
        cmd_data = bytes([MifareCommand.READ, block_number])
        return self.in_data_exchange(target_id, cmd_data)
    
    def mifare_write_block(self, block_number: int, data: bytes, target_id: int = 1) -> bool:
        """写入Mifare块"""
        if len(data) != 16:
            raise ValueError("数据必须是16字节")
        
        cmd_data = bytes([MifareCommand.WRITE, block_number]) + data
        response = self.in_data_exchange(target_id, cmd_data)
        return response is not None
    
    def read_ntag_page(self, page_number: int, target_id: int = 1) -> Optional[bytes]:
        """读取NTAG页面"""
        block_num = page_number // 4
        block_data = self.mifare_read_block(block_num, target_id)
        
        if block_data and len(block_data) == 16:
            page_in_block = page_number % 4
            return block_data[page_in_block*4:(page_in_block+1)*4]
        return None
    
    def write_ntag_page(self, page_number: int, data: bytes, target_id: int = 1) -> bool:
        """写入NTAG页面"""
        if len(data) != 4:
            raise ValueError("页面数据必须是4字节")
        
        if page_number < 4:
            raise PN532Error("前4页是只读的")
        
        block_num = page_number // 4
        page_in_block = page_number % 4
        
        block_data = self.mifare_read_block(block_num, target_id)
        if not block_data:
            return False
        
        new_block = bytearray(block_data)
        new_block[page_in_block*4:(page_in_block+1)*4] = data
        
        return self.mifare_write_block(block_num, bytes(new_block), target_id)
    
    def rf_configuration(self, cfg_item: int, cfg_data: bytes) -> bool:
        """RF配置"""
        params = bytes([cfg_item]) + cfg_data
        try:
            response = self.send_command(PN532Command.RF_CONFIGURATION, params)
            return response is not None and len(response) == 0
        except:
            return False
    
    def set_rf_field(self, auto_rf: bool = True, rf_on: bool = True) -> bool:
        """设置RF场"""
        cfg_item = 0x01
        cfg_data = bytes([
            0x01 if auto_rf else 0x00,
            0x01 if rf_on else 0x00
        ])
        return self.rf_configuration(cfg_item, cfg_data)


class NTAGCard:
    """NTAG卡片基类"""
    
    def __init__(self, pn532: PN532Protocol, uid: bytes):
        self.pn532 = pn532
        self.uid = uid
        self.target_id = 1
    
    def read_page(self, page: int) -> Optional[bytes]:
        """读取页面"""
        return self.pn532.read_ntag_page(page, self.target_id)
    
    def write_page(self, page: int, data: bytes) -> bool:
        """写入页面"""
        return self.pn532.write_ntag_page(page, data, self.target_id)


class NTAG215(NTAGCard):
    """NTAG215标签"""
    
    USER_MEMORY_START = 4
    USER_MEMORY_END = 129
    USER_MEMORY_SIZE = 504
    
    CONFIG_PAGE_1 = 0x83
    CONFIG_PAGE_2 = 0x84
    PWD_PAGE = 0x85
    PACK_PAGE = 0x86
    
    def __init__(self, pn532: PN532Protocol, uid: bytes):
        super().__init__(pn532, uid)
        self.tag_type = "NTAG215"
    
    def read_all_pages(self) -> Dict[int, bytes]:
        """读取所有用户页面"""
        pages = {}
        for page in range(self.USER_MEMORY_START, self.USER_MEMORY_END):
            data = self.read_page(page)
            if data:
                pages[page] = data
            else:
                break
        return pages
    
    def write_ndef_message(self, message: bytes) -> bool:
        """写入NDEF消息"""
        if len(message) > 255:
            tlv = bytes([0x03, 0xFF]) + struct.pack('>H', len(message)) + message + bytes([0xFE])
        else:
            tlv = bytes([0x03, len(message)]) + message + bytes([0xFE])
        
        while len(tlv) % 4 != 0:
            tlv += b'\x00'
        
        page = self.USER_MEMORY_START
        for i in range(0, len(tlv), 4):
            chunk = tlv[i:i+4]
            if not self.write_page(page, chunk):
                return False
            page += 1
        
        return True
    
    def erase_user_memory(self) -> bool:
        """擦除所有用户数据"""
        empty = b'\x00\x00\x00\x00'
        for page in range(self.USER_MEMORY_START, self.USER_MEMORY_END):
            if not self.write_page(page, empty):
                return False
        return True


class NTAG216(NTAGCard):
    """NTAG216标签"""
    
    USER_MEMORY_START = 4
    USER_MEMORY_END = 225
    USER_MEMORY_SIZE = 888
    
    CONFIG_PAGE_1 = 0xE3
    CONFIG_PAGE_2 = 0xE4
    PWD_PAGE = 0xE5
    PACK_PAGE = 0xE6
    
    def __init__(self, pn532: PN532Protocol, uid: bytes):
        super().__init__(pn532, uid)
        self.tag_type = "NTAG216"


class BambuTagParser:
    """Bambu Lab标签数据解析器"""
    
    @staticmethod
    def parse(pages: Dict[int, bytes]) -> Dict:
        """解析Bambu标签数据"""
        result = {
            'is_bambu_tag': False,
            'is_encrypted': True,
            'material': 'Unknown',
            'color': 'Unknown',
            'nozzle_temp': 0,
            'bed_temp': 0,
            'total_weight': 0,
            'remaining_weight': 0,
            'raw_pages': {f'Page_{k:02X}': v.hex().upper() for k, v in pages.items()}
        }
        
        if not pages:
            return result
        
        page_4 = pages.get(4, b'')
        if len(page_4) >= 1 and page_4[0] == 0x03:
            result['is_bambu_tag'] = True
            
            combined = b''.join([pages.get(i, b'') for i in range(4, 20)])
            
            if b'BAMB' in combined or b'bamb' in combined:
                result['material'] = 'Bambu Official'
            elif b'PLA' in combined:
                result['material'] = 'PLA (Encrypted)'
            elif b'PETG' in combined:
                result['material'] = 'PETG (Encrypted)'
            else:
                result['material'] = 'Encrypted Material'
            
            result['has_password'] = len(pages) > 130
        
        return result
