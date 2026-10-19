# beat-locked-vlog-editor

**中文** · [English](#english)

一个 Claude Code Skill（也可以单独当命令行工具用）：把一个文件夹的原始素材和一首 BGM，剪成**每一刀都落在鼓点上**的 vlog 混剪。镜头节奏跟着歌曲结构走，导出规格**不低于原素材**（例如 4K 50fps 10 位）。

## 适合剪什么

| 适合 ✅ | 不适合 ❌ |
|---|---|
| 以音乐为主、几乎没有对白的画面混剪 | 口播、采访、教程等以说话为主的视频（应按台词剪） |
| citywalk、旅行一日、探店、逛展/活动记录、周末或日常 vlog | 需要严格叙事连贯的剧情片 |
| 手持、稳定器、运动相机、手机拍的第一视角素材 | 没有 BGM 的视频（整套方法以节拍为骨架） |
| 30 秒到 5 分钟，横屏或竖屏 | 需要多机位同步、复杂特效的片子 |

## 它做什么

1. **实测节拍**：逐拍检测 BGM，并用底鼓定位每小节的第一拍。不用"一个锚点 + BPM"往后推算网格（这种算法几十秒后就会漂移 0.1–0.25 秒，听起来就是"没踩上点"）。
2. **选最稳的入点**：给每段素材的每 0.1 秒计算手抖程度，在你给定的候选窗口里自动挑最稳的一段。
3. **镜头长度跟着音乐段落走**：前奏用预告，副歌一小节一刀，音乐停顿时放慢，渐强时用半小节加速，结尾落在乐句的第一拍上。
4. **审片表**：先出原素材联系表供选镜，再出每个镜头首、中、尾三帧的复核表，查手指入镜、甩镜、招牌没拍全等问题。
5. **按原规格逐帧渲染**：画幅、分辨率、帧率都跟原素材一致（竖屏出竖屏，59.94fps 这类分数帧率也能做到逐帧精确）；调色全程 16 位，画面只编码一次；分辨率设得比原素材低时脚本会拒绝导出。
6. **成片验收**：从成片画面里检测切点，从混音里定位音乐位置，至少 90% 的切点落在节拍 ±40ms 内才算合格。
7. **按场景调色**：先识别晴天、阴天、黄昏、夜景、室内、雪景和季节，选对应的调色方案，再逐个镜头微调（亮的镜头和人脸少加暖）。
8. **可选**：主角美颜（仅 macOS）、地名字幕和开头标题。

## 安装

依赖：

- `ffmpeg` / `ffprobe` 6 或更新版本，需要带 libx265，以及 `colortemperature`、`vibrance`、`scdet` 这三个滤镜
  - macOS：`brew install ffmpeg`
  - Ubuntu：`sudo apt install ffmpeg`
  - Windows：用 gyan.dev 的 full build
- Python 3.9 或更新版本：`pip install -r requirements.txt`（只需要 numpy 和 Pillow）
- 美颜（可选，仅 macOS）：需要 Xcode 命令行工具，然后编译：
  `swiftc -O scripts/detect_faces.swift -o bin/detect_faces`

作为 Claude Code Skill 安装：

```bash
# 个人全局可用
git clone https://github.com/jackiezheng1318-hash/beat-locked-vlog-editor.git ~/.claude/skills/beat-locked-vlog-editor
# 或者只在某个项目里用
git clone https://github.com/jackiezheng1318-hash/beat-locked-vlog-editor.git <your-project>/.claude/skills/beat-locked-vlog-editor
```

然后对 Claude 说："用这些素材和这首歌剪一条 2 分钟的 citywalk vlog：素材在 `clips/`，BGM 是 `song.mp3`。"

自测（只用合成的音视频，约 20 秒）：

```bash
python tests/self_test.py
```

## 不用 Claude，手动跑

```bash
python scripts/beat_grid.py song.mp3 work/beats.json
python scripts/shot_stability.py work/stability.json clips/*.MP4
python scripts/raw_contact_sheets.py work/sheets work/stability.json clips/*.MP4
# 参照 examples/shots.csv 写好 work/shots.csv
python scripts/beat_locked_edl.py work/shots.csv work/beats.json work/stability.json work/edl --end 120
python scripts/shot_review.py work/edl.json work/review
python scripts/render_beat_locked.py work/edl.json song.mp3 out/final.mp4 work/render --adaptive-grade
python scripts/verify_beat_sync.py out/final.mp4 work/beats.json song.mp3
```

剪辑方法见 [references/method.md](references/method.md)，调色、美颜和字幕见 [references/captions-and-look.md](references/captions-and-look.md)。

## 局限

- 节拍检测针对鼓点清楚的流行、电子、说唱类音乐。纯钢琴、古典或没有鼓的歌，检测效果会差。
- 美颜依赖 macOS 的 Vision 框架；在其他系统上，把镜头清单里的 `beauty` 都设为 0 即可。
- 4K 10 位 HEVC 渲染比较慢，大约是实时长度的 10–15 倍（2 分钟的片子要 20–30 分钟）。
- AI 看不了正常速度的视频，节奏和审美最后要由人来判断。
- 方法提炼自一位作者的一条获认可的作品，是默认起点，不是定律。

## 许可证

MIT，见 [LICENSE](LICENSE)。你的素材和音乐的版权归你自己，本仓库不包含任何音视频素材。

---

## English

A Claude Code Skill (also usable as plain CLI scripts) that turns a folder of raw clips plus one
song into a montage where **every cut lands on the kick drum**, the shot rhythm follows the song's
structure, and the export is **never below the source spec** (e.g. 4K 50 fps 10-bit).

**Good for:** music-driven montages with little or no dialogue: city walks, travel days, food or shop visits, events, and weekend or daily-life vlogs. Works especially well with handheld, gimbal, action-cam or phone POV footage, 30 s to 5 min long.
**Not for:** talking-head, interview or tutorial videos (cut those on speech), scripted narrative, or videos without a BGM.

**Pipeline:**

1. `beat_grid.py` measures every beat and finds each bar's first beat from the kick drum.
2. `shot_stability.py` scores handheld shake for every 0.1 s of each clip.
3. `raw_contact_sheets.py` builds contact sheets of the raw footage for shot selection.
4. `beat_locked_edl.py` places every cut on a measured beat, with frame-exact durations and the steadiest in-point inside each candidate window.
5. `shot_review.py` shows the first, middle and last frame of every shot for review.
6. `render_beat_locked.py` grades in 16-bit RGB, encodes once, and outputs at the source resolution, frame rate and bit depth.
7. `verify_beat_sync.py` measures the cuts from the finished video's pixels; the edit passes when ≥ 90 % of cuts are within ±40 ms of a beat.

Also: scene-aware grading (sunny / overcast / golden hour / night / indoor / snow × season, then per-shot
adjustment), source-spec output including vertical and fractional frame rates (59.94 fps joins are
frame-exact), plus optional face retouch (macOS only) and captions.

**Install:**

- ffmpeg ≥ 6 with libx265
- `pip install -r requirements.txt` (numpy, Pillow)
- Optionally, `swiftc -O scripts/detect_faces.swift -o bin/detect_faces` on macOS for face retouch
- Clone into `~/.claude/skills/beat-locked-vlog-editor`
- Run `python tests/self_test.py` to check the setup

MIT licensed. No media is included.
