# 星轨猫猫仪表盘（antigravity-pulse-lite）

> 适用平台：**Windows（Antigravity 2.0 桌面端）** + **Python 3.10+**  
> 特点：**零第三方依赖** · **液态玻璃（Liquid Glass）UI** · **不修改 `app.asar` 与快捷方式** · **不写 SQLite 账本与日志文件**

专为 Antigravity 2.0 桌面端右侧辅助栏打造的轻量纯中文实时监控面板，直连本机 `127.0.0.1` 的 `language_server` 本地接口，随时掌握生成速度、缓存命中、上下文占用与共享额度。

---

## 核心特性

- **液态玻璃（Liquid Glass）动态视觉**
  - 半透明磨砂玻璃卡片、顶部镜面折射高光与动态星海流光背景，支持一键切换深 / 浅主题并自动记住偏好；
  - 全局等宽数字防抖动排版 + **全动态响应式适配**：侧栏拉宽或压到极窄都能优雅重排，绝不挤压错位。
- **四表情星海猫猫互动看板**
  - 根据实时速率、额度状态、高上下文提醒与连接健康度自动切换 **4 种高清表情**（得意托腮 / 开心眯眼 / 好奇圆眼 / 委屈犯困）；
  - 点击猫猫头像可触发傲娇台词与**四角星芒 `✦` 飘散粒子**，连续快戳 5 下还能触发**算力过热彩蛋**；
  - 支持自由替换 `sidecars/panel/avatars/` 下的 `happy.png`、`curious.png`、`sleepy.png`、`smug.jpg` 自定义专属头像。
- **对话切换 & 高上下文提醒（v0.2.0 新增）**
  - 内置近期对话选择器（默认“自动跟随最新”，可随时切查任意历史对话的速度、缓存与上下文）；
  - 上下文窗口占用达到 `≥ 80%` 时触发琥珀柔光提醒，猫猫主动提示使用 `/compact` 压缩上下文；
  - 自动记住你的深/浅主题、平滑/阶梯曲线与当前 Tab 偏好（纯浏览器 `localStorage`，零磁盘文件垃圾）。
- **实时生成速率 & 丝滑贝塞尔曲线**
  - 展示最近 TPS、会话加权均速、峰值速率、首字延迟（TTFT）、模型用时与工具用时；
  - 内置 **MAD 稳健离群过滤** 剔除短窗口异常毛刺；支持 **星芒阶梯** 与 **单调三次贝塞尔平滑曲线** 一键切换。
- **Token 缓存拆解与上下文监控**
  - 实时统计总 Token、缓存命中率、三段式占比彩条（缓存读取 / 未缓存输入 / 输出）及思考输出；
  - 读取宿主上报的上下文窗口占用百分比与已用 / 上限容量。
- **双组共享额度 & 消耗节奏预测**
  - 支持 **Gemini 模型** 与 **Claude / GPT 模型** 额度组切换，常驻展示 **5 小时 / 周剩余额度** 与每秒走动的重置倒计时；
  - 按当前周期进度线性估算重置前剩余比例，预计提前耗尽时自动高亮提醒。

---

## 目录结构

```text
antigravity-pulse-lite/
├── plugin.json                # Antigravity 插件清单
├── assets/logo.svg            # 星芒猫耳插件图标
├── LICENSE                    # MIT 协议
└── sidecars/panel/
    ├── sidecar.json           # Sidecar Web UI 声明（右侧辅助栏）
    ├── collector.py           # 本机 language_server 发现与只读 RPC 采集器
    ├── server.py              # 纯 Python 标准库本地 HTTP 服务（仅监听 127.0.0.1）
    ├── index.html             # 单文件液态玻璃前端界面
    └── avatars/               # 四表情独立头像（可自由替换）
        ├── happy.png
        ├── curious.png
        ├── sleepy.png
        └── smug.jpg
```

---

## 安装方式（Windows）

1. 从 [Releases](https://github.com/Tomo4rin/antigravity-pulse-lite/releases) 下载最新压缩包并解压，将 `antigravity-pulse-lite` 整个文件夹放入：
   ```text
   %USERPROFILE%\.gemini\config\plugins\antigravity-pulse-lite\
   ```
2. 在 Antigravity 的 **Customizations → Plugins** 中启用 **`星轨猫猫仪表盘`** 并重启客户端。
3. 展开窗口右上角的右侧辅助栏，点击顶部的 **`+` → Extensions → 星轨猫猫仪表盘** 即可常驻查看。

---

## 命令行调试与本地预览

```powershell
# 只读测试采集本机 Antigravity 实时指标
python -B sidecars/panel/collector.py

# 本地独立启动预览（默认 http://127.0.0.1:17892）
python -B sidecars/panel/server.py
```

## 开源协议

[MIT](LICENSE)
