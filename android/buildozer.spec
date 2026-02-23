[app]
title = Bambu RFID Manager Pro
package.name = bamburfidpro
package.domain = org.bamburesearch
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,txt
version = 1.0.0
requirements = python3,kivy,pyjnius,android,pyserial
android.permissions = INTERNET,USB_PERMISSION,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
android.features = android.hardware.usb.host
android.sdk = 33
android.archs = arm64-v8a,armeabi-v7a
orientation = portrait
fullscreen = 0
android.allow_backup = True

# 使用稳定的 build-tools 版本，避免 rc 版本
android.build_tools = 33.0.0
android.api = 33
android.minapi = 21
android.ndk = 25.2.9519653

[buildozer]
log_level = 2
warn_on_root = 1
