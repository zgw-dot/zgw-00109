# 离线巡检任务包服务

本地可启动的后端服务，用于管理离线巡检任务包的完整生命周期。

## 功能特性

- **巡检模板管理**：创建、查询、更新、删除巡检模板及检查项
- **任务包生命周期**：草稿 → 已发放 → 已同步 → 已关闭 的完整状态流转
- **读数上传**：支持离线采集后批量上传读数
- **冲突检测与解决**：自动检测同一设备同一检查项的读数冲突，支持手动解决
- **审计日志**：完整记录所有关键操作
- **报告导出**：支持 JSON 和 Excel 格式导出巡检报告
- **数据持久化**：基于 SQLite，重启后数据不丢失

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动服务

```bash
python main.py
```

服务将在 `http://localhost:8000` 启动。

### 3. 访问 API 文档

- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc

## 核心概念

### 状态流转

```
draft(草稿) → issued(已发放) → synced(已同步) → closed(已关闭)
     ↑              ↑
     └─────rollback─┘
```

| 状态 | 说明 | 允许操作 |
|------|------|----------|
| draft | 任务包刚创建，尚未发放 | 可编辑、可发放 |
| issued | 任务包已发放给现场人员 | 可上传读数、可撤回为草稿 |
| synced | 读数已同步完成，无冲突 | 可关闭、可回退为已发放 |
| closed | 任务包已关闭归档 | 只读 |

### 冲突检测规则

当上传读数时，若同一任务包下同一设备的同一检查项已存在读数且值不相同：
1. 不覆盖原有读数（保护已有数据）
2. 创建一条 `open` 状态的冲突记录
3. 返回冲突信息，等待人工解决

## API 接口说明

### 1. 巡检模板管理

#### 创建模板
```bash
curl -X POST "http://localhost:8000/api/templates" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "变压器日常巡检模板",
    "description": "用于变压器的日常巡检工作",
    "check_items": [
      {
        "device_code": "TRANS-001",
        "item_name": "油温",
        "unit": "°C",
        "standard_value": "≤85",
        "tolerance": "±5"
      },
      {
        "device_code": "TRANS-001",
        "item_name": "油位",
        "unit": "mm",
        "standard_value": "150-250",
        "tolerance": "±10"
      },
      {
        "device_code": "TRANS-002",
        "item_name": "油温",
        "unit": "°C",
        "standard_value": "≤85",
        "tolerance": "±5"
      }
    ]
  }'
```

#### 查询模板列表
```bash
curl "http://localhost:8000/api/templates"
```

#### 查询单个模板
```bash
curl "http://localhost:8000/api/templates/1"
```

#### 更新模板
```bash
curl -X PUT "http://localhost:8000/api/templates/1" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "变压器日常巡检模板V2"
  }'
```

#### 删除模板
```bash
curl -X DELETE "http://localhost:8000/api/templates/1"
```

### 2. 任务包管理

#### 创建任务包
```bash
curl -X POST "http://localhost:8000/api/task-packages" \
  -H "Content-Type: application/json" \
  -d '{
    "package_no": "PKG-2024-001",
    "template_id": 1,
    "operator": "管理员"
  }'
```

#### 发放任务包
```bash
curl -X POST "http://localhost:8000/api/task-packages/PKG-2024-001/issue?operator=管理员"
```

#### 标记为已同步
```bash
curl -X POST "http://localhost:8000/api/task-packages/PKG-2024-001/sync?operator=管理员"
```

#### 关闭任务包
```bash
curl -X POST "http://localhost:8000/api/task-packages/PKG-2024-001/close?operator=管理员"
```

#### 撤回为草稿
```bash
curl -X POST "http://localhost:8000/api/task-packages/PKG-2024-001/rollback-draft?operator=管理员"
```

#### 查询任务包列表
```bash
# 全部任务包
curl "http://localhost:8000/api/task-packages"

# 按状态过滤
curl "http://localhost:8000/api/task-packages?status=issued"
```

#### 查询任务包详情
```bash
curl "http://localhost:8000/api/task-packages/PKG-2024-001"
```

#### 查询任务包读数
```bash
curl "http://localhost:8000/api/task-packages/PKG-2024-001/readings"
```

#### 查询任务包冲突
```bash
curl "http://localhost:8000/api/task-packages/PKG-2024-001/conflicts"
```

### 3. 读数上传

#### 批量上传读数
```bash
curl -X POST "http://localhost:8000/api/readings/upload" \
  -H "Content-Type: application/json" \
  -d '{
    "package_no": "PKG-2024-001",
    "readings": [
      {
        "device_code": "TRANS-001",
        "item_name": "油温",
        "reading_value": "78",
        "collected_at": "2024-01-15T10:30:00",
        "source_type": "offline"
      },
      {
        "device_code": "TRANS-001",
        "item_name": "油位",
        "reading_value": "180",
        "collected_at": "2024-01-15T10:31:00",
        "source_type": "offline"
      },
      {
        "device_code": "TRANS-002",
        "item_name": "油温",
        "reading_value": "72",
        "collected_at": "2024-01-15T10:32:00",
        "source_type": "offline"
      }
    ]
  }'
```

#### 查询读数列表
```bash
# 全部读数
curl "http://localhost:8000/api/readings"

# 按任务包过滤
curl "http://localhost:8000/api/readings?package_no=PKG-2024-001"

# 按设备过滤
curl "http://localhost:8000/api/readings?device_code=TRANS-001"
```

### 4. 冲突管理

#### 查询冲突列表
```bash
# 全部冲突
curl "http://localhost:8000/api/conflicts"

# 未解决的冲突
curl "http://localhost:8000/api/conflicts?status=open"

# 按任务包过滤
curl "http://localhost:8000/api/conflicts?package_no=PKG-2024-001"
```

#### 解决冲突
```bash
# 保留新值
curl -X POST "http://localhost:8000/api/conflicts/1/resolve" \
  -H "Content-Type: application/json" \
  -d '{
    "resolution_note": "现场核实，第二次读数更准确",
    "keep_value": "new",
    "resolved_by": "管理员"
  }'

# 保留原值
curl -X POST "http://localhost:8000/api/conflicts/1/resolve" \
  -H "Content-Type: application/json" \
  -d '{
    "resolution_note": "第一次读数正确，第二次为误操作",
    "keep_value": "existing",
    "resolved_by": "管理员"
  }'
```

### 5. 审计日志

#### 查询审计日志
```bash
# 全部日志
curl "http://localhost:8000/api/audit-logs"

# 按操作类型过滤
curl "http://localhost:8000/api/audit-logs?action=reading_uploaded"

# 按操作人员过滤
curl "http://localhost:8000/api/audit-logs?operator=管理员"
```

### 6. 报告导出

#### 导出 JSON 报告
```bash
curl -O "http://localhost:8000/api/reports/PKG-2024-001/json"
```

#### 导出 Excel 报告
```bash
curl -O "http://localhost:8000/api/reports/PKG-2024-001/excel"
```

## 错误码说明

| 错误码 | 说明 |
|--------|------|
| 40401 | 任务包编号不存在 |
| 40901 | 任务包状态不允许此操作 |

## 常见错误响应示例

### 未知包编号上传
```json
{
  "detail": "任务包编号 'UNKNOWN-001' 不存在，无法上传读数"
}
```

### 同一设备重复提交不同读数
```json
{
  "success": true,
  "message": "成功处理 0 条读数，检测到 1 个冲突需要解决",
  "package_no": "PKG-2024-001",
  "readings_processed": 0,
  "conflicts_found": 1,
  "conflicts": [...]
}
```

### 未解决冲突就关闭
```json
{
  "detail": "任务包 'PKG-2024-001' 存在未解决的冲突，无法关闭。请先解决所有冲突。"
}
```

### 状态流转错误
```json
{
  "detail": "任务包状态为 'draft'，不允许此操作。允许的状态: issued, synced"
}
```

## 数据持久化

数据存储在项目根目录的 `inspection.db` SQLite 文件中。重启服务后，所有已同步读数和冲突状态都会保留。

如需重置数据，停止服务后删除 `inspection.db` 文件，重新启动服务即可自动创建新的数据库。

## 测试验证

运行测试脚本验证完整功能：

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务（另开一个终端）
python main.py

# 运行测试脚本
python test_main_flow.py
python test_error_cases.py
python test_restart_recovery.py
```

测试脚本将自动验证：
1. 主链路：创建模板 → 生成任务包 → 发放 → 上传读数 → 解决冲突 → 同步 → 关闭 → 导出报告
2. 异常场景：未知包编号上传、重复提交不同读数、未解决冲突就关闭
3. 重启恢复：上传数据后重启服务，验证数据完整性

## 最小管理说明

### 管理员操作流程

1. **创建巡检模板**
   - 定义检查设备、检查项、标准值和公差
   - 模板可重复使用，一个模板可生成多个任务包

2. **生成并发放任务包**
   - 创建任务包时指定唯一编号（建议按规则命名，如 PKG-年月-序号）
   - 确认无误后点击发放，任务包状态变为"已发放"

3. **同步读数并解决冲突**
   - 现场人员离线采集读数后，批量上传到系统
   - 系统自动检测冲突，管理员逐条解决冲突（保留原值或新值）
   - 所有冲突解决后，标记任务包为"已同步"

4. **关闭任务包并导出报告**
   - 确认所有读数无误后，关闭任务包
   - 导出 JSON 或 Excel 格式的巡检报告归档

### 注意事项

- 任务包编号必须全局唯一
- 已发放的任务包才能上传读数
- 必须解决所有冲突才能标记为已同步或关闭
- 已关闭的任务包不可再上传读数或修改
- 所有关键操作都会记录审计日志，可追溯
