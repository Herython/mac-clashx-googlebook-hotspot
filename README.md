# Mac ClashX 热点透明代理工具

复用现有 ClashX，将 iPhone USB 网络通过 Mac Wi-Fi 热点提供给 Googlebook。支持 IPv4 TCP 透明转发、经 ClashX 的加密 DNS，以及基于 Mac 时间的本地 NTP 校时。

[启动、关闭与故障处理](outputs/Googlebook联网工具箱/先看这里.md)

## 使用

1. 确认 iPhone USB 已连接、ClashX 运行在 `127.0.0.1:7890`。
2. 开启 macOS「互联网共享」：来源为 iPhone USB，共享给 Wi-Fi。
3. 双击工具箱中的 `启动透明代理.command`，本机输入管理员密码，看到 READY 后连接热点。
4. 用完在转发终端按 Control+C，等待临时规则移除，再关闭互联网共享。

需要 macOS、可用的 `/usr/bin/python3`、pf 及管理员授权。当前固定使用 `bridge100` / `192.168.2.1/24`，使用前需确认环境。ClashX 仍按当前规则决定出口。

IPv6 及除 DNS、DHCP、NTP 外的 UDP 被阻止，不是完整 TUN。不会替换 ClashX、修改 `/etc/pf.conf`、放宽 `/dev/pf` 权限或设置开机启动。

## 隐私与 Git

仓库采用文件白名单：只提交核心程序、启动/恢复脚本和已去除密码的说明。日志、历史诊断、网络快照、本机热点密码、缓存及工作草稿保留在本机且被忽略。新增文件默认不进入版本控制，需检查后调整 `.gitignore`。

运行时会记录域名、时间及局域网 IP，并生成 pf 状态快照。这些内容可能反映使用活动，请勿强制加入 Git。仓库不包含代理订阅、节点配置或登录凭据。

该方案已在原环境帮助设备完成激活；其他系统版本和网络环境需重新验证。
