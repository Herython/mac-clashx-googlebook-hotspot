#!/bin/zsh
print '这会仅清除 本工具的临时转发规则，恢复普通热点直连。'
print '不会清空系统防火墙规则，也不会关闭互联网共享。'
/usr/bin/sudo /sbin/pfctl -a com.apple/000.codex-googlebook -F all
if [[ $? -eq 0 ]]; then
  print '临时规则已清除。如原转发终端仍在运行，请在原窗口按 Control+C 结束程序。'
else
  print '未能清除规则，请保留错误提示以便排查。'
fi
print '按回车关闭。'
read
