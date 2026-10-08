# SSM 本地谱面、触控与计时版本

这个版本读取 SSM GUI 已解包的本地 BanG BMS 谱面，由 SSM 原版 Go 解析器计算音符时间、轨道和连接，再交给同一套触控生成与播放核心。

## 实际执行流程

```text
现有 GUI / MAA 选曲
  → 按曲目 id / 难度查找本地 BMS 文件
  → SSM ParseBMS（完整 BPM 时间表、长条、滑条、方向甩尾）
  → SSM GenerateHumanizedTouchEvent（随机扰动 / Great 模式关闭）
  → SSM 冲突图和 DSATUR 手指分配
  → SSM scrcpy 触控编码
  → SSM Go playEvents 绝对时间调度
  → 模拟器
```

SSM 来源固定为 [v3.7.0 / 061d1b8](https://github.com/hj6hki123/ssm-gui/tree/061d1b880e42b57698be35e9a4a841a44a684fef)。BMS 解析、触控生成、手指分配和调度循环直接复用 Go 源码。`scores/bms.go` 与 SSM release 附带的源码逐字节一致。

Bestdori 仍用于曲目名称、id 和难度等元数据。实际播放不再调用 Bestdori JSON 谱面、旧拍数换算器或 timed-note 转换接口。

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

`SSM ready` 同时显示 `本地 BMS <文件名>`，用于确认曲目和难度对应的实际输入。

在其他机器上，从源码启动前需要创建 `.venv`、安装 `requirements.txt`，并安装 Go 1.25 或更高版本，然后执行：

```powershell
.\.venv\Scripts\python.exe build_ssm.py
```

发布构建也会自动编译 Go 核心，并带上固定的 scrcpy server 3.3.1。

## 导入本地谱面

从 SSM GUI release 目录导入，或直接传入其 `assets/star/forassetbundle/startapp/musicscore` 目录：

```powershell
.\.venv\Scripts\python.exe import_ssm_charts.py "D:\ssm-gui-windows-3.7.0-full-amd64"
```

只复制已解包的 `.txt` 谱面，保留 `musicscore*/NNN/*_<难度>.txt` 结构。目标目录是 `data/ssm/charts`；这份本地数据不进入 Git，发布构建在该目录存在时会把谱面带入发布包。

查找规则与 SSM GUI 一致：按曲目 id 和难度匹配，多个匹配按路径排序取第一个。缺少对应曲目或难度时明确报错，不替换成其他谱面。本机已从用户已有的 release 导入 757 首歌、1656 张谱面：HARD 757、EXPERT 757、SPECIAL 142；导入文件逐字节校验通过。这份 release 没有 EASY/NORMAL 谱面。

## 验证与复测

```powershell
go -C playback/ssm test ./...
.\.venv\Scripts\python.exe _test_ssm.py
```

Go 测试和 13 项 Python 接入测试覆盖跨 BPM 长条、方向甩尾合并、本地导入与曲目/难度匹配、缺失或被解析器拒绝的谱面、首音目标时刻、停止后重载及退出清理。已有触控、手指分配、scrcpy 编码、调度和 SSM 人性化测试继续保留。

以下 8 张实际本地 BMS 谱面成功生成触控，并验证了每次移动/抬手都有对应按下、曲终没有残留手指：

| 谱面 | 触控动作数 | 使用手指数 |
| --- | --- | --- |
| YELL（474，HARD） | 8219 | 2 |
| 少女レイ（496） | 5004 | 2 |
| シカ色デイズ（655） | 3819 | 2 |
| goodbye（388） | 7860 | 2 |
| GO!!!（237） | 5903 | 2 |
| SENSENFUKOKU（596，SPECIAL） | 8310 | 2 |
| 一夜物語（487，SPECIAL） | 8394 | 2 |
| HELL! or HELL?（486，SPECIAL） | 8211 | 2 |

已发现上游限制：`#786 SPECIAL` 在原版 SSM BMS 解析器中报 `Slide End B ... has no slide head`；本版保留相同解析行为，并向界面报告被拒绝的谱面文件。SSM BMS 源码也将该谱面的宽轨键处理标记为未实现。

此前已在本机 MuMuPlayer12 v5 上验证 scrcpy 连接建立与正常关闭；本次控制变量实验只更换谱面输入与解析，保持原首音检测、photogate、触控参数和调度方式。

实机对比时固定 photogate、流速、画质和模拟器配置，关闭自动校准，用同曲同难度比较切换本地 BMS 前后的 MISS、FAST/SLOW。首音同步仍由本项目的截图检测决定。

连接检查和离线测试不能证明整曲 MISS 已改善，需继续用实际打歌成绩判断。
