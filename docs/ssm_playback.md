# SSM 触控与计时版本

BPM 单项实验已通过回退提交 `b18b088` 撤销。这个版本从 v1.2.7 的谱面解析出发，把触控生成和播放执行交给 SSM GUI 的 Go 核心。

## 实际执行流程

```text
现有 GUI / MAA 选曲
  → Bestdori 谱面与 v1.2.7 拍数换算
  → SSM 音符模型
  → SSM GenerateHumanizedTouchEvent（随机扰动 / Great 模式关闭）
  → SSM 冲突图和 DSATUR 手指分配
  → SSM scrcpy 触控编码
  → SSM Go playEvents 绝对时间调度
  → 模拟器
```

SSM 来源固定为 [061d1b8](https://github.com/hj6hki123/ssm-gui/tree/061d1b880e42b57698be35e9a4a841a44a684fef)。触控生成、手指分配和调度循环直接复用 Go 源码。

短按持续 10 ms；普通长条到尾端先移动，再于 1 ms 后抬手；甩尾持续 60 ms，报告间隔 5 ms，结束后再隔 5 ms 抬手。手指按时间冲突分配，共享端点也视为冲突。

播放不再发送 minitouch 的相对等待和 100 动作分块。Go 使用 `event.Timestamp - time.Since(start).Milliseconds()` 判断每个时间点；远离事件时休眠，临近时使用 SSM 的轮询策略。同一时间点的触控打包写入 scrcpy 控制 socket。

首音检测的阈值、冻结逻辑和 photogate 保持原流程。检测后把首音的目标时刻交给 Go，避免在 Python 休眠后再额外叠加通信延迟。生命检测留在 Python 中，每秒检查一次；Go 独立发送触控。生命耗尽、停止或退出时取消播放并释放手指。

## 启动

本机已经准备好 `.venv` 和编译后的播放核心。关闭旧 GUI 后，双击项目根目录的 `run_gui_src.bat`，或运行：

```powershell
cd D:\opencode-lab\bangdream-autodori
.\run_gui_src.bat
```

开始打歌后，日志应出现 `SSM inited`、`SSM ready`，随后显示 `SSM 触控`。这说明正在使用新后端。

在其他机器上，从源码启动前需要创建 `.venv`、安装 `requirements.txt`，并安装 Go 1.25 或更高版本，然后执行：

```powershell
.\.venv\Scripts\python.exe build_ssm.py
```

发布构建也会自动编译 Go 核心，并带上固定的 scrcpy server 3.3.1。

## 验证与复测

```powershell
go -C playback/ssm test ./...
.\.venv\Scripts\python.exe _test_ssm.py
.\.venv\Scripts\python.exe _test_chart.py
```

Go 测试、6 项 Python 接入测试和原有 15 项谱面检查均通过。已检查长条尾端、同拍换指、六指同时按下、同拍滑条、scrcpy 坐标编码、调度延迟追赶和取消、跨进程首音目标时刻、停止后重载及退出清理。SSM 原有测试也已保留并通过。

5 张实际缓存的 HARD 谱面均成功生成触控，并验证了每次移动/抬手都有对应按下、曲终没有残留手指：

| 谱面 | 触控动作数 | 使用手指数 |
| --- | --- | --- |
| YELL（474） | 8200 | 2 |
| 少女レイ（496） | 5004 | 2 |
| シカ色デイズ（655） | 3817 | 2 |
| goodbye（388） | 7860 | 2 |
| GO!!!（237） | 5903 | 2 |

已在本机 MuMuPlayer12 v5 上验证 scrcpy 连接建立与正常关闭，GUI 初始化和 SSM 日志显示也通过检查。

实机对比时固定 photogate、流速、画质和模拟器配置，关闭自动校准，优先用少女レイ、GO!!! 等常速曲比较原版和本版的 MISS、FAST/SLOW。这里已回退谱面解析改动；跨 BPM 的谱面时间仍按 v1.2.7 计算。

连接检查和离线测试不能证明整曲 MISS 已改善，需继续用实际打歌成绩判断。
