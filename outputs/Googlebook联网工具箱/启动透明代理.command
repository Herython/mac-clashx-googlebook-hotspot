#!/bin/zsh
cd -- "${0:A:h}"
print '启动前：连接 iPhone USB，运行 ClashX，并开启 iPhone USB → Wi-Fi 互联网共享。'
print '请输入 Mac 登录密码；出现 READY 后保持本窗口打开。停止时按 Control+C。'
/usr/bin/sudo /usr/bin/python3 ./hotspot-proxy.py 2>&1 | /usr/bin/tee ./运行记录/终端输出.log
print '
程序已结束。如有报错，请查看上方提示或运行记录。按回车关闭。'
read
