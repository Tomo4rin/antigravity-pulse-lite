# 星轨猫猫仪表盘（antigravity-pulse-lite）

> 适用平台：**Windows（Antigravity 2.0 桌面端）** + **Python 3.10+**  
> 特点：**零第三方依赖** · **不修改 `app.asar` 与快捷方式** · **不写 SQLite 账本与日志文件** · **纯中文原生侧栏**

## 核心功能

- **星海猫猫动态表情**：根据当前速率、额度余额与连接状态自动切换 3 种表情（开心 / 好奇 / 犯困），也可点击猫猫头像互动。
- **实时生成速率**：最近 TPS、会话均速、峰值速率、首字延迟（TTFT）、模型/工具用时，以及星海彩虹渐变折线图。
- **Token 与缓存明细**：缓存命中率、三段式比例条、缓存读取 / 未缓存输入 / 输出 / 缓存写入拆解。
- **上下文与共享额度**：上下文窗口已用百分比、Gemini 与 Claude/GPT 组切换、5 小时 / 周剩余额度实时倒计时与消耗节奏预测。

## 安装方式

1. 将本目录复制到 `%USERPROFILE%\.gemini\config\plugins\antigravity-pulse-lite\`。
2. 在 Antigravity 的 **Customizations → Plugins** 中启用 **`星轨猫猫仪表盘`** 并重启客户端。
3. 在窗口右上角展开右侧辅助栏，点击 **`+` → Extensions → 星轨猫猫仪表盘** 即可常驻查看。

## 命令行调试与本地预览

```powershell
# 测试采集本机 Antigravity 实时指标（只读）
python -B sidecars/panel/collector.py --test

# 本地独立启动预览（默认 http://127.0.0.1:17892）
python -B sidecars/panel/server.py
```
