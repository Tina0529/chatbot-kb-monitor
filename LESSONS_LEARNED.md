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
