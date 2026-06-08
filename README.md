# 离线巡检任务包服务

本地可启动的后端服务，用于管理离线巡检任务包的完整生命周期。

## 功能特性

- **巡检模板管理**：创建、查询、更新、删除巡检模板及检查项
- **任务包生命周期**：草稿 → 已发放 → 已同步 → 已关闭 的完整状态流转
- **读数上传**：支持离线采集后批量上传读数
- **冲突检测与解决**：自动检测同一设备同一检查项的读数冲突，支持手动解决
- **审计日志**：完整记录所有关键操作，支持按操作人和批次查询
- **报告导出**：支持 JSON 和 Excel 格式导出巡检报告
- **数据持久化**：基于 SQLite，重启后数据不丢失
- **批量导入管理**：支持 CSV 和 JSON 批量导入模板和任务包草稿，含字段校验和重复检测
- **批量导出管理**：支持按批次、操作人、实体类型导出，包含批次信息、当前状态和读数摘要
- **发布前校验**：发布前自动检查模板存在、检查项完整、任务包号未占用
- **撤回发布控制**：仅已发放且未同步读数的任务包可撤回，已同步/已关闭状态不可撤回

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

# 按导入批次过滤
curl "http://localhost:8000/api/audit-logs?batch_no=BATCH-20240101120000"
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

### 7. 批量管理

#### JSON 批量导入模板和任务包
```bash
curl -X POST "http://localhost:8000/api/batch/import/json" \
  -H "Content-Type: application/json" \
  -d '{
    "templates": [
      {
        "name": "批量导入变压器模板",
        "description": "批量导入的变压器巡检模板",
        "check_items": [
          {"device_code": "TRANS-001", "item_name": "油温", "unit": "°C", "standard_value": "≤85", "tolerance": "±5"}
        ]
      }
    ],
    "task_packages": [
      {
        "package_no": "PKG-BATCH-001",
        "template_id": 1,
        "operator": "批量管理员"
      }
    ],
    "operator": "批量管理员"
  }'
```

#### CSV 批量导入
```bash
curl -X POST "http://localhost:8000/api/batch/import/csv?operator=批量管理员" \
  -F "file=@import_data.csv"
```

**CSV 格式示例**：
```csv
record_type,template_name,description,check_items,package_no,template_id,operator
template,变压器模板,变压器巡检模板,"[{""device_code"":""TRANS-001"",""item_name"":"油温","unit":"°C"}]",,,
task_package,,,,PKG-BATCH-001,1,批量管理员
```

#### 发布前校验
```bash
# 校验任务包是否可发布
curl "http://localhost:8000/api/batch/validate-publish/PKG-BATCH-001"
```

#### 发布任务包（含校验）
```bash
curl -X POST "http://localhost:8000/api/batch/publish/PKG-BATCH-001?operator=发布管理员"
```

#### 撤回前校验
```bash
# 校验任务包是否可撤回
curl "http://localhost:8000/api/batch/validate-revoke/PKG-BATCH-001"
```

#### 撤回任务包（含校验）
```bash
curl -X POST "http://localhost:8000/api/batch/revoke/PKG-BATCH-001?operator=撤回管理员"
```

#### 批量导出
```bash
# 按批次导出
curl "http://localhost:8000/api/batch/export?batch_no=BATCH-20240101120000"

# 按操作人导出
curl "http://localhost:8000/api/batch/export?operator=批量管理员"

# 按实体类型导出（template/task_package）
curl "http://localhost:8000/api/batch/export?entity_type=task_package"
```

#### 查询导入批次列表
```bash
curl "http://localhost:8000/api/batch/batches"
```

#### 查询批次详情
```bash
curl "http://localhost:8000/api/batch/batches/BATCH-20240101120000"
```

### 8. 发布与撤回权限说明

#### 发布前校验项
1. 任务包必须存在
2. 任务包状态必须是 `draft`（草稿）
3. 关联的模板必须存在
4. 模板必须包含至少一个检查项
5. 任务包编号不能被其他任务包占用

#### 撤回权限限制
| 任务包状态 | 读数数量 | 是否可撤回 | 说明 |
|-----------|---------|-----------|------|
| draft | 0 | ❌ 否 | 已经是草稿状态 |
| issued | 0 | ✅ 是 | 已发放但未上传读数 |
| issued | ≥1 | ❌ 否 | 已上传读数，不能撤回 |
| synced | ≥1 | ❌ 否 | 已同步完成 |
| closed | ≥0 | ❌ 否 | 已关闭归档 |

### 9. 导入结果说明

批量导入返回详细的每条记录处理结果：
```json
{
  "success": false,
  "message": "批量导入完成: 成功 2 条，失败 2 条",
  "batch_no": "BATCH-20240101120000",
  "total_records": 4,
  "success_count": 2,
  "failed_count": 2,
  "results": [
    {
      "row_index": 2,
      "success": true,
      "record_type": "template",
      "identifier": "变压器模板",
      "message": "导入成功，模板ID: 1",
      "errors": []
    },
    {
      "row_index": 4,
      "success": false,
      "record_type": "task_package",
      "identifier": "PKG-BATCH-001",
      "message": "任务包编号重复",
      "errors": ["任务包编号 'PKG-BATCH-001' 已存在或在本次导入中重复"]
    }
  ]
}
```

### 10. 批量导出说明

导出数据包含：
- **batch_no**: 原始导入批次号
- **import_batch**: 完整的导入批次信息（批次号、来源类型、操作人、创建时间等）
- **current_status**: 当前状态（draft/issued/synced/closed/active）
- **reading_summary**: 读数摘要（总读数、冲突总数、未解决冲突、已解决冲突）
- **data**: 完整的实体数据

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
python test_batch_management.py
```

测试脚本将自动验证：
1. **主链路** (`test_main_flow.py`)：创建模板 → 生成任务包 → 发放 → 上传读数 → 解决冲突 → 同步 → 关闭 → 导出报告
2. **异常场景** (`test_error_cases.py`)：未知包编号上传、重复提交不同读数、未解决冲突就关闭
3. **重启恢复** (`test_restart_recovery.py`)：上传数据后重启服务，验证数据完整性
4. **批量管理** (`test_batch_management.py`)：
   - 成功批量导入（JSON和CSV）
   - 重复数据失败不污染库
   - 发布前校验逻辑
   - 发布和撤回权限验证
   - 重启后导出仍一致
   - 审计日志按操作人和批次查询

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
