# JW.SWU
## A set of unities for jw.swu.edu.cn
## 仅供学习交流使用，禁止商用！！！
# 浏览器登录修复分支（候选版）

分支：`revive/browser-login`；上游基线：`47ed121937a7f98acc428983072e0ef6fc75c390`。

**状态：本地回归与模拟站浏览器测试通过；已在本机用户 Edge 中确认已登录教务主页及真实“当前不属于选课阶段”提示。助手独立浏览器的登录、开放期课程查询及实际选课结果仍待现场验收，不是选课功能已恢复的正式发布。**

## 修复思路

2022 年作者在 [Issue #3](https://github.com/F-19-F/JW.SWU/issues/3) 说明学校 SSO 新增浏览器校验，原登录失效。新版本不分析或绕过验证码，而是打开真实浏览器，由学生本人登录和完成验证，后续请求直接在当前教务页面执行同源 fetch。账号密码不交给 Python，不导出 Cookie，不关闭 TLS 验证。

- 不再依赖旧正则提取登录令牌和 `res.history[2]`。
- 修复终端等待输入期间浏览器事件未同步的问题：用户手动跳转或打开新标签页后，先同步页面状态再识别选课页；已关闭窗口和脱离页面的 iframe 分别处理。
- 从实际 DOM 的 input/select 当前值读取学年、学期、批次、类别及 CSRF 参数。
- 支持教学班、实践/子教学班的明确选择；修复原来默认第一个班和 `%2C` 双重编码问题。
- 修复第二目标课程匹配失败、空目标返回 None、整页后空页越界、重复分页死循环。
- 不再保存明文密码、不做无限登录重试或 0.8 秒抢课循环。
- 查询和提交分离；每次选课明确确认；超时或不明结果立即停止，先到网页核对。
- 浏览器中更换批次/类别后拒绝继续使用过期参数。

## Windows：双击启动

需要 Python 3.10+ 和 Microsoft Edge。第一次启动会在项目内建立 `.venv` 并安装依赖。

双击 `start.cmd`。如未安装系统 Python，本机 Codex 自带 Python 存在时启动器会自动使用它；其他电脑可安装 Python，或设置 `JW_SWU_PYTHON` 为解释器完整路径。

1. 新开的浏览器默认访问[新版办事大厅](https://ywtb.swu.edu.cn/)，在学校页面完成统一身份认证、验证码。
2. 进入教务系统 → 自主选课。开放期打开**具体选课批次与类别**；未开放时停留在学校关闭提示页也可以识别。只保留一个选课标签页。
3. 回终端按回车，输入课程名称关键词。
4. 选择课程、教师、上课时间对应的教学班；有实践课时再选择子教学班。
5. 核对信息，输入 `确认选课`，才发送一次选课请求。
6. 服务器返回成功后，必须在学校网页的“已选课程”和课表中核对。终端的成功提示只是服务器响应，并不是独立核验。

如果网页打不开，先区分“办事大厅打不开”和“大厅能打开但教务系统打不开”。校外访问教务系统时，按学校官方[无感 VPN 指引](https://nic.swu.edu.cn/info/1034/2159.htm)，在办事大厅点击“访问内网”；也可从[学校无感 VPN 入口](https://v.swu.edu.cn)进入。学校已发布[旧版 WebVPN 维护暂停通知](https://nic.swu.edu.cn/info/1042/2186.htm)，本版本不引导到旧 WebVPN。

默认入口已从旧教务系统固定 CAS 回跳地址更换为新版门户，让门户自行构造认证回跳参数。新版门户仍可能跳到 `uaaap.swu.edu.cn`，这属于学校当前认证链路，并不代表访问了旧门户。

退出输入 `q`。所有时间窗口、容量、冲突、学分限制仍由学校决定。非选课时段没有当前选课参数时，先用学校网页确认开放时段。

### 选课尚未开放时

- 正常模式：识别学校“当前不属于选课阶段”的可见提示，显示“已登录，选课未开放”，正常退出；不发送课程查询或选课提交。
- `-Action login`：进入教务主页即可验证登录，不要求打开选课类别。
- `-Action diagnose`：可在教务主页或未开放页输出 `teaching_home` / `selection_closed` 状态，仅输出参数名称，不输出参数值或个人信息。
- 只打开办事大厅不等于进入教务系统；教务主页通过实际登录标识确认，密码表单不被当成已登录。
- 主页和自主选课同时打开时，优先使用自主选课页。多个自主选课页仍需由学生关闭到唯一一个，避免选错批次。
- 未开放提示来自学校，工具不会尝试改变选课时间窗口。开放期再验证真实课程列表、教学班及正式选课结果。

```powershell
# 使用 Chrome / 使用独立 Chromium
.\start.ps1 -Browser chrome
.\start.ps1 -Browser chromium
# 只登录 / 脱敏诊断 / 完整本地测试
.\start.ps1 -Action login
.\start.ps1 -Action diagnose
.\start.ps1 -Action test
```

默认使用临时会话，程序退出后关闭窗口。不使用日常浏览器个人数据目录。可在命令行显式指定专用 `--profile browser-profile` 复用本地会话；不要把该目录发给他人或提交到 Git。

## macOS / Linux / 手工启动

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
python Course_Selection.py --browser chromium
```

Windows 手工启动使用 `.venv\Scripts\python.exe`。`ChromeLogin.py` 继续保留为登录入口。旧的 `Login(username, password)` 密码调用不再使用；新接口是 `session, num = Login()`，使用 `with session:` 关闭资源。

## 测试与测试边界

```sh
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python -m pytest -q --cov=BrowserSession --cov=Login --cov=Course_Selection --cov-report=term-missing
```

`tests/test_browser.py` 启动真实 Chromium，但通过路由拦截**全部**请求。它执行真实的 Login → DOM 参数读取 → 浏览器 Cookie → 查询 → 选择教学班 → 一次提交 → 模拟“已选课程”核对，并检验登录失效；模拟站不是学校生产系统。其他测试覆盖分页、接口异常、取消、错误班号输入、批次切换、子教学班、超时不重试、资源关闭和日志脱敏。CI 配置包含 Python 3.10/3.12/3.13；本次仅本机 Python 3.12 实测，远端 CI 尚未运行。

另有两项浏览器回归专门模拟终端 `input()` 阻塞时的独立页面跳转和弹出新标签页，避免只用 Playwright 自己点击导致事件循环问题被测试掩盖。公开入口已用真实 Edge 无账号访问验证为 HTTP 200；这不等于学生账号登录验证。

`requirements.txt` 为兼容范围；`requirements-tested.txt` 记录本次实测依赖版本。测试不需要真实账号，不上传页面、HAR、凭据或选课数据。

## 尚待真实验收

- 新浏览器能否完成学校当前 SSO 和浏览器校验，进入实际选课页面。
- 页面路径、隐藏字段和原正方接口是否仍与本分支兼容；目前接口路径基于上游代码，不是生产接口已验证声明。
- 普通课程与实践/子教学班的实际查询、时间显示、组合提交。
- 学生亲自确认一门课程后，学校已选课程与课表是否真实出现该教学班。

如果诊断报缺少字段或接口结构变化，保持浏览器在实际页面，先提供脱敏的字段名和错误提示，再逐项适配。不要直接上传完整 HTML、Cookie、密码或 HAR。

## 维护任务提示词

```text
请维护 JW.SWU 的 revive/browser-login 分支。
先读取 README 和测试，复现问题；保留学生亲自完成学校登录/验证码的流程。
用当前选课页面的脱敏字段名与响应结构核对上游接口，不把模拟通过视为生产可用。
修改前补回归测试；执行浏览器模拟测试、单次提交与取消测试，并更新验证记录。
避免日志中出现账号、Cookie、令牌或个人页面，提交前检查 diff。
最终分别报告：代码测试、真实登录、真实查询、实际选课核验、GitHub 发布状态。
```

## 发布与回滚

交付目录 `maintenance` 包含精确差异、原版 ZIP、逐文件 SHA-256、可执行 `ROLLBACK.sh`、Python 回滚器和验证记录。回滚器只接受与交付哈希完全一致的项目；存在后续编辑时先停止，不覆盖新工作。请先在副本试用。回滚恢复原来已失修的旧版，并非恢复一个生产可用版本。

本地分支与 Git bundle 可直接交接。本次未向上游写入或推送任何内容。需要发布到自己的 GitHub 时，先 fork 上游，再在本地分支执行：

```sh
git remote add mine https://github.com/YOUR_ACCOUNT/JW.SWU.git
git push mine revive/browser-login
```
