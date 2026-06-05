# JLU DrCOM 校园网自动认证

这是一个面向吉林大学校园网的 DrCOM UDP 自动认证服务。程序会等待指定 WiFi 连接，向 JLU 校园网 DrCOM 认证服务器登录，并通过周期性心跳保持在线，适合放在宿舍、实验室或小型边缘设备上自动维持校园网连接。

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

## 配置

复制 `.env.example` 到本机私有配置文件，例如 `/etc/jlu-drcom-auth.env`，然后填写真实信息：

```sh
sudo install -m 600 .env.example /etc/jlu-drcom-auth.env
sudo editor /etc/jlu-drcom-auth.env
```

必填变量：

- `DRCOM_WIFI_SSID`：校园网 WiFi 名称
- `DRCOM_WIFI_IFACE`：无线网卡名称，例如 `wlan0`
- `DRCOM_SERVER`：DrCOM 认证服务器地址
- `DRCOM_USERNAME`：认证账号
- `DRCOM_PASSWORD`：认证密码
- `DRCOM_REGISTERED_MAC`：绑定或注册的 MAC 地址

`DRCOM_REGISTERED_MAC` 可以写成 12 位十六进制，也可以带 `:` 分隔，例如：

```text
001122334455
00:11:22:33:44:55
```

本地手动运行时，先加载私有配置：

```sh
set -a
. /etc/jlu-drcom-auth.env
set +a
python3 drcom_auth.py
```

## systemd 部署

`systemd` 是 Linux 上常用的后台服务管理工具。把认证脚本注册成 systemd 服务后，设备开机时会自动启动认证程序；如果程序异常退出，systemd 也会按服务文件里的规则自动重启它。

安装脚本和服务文件：

```sh
sudo mkdir -p /opt/jlu-drcom-auth
sudo cp drcom_auth.py /opt/jlu-drcom-auth/
sudo cp jlu-drcom-auth.service /etc/systemd/system/jlu-drcom-auth.service
sudo systemctl daemon-reload
sudo systemctl enable --now jlu-drcom-auth.service
```

这些命令的作用：

- `sudo mkdir -p /opt/jlu-drcom-auth`：创建程序安装目录。
- `sudo cp drcom_auth.py /opt/jlu-drcom-auth/`：把认证脚本复制到固定安装目录。
- `sudo cp jlu-drcom-auth.service /etc/systemd/system/jlu-drcom-auth.service`：把服务配置文件安装到 systemd 的系统服务目录。
- `sudo systemctl daemon-reload`：让 systemd 重新读取刚安装的服务文件。
- `sudo systemctl enable --now jlu-drcom-auth.service`：设置开机自启，并立刻启动服务。

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
