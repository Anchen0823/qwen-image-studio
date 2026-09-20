# Qwen Image Studio

面向 Windows 的 Qwen-Image-2.1 本地图像工作台。中文界面、批量排队、参考图编辑，以及可供 agent 调用的 JSON 命令行和 Codex skill。

## 启动

双击 `start.cmd`，或已创建的桌面 **Qwen Image Studio** 快捷方式。桌面使用 Tk + Pillow，无需浏览器或前端服务。

当前机器复用 `D:\AI\Qwen-Image-2.1` 下已安装的 Python 3.12、PyTorch CUDA、Pillow 和 DiffSynth-Studio 环境及模型。仓库不包含模型、环境或权重下载器。其他机器需要先安装兼容的 QwenImage21Pipeline；可用 `QWEN_MODEL_DIR` 指定模型安装根目录，再使用该环境的 Python 启动 `workbench.py`。

## 创作与批量队列

- 提示词自动按字符换行，适配中文与长英文；Enter 换行、Ctrl+Enter 入队。输入框有独立滚动条，小窗口也保留多行编辑空间。
- 切换“批量任务”，用独立一行 `---` 分隔提示词；每个提示词内部可换行。可导入本地 UTF-8 文本。
- 每个任务可生成 1–20 份，一次最多入队 200 项。入队时冻结参数；修改编辑器不会影响已排队任务。随机种子 `-1` 为每份生成独立种子，固定种子的重复份数保持相同种子。
- 添加参考图后使用同一批次提示词进行图片编辑。单任务或不同参数的批次也可使用命令行 JSON 导入。
- 按提交顺序逐项执行。暂停在当前任务结束后生效；取消可针对选中的等待或运行中任务。失败不阻塞后续任务，失败、取消或中断项可以重试。
- 队列保存到 `.state/queue.sqlite3`。正常关闭会中断本窗口负责的当前生成，等待任务保留；重新打开继续等待项。异常退出的运行项会标记中断，需手动重试。完整保存但未写回状态的图片可被恢复为完成。
- 桌面与 CLI 共用运行锁，避免二者同时使用 GPU。关闭界面不会停止另一个 CLI 拥有的运行器。多个不同工作目录的队列各自独立，不应同时对同一 GPU 运行。
- 双击任务查看完整提示词、参数、错误及日志；作品支持预览、另存为、历史记录与参数复用。

图片保存在 `outputs/*.png`，同名 `.json` 保存参数与结果，`.log` 保存模型日志。队列、提示词偏好、实际提示词文件、作品、参考图、benchmark 数据与模型均已加入 Git 忽略规则。公有仓库仅发布程序、文档与测试代码。

## Agent / 命令行

使用模型环境的 Python。以下 PowerShell 命令在项目根目录运行：

```powershell
$qwenPython = 'D:\AI\Qwen-Image-2.1\.venv\Scripts\python.exe'
& $qwenPython qwen_cli.py submit --batch local/batch.json
& $qwenPython qwen_cli.py run
& $qwenPython qwen_cli.py status
```

请先在忽略的 `local/` 目录准备自己的批次文件；该文件不随仓库分发。`submit` 只提交，桌面开启时会自动处理；未开桌面时，`run` 运行至队列为空或暂停。命令标准输出为 JSON，模型输出写入任务日志。`run` 进程成功退出不等于每个任务成功，需检查每项 `status`，失败任务仍会保留并继续后续任务。

| 命令 | 行为 |
| --- | --- |
| `submit --prompt "描述"` | 提交单项，支持 `--width --height --steps --seed --edit` |
| `submit --prompt-file prompts.txt` | 用 `---` 分隔的 UTF-8 批次 |
| `submit --batch batch.json` | 各项可指定独立参数的 JSON 数组 |
| `status --id TASK_ID` | 获取单项状态、实际种子、结果路径或错误 |
| `wait TASK_ID --timeout 60` | 有界等待，不会启动运行器 |
| `cancel TASK_ID` / `retry TASK_ID` | 取消或重试单项 |
| `pause` / `resume` | 修改调度状态，resume 本身不启动运行器 |

全局参数 `--workspace PATH`、`--model-dir PATH` 必须放在子命令之前。长文本建议使用 UTF-8 文件以避免 shell 转义问题。默认 512×512、40 步；1–4 步仅用于运行通路测试。

## Codex skill

`skills/qwen-image-local` 是可安装的完整 skill，包含说明、界面元数据和 CLI 适配器。运行 `./install-skill.ps1` 安装到个人 Codex skills 目录（遵循 `CODEX_HOME`）。新会话中使用 `$qwen-image-local` 请求生成或编辑图片；如果工作台迁移，可设置 `QWEN_WORKBENCH`。

Skill 经 frontmatter 验证，入口支持相同的队列命令。它使用本地 Qwen 模型，不依赖远程图像生成服务。

## 实现与验证

- `workbench.py`：中文桌面布局、编辑器、预览、队列与历史。
- `engine.py`：SQLite 持久化、原子批量提交、操作系统锁、后台执行及状态恢复。
- `worker.py`：离线 Qwen 推理、进度事件、原子图片保存。
- `qwen_cli.py`：JSON 命令接口；`skills/` 为 agent 使用说明。

```powershell
& $qwenPython tests/test_engine.py
& $qwenPython tests/ui_smoke.py
# 下列测试会真实占用 GPU、生成两张低步数图片：
& $qwenPython tests/gpu_smoke.py
```

自动测试覆盖批次原子性、中文多行文本、先进先出、单运行器竞争、失败续跑、运行中取消、重试、暂停恢复、CLI JSON、界面换行及参数快照。UI 测试使用明确的模拟进程；GPU 测试独立调用真实模型。检查截图和测试输出位于忽略的 `verification/`。

本机为 RTX 4060 Laptop 8GB。早期 512×512、40 步安装测试约 8 分钟；实际耗时受显存、磁盘、分辨率及参考图影响。推理每项独立加载模型，任务完成后释放显存。

常用图像生成 benchmark、官方入口与本机测试建议见 [BENCHMARKS.md](BENCHMARKS.md)。
