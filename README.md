# DGLAB-V2.0-socket

![GitHub last commit](https://img.shields.io/github/last-commit/shilapi/DGLAB-V2.0-socket)
![GitHub Release](https://img.shields.io/github/v/release/shilapi/DGLAB-V2.0-socket)
[![CodeFactor](https://www.codefactor.io/repository/github/shilapi/dglab-v2.0-socket/badge)](https://www.codefactor.io/repository/github/shilapi/dglab-v2.0-socket)

一个完整的 DGLAB2.0 郊狼2.0 WebSocket 受控端实现，并附带本地 Web 控制面板、中英双语 i18n、实时波形可视化。

基于 [DGLAB-python-driver](https://github.com/shilapi/DGLAB-python-driver)。

目标：让郊狼 2.0 主机也能用上 WebSocket 远控协议，同时可在本地浏览器直接控制。

## 快速启动

```bash
pip install -r requirements
python ./src/main.py
```

Windows 也可双击 `run.bat`。

浏览器打开：http://127.0.0.1:8787

## 面板功能

- **通道控制** — A/B 强度滑条，±1/±5 快捷加减，一键归零
- **Live Waveform** — 基于 (X,Y,Z) 实时重建示波器波形，显示周期、频率、占空比
- **硬件连接** — 手动连接/断开 DGLab 2.0 设备 (BLE)
- **WebSocket 连接** — 粘贴二维码内容 / 拖入图片 / Ctrl+V 粘贴 / 屏幕扫码
- **紧急停止** — 一键归零
- **设置** — 通道强度上限、波形转换比例
- **中英切换** — 自动检测浏览器语言，手动切换，localStorage 持久化
- **活动日志** — 实时操作记录，带 i18n 翻译

## 启动

### 依赖

```
pip install -r requirements
```

### 运行

```bash
python ./src/main.py
```

或 Windows 双击 `run.bat`。

打开 http://127.0.0.1:8787

## 配置 `config.yaml`

| Key | Value |
|---|---|
| QR_Content | 连接二维码内容（含 `ws://` / `wss://`），可空，留空需后续手动填入 |
| Channel_A_limit | 通道 A 强度上限 |
| Channel_B_limit | 通道 B 强度上限 |
| Wave_convert_ratio | 3.0 波形到 2.0 的转换比例，建议 2–20 |
| Debug | 是否开启 debug 日志 |

## 项目结构

```
DGLAB-V2.0-socket/
├── src/
│   ├── main.py          # 入口
│   ├── api.py           # FastAPI 服务 (REST API)
│   ├── device.py        # BLE 设备管理
│   ├── ws_client.py     # WebSocket 客户端
│   ├── handler.py       # WS 协议消息处理
│   ├── model.py         # 状态模型 (AppState)
│   └── utils.py         # 二维码 / 波形转换
├── web/
│   ├── index.html       # 面板 HTML
│   ├── style.css        # Spacex 风格样式
│   ├── app.js           # 面板交互逻辑
│   ├── wave.js          # 实时波形可视化
│   ├── i18n.js          # 国际化运行时
│   └── i18n/
│       ├── index.json   # 语言注册表
│       ├── en.json      # 英文翻译
│       └── zh.json      # 中文翻译
├── config.yaml          # 本地配置
├── requirements         # Python 依赖
└── run.bat              # Windows 启动脚本
```

## 波形转换

由于郊狼 2.0 与 3.0 的波形存储方式不同，3.0 协议中的十六进制波形串需转换为 2.0 的 (X, Y, Z) 格式：

- **X** = 脉冲时间 (ms) = `1000 / freq / ratio`
- **Y** = 间隔时间 (ms) = `1000 / freq - X`
- **Z** = 强度系数 = `strength / 5`

**Wave_convert_ratio（建议 2–20）** 数值越小体感越强。

## API 接口 (REST)

| Method | Path | 说明 |
|--------|------|------|
| GET | /api/status | 全量状态快照 |
| POST | /api/device/connect | 连接设备 (BLE) |
| POST | /api/device/disconnect | 断开设备 |
| POST | /api/strength | 设置强度 |
| POST | /api/limits | 设置强度上限 |
| POST | /api/wave | 设置波形 |
| POST | /api/emergency-stop | 紧急停止 |
| POST | /api/ws/connect | 连接 WebSocket |
| POST | /api/ws/disconnect | 断开 WebSocket |
| POST | /api/qr/scan | 屏幕扫码 |
| POST | /api/qr/image | 上传图片解码二维码 |
| GET | /api/config | 获取配置 |
| POST | /api/config | 更新配置 |

## 国际化

支持中英双语，自动检测浏览器语言，也可手动切换（顶部 EN / 中文 按钮）。

选择会保存到 localStorage。

### 添加新语言

1. 在 `web/i18n/` 下新建 `xx.json`（复制 `en.json` 翻译）
2. 在 `web/i18n/index.json` 的 `locales` 数组中添加条目
3. 在 HTML 中补充 `<button data-locale="xx">`
