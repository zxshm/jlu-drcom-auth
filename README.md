# JLU DrCOM 校园网自动认证与路由器使用教程

这是一个面向吉林大学校园网的 DrCOM UDP 自动认证服务，主要用于路由器或充当路由器的 ARM Linux 设备自动完成校园网认证。程序会等待指定网络连接，向 JLU 校园网 DrCOM 认证服务器登录，并通过周期性心跳保持在线，适合放在宿舍、实验室或小型边缘设备上自动维持局域网出口连接。

关键词：吉林大学校园网、JLU 校园网、吉林大学路由器、DrCOM 自动认证、校园网路由器认证、RK3588 软路由、ARM64 Linux 网关。

本项目不包含任何真实账号、密码或 MAC 地址。所有敏感配置都通过环境变量或本机私有配置文件提供。

## 适用平台

推荐运行环境：

- ARM64 Linux 设备
- Python 3
- NetworkManager 和 `nmcli`
- 已保存目标 WiFi 的 NetworkManager 连接配置

已适配和推荐的设备类型：

- RK3588 / RK3588S 开发板或小主机
- RK3566 / RK3568 设备
- Raspberry Pi 4 / 5
- Orange Pi、Radxa、FriendlyELEC 等 ARM64 Linux 单板机
- 其他长期在线的 ARM64 Linux 设备

本项目使用纯 Python 和系统命令实现，没有依赖特定 CPU 指令。理论上 x86_64 Linux 也可以运行，但主要面向 ARM64 Linux 常驻设备维护。

## 功能

- 自动检测并连接已有的 NetworkManager WiFi 配置。
- 执行 DrCOM UDP challenge/login 认证流程。
- 登录成功后持续发送心跳包维持在线。
- WiFi 未连接、服务器不可达、心跳异常时自动重试。
- 支持通过 systemd 后台运行和开机自启。
- 账号、密码、MAC 等敏感信息不写入源码仓库。

## 路由器接入流程

这个项目的本意是让路由器或 ARM Linux 网关设备代替局域网内的普通电脑持续完成 JLU DrCOM 认证。完整流程可以分成两部分：先把路由器接入吉林大学校园网，再把本项目部署到路由器或旁路认证设备上。

### 1. 查询校园网参数

先用能访问校园网业务平台的设备打开：

```text
http://ip.jlu.edu.cn
```

在页面中查询并记录当前账号对应的网络参数，通常包括：

- IP 地址
- 子网掩码
- 默认网关
- DNS 服务器
- 网卡物理地址，也就是 MAC 地址

这些参数后面要填入路由器的上网设置中。

### 2. 设置路由器 WAN 口为静态 IP

用网线把校园网网口接到路由器的 WAN 口，然后进入路由器管理后台，把“上网方式”或“WAN 口连接方式”改为：

```text
手动 IP / 静态 IP / Static IP
```

然后把 `ip.jlu.edu.cn` 中查询到的参数填进去：

- IP 地址填入路由器 WAN 口 IP。
- 子网掩码填入路由器 WAN 口子网掩码。
- 默认网关填入路由器 WAN 口网关。
- DNS 填入路由器 WAN 口 DNS。

### 3. 处理 MAC 地址

吉林大学校园网会记录入网设备的 MAC 地址，所以路由器侧也要处理 MAC。

如果路由器支持 MAC 地址克隆：

- 在路由器后台找到“MAC 克隆”或“修改 WAN 口 MAC”功能。
- 把 WAN 口 MAC 改成 `ip.jlu.edu.cn` 中登记的 MAC 地址。

如果路由器不支持 MAC 地址克隆：

- 查看路由器 WAN 口的真实 MAC 地址。
- 到 `ip.jlu.edu.cn` 中把登记的网卡物理地址改为路由器 WAN 口 MAC。

这一步完成后，校园网侧看到的设备 MAC 应该和业务平台登记的 MAC 保持一致。

### 4. 完成一次客户端认证

路由器静态 IP、网关、DNS、MAC 都配置完成后，让局域网内任意一台设备连接到这个路由器，然后运行吉林大学校园网客户端进行认证。

认证成功后，局域网内设备一般就可以通过这个路由器访问网络。

### 5. 使用本项目自动维持认证

手动客户端认证可以验证路由器参数是否配置正确。本项目用于把这一步自动化：把脚本部署到路由器本身，或部署到局域网内一台长期在线的 ARM Linux 设备上，让它自动完成 DrCOM 登录并持续发送心跳。

部署完成后，设备重启或认证掉线时，systemd 会重新拉起认证服务，减少手动打开客户端登录的次数。

## 配置

复制 `.env.example` 到 `.env`（本机私有配置文件），然后填写真实信息：

```sh
cp .env.example .env
chmod 600 .env
editor .env
```

脚本启动时会自动加载同目录下的 `.env` 文件，无需手动 `source`。

必填变量：

- `DRCOM_WIFI_SSID`：校园网 WiFi 名称
- `DRCOM_WIFI_IFACE`：无线网卡名称，例如 `wlan0`
- `DRCOM_SERVER`：DrCOM 认证服务器地址（内网地址，如 `10.100.61.3`，**不是公网 IP**）
- `DRCOM_USERNAME`：认证账号
- `DRCOM_PASSWORD`：认证密码
- `DRCOM_REGISTERED_MAC`：绑定或注册的 MAC 地址

`DRCOM_REGISTERED_MAC` 可以写成 12 位十六进制，也可以带 `:` 分隔，例如：

```text
001122334455
00:11:22:33:44:55
```

可选变量：

- `DRCOM_HOST_NAME`：主机名，默认 `Linux`
- `DRCOM_HOST_OS`：操作系统，默认 `Linux`
- `DRCOM_PRIMARY_DNS`：主 DNS，默认 `10.10.10.10`
- `DRCOM_DHCP_SERVER`：DHCP 服务器，默认 `0.0.0.0`
- `DRCOM_CHECK_INTERVAL`：主循环检查间隔（秒），默认 `30`
- `DRCOM_WIFI_RETRY_INTERVAL`：WiFi 重试间隔（秒），默认 `5`
- `DRCOM_MAX_WIFI_RETRIES`：WiFi 最大重试次数，默认 `20`
- `DRCOM_KEEP_ALIVE_INTERVAL`：心跳间隔（秒），默认 `10`
- `DRCOM_SOCKET_TIMEOUT`：Socket 超时（秒），默认 `10`
- `DRCOM_MAX_UDP_RETRIES`：UDP 单次发送最大重试次数，默认 `3`

本地手动运行：

```sh
python3 drcom_auth.py
```

脚本会自动加载 `.env`，无需手动设置环境变量。

## systemd 部署

`systemd` 是 Linux 上常用的后台服务管理工具。把认证脚本注册成 systemd 服务后，设备开机时会自动启动认证程序；如果程序异常退出，systemd 也会按服务文件里的规则自动重启它。

安装脚本和服务文件：

```sh
sudo cp jlu-drcom-auth.service /etc/systemd/system/jlu-drcom-auth.service
sudo systemctl daemon-reload
sudo systemctl enable --now jlu-drcom-auth.service
```

注意：服务文件中 `WorkingDirectory` 设为脚本所在目录，脚本会从该目录加载 `.env` 配置文件。如果你的脚本放在其他位置，请同时修改 service 文件中的 `WorkingDirectory` 和 `ExecStart` 路径。

查看服务状态：

```sh
systemctl status jlu-drcom-auth.service
```

这个命令可以看到服务是否正在运行、最近是否报错、进程号以及最近几行日志。

查看服务日志：

```sh
journalctl -u jlu-drcom-auth.service -f
```

这个命令会持续跟随服务日志，适合排查 WiFi 连接、认证失败或心跳异常等问题。脚本默认也会在运行目录写入本地日志文件：`drcom_auth.log`。

## 注意事项

- 本项目面向吉林大学校园网 DrCOM UDP 认证环境编写。
- 设备需要能够连接吉林大学校园网 WiFi，并访问 JLU DrCOM 认证服务器。
- WiFi 名称、网卡名、账号、密码、MAC 地址都应该只保存在本机私有配置文件中。
- 请在符合吉林大学校园网管理规定和账号使用规则的前提下使用本项目。
