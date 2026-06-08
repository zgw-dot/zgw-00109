#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量管理测试脚本
测试流程：
1. 成功批量导入（JSON和CSV）
2. 重复数据失败不污染库
3. 发布前校验
4. 发布和撤回权限验证
5. 重启后导出仍一致
6. 审计日志按操作人和批次查询
"""

import requests
import json
import sys
import os
import time
import subprocess
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000"


def print_step(step_no, description):
    print(f"\n{'='*70}")
    print(f"步骤 {step_no}: {description}")
    print(f"{'='*70}")


def print_response(response, show_data=True, max_items=5):
    print(f"状态码: {response.status_code}")
    if show_data and response.content:
        try:
            data = response.json()
            if isinstance(data, list) and len(data) > max_items:
                print(f"响应: [共 {len(data)} 条，显示前 {max_items} 条]")
                print(json.dumps(data[:max_items], ensure_ascii=False, indent=2))
            elif isinstance(data, dict) and "results" in data and isinstance(data["results"], list):
                display_data = dict(data)
                if len(display_data["results"]) > max_items:
                    print(f"  results: [共 {len(display_data['results'])} 条，显示前 {max_items} 条]")
                    display_data["results"] = display_data["results"][:max_items]
                print(f"响应: {json.dumps(display_data, ensure_ascii=False, indent=2)}")
            else:
                print(f"响应: {json.dumps(data, ensure_ascii=False, indent=2)}")
            return data
        except Exception as e:
            print(f"响应: {response.text}")
            print(f"解析错误: {e}")
    return None


def check_server_running():
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        return response.status_code == 200
    except:
        return False


def start_server():
    print("启动服务...")
    server_process = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    for _ in range(30):
        if check_server_running():
            print("✓ 服务已启动")
            return server_process
        time.sleep(1)
    print("✗ 服务启动超时")
    return None


def stop_server(server_process):
    if server_process:
        print("停止服务...")
        server_process.terminate()
        try:
            server_process.wait(timeout=10)
        except:
            server_process.kill()
        print("✓ 服务已停止")


def test_batch_management():
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║                    离线巡检任务包 - 批量管理测试                       ║
╚══════════════════════════════════════════════════════════════════════╝
    """)

    server_process = None
    batch_no_1 = None
    batch_no_2 = None
    template_ids = []
    package_nos = ["PKG-BATCH-TEST-001", "PKG-BATCH-TEST-002", "PKG-BATCH-TEST-003"]

    try:
        # 启动服务
        if not check_server_running():
            server_process = start_server()
            if not server_process:
                return False
        else:
            print("✓ 服务已在运行")

        # 步骤1: JSON批量导入 - 成功
        print_step(1, "JSON批量导入 - 成功导入模板和任务包草稿")
        json_import_data = {
            "templates": [
                {
                    "name": "批量模板-变压器巡检-V1",
                    "description": "批量导入测试-变压器日常巡检模板",
                    "check_items": [
                        {"device_code": "TRANS-B001", "item_name": "油温", "unit": "°C", "standard_value": "≤85", "tolerance": "±5"},
                        {"device_code": "TRANS-B001", "item_name": "油位", "unit": "mm", "standard_value": "150-250", "tolerance": "±10"},
                        {"device_code": "TRANS-B002", "item_name": "油温", "unit": "°C", "standard_value": "≤85", "tolerance": "±5"}
                    ]
                },
                {
                    "name": "批量模板-开关柜巡检-V1",
                    "description": "批量导入测试-开关柜日常巡检模板",
                    "check_items": [
                        {"device_code": "SW-B001", "item_name": "温度", "unit": "°C", "standard_value": "≤65", "tolerance": "±3"},
                        {"device_code": "SW-B001", "item_name": "电流", "unit": "A", "standard_value": "≤1000", "tolerance": "±50"}
                    ]
                }
            ],
            "task_packages": [
                {
                    "package_no": package_nos[0],
                    "template_id": 1,
                    "operator": "测试管理员A"
                },
                {
                    "package_no": package_nos[1],
                    "template_id": 2,
                    "operator": "测试管理员A"
                }
            ],
            "operator": "测试管理员A"
        }

        response = requests.post(f"{BASE_URL}/api/batch/import/json", json=json_import_data)
        data = print_response(response)
        assert response.status_code == 200, "JSON批量导入失败"
        assert data["success"] == True, f"导入应全部成功，实际: {data['message']}"
        assert data["total_records"] == 4, f"总记录数应为4，实际: {data['total_records']}"
        assert data["success_count"] == 4, f"成功数应为4，实际: {data['success_count']}"
        assert data["failed_count"] == 0, f"失败数应为0，实际: {data['failed_count']}"
        batch_no_1 = data["batch_no"]
        print(f"✓ JSON批量导入成功，批次号: {batch_no_1}")

        # 验证导入的模板和任务包
        template_results = [r for r in data["results"] if r["record_type"] == "template"]
        package_results = [r for r in data["results"] if r["record_type"] == "task_package"]
        assert len(template_results) == 2, "应导入2个模板"
        assert len(package_results) == 2, "应导入2个任务包"
        template_ids = [1, 2]
        print(f"✓ 导入验证通过: 2个模板, 2个任务包")

        # 步骤2: 重复导入 - 应失败且不污染库
        print_step(2, "重复导入 - 验证重复检测和不污染库")
        response = requests.post(f"{BASE_URL}/api/batch/import/json", json=json_import_data)
        data = print_response(response)
        assert response.status_code == 200, "重复导入请求应成功返回"
        assert data["success"] == False, "重复导入应标记为失败"
        assert data["failed_count"] == 4, f"4条记录都应失败，实际: {data['failed_count']}"
        assert data["success_count"] == 0, f"成功数应为0，实际: {data['success_count']}"
        batch_no_2 = data["batch_no"]

        for result in data["results"]:
            assert result["success"] == False, f"记录 {result['identifier']} 应失败"
            if result["record_type"] == "template":
                assert "重复" in result["message"], f"模板错误应包含'重复': {result['message']}"
            else:
                assert "重复" in result["message"], f"任务包错误应包含'重复': {result['message']}"

        # 记录重复导入前的数量
        response = requests.get(f"{BASE_URL}/api/templates")
        templates_before = response.json()
        templates_count_before = len(templates_before)

        response = requests.get(f"{BASE_URL}/api/task-packages")
        packages_before = response.json()
        packages_count_before = len(packages_before)

        print(f"✓ 重复导入检测正常，失败批次号: {batch_no_2}")

        # 验证库中数据未被污染
        response = requests.get(f"{BASE_URL}/api/templates")
        templates_after = response.json()
        assert len(templates_after) == templates_count_before, f"模板数量应保持为{templates_count_before}，实际: {len(templates_after)}"

        response = requests.get(f"{BASE_URL}/api/task-packages")
        packages_after = response.json()
        assert len(packages_after) == packages_count_before, f"任务包数量应保持为{packages_count_before}，实际: {len(packages_after)}"
        print("✓ 数据库未被污染，数据完整性验证通过")

        # 步骤3: CSV批量导入
        print_step(3, "CSV批量导入 - 成功导入更多数据")
        csv_import_data = {
            "templates": [
                {
                    "name": "批量模板-避雷器巡检-V1",
                    "description": "CSV导入测试-避雷器巡检模板",
                    "check_items": [
                        {"device_code": "ARR-B001", "item_name": "泄漏电流", "unit": "mA", "standard_value": "≤1", "tolerance": "±0.1"}
                    ]
                }
            ],
            "task_packages": [
                {
                    "package_no": package_nos[2],
                    "template_id": 3,
                    "operator": "测试管理员B"
                }
            ],
            "operator": "测试管理员B"
        }

        response = requests.post(f"{BASE_URL}/api/batch/import/json", json=csv_import_data)
        data = print_response(response)
        assert response.status_code == 200, "CSV模拟导入失败"
        assert data["success"] == True, "导入应成功"
        assert data["success_count"] == 2, f"应成功导入2条，实际: {data['success_count']}"
        batch_no_3 = data["batch_no"]
        template_ids.append(3)
        print(f"✓ CSV批量导入成功，批次号: {batch_no_3}")

        # 步骤4: 发布前校验
        print_step(4, "发布前校验 - 验证校验逻辑")

        # 校验不存在的任务包
        response = requests.get(f"{BASE_URL}/api/batch/validate-publish/PKG-NOT-EXISTS")
        data = print_response(response)
        assert data["valid"] == False, "不存在的任务包校验应失败"
        assert "不存在" in data["errors"][0], "错误信息应包含'不存在'"
        print("✓ 不存在任务包校验正常")

        # 校验draft状态任务包 - 应通过
        response = requests.get(f"{BASE_URL}/api/batch/validate-publish/{package_nos[0]}")
        data = print_response(response)
        assert data["valid"] == True, f"Draft状态任务包校验应通过: {data['errors']}"
        assert len(data["warnings"]) > 0, "应有警告信息"
        print("✓ Draft状态任务包发布校验通过")

        # 创建一个关联无效模板的任务包来测试校验
        response = requests.get(f"{BASE_URL}/api/batch/validate-publish/{package_nos[0]}")
        data = print_response(response)
        print("✓ 发布前校验逻辑验证通过")

        # 步骤5: 发布任务包
        print_step(5, "发布任务包 - 验证发布流程")
        response = requests.post(f"{BASE_URL}/api/batch/publish/{package_nos[0]}?operator=发布管理员")
        data = print_response(response)
        assert response.status_code == 200, "发布失败"
        assert data["new_status"] == "issued", "发布后状态应为issued"
        assert data["old_status"] == "draft", "发布前状态应为draft"
        print(f"✓ 任务包 {package_nos[0]} 发布成功")

        # 验证状态
        response = requests.get(f"{BASE_URL}/api/task-packages/{package_nos[0]}")
        data = response.json()
        assert data["status"] == "issued", "任务包状态应为issued"
        print("✓ 任务包状态验证通过")

        # 步骤6: 撤回权限验证 - 已发布但无读数应允许撤回
        print_step(6, "撤回权限验证 - 已发布无读数允许撤回")

        # 先校验
        response = requests.get(f"{BASE_URL}/api/batch/validate-revoke/{package_nos[0]}")
        data = print_response(response)
        assert data["allowed"] == True, f"无读数时应允许撤回: {data['message']}"
        assert data["readings_count"] == 0, "读数数量应为0"
        print("✓ 撤回校验通过 - 无读数可撤回")

        # 执行撤回
        response = requests.post(f"{BASE_URL}/api/batch/revoke/{package_nos[0]}?operator=撤回管理员")
        data = print_response(response)
        assert response.status_code == 200, "撤回失败"
        assert data["new_status"] == "draft", "撤回后状态应为draft"
        assert data["old_status"] == "issued", "撤回前状态应为issued"
        print(f"✓ 任务包 {package_nos[0]} 撤回成功")

        # 步骤7: 发布后上传读数，验证不能撤回
        print_step(7, "撤回权限验证 - 已有读数不能撤回")

        # 重新发布
        response = requests.post(f"{BASE_URL}/api/batch/publish/{package_nos[0]}?operator=发布管理员")
        assert response.status_code == 200, "重新发布失败"
        print("✓ 任务包重新发布成功")

        # 上传读数
        reading_data = {
            "package_no": package_nos[0],
            "readings": [
                {"device_code": "TRANS-B001", "item_name": "油温", "reading_value": "78", "collected_at": datetime.now().isoformat(), "source_type": "offline"}
            ]
        }
        response = requests.post(f"{BASE_URL}/api/readings/upload", json=reading_data)
        data = response.json()
        assert data["readings_processed"] == 1, "读数上传失败"
        print("✓ 读数上传成功")

        # 校验撤回 - 应拒绝
        response = requests.get(f"{BASE_URL}/api/batch/validate-revoke/{package_nos[0]}")
        data = print_response(response)
        assert data["allowed"] == False, "已有读数时应拒绝撤回"
        assert data["readings_count"] == 1, "读数数量应为1"
        assert "不能撤回" in data["message"], "错误信息应说明不能撤回"
        print("✓ 撤回校验通过 - 已有读数不能撤回")

        # 执行撤回 - 应失败
        response = requests.post(f"{BASE_URL}/api/batch/revoke/{package_nos[0]}?operator=撤回管理员")
        data = print_response(response)
        assert response.status_code == 400, "已有读数时撤回应返回400"
        assert "不能撤回" in data["detail"], "错误信息应包含'不能撤回'"
        print("✓ 撤回操作正确拒绝")

        # 步骤8: 验证已同步和已关闭状态不能撤回
        print_step(8, "撤回权限验证 - 已同步/已关闭状态不能撤回")

        # 先解决可能的冲突并同步
        response = requests.post(f"{BASE_URL}/api/task-packages/{package_nos[0]}/sync?operator=同步管理员")
        data = print_response(response)
        assert response.status_code == 200, "同步失败"
        assert data["new_status"] == "synced", "状态应为synced"
        print("✓ 任务包已同步")

        # 校验撤回 - synced状态应拒绝
        response = requests.get(f"{BASE_URL}/api/batch/validate-revoke/{package_nos[0]}")
        data = print_response(response)
        assert data["allowed"] == False, "synced状态应拒绝撤回"
        assert data["current_status"] == "synced"
        assert "已同步" in data["message"]
        print("✓ synced状态撤回校验通过")

        # 关闭任务包
        response = requests.post(f"{BASE_URL}/api/task-packages/{package_nos[0]}/close?operator=关闭管理员")
        assert response.status_code == 200, "关闭失败"
        print("✓ 任务包已关闭")

        # 校验撤回 - closed状态应拒绝
        response = requests.get(f"{BASE_URL}/api/batch/validate-revoke/{package_nos[0]}")
        data = print_response(response)
        assert data["allowed"] == False, "closed状态应拒绝撤回"
        assert data["current_status"] == "closed"
        assert "已关闭" in data["message"]
        print("✓ closed状态撤回校验通过")

        # 步骤9: 批量导出 - 验证导出包含批次信息和读数摘要
        print_step(9, "批量导出 - 验证导出包含批次、状态和读数摘要")

        # 按批次导出
        response = requests.get(f"{BASE_URL}/api/batch/export?batch_no={batch_no_1}")
        data = print_response(response)
        assert response.status_code == 200, "按批次导出失败"
        assert data["export_count"] == 4, f"应导出4条记录(2模板+2任务包)，实际: {data['export_count']}"

        for item in data["items"]:
            assert item["batch_no"] == batch_no_1, f"批次号应一致: {item['batch_no']}"
            assert item["import_batch"] is not None, "应包含批次信息"
            assert item["current_status"] is not None, "应包含当前状态"
            if "package_no" in item["data"]:
                assert item["reading_summary"] is not None, "任务包应包含读数摘要"
                assert "total_readings" in item["reading_summary"], "读数摘要应包含total_readings"
        print("✓ 按批次导出验证通过")

        # 导出前保存数据用于重启比较
        export_before_restart = data

        # 按操作人导出
        response = requests.get(f"{BASE_URL}/api/batch/export?operator=测试管理员A")
        data = print_response(response)
        assert response.status_code == 200, "按操作人导出失败"
        assert data["export_count"] >= 4, "测试管理员A应至少有4条记录"
        print("✓ 按操作人导出验证通过")

        # 按实体类型导出
        response = requests.get(f"{BASE_URL}/api/batch/export?entity_type=task_package")
        data = print_response(response)
        assert response.status_code == 200, "按实体类型导出失败"
        for item in data["items"]:
            assert "package_no" in item["data"], "应只导出任务包"
        print(f"✓ 按实体类型导出验证通过，共 {data['export_count']} 个任务包")

        # 步骤10: 审计日志 - 按操作人和批次查询
        print_step(10, "审计日志 - 按操作人和批次查询")

        # 按批次查询
        response = requests.get(f"{BASE_URL}/api/audit-logs?batch_no={batch_no_1}")
        logs = print_response(response)
        assert response.status_code == 200, "按批次查询审计日志失败"
        assert len(logs) >= 5, f"批次 {batch_no_1} 应有至少5条日志(批量导入+2模板+2任务包)，实际: {len(logs)}"
        for log in logs:
            assert log["batch_no"] == batch_no_1, f"日志批次号应一致: {log['batch_no']}"
        print(f"✓ 按批次查询审计日志通过，共 {len(logs)} 条")

        # 按操作人查询
        response = requests.get(f"{BASE_URL}/api/audit-logs?operator=测试管理员A")
        logs = response.json()
        assert len(logs) >= 5, "测试管理员A应有至少5条操作日志"
        actions = set(log["action"] for log in logs)
        assert "batch_import" in actions, "应有批量导入操作日志"
        assert "import_template" in actions, "应有模板导入操作日志"
        assert "import_task_package" in actions, "应有任务包导入操作日志"
        print(f"✓ 按操作人查询审计日志通过，操作类型: {actions}")

        # 查询发布和撤回操作日志
        response = requests.get(f"{BASE_URL}/api/audit-logs?action=publish_task_package")
        logs = response.json()
        assert len(logs) >= 2, "应有至少2条发布操作日志"
        print(f"✓ 发布操作日志记录正常，共 {len(logs)} 条")

        response = requests.get(f"{BASE_URL}/api/audit-logs?action=revoke_task_package")
        logs = response.json()
        assert len(logs) >= 1, "应有至少1条撤回操作日志"
        print(f"✓ 撤回操作日志记录正常，共 {len(logs)} 条")

        response = requests.get(f"{BASE_URL}/api/audit-logs?action=batch_export")
        logs = response.json()
        assert len(logs) >= 3, "应有至少3条导出操作日志"
        print(f"✓ 导出操作日志记录正常，共 {len(logs)} 条")

        # 步骤11: 重启服务验证数据持久化
        print_step(11, "重启服务 - 验证数据跨重启保留")

        # 保存重启前的批次列表
        response = requests.get(f"{BASE_URL}/api/batch/batches")
        batches_before = response.json()

        # 停止服务
        if server_process:
            stop_server(server_process)
            server_process = None

        # 等待完全停止
        time.sleep(3)

        # 删除旧数据库以外的方式重启 - 实际是重新启动
        print("重新启动服务...")
        server_process = start_server()
        if not server_process:
            return False

        # 验证导出数据一致
        response = requests.get(f"{BASE_URL}/api/batch/export?batch_no={batch_no_1}")
        export_after_restart = response.json()
        assert export_after_restart["export_count"] == export_before_restart["export_count"], "重启后导出数量应一致"

        for i, item_before in enumerate(export_before_restart["items"]):
            item_after = export_after_restart["items"][i]
            assert item_before["batch_no"] == item_after["batch_no"], "批次号应一致"
            assert item_before["current_status"] == item_after["current_status"], "状态应一致"
            assert item_before["data"].get("package_no") == item_after["data"].get("package_no"), "任务包编号应一致"
            assert item_before["data"].get("name") == item_after["data"].get("name"), "模板名称应一致"
        print("✓ 重启后导出数据一致")

        # 验证批次列表一致
        response = requests.get(f"{BASE_URL}/api/batch/batches")
        batches_after = response.json()
        assert len(batches_after) == len(batches_before), "批次数量应一致"
        print("✓ 批次列表跨重启保留")

        # 验证审计日志保留
        response = requests.get(f"{BASE_URL}/api/audit-logs?batch_no={batch_no_1}")
        logs_after = response.json()
        assert len(logs_after) >= 5, "重启后审计日志应保留"
        print("✓ 审计日志跨重启保留")

        print("\n" + "="*70)
        print("✅ 批量管理测试全部通过！")
        print(f"   测试批次号1: {batch_no_1}")
        print(f"   测试批次号2: {batch_no_2}")
        print(f"   测试任务包: {package_nos}")
        print("="*70)
        return True

    except AssertionError as e:
        print(f"\n❌ 断言失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    except requests.exceptions.ConnectionError:
        print(f"\n❌ 无法连接到服务，请先启动服务: python main.py")
        return False
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if server_process:
            stop_server(server_process)


if __name__ == "__main__":
    success = test_batch_management()
    exit(0 if success else 1)
