# KB Monitor GitHub Actions 部署经验总结

## 项目概述
将知识库监控脚本部署到 GitHub Actions，实现定时监控知识库文件学习状态，并通过 Lark 发送通知。

## 遇到的问题与解决方案

### 1. 扫描到 0 items - 选择器错误

**问题：**
- 使用 `tbody tr` 选择器无法找到表格行
- 页面显示正常，但脚本扫描不到任何文件

**原因：**
- 目标页面使用 **Mantine UI** 框架
- 实际的 class 是 `.mantine-Table-tbody tr`
- 标准的 `tbody tr` 选择器无法匹配

**解决方案：**
- 创建调试模式脚本，输出页面 HTML 进行分析
- 发现正确的选择器：`.mantine-Table-tbody tr`
- 添加多选择器策略，按优先级尝试

**经验教训：**
- 先用调试模式分析页面结构，不要假设标准 HTML 结构
- 现代 UI 框架（Mantine、Ant Design 等）使用自定义 class
- 使用浏览器开发者工具检查真实元素结构

---

### 2. 没有登录步骤 - 认证缺失

**问题：**
- 直接访问 `DIRECT_KB_URL` 无法获取数据
- 页面可能重定向或显示空白

**原因：**
- KB 页面需要登录认证
- 初始版本直接导航到目标 URL，跳过了登录流程

**解决方案：**
```python
# Step 1: 先登录
await page.goto(base_url)
await page.fill('input[name="username"]', username)
await page.fill('input[type="password"]', password)
await page.locator('button[type="submit"]').click()

# Step 2: 再导航到目标页面
await page.goto(direct_kb_url)
```

**经验教训：**
- 检查页面是否需要认证
- 模拟完整的用户操作流程
- 添加足够的等待时间让页面加载

---

### 3. 图片显示为方框 - 缺少日语字体

**问题：**
- Lark 消息中的截图日文文字显示为方框 (tofu)
- 本地运行正常，GitHub Actions 显示异常

**原因：**
- GitHub Actions Ubuntu 环境默认只安装英文字体
- Playwright 截图使用系统字体渲染
- 日文汉字、假名无法渲染，显示为方框

**解决方案：**
在 workflow 中安装 CJK 字体：
```yaml
- name: Install system dependencies
  run: |
    sudo apt-get install -y \
      fonts-noto-cjk \
      fonts-noto-cjk-extra
```

**经验教训：**
- CI/CD 环境可能缺少某些语言字体
- CJK（中日韩）内容需要专门的字体包
- Noto CJK 是开源的 CJK 字体解决方案

---

### 4. 时间显示不正确 - 时区问题

**问题：**
- 显示的时间不是日本时间
- 标记为 `(Asia/Tokyo)` 但实际是 UTC 时间

**原因：**
```python
# 错误写法 - 获取的是 UTC 时间
datetime.now().strftime('%Y-%m-%d %H:%M')
```

**解决方案：**
```python
# 正确写法 - 使用 UTC+9 时区
from datetime import timezone, timedelta

japan_tz = timezone(timedelta(hours=9))
datetime.now(japan_tz).strftime('%Y-%m-%d %H:%M')
```

**经验教训：**
- `datetime.now()` 默认返回系统时间（UTC）
- 需要明确指定时区才能获取正确时间
- 日本时间是 UTC+9

---

### 5. lark_oapi 导入错误 - 路径不正确

**问题：**
```
ModuleNotFoundError: No module named 'lark_oapi.im'
```

**原因：**
- 使用了错误的导入路径
- lark-oapi SDK 的正确路径包含 `api` 目录

**解决方案：**
```python
# 错误
from lark_oapi.im.v1.model.create_image_request import CreateImageRequest

# 正确
from lark_oapi.api.im.v1.model.create_image_request import CreateImageRequest
```

**经验教训：**
- 参考官方文档的导入示例
- 与本地工作正常的代码对比
- SDK 版本可能有差异，注意版本兼容性

---

### 6. 图片上传失败 - HTTP 实现问题

**问题：**
- 使用 HTTP POST 上传图片，返回成功但图片无法显示
- 图片显示为乱码或方框

**原因：**
- HTTP multipart/form-data 实现可能有问题
- SDK 封装了正确的请求格式

**解决方案：**
使用官方 SDK 的标准方式：
```python
import lark_oapi
from lark_oapi.api.im.v1.model.create_image_request import CreateImageRequest
from lark_oapi.api.im.v1.model.create_image_request_body import CreateImageRequestBody

request = (
    CreateImageRequest.builder()
    .request_body(
        CreateImageRequestBody.builder()
        .image_type("message")
        .build()
    )
    .build()
)

with open(image_file, 'rb') as f:
    request.body.image = f
    client = lark_oapi.Client.builder().app_id(app_id).app_secret(app_secret).build()
    response = client.im.v1.image.create(request)
```

**经验教训：**
- 优先使用官方 SDK
- SDK 处理了边界情况和签名
- 自实现 HTTP 容易出错

---

### 7. GitHub Actions 队列延迟 - 调度时间不等于执行时间

**问题：**
- 设置 cron: `20 0 * * *` (UTC 00:20 = JST 09:20)
- 但实际执行时间可能延迟 20-30 分钟
- 通知消息显示时间为实际执行完成时间，而非触发时间

**原因：**
- GitHub Actions 使用公共 runner 时，任务需要排队等待
- 高峰时段（如早上 9 点）队列等待时间更长
- **触发时间** ≠ **开始执行时间**
- 手动触发通常立即执行，定时触发可能延迟

**实际案例：**
| 触发方式 | 触发时间 | 开始时间 | 完成时间 | 延迟 |
|---------|---------|---------|---------|------|
| 手动触发 | 立即 | 立即 | ~1分钟后 | 几乎无延迟 |
| 定时触发 | 09:20 | 09:47 | 09:48 | ~27分钟 |

**解决方案：**
- **方案1（推荐）**: 调整 cron 时间，预留缓冲
  ```yaml
  # 原计划 09:20 执行，提前 30 分钟设置
  schedule:
    - cron: '50 23 * * *'  # UTC 23:50 = JST 08:50
  ```
- **方案2**: 接受延迟，只要每天能监控即可
- **方案3**: 使用付费的 self-hosted runner���无队列延迟）

**经验教训：**
- GitHub Actions 免费版公共 runner 有队列延迟
- 定时任务的触发时间只是进入队列的时间
- 对时间敏感的任务需要考虑提前调度或使用付费方案
- 手动触发可以快速验证脚本功能
- 查看日志中的 "Started at" 确认实际执行时间

---

## 下次注意事项

### 开发阶段

1. **先调试页面结构**
   - 使用调试模式分析页面 HTML
   - 找到正确的 CSS 选择器
   - 不要假设标准 HTML 结构

2. **检查认证流程**
   - 确认页面是否需要登录
   - 完整模拟用户操作
   - 处理可能的登录失败

3. **参考本地实现**
   - 对比本地工作正常的代码
   - 使用相同的 SDK 和导入路径
   - 保持实现一致性

### 部署阶段

4. **字体支持**
   - CJK 内容需要安装对应字体
   - `fonts-noto-cjk` 是通用解决方案
   - 测试截图中的文字是否正常

5. **时区处理**
   - 明确需要的时区
   - 使用 `datetime` 的 timezone 参数
   - 在消息中标注时区

6. **使用官方 SDK**
   - 图片上传等功能优先用 SDK
   - 避免 HTTP 自实现
   - 参考官方文档示例

### 调试技巧

7. **添加调试模式**
   - 输出页面 HTML
   - 尝试多个选择器
   - 保存截图和日志

8. **错误处理**
   - 图片上传失败不应阻塞主流程
   - 发送详细的错误通知
   - 记录完整的调试信息

---

## GitHub Actions Workflow 操作指南

### 快速开始

为其他项目设置 GitHub Actions 时，按照以下步骤操作：

### 1. 创建 Workflow 文件

在项目根目录创建 `.github/workflows/` 目录结构：

```bash
mkdir -p .github/workflows
```

创建 workflow YAML 文件（如 `my-task.yml`）：

```yaml
name: My Task  # workflow 名称

on:
  # 定时触发
  schedule:
    - cron: '0 9 * * *'  # 每天 UTC 9:00

  # 手动触发
  workflow_dispatch:

jobs:
  my-job:
    name: My Job
    runs-on: ubuntu-latest

    steps:
      # 1. 检出代码
      - name: Checkout code
        uses: actions/checkout@v4

      # 2. 设置 Python
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      # 3. 安装依赖
      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      # 4. 运行脚本
      - name: Run my script
        env:
          MY_SECRET: ${{ secrets.MY_SECRET }}
        run: |
          python my_script.py
```

### 2. 设置 Secrets（敏感信息）

**步骤：**

1. 打开 GitHub 仓库页面
2. 点击 **Settings** → **Secrets and variables** → **Actions**
3. 点击 **New repository secret**
4. 添加所需的密钥

**常用 Secrets 类型：**

| 类型 | 示例 | 说明 |
|------|------|------|
| 用户名/密码 | `USERNAME`, `PASSWORD` | 登录凭据 |
| API Key | `API_KEY`, `TOKEN` | 第三方 API 访问 |
| Webhook URL | `WEBHOOK_URL` | 通知回调 |
| App ID/Secret | `APP_ID`, `APP_SECRET` | 应用认证 |

**在 Workflow 中使用：**

```yaml
env:
  USERNAME: ${{ secrets.USERNAME }}
  PASSWORD: ${{ secrets.PASSWORD }}
```

或直接在步骤中引用：

```yaml
- name: Run script
  run: python script.py --token ${{ secrets.MY_TOKEN }}
```

### 3. Cron 表达式说明

**格式：** `分钟 小时 日期 月份 星期`

**常用示例：**

| Cron 表达式 | UTC 时间 | 日本时间 | 说明 |
|------------|---------|---------|------|
| `0 0 * * *` | 00:00 | 09:00 | 每天 9 点 |
| `20 0 * * *` | 00:20 | 09:20 | 每天 9:20 |
| `0 1 * * *` | 01:00 | 10:00 | 每天 10 点 |
| `0 */6 * * *` | 每 6 小时 | 每 6 小时 | 每 6 小时一次 |
| `0 9 * * 1-5` | 09:00 | 18:00 | 工作日 18 点 |
| `0 0 * * 0` | 00:00 | 09:00 | 每周日 9 点 |

**时区转换公式：**
```
日本时间 (JST) = UTC 时间 + 9 小时
UTC 时间 = 日本时间 - 9 小时
```

**提前调度（应对队列延迟）：**
```yaml
# 希望日本时间 9:00 执行，考虑 30 分钟延迟
schedule:
  - cron: '30 23 * * *'  # UTC 23:30 = JST 08:30
```

### 4. 手动触发 Workflow

**方法 1：通过网页**
1. 访问 `https://github.com/用户名/仓库名/actions`
2. 点击左侧的 workflow 名称
3. 点击右侧 **"Run workflow"** 按钮
4. 选择分支（通常是 `master` 或 `main`）
5. 如果有输入参数，设置后点击 **"Run workflow"**

**方法 2：通过 GitHub CLI**
```bash
gh workflow run "My Task"
```

### 5. 常用 Workflow 配置

#### 5.1 设置超时时间

```yaml
jobs:
  my-job:
    runs-on: ubuntu-latest
    timeout-minutes: 30  # 30 分钟后超时
```

#### 5.2 条件执行

```yaml
# 只在主分支运行
if: github.ref == 'refs/heads/main'

# 只在手动触发时运行
if: github.event_name == 'workflow_dispatch'

# 只在 Push 时运行
if: github.event_name == 'push'
```

#### 5.3 矩阵策略（多版本测试）

```yaml
strategy:
  matrix:
    python-version: ['3.9', '3.10', '3.11']
    os: [ubuntu-latest, windows-latest]

steps:
  - uses: actions/setup-python@v4
    with:
      python-version: ${{ matrix.python-version }}
```

#### 5.4 缓存依赖（加速构建）

```yaml
- name: Cache pip packages
  uses: actions/cache@v3
  with:
    path: ~/.cache/pip
    key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements.txt') }}
```

#### 5.5 上传 Artifact（保存输出）

```yaml
# 保存文件
- name: Upload artifacts
  uses: actions/upload-artifact@v4
  with:
    name: my-output
    path: output/
    retention-days: 7  # 保留 7 天

# 失败时也保存
- name: Upload logs on failure
  if: failure()
  uses: actions/upload-artifact@v4
  with:
    name: logs
    path: logs/
```

### 6. Python 项目常用配置

#### 6.1 安装系统依赖

```yaml
- name: Install system dependencies
  run: |
    sudo apt-get update
    sudo apt-get install -y \
      libnss3 \
      libnspr4 \
      libatk1.0-0 \
      libatk-bridge2.0-0 \
      libcups2 \
      fonts-liberation \
      fonts-noto-cjk  # CJK 字体
```

#### 6.2 安装 Playwright

```yaml
- name: Install Playwright
  run: |
    pip install playwright
    playwright install chromium
```

#### 6.3 使用虚拟环境

```yaml
- name: Set up virtual environment
  run: |
    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt

- name: Run script
  run: |
    source venv/bin/activate
    python my_script.py
```

### 7. 调试技巧

#### 7.1 启用调试日志

```yaml
- name: Run script with debug
  env:
    DEBUG: "true"
  run: python my_script.py
```

#### 7.2 使用 tmate 进行交互式调试

```yaml
- name: Setup tmate session
  if: failure()
  uses: mxschmitt/action-tmate@v3
  timeout-minutes: 30
```

#### 7.3 查看 Workflow 日志

1. 访问 Actions 页面
2. 点击具体的 workflow 运行
3. 点击 job 名称
4. 展开步骤查看详细日志

### 8. Workflow 模板

#### 8.1 简单定时任务

```yaml
name: Scheduled Task

on:
  schedule:
    - cron: '0 0 * * *'  # 每天 UTC 0:00
  workflow_dispatch:

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - run: pip install -r requirements.txt
      - run: python script.py
```

#### 8.2 带重试的任务

```yaml
name: Task with Retry

on:
  schedule:
    - cron: '0 0 * * *'
  workflow_dispatch:

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run with retry
        uses: nick-fields/retry@v2
        with:
          timeout_minutes: 10
          max_attempts: 3
          command: python script.py
```

#### 8.3 多环境配置

```yaml
name: Multi-Environment

on:
  workflow_dispatch:
    inputs:
      environment:
        description: 'Environment'
        required: true
        type: choice
        options:
          - dev
          - staging
          - production

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to ${{ github.event.inputs.environment }}
        run: |
          echo "Deploying to ${{ github.event.inputs.environment }}"
          # 部署命令
```

### 9. 常见问题

| 问题 | 解决方案 |
|------|---------|
| **Workflow 不触发** | 检查 cron 语法，确认文件在 `.github/workflows/` 目录 |
| **Secrets 读取失败** | 确认 Secret 名称正确，区分大小写 |
| **超时错误** | 增加 `timeout-minutes` 或优化脚本性能 |
| **权限错误** | 在 workflow 中添加 `permissions` 配置 |
| **找不到文件** | 确认使用 `actions/checkout@v4` 检出代码 |

---

## 有用的资源

### Mantine UI
- 官方文档: https://mantine.dev/
- Table 组件: https://mantine.dev/core/table/

### Lark API
- 图片上传: https://open.larksuite.com/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/image/create
- Python SDK: https://github.com/larksuite/lark-oapi-python

### Playwright
- Python 文档: https://playwright.dev/python/
- 选择器指南: https://playwright.dev/python/selectors/

### GitHub Actions
- 文档: https://docs.github.com/en/actions
- Secrets: https://docs.github.com/en/actions/security-guides/encrypted-secrets

---

## 更新历史

| 日期 | 更新内容 |
|------|---------|
| 2026-01-18 | 初始版本 - 记录部署过程中遇到的问题和解决方案 |
| 2026-01-19 | 添加 GitHub Actions 队列延迟问题说明 |
| 2026-01-19 | 添加完整的 GitHub Actions Workflow 操作指南 |
