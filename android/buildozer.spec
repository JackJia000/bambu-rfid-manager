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
android.api = 33
android.minapi = 21
android.ndk = 25b
android.sdk = 33
android.archs = arm64-v8a,armeabi-v7a
orientation = portrait
fullscreen = 0
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
