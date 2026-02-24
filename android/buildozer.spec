[app]
title = Bambu RFID Manager Pro
package.name = bamburfidpro
package.domain = org.bamburesearch
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,txt
version = 1.0.0
requirements = python3,kivy,pyjnius,android

android.permissions = INTERNET,USB_PERMISSION,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
android.features = android.hardware.usb.host

# 使用稳定的版本
android.api = 33
android.minapi = 21
android.ndk=23b
# android.ndk_url = https://mirrors.tuna.tsinghua.edu.cn/android/repository/android-ndk-r25b-linux-x86_64.zip
android.build_tools = 33.0.0
android.archs = arm64-v8a

orientation = portrait
fullscreen = 0
android.allow_backup = True

# 禁用不必要的下载
android.skip_update = True

[buildozer]
log_level = 2
warn_on_root = 0
