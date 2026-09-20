# 图像生成 benchmark 选型

核对日期：2026-09-21。下列是官方论文或项目维护的测试集；本项目未声称已经获得它们的正式分数。实际数据、生成图、任务提示词、日志与评分结果仅放在 Git 忽略目录。

## 建议组合

先使用 **GenEval + LongText-Bench** 分别检查基础组合能力和中英文文字渲染，再增加 **DPG-Bench** 的复杂描述。GenEval 2 可以补充更复杂的组合能力，Qwen-Image-Bench 则适合资源充裕时做综合评估。

| 测试集 | 主要考察内容 | 评分与运行条件 |
| --- | --- | --- |
| [GenEval](https://github.com/djghosh13/geneval) | 单物体、双物体、数量、颜色、位置、颜色归属 | 官方原始元数据实查 553 条；常规每提示词 4 图。评分需要独立的 Mask2Former / MMDetection 环境。适合作为基础诊断。 |
| [DPG-Bench](https://github.com/TencentQQGYLab/ELLA#-dpg-bench) | 较长、稠密描述中多个细节和关系能否同时满足 | 官方建议每条生成 4 图并组成 2×2 网格，通过问答式评估；须保留官方提示词文件名与评分协议。 |
| [T2I-CompBench / ++](https://github.com/Karine-Huang/T2I-CompBench) | 属性绑定、空间关系、数量及复杂组合 | 各维度分别使用 BLIP-VQA、UniDet、CLIP 等评估工具；++ 与原版协议不能混用。旧依赖建议隔离安装。 |
| [GenEval 2](https://github.com/facebookresearch/GenEval2) | 800 条更高组合复杂度描述；物体、属性、关系、数量 | 使用 Soft-TIFA；当前官方实现采用 Qwen3-VL-8B-Instruct，需额外评判模型。8GB 显存不应直接假设能原精度全量加载。 |
| [LongText-Bench](https://huggingface.co/datasets/X-Omni/LongText-Bench) | 中英文长文字、招牌、海报、幻灯片等 8 类场景 | 当前官方文件实查英文 160 条、中文 160 条；每条标准采样 4 次。[官方评估代码](https://github.com/X-Omni-Team/X-Omni/tree/main/textbench)使用视觉语言模型评估文本。特别适合补测 Qwen 的文字能力。 |
| [Qwen-Image-Bench](https://github.com/QwenLM/Qwen-Image-Bench) | 质量、美感、语义对齐、真实世界一致性、创意，覆盖 56 个细分面向 | 官方 Q-Judger 基于 Qwen3.6-27B；输入包括 ID、提示词、图片路径。本机 8GB 不适合直接照搬默认评判配置，应另配评估资源。 |

Qwen 团队的[原始模型介绍](https://qwenlm.github.io/blog/qwen-image/)也采用了 GenEval、DPG 和 LongText-Bench 等测试。这里用它说明选型依据，不把其他模型或旧版本的分数当作本机 Qwen-Image-2.1 的结果。

## 本机运行建议

1. 先做约 24 张的分层诊断，例如 GenEval 六类各抽 2 条（12 张），LongText 中英文各抽 6 条（12 张）。保存抽样规则、原始条目 ID 与固定种子，不挑图替换失败项。
2. 512×512、40 步可作为本机的固定诊断设置，但长文字可能需要更高分辨率。修改分辨率、采样次数或评分器后，应明确标为自定义配置，不能直接对照官方榜单。
3. 以本机早期约 8 分钟/张估算，24 张约 3.2 小时；GenEval 全集按 553×4 张计算，单生成阶段约 12.3 天。这是粗略线性估计，未计评分时间，也不是性能保证。
4. 生成与评判分阶段运行，释放生成模型后再加载评分模型；为官方评分工具建立独立环境，避免覆盖工作台的 DiffSynth / PyTorch 依赖。
5. 报告同时给出样本数、成功/失败数、参数、模型版本、评分器版本、逐类结果。抽样结果不称为完整 benchmark 分数；视觉浏览也不替代官方评分。

## 已核实的本地元数据

本次从官方地址下载并解析了 GenEval、GenEval 2 和 LongText-Bench 中英文文件，保存在忽略的 `benchmarks/data/`。来源 URL 与 SHA-256 保存在该目录的 `sources.json`，不随公有仓库上传。

GenEval 输出按提示词索引分目录，每个目录含 `metadata.jsonl` 与 `samples/`；LongText 输出遵循 `{prompt_id}_{repeat_id}.png`，且中英文应分目录以免 ID 碰撞。工作台当前采用任务 ID 文件名，因此正式评分前需要明确的导出映射，不能直接把 `outputs/` 当成官方评分输入。

GenEval 2 评估输入是提示词到图片路径的 JSON 映射，其官方代码支持 `soft_tifa_am` 与 `soft_tifa_gm`。正式运行时应固定[评估代码版本](https://github.com/facebookresearch/GenEval2/blob/main/evaluation.py)，并遵守其 CC BY-NC 4.0 许可。

## 风格探索与正式 benchmark 的区别

用户指定的约 10 张多风格生成属于非正式风格探索。公开提示词模板经过改写后，不再属于任何官方测试集。其提示词、来源、任务 ID、图片与日志保存在本地忽略目录，不计作正式 benchmark 结果，也不上传到 GitHub。
