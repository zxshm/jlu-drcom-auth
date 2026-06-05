# JLU DrCOM 校园网自动认证

这是一个用于 Linux 的 DrCOM UDP 校园网自动认证服务。程序会等待指定 WiFi 连接，向 DrCOM 认证服务器登录，并通过周期性心跳保持在线。

## 功能

- 自动检测并连接已有的 NetworkManager WiFi 配置。
- 执行 DrCOM UDP challenge/login 认证流程。
- 登录成功后持续发送心跳包维持在线。
- WiFi 未连接、服务器不可达、心跳异常时自动重试。
- 支持通过 systemd 后台运行和开机自启。
- 账号、密码、MAC 等敏感信息通过环境变量提供，不写入仓库。

## 运行要求

- Linux
- Python 3
- NetworkManager 和 `nmcli`
- 目标 WiFi 已经在系统中保存为 NetworkManager 连接配置

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

安装脚本和服务文件：

```sh
sudo mkdir -p /opt/jlu-drcom-auth
sudo cp drcom_auth.py /opt/jlu-drcom-auth/
sudo cp jlu-drcom-auth.service /etc/systemd/system/jlu-drcom-auth.service
sudo systemctl daemon-reload
sudo systemctl enable --now jlu-drcom-auth.service
```

查看服务日志：

```sh
journalctl -u jlu-drcom-auth.service -f
```

脚本默认也会在运行目录写入本地日志文件：`drcom_auth.log`。

## 安全说明

不要把真实账号、密码、MAC 地址、IP 缓存或日志提交到仓库。本项目已经通过 `.gitignore` 忽略以下内容：

- `.env`
- `*.env`
- `.drcom_ip_cache`
- `*.log`
- Python 缓存文件

如果你要公开仓库，请先确认提交历史中没有出现过真实凭据。
